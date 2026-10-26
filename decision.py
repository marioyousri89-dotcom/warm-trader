"""Decision layer: Aggregator (votes -> a score), Risk manager (hard limits), Portfolio/Executor (PAPER only).

There is deliberately NO real order code here. To go live you would add an exchange adapter
behind Portfolio.open_trade / close_trade; the risk manager stays in front of it."""
import json

from strategies import TAGS


def tag_factor(tag, label):
    if label in ("up", "down"):
        return {"trend": 1.3, "revert": 0.6}.get(tag, 1.0)
    if label == "range":
        return {"trend": 0.6, "revert": 1.3}.get(tag, 1.0)
    return 1.0


class Aggregator:
    PRIOR = 3.0   # shrinks the score when only a few agents have an opinion

    def score(self, sym, sigs, swarm, regime, agent_filter=None):
        num, den, contrib = 0.0, self.PRIOR, []
        for s in sigs:
            a = swarm.agents.get(s["agent"])
            if not a or not a["active"] or (agent_filter and not agent_filter(a)):
                continue
            w = a["weight"] * getattr(swarm, "pulse", {}).get(a["grp"], 1.0)    # minute-by-minute team pulse
            if s["kind"] in ("scout", "predict"):
                w *= swarm.vfactor(a["name"], sym) * tag_factor(TAGS.get(a["lens"], "neutral"), regime["label"])
            if w <= 0.05:
                continue
            num += w * s["confidence"] * s["direction"]
            den += w
            contrib.append((a["name"], s["direction"], round(s["confidence"], 2), round(w, 2)))
        score = num / den
        d = 1 if score > 0 else (-1 if score < 0 else 0)
        contrib.sort(key=lambda t: -t[2] * t[3])
        return {"symbol": sym, "score": score, "dir": d, "agree": sum(1 for c in contrib if c[1] == d),
                "n": len(contrib), "top": contrib[:6], "regime": regime["label"], "vol_high": regime["vol_high"]}


class Portfolio:
    """Positions are keyed by (desk, symbol): every trading desk has its own book."""

    def __init__(self, cfg, brain):
        self.cfg, self.b = cfg, brain
        self.realized = 0.0
        self.open = {}
        self.peak = cfg.start_equity
        self.last_equity = cfg.start_equity
        self.halted = False
        self.halt_reason = ""
        self.session = ""            # current market session, set by the engine every cycle
        self.sess_of = {}             # trade id -> session it was opened in
        self.hook_open = self.hook_close = None   # broker mirrors (live phase only)
        self.paused = False          # manual pause: no NEW trades (set from the app)
        self.day = 0
        self.day_start = cfg.start_equity
        self.day_blocked = False

    def equity(self, prices):
        unreal = sum(t["side"] * t["size"] * (prices[t["symbol"]] - t["entry"]) for t in self.open.values())
        return self.cfg.start_equity + self.realized + unreal

    def exposure(self, prices):
        return sum(t["size"] * prices[t["symbol"]] for t in self.open.values())

    def sym_exposure(self, sym, prices):
        return sum(t["size"] * prices[sym] for t in self.open.values() if t["symbol"] == sym)

    def heat(self):
        """Money at risk (down to the stops) across every open trade."""
        return sum(t["risk"] for t in self.open.values())

    def has(self, desk, sym):
        return (desk, sym) in self.open

    def desk_count(self, desk):
        return sum(1 for k in self.open if k[0] == desk)

    def desk_unrealized(self, desk, prices):
        return sum(t["side"] * t["size"] * (prices[t["symbol"]] - t["entry"]) for t in self.open.values() if t["desk"] == desk)

    def drawdown(self, eq):
        return max(0.0, 1 - eq / self.peak)

    def open_trade(self, desk, sym, side, size, price, stop, target, cycle, regime, sources, score, reason,
                   max_hold, risk):
        fee = size * price * self.cfg.fee
        self.realized -= fee
        entry = price * (1 + side * self.cfg.slippage)
        t = {"desk": desk, "symbol": sym, "side": side, "size": size, "entry": entry, "stop": stop, "target": target,
             "open_cycle": cycle, "fees": fee, "regime": regime, "sources": sources, "score": score, "reason": reason,
             "max_hold": max_hold, "risk": risk}
        t["id"] = self.b.x(
            "INSERT INTO trades(symbol,side,size,entry,stop,target,open_cycle,fees,status,regime,sources,score,reason,desk)"
            " VALUES(?,?,?,?,?,?,?,?,'open',?,?,?,?,?)",
            (sym, side, size, entry, stop, target, cycle, fee, regime, json.dumps(sources), score, reason, desk))
        self.open[(desk, sym)] = t
        self.sess_of[t["id"]] = self.session
        if len(self.sess_of) > 3000:
            self.sess_of.pop(next(iter(self.sess_of)))
        if self.hook_open:
            self.hook_open(t)
        return t

    def close_trade(self, t, px, cycle, why):
        exit_px = px * (1 - t["side"] * self.cfg.slippage)
        fee = t["size"] * exit_px * self.cfg.fee
        gross = t["side"] * t["size"] * (exit_px - t["entry"])
        self.realized += gross - fee
        t["fees"] += fee
        pnl = gross - t["fees"]
        self.b.x("UPDATE trades SET close_cycle=?,exit=?,pnl=?,fees=?,status='closed',reason=reason||? WHERE id=?",
                 (cycle, exit_px, pnl, t["fees"], f" | exit: {why}", t["id"]))
        self.open.pop((t["desk"], t["symbol"]), None)
        if self.hook_close:
            self.hook_close(t)
        return pnl

    def settle(self, cycle, market):
        closed = []
        for t in list(self.open.values()):
            c = market.candles[t["symbol"]][-1]
            hit_stop = (c["l"] <= t["stop"]) if t["side"] > 0 else (c["h"] >= t["stop"])
            hit_tgt = (c["h"] >= t["target"]) if t["side"] > 0 else (c["l"] <= t["target"])
            if hit_stop:      # if both touched in one candle, assume the stop came first (conservative)
                closed.append(self.close_trade(t, t["stop"], cycle, "stop"))
            elif hit_tgt:
                closed.append(self.close_trade(t, t["target"], cycle, "target"))
            elif cycle - t["open_cycle"] >= t["max_hold"]:
                closed.append(self.close_trade(t, c["c"], cycle, "time"))
        return closed

    def flatten(self, market, cycle, why):
        for t in list(self.open.values()):
            self.close_trade(t, market.last(t["symbol"]), cycle, why)


