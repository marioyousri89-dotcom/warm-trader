"""The shared brain: one SQLite database every agent reads from and writes to.

Tables
  signals    the blackboard: every finding every agent posts
  agents     the roster with each agent's live accuracy and voting weight
  trades     paper trades opened/closed by the executor
  lessons    what the Improver agents (and Claude) learned
  equity     equity curve
  trader_pos positions of the (simulated) traders the copy agents watch
  kv         small shared state
"""
import json
import os
import sqlite3
import threading

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=OFF;
CREATE TABLE IF NOT EXISTS signals(
  id INTEGER PRIMARY KEY, cycle INT, agent TEXT, grp TEXT, symbol TEXT, kind TEXT,
  direction INT, confidence REAL, payload TEXT, entry_price REAL, due INT,
  resolved INT DEFAULT 0, hit INT);
CREATE INDEX IF NOT EXISTS ix_sig_cycle ON signals(cycle);
CREATE INDEX IF NOT EXISTS ix_sig_due ON signals(due, resolved);
CREATE TABLE IF NOT EXISTS agents(
  name TEXT PRIMARY KEY, grp TEXT, lens TEXT, params TEXT, active INT,
  n INT, acc REAL, weight REAL, born INT, parent TEXT);
CREATE TABLE IF NOT EXISTS trades(
  id INTEGER PRIMARY KEY, symbol TEXT, side INT, size REAL, entry REAL, stop REAL,
  target REAL, open_cycle INT, close_cycle INT, exit REAL, pnl REAL, fees REAL,
  status TEXT, regime TEXT, sources TEXT, score REAL, reason TEXT, desk TEXT);
CREATE TABLE IF NOT EXISTS hours(hour INT PRIMARY KEY, cycle INT, pnl REAL, equity REAL, trades INT, best_desk TEXT);
CREATE TABLE IF NOT EXISTS lessons(id INTEGER PRIMARY KEY, cycle INT, author TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS equity(cycle INT PRIMARY KEY, equity REAL);
CREATE TABLE IF NOT EXISTS trader_pos(
  id INTEGER PRIMARY KEY, trader TEXT, symbol TEXT, side INT, entry REAL,
  open_cycle INT, close_cycle INT, exit REAL, pnl REAL, status TEXT);
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
"""


class Brain:
    def __init__(self, path, keep=False):
        if not keep:
            for suffix in ("", "-wal", "-shm"):
                if os.path.exists(path + suffix):
                    os.remove(path + suffix)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.db.executescript(SCHEMA)
        self._buf = []
        if keep:
            with self.lock:
                try:                      # databases from the first version have no desk column
                    self.db.execute("ALTER TABLE trades ADD COLUMN desk TEXT")
                except sqlite3.OperationalError:
                    pass
                for t in ("signals", "trades", "equity", "trader_pos", "hours"):
                    self.db.execute(f"DELETE FROM {t}")
                self.db.commit()

    # ---- raw helpers -------------------------------------------------
    def q(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def x(self, sql, args=()):
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur.lastrowid

    # ---- blackboard ---------------------------------------------------
    def post(self, cycle, agent, grp, symbol, kind, direction=0, confidence=0.0,
             payload=None, entry_price=None, due=None):
        self._buf.append((cycle, agent, grp, symbol, kind, int(direction), float(confidence),
                          json.dumps(payload or {}), entry_price, due))

    def flush(self):
        if not self._buf:
            return
        with self.lock:
            self.db.executemany(
                "INSERT INTO signals(cycle,agent,grp,symbol,kind,direction,confidence,payload,entry_price,due)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)", self._buf)
            self.db.commit()
        self._buf = []

    def signals_at(self, cycle, kinds):
        marks = ",".join("?" * len(kinds))
        rows = self.q(f"SELECT * FROM signals WHERE cycle=? AND kind IN ({marks})", (cycle, *kinds))
        for r in rows:
            r["payload"] = json.loads(r["payload"] or "{}")
        return rows

    # ---- shared small state ------------------------------------------
    def kv_get(self, k, default=None):
        r = self.q("SELECT v FROM kv WHERE k=?", (k,))
        return json.loads(r[0]["v"]) if r else default

    def kv_set(self, k, v):
        self.x("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, json.dumps(v)))

    # ---- lessons ------------------------------------------------------
    def add_lesson(self, cycle, author, text):
        self.x("INSERT INTO lessons(cycle,author,text) VALUES(?,?,?)", (cycle, author, text))

    def lessons(self, n=10):
        return self.q("SELECT * FROM lessons ORDER BY id DESC LIMIT ?", (n,))

    def prune(self, cycle, keep_cycles=2000):
        self.x("DELETE FROM signals WHERE cycle<? AND resolved=1", (cycle - keep_cycles,))