class Risk:
    """Hard limits. Nothing upstream (desks, agents, Claude, improvers, the app) can override these."""

    def __init__(self, cfg):
        self.cfg = cfg

    def approve(self, desk, sym, price, atr_val, stop_mult, conv, vol_high, corr_high, port, equity, prices, mult):
        """Returns (size, verdict, risk_amount). size 0 means rejected."""
        cfg = self.cfg
        if port.halted:
            return 0.0, "halted", 0.0
        if port.paused:
            return 0.0, "paused from the app", 0.0
        if port.day_blocked:
            return 0.0, "daily loss limit reached", 0.0
        if port.has(desk, sym):
            return 0.0, "already in position", 0.0
        if port.desk_count(desk) >= cfg.max_positions_per_desk:
            return 0.0, "desk position limit", 0.0
        if len(port.open) >= (max(1, cfg.max_positions - 1) if corr_high else cfg.max_positions):
            return 0.0, "max positions", 0.0
        stop_dist = stop_mult * atr_val
        if stop_dist <= 0:
            return 0.0, "no volatility data", 0.0
        if stop_dist / price < 4 * (cfg.fee + cfg.slippage):   # the move we'd risk is too small to beat round-trip costs
            return 0.0, "move too small to beat fees", 0.0
        risk = equity * cfg.risk_per_trade * min(1.5, max(0.5, conv / 0.5)) * mult * (0.5 if vol_high else 1.0)
        room = cfg.max_heat * equity - port.heat()
        if room < equity * 0.001:
            return 0.0, "portfolio heat limit", 0.0
        risk = min(risk, room)
        notional = min(risk / stop_dist * price,
                       cfg.max_trade_exposure * equity * mult,
                       cfg.max_symbol_exposure * equity - port.sym_exposure(sym, prices),
                       cfg.max_exposure * equity - port.exposure(prices))
        if notional < equity * 0.003:
            return 0.0, "exposure cap", 0.0
        size = notional / price
        return size, "ok", size * stop_dist
