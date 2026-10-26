"""Live dashboard: a tiny web server (standard library only).

Every page has (1) a CLUSTERS strip: the agent teams that work on that page, live, and
(2) the MARKET PIPE strip: the shared feed of 500+ public data feeds, so every page can see the market.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="theme-color" content="#0d1117">
<title>Swarm Trader</title>
<style>
:root{--bg:#0d1117;--card:#161b22;--line:#262d38;--tx:#e6edf3;--mut:#8b949e;--up:#3fb950;--dn:#f85149;--ac:#58a6ff;--warn:#d29922;--pipe:#a371f7}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
header{display:flex;flex-wrap:wrap;gap:16px;align-items:center;padding:12px 16px;border-bottom:1px solid var(--line)}
h1{font-size:17px;margin:0 8px 0 0}.kpi b{display:block;font-size:19px}.kpi span{color:var(--mut);font-size:11.5px}
nav{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line);display:flex;gap:4px;overflow-x:auto;padding:8px 12px;scrollbar-width:none}
nav a{flex:0 0 auto;color:var(--mut);text-decoration:none;font-size:12px;letter-spacing:.04em;padding:6px 10px;border-radius:16px;border:1px solid var(--line);white-space:nowrap}
nav a.on{color:var(--tx);border-color:var(--ac);background:#1f2a3a}
.chip{display:inline-block;padding:3px 9px;border-radius:20px;font-size:12px;border:1px solid var(--line);color:var(--mut);margin:2px 2px 2px 0}
.chip.on{color:var(--up);border-color:var(--up)}.chip.bad{color:var(--dn);border-color:var(--dn)}
.pipebar{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;padding:8px 16px;border-bottom:1px solid var(--line);font-size:12.5px;cursor:pointer;background:#120f1d}
.pipebar b{color:var(--pipe)}
.tape{overflow:hidden;white-space:nowrap;border-bottom:1px solid var(--line);background:rgba(0,0,0,.35);font:12px ui-monospace,Menlo,monospace;padding:5px 0;position:relative;z-index:1;cursor:pointer}
.tapein{display:inline-block;padding-left:100%;animation:tape 90s linear infinite}.tapein span{margin-right:34px}
@keyframes tape{from{transform:translateX(0)}to{transform:translateX(-100%)}}
.live{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--up);box-shadow:0 0 8px var(--up);animation:blink 1.2s infinite;margin-right:4px}@keyframes blink{50%{opacity:.25}}
.desc{padding:12px 16px 0;color:var(--mut);max-width:1100px}.desc h2{color:var(--tx);font-size:18px;margin:0 0 4px}
.clusters{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:8px;padding:10px 16px}
.cl{border:1px solid var(--line);border-left:3px solid var(--ac);border-radius:8px;padding:7px 9px;background:var(--card)}
.cl b{font-size:16px}.cl small{color:var(--mut);display:block;font-size:11.5px}.cl .t{text-transform:uppercase;font-size:11px;letter-spacing:.06em;color:var(--ac)}
main{display:grid;grid-template-columns:repeat(12,1fr);gap:12px;padding:6px 16px 40px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;overflow:auto}
.card h3{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--mut);margin:0 0 8px}
.c12{grid-column:span 12}.c8{grid-column:span 8}.c6{grid-column:span 6}.c4{grid-column:span 4}.c3{grid-column:span 3}
@media(max-width:900px){.c8,.c6,.c4,.c3{grid-column:span 12}}
table{width:100%;border-collapse:collapse;font-size:12.5px}th{color:var(--mut);font-weight:500;text-align:left;position:sticky;top:0;background:var(--card)}
td,th{padding:3px 6px;border-bottom:1px solid var(--line);white-space:nowrap}td.w{white-space:normal}
.up{color:var(--up)}.dn{color:var(--dn)}.mut{color:var(--mut)}.pp{color:var(--pipe)}
.groups{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.g{border:1px solid var(--line);border-radius:8px;padding:8px 10px}.g b{font-size:18px}.g small{color:var(--mut);display:block}
.list div{padding:4px 0;border-bottom:1px solid var(--line);font-size:12.5px}
canvas{width:100%;height:220px;display:block}
.big{font-size:22px;font-weight:600}.stat{display:flex;gap:18px;flex-wrap:wrap}.stat div span{display:block;color:var(--mut);font-size:11.5px}
button{background:#21262d;color:var(--tx);border:1px solid var(--line);border-radius:8px;padding:9px 14px;font-size:14px;margin:2px}
input{background:var(--bg);color:var(--tx);border:1px solid var(--line);border-radius:8px;padding:9px;width:70%;font-size:14px}
.eng{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px}
.eng .card{border-top:3px solid var(--ac)}.eng .n{font-size:28px;color:var(--ac);font-weight:700;float:right}
.sitemap{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;cursor:pointer;position:relative}
.tile:hover{border-color:var(--ac)}.tile h4{margin:0 0 4px;font-size:14px;letter-spacing:.04em}.tile p{margin:0 0 8px;color:var(--mut);font-size:12px}
.tile .num{position:absolute;top:10px;right:12px;color:var(--mut);font-size:11px}
.mini{display:flex;flex-wrap:wrap;gap:4px}.mini span{font-size:11px;border:1px solid var(--line);border-left:3px solid var(--ac);border-radius:6px;padding:2px 6px}
.tile .pl{margin-top:8px;font-size:11px;color:var(--pipe)}
.page{display:none}.page.on{display:contents}
.scroll{max-height:520px;overflow:auto}
@media(max-width:600px){header{padding:10px}main{padding:6px 10px 40px}.clusters{padding:10px}}

/* ===== HUD look ===== */
:root{--bg:#05060b;--card:rgba(14,17,28,.86);--line:#1e2436;--ac:#3ef0ff;--pipe:#ff3ea5;--mag:#ff3ea5;--vio:#a371f7}
body{background:radial-gradient(1200px 600px at 70% -10%,rgba(163,113,247,.12),transparent),radial-gradient(900px 500px at -10% 30%,rgba(62,240,255,.07),transparent),var(--bg);
 background-attachment:fixed}
body:before{content:"";position:fixed;inset:0;pointer-events:none;background-image:linear-gradient(rgba(255,255,255,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.025) 1px,transparent 1px);background-size:32px 32px;z-index:0}
header,nav,.pipebar,.desc,.clusters,main{position:relative;z-index:1}
h1,.card h3,nav a,.cl .t,.kpi span,.tile h4,.stat div span{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
h1{letter-spacing:.12em;text-transform:uppercase;background:linear-gradient(90deg,#fff,#ff3ea5);-webkit-background-clip:text;background-clip:text;color:transparent}
.card{box-shadow:0 0 0 1px rgba(62,240,255,.04),0 8px 30px rgba(0,0,0,.45);backdrop-filter:blur(4px)}
.card h3{color:#9aa4bf}.card h3:before{content:"■ ";color:var(--mag);font-size:9px;vertical-align:2px}
nav{background:rgba(5,6,11,.92);backdrop-filter:blur(6px)}
nav a.on{border-color:var(--mag);color:#fff;background:rgba(255,62,165,.12);box-shadow:0 0 12px rgba(255,62,165,.35)}
.pipebar{background:linear-gradient(90deg,rgba(255,62,165,.10),rgba(62,240,255,.05))}
.kpi b{font-family:ui-monospace,Menlo,monospace;text-shadow:0 0 14px rgba(62,240,255,.35)}
.big{font-family:ui-monospace,Menlo,monospace}
.clusters{display:block;padding:8px 16px}
.clwrap{position:relative;border:1px solid var(--line);border-radius:12px;background:rgba(3,4,9,.9);overflow:hidden}
.clwrap canvas{display:block;width:100%;height:240px}
.clwrap .hudl{position:absolute;left:10px;top:8px;font:11px ui-monospace,Menlo,monospace;color:#9aa4bf;letter-spacing:.06em}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.chips span{font:11.5px ui-monospace,Menlo,monospace;border:1px solid var(--line);border-left:3px solid;border-radius:6px;padding:3px 7px;background:var(--card)}
.tile{box-shadow:0 0 18px rgba(62,240,255,.05)}.tile:hover{box-shadow:0 0 18px rgba(255,62,165,.25);border-color:var(--mag)}
.heat td{width:auto;text-align:center;font:11px ui-monospace,Menlo,monospace}
.rule{display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:1px solid var(--line);font:12.5px ui-monospace,Menlo,monospace}
.rule .ok{color:var(--up)}.bar{height:4px;background:#1b2132;border-radius:3px;margin-top:3px}.bar i{display:block;height:4px;border-radius:3px;background:var(--mag)}
.sess{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px}
.sess div{border:1px solid var(--line);border-radius:8px;padding:8px;font:12px ui-monospace,Menlo,monospace}.sess .open{border-color:var(--up);box-shadow:0 0 10px rgba(63,185,80,.25)}
</style></head><body>
<header><h1>Swarm Trader</h1>
<div class="kpi"><b id="eq">-</b><span>equity (paper)</span></div>
<div class="kpi"><b id="pnl">-</b><span>profit / loss</span></div>
<div class="kpi"><b id="ddk">-</b><span>drawdown</span></div>
<div class="kpi"><b id="tr">-</b><span>closed trades / win</span></div>
<div class="kpi"><b id="cy">-</b><span id="mode">cycle</span></div>
<span id="llm" class="chip">Claude</span><span id="risk" class="chip">risk</span><span class="chip">PAPER ONLY</span><a id="hbadge" class="chip" href="#council" style="display:none;border-color:var(--mag);color:var(--mag);text-decoration:none"></a></header>
<nav id="nav"></nav>
<div class="pipebar" id="pipebar" onclick="go('pipe')"><b>MARKET PIPE</b><span class="mut">starting...</span></div>
<div class="tape" onclick="go('news')"><div class="tapein" id="tape"></div></div>
<div class="desc" id="desc"></div>
<div class="clusters" id="clusters"></div>
<main>

<!-- SITE MAP -->
<section class="page" data-p="map">
<div class="card c12" style="border-color:var(--pipe)"><h3 class=pp>Market pipe (feeds every page)</h3><div id="mappipe" class="stat"></div></div>
<div class="c12 sitemap" id="sitemap"></div>
</section>

<!-- HOME -->
<section class="page" data-p="home">
<div class="card c8"><h3>Equity curve (paper money)</h3><canvas id="ch" width="900" height="220"></canvas></div>
<div class="card c4"><h3>Chief strategist this cycle</h3><div id="note" class="mut" style="margin-bottom:6px"></div><div id="dec"></div>
<h3 style="margin-top:10px">Regimes</h3><div id="reg"></div><h3 style="margin-top:10px">Market data</h3><div id="mnote" class="mut"></div></div>
<div class="card c12"><h3>Every team, one brain</h3><div class="groups" id="groups"></div></div>
<div class="card c6"><h3>Open positions</h3><table id="open"></table></div>
<div class="card c6"><h3>Profit each hour</h3><table id="hours"></table></div>
</section>

<!-- TRADES -->
<section class="page" data-p="trades">
<div class="card c12"><h3>Open positions</h3><table id="open2"></table></div>
<div class="card c12"><h3>Closed trades (most recent first)</h3><table id="closed"></table></div>
</section>

<!-- DESKS -->
<section class="page" data-p="desks">
<div class="card c8"><h3>Trading desks ranked by profit per hour (24h)</h3><table id="desks"></table></div>
<div class="card c4"><h3>Profit each hour</h3><table id="hours2"></table></div>
<div class="card c12"><h3>Desk log</h3><div class="list" id="dlog"></div></div>
</section>

<!-- DECISION DESK -->
<section class="page" data-p="decision">
<div class="card c8"><h3>Decision ring · desks around · one gate decides</h3><div id="ring"></div></div>
<div class="card c4"><h3>6 risk rules every trade must pass</h3><div id="rules"></div></div>
<div class="card c12"><h3>Desks propose, the risk manager approves or rejects</h3><div class="stat" id="ddstat"></div>
<div class="mut" id="ddr" style="margin:8px 0"></div><div class="list" id="ddl"></div></div>
</section>

<!-- COUNCIL -->
<section class="page" data-p="council">
<div class="card c12"><h3>Five seats · one gate · you make the final call</h3><div class="eng" id="seats"></div>
<div class="stat" id="cstat" style="margin-top:10px"></div>
<div style="margin-top:10px"><button onclick="ctl('review_on')">Human review ON</button><button onclick="ctl('review_off')">Human review OFF (auto, paper)</button> <span id="crev" class=mut></span></div></div>
<div class="card c12" style="border-color:var(--mag)"><h3>Waiting for you (hand-offs)</h3><div id="cq" class="list"></div></div>
<div class="card c12"><h3>Council log · every proposal, every seat's score</h3><div class="scroll"><table id="clog"></table></div></div>
</section>

<!-- MATRIX -->
<section class="page" data-p="matrix">
<div class="card c12"><h3>Matrix: one row per traded market, every input side by side</h3><table id="matrix"></table>
<p class="mut" style="margin:8px 0 0">Chart price = what the robot trades on. Pipe price = median of every exchange in the pipe. Votes = signals posted in the last 30 entries of the brain.</p></div>
<div class="card c12"><h3>Signal heatmap · market × team (green = buy pressure, red = sell)</h3><table class="heat" id="heat"></table></div>
<div class="card c12"><h3>Fast lane · reacts within ~1 s of new news or prices (live stops/targets + News Desk)</h3><div class="list" id="fastlog"></div></div>
<div class="card c12"><h3>Pipe agents: their latest votes</h3><div class="list" id="pipevotes"></div></div>
</section>

<!-- BRAIN -->
<section class="page" data-p="brain">
<div class="card c12"><h3>All teams</h3><div class="groups" id="groups2"></div></div>
<div class="card c6"><h3>Most trusted agents (voting weight)</h3><table id="top"></table></div>
<div class="card c6"><h3>Least trusted agents</h3><table id="bot"></table></div>
<div class="card c6"><h3>Shared brain: live signal feed</h3><div class="list scroll" id="feed"></div></div>
<div class="card c6"><h3>Lessons learned</h3><div class="list scroll" id="less"></div></div>
<div class="card c12"><h3>Settings the improvers tuned (within hard limits)</h3><div id="set" class="mut"></div></div>
</section>

<!-- FLOW & RESEARCH -->
<section class="page" data-p="flow">
<div class="card c6"><h3>Buy / sell vote flow per market (recent signals)</h3><table id="flowt"></table></div>
<div class="card c6"><h3>Pipe research per market</h3><table id="research"></table></div>
<div class="card c12"><h3>Latest signals</h3><div class="list scroll" id="feed2"></div></div>
</section>

<!-- MARKET PIPE -->
<section class="page" data-p="pipe">
<div class="card c12"><div class="stat" id="pstat"></div></div>
<div class="card c6"><h3>Live feeds by category</h3><table id="pcat"></table></div>
<div class="card c6"><h3>Providers (each splits into many feeds)</h3><div class="scroll"><table id="pprov"></table></div></div>
<div class="card c12"><h3>Every feed <input id="pfind" placeholder="filter, e.g. BTC or news or kraken" style="width:220px;padding:5px;font-size:12px;margin-left:8px" oninput="renderPipe()"></h3>
<div class="scroll"><table id="pfeeds"></table></div></div>
</section>

<!-- STOCKS & CRYPTO -->
<section class="page" data-p="crypto">
<div class="card c12"><h3>Crypto: consensus across every exchange in the pipe</h3><div class="scroll"><table id="coins"></table></div></div>
<div class="card c12"><h3>Stocks and crypto ETFs</h3><table id="stocks"></table></div>
<div class="card c12"><h3>New tokens &amp; trending pools (DexScreener, GeckoTerminal) · watch only, never traded</h3><div class="scroll"><table id="newtok"></table></div></div>
<div class="card c12"><h3>Regional prices · same coin on exchanges around the world (converted to USD)</h3><div class="scroll"><table id="regional"></table></div></div>
</section>

<!-- WORLD MARKETS -->
<section class="page" data-p="world">
<div class="card c12"><h3>Timezone view · which markets are open right now, and how they moved</h3><div class="sess" id="sess"></div><div class="mut" id="tzread" style="margin-top:8px"></div></div>
<div class="card c12"><div class="stat" id="wstat"></div></div>
<div class="card c6"><h3>Stock indices</h3><table id="widx"></table></div>
<div class="card c6"><h3>Commodities, rates, dollar</h3><table id="wcom"></table></div>
<div class="card c12"><h3>Currencies (per 1 US dollar)</h3><div class="scroll"><table id="wfx"></table></div></div>
<div class="card c12"><h3>On-chain, DeFi and sentiment</h3><table id="wother"></table></div>
</section>

<!-- NEWS -->
<section class="page" data-p="news">
<div class="card c12"><div class="stat" id="nstat"></div></div>
<div class="card c12"><h3>Headlines from every news feed (green = upbeat words, red = downbeat words)</h3><div class="list scroll" id="heads"></div></div>
<div class="card c12"><h3>Macro team: world events (prices moved by headlines and prediction markets)</h3><div id="macro" class="mut"></div></div>
</section>

<!-- POLYMARKET -->
<section class="page" data-p="poly">
<div class="card c6"><h3>Polymarket prediction desk (paper money)</h3><div id="poly" class="mut"></div><table id="polyt"></table></div>
<div class="card c6"><h3>What prediction markets say right now (pipe)</h3><div class="scroll"><table id="preds"></table></div></div>
</section>

<!-- 8 ENGINES -->
<section class="page" data-p="engines">
<div class="card c12"><div class="eng" id="eng"></div></div>
<div class="card c12"><h3>Guardrails · always on</h3><div id="guard"></div></div>
<div class="card c12"><h3>How this compares with open-source trading agents</h3><div class="list" id="oss"></div></div>
</section>

<!-- ACADEMY -->
<section class="page" data-p="academy">
<div class="card c12"><h3>Graduation report</h3><div id="grad" class="mut"></div></div>
<div class="card c12"><h3>Exam by team</h3><table id="gradg"></table></div>
<div class="card c12" style="border-color:var(--mag)"><h3>Self-development · a report every live hour</h3><div class="stat" id="sdstat"></div><div class="scroll"><table id="sdlog"></table></div></div>
<div class="card c6"><h3>News publishers it has learned to TRUST</h3><table id="pubtop"></table></div>
<div class="card c6"><h3>News publishers it has learned to DOUBT</h3><table id="pubbot"></table></div>
</section>

<!-- ACCOUNTS -->
<section class="page" data-p="accounts">
<div class="card c6"><h3>Broker mirrors (demo accounts only)</h3><table id="brk"></table></div>
<div class="card c6"><h3>Copy-trading targets (skill vs luck)</h3><table id="trd"></table></div>
<div class="card c12"><h3>Polymarket bankroll</h3><div id="polyacc" class="mut"></div></div>
</section>

<!-- MANAGER -->
<section class="page" data-p="manager">
<div class="card c12"><h3>General Manager: talk to the AI running the operation</h3>
<div style="margin-bottom:8px"><button id="mic" onclick="listen()" style="font-size:18px">🎤 Speak</button> <button onclick="brief()">Daily briefing</button>
<label class="mut"><input type="checkbox" id="spk" checked style="width:auto"> read replies aloud</label> <span id="micmsg" class="mut"></span></div>
<div id="chat" class="mut" style="max-height:300px;overflow:auto"></div>
<input id="q" placeholder="e.g. why did we lose on ETH today?" onkeydown="if(event.key=='Enter')ask()"><button onclick="ask()">Ask</button></div>
<div class="card c12"><h3>Owner controls</h3>
<button onclick="ctl('pause')">Pause trading</button> <button onclick="ctl('resume')">Resume</button>
<button onclick="if(confirm('Close ALL positions and pause?'))ctl('flatten')">Flatten all</button>
<button onclick="if(confirm('Clear the kill switch?'))ctl('reset_halt')">Clear kill switch</button>
<div id="ctlmsg" class="mut" style="margin-top:6px"></div></div>
<div class="card c12"><h3>Organisation</h3><table id="org"></table></div>
<div class="card c12"><h3>Development team: post-mortem and proposals (need your approval)</h3><div id="dev" class="list"></div></div>
</section>

<!-- HELP -->
<section class="page" data-p="help">
<div class="card c12 list" id="help"></div>
</section>
</main>
<script>
const $=id=>document.getElementById(id),f=(n,d=2)=>n==null||isNaN(n)?'-':Number(n).toFixed(d);
const esc=t=>String(t==null?'':t).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
const cls=v=>v>0?'up':v<0?'dn':'mut',side=s=>s>0?'<span class=up>LONG</span>':s<0?'<span class=dn>SHORT</span>':'<span class=mut>-</span>';
const pct=(v,d=2)=>v==null?'-':'<span class='+cls(v)+'>'+(v>0?'+':'')+f(v*100,d)+'%</span>';
const big=n=>n==null?'-':Math.abs(n)>=1e12?f(n/1e12,2)+'T':Math.abs(n)>=1e9?f(n/1e9,2)+'B':Math.abs(n)>=1e6?f(n/1e6,2)+'M':Math.abs(n)>=1e4?f(n/1e3,1)+'k':f(n,n<1?4:2);
const px=n=>n==null?'-':n>=1000?Number(n).toLocaleString(undefined,{maximumFractionDigits:0}):n>=1?f(n,2):f(n,6);
function tbl(el,head,rows){const e=$(el);if(!e)return;e.innerHTML='<tr>'+head.map(h=>'<th>'+h+'</th>').join('')+'</tr>'+(rows.length?rows.map(r=>'<tr>'+r.map(c=>'<td>'+c+'</td>').join('')+'</tr>').join(''):'<tr><td class=mut colspan='+head.length+'>nothing yet</td></tr>')}
const Q=location.search;
const PAGES=[
['map','SITE MAP','Every page of the app, the agent clusters working on each one, and the market pipe that feeds them all. Tap a tile to open it.',['scout','analyst','quant','copy','predictor','macro','platform','pipe','desk','improver']],
['home','HOME','Your paper account at a glance: money, the equity curve, what the chief strategist decided, and the teams.',['scout','analyst','quant','predictor','macro','pipe','desk','improver']],
['trades','TRADES','Every open position and every closed paper trade, with the desk that took it and why.',['desk']],
['desks','DESKS','Ten trading desks, each with its own style and slice of capital, ranked by profit per hour. Losing desks cool off.',['desk','improver']],
['decision','DECISION DESK','Desks propose trades; the risk manager is the single approval layer. Shows what was approved, rejected, and why.',['desk','quant','improver']],
['council','COUNCIL','Every trade idea goes to five seats: SOURCES (do exchanges and stories confirm it?), SENTIMENT (news, crowd, funding), CHARTS (regime), THESIS (case for vs strongest case against) and RISK (six hard rules, veto). One confidence number goes to the GATE, calibrated in the academy on this system’s own ideas: the strongest ~20% go ahead (paper), the next band comes to YOU (max 3 waiting), the rest is dropped. Unanswered hand-offs expire after two candles (2 hours live); nothing is chased.',['pipe','analyst','scout','predictor','quant','desk']],
['matrix','MATRIX','One row per traded market: chart price, pipe price, regime, team votes and the final decision, side by side.',['analyst','quant','scout','predictor','pipe']],
['brain','BRAIN','The shared brain: every team posts here. Trust (voting weight) is earned by hit rate, not given.',['scout','analyst','quant','copy','predictor','macro','platform','pipe','desk','improver']],
['flow','FLOW & RESEARCH','Buy and sell vote flow from the research teams, plus what the market pipe says about each market.',['scout','predictor','pipe','platform']],
['pipe','MARKET PIPE','The shared intake every page reads: ~270 platforms (~55 exchanges worldwide, perpetual futures, ~190 news, central-bank, regulator and Reddit feeds incl. Google News searches that name hundreds of publishers), plus public exchanges, perpetual futures, news, world markets, currencies, prediction markets, on-chain and DeFi. Each provider splits into many feeds. "Live" counts only feeds that answered in the last 15 minutes.',['pipe','macro']],
['crypto','STOCKS & CRYPTO','60 coins priced by every exchange in the pipe (median), with how far exchanges disagree, funding and USD premium; plus key stocks and crypto ETFs.',['pipe','scout','quant']],
['world','WORLD MARKETS','About 55 world indices, commodities, rates and stocks, 40 currencies, and on-chain/DeFi gauges. Used as a risk-on / risk-off vote.',['macro','pipe']],
['news','NEWS','Headlines from ~35 news and central-bank feeds, scored by simple upbeat/downbeat word counts. Headlines are data, never instructions.',['macro','pipe']],
['poly','POLYMARKET','Paper bets on prediction markets, plus live odds from Polymarket, Kalshi and Manifold. Paper only (Polymarket is blocked in Australia).',['macro']],
['engines','8 ENGINES','The whole machine as eight steps: scan, analyse, research, flow, decide, risk, execute, learn, each with its live numbers.',['scout','analyst','quant','predictor','pipe','desk','improver']],
['academy','ACADEMY & SELF-DEV','Before trading, agents train on real history and sit an exam on data nobody trained on. Then, every live hour, the system teaches itself: improvers re-weight, retire and clone agents; the council gate re-calibrates; and every headline is checked an hour later against the price, so each news publisher earns (or loses) trust. Reports below.',['improver','quant']],
['accounts','ACCOUNTS','Demo broker mirrors (off unless you switch them on) and the copy-trading targets, scored for skill versus luck.',['copy','desk']],
['manager','MANAGER','Talk to the General Manager by voice or text, get the daily briefing, and use the owner controls.',['improver']],
['help','HELP','What everything means.',[]]];
let S=null,P=null,cur='map',lastPipe=0;
$('nav').innerHTML=PAGES.map(p=>'<a href="#'+p[0]+'" id="n_'+p[0]+'">'+p[1]+'</a>').join('');
function go(p){location.hash=p}
function route(){cur=(location.hash||'#map').slice(1);if(!PAGES.find(p=>p[0]==cur))cur='map';
document.querySelectorAll('.page').forEach(s=>s.classList.toggle('on',s.dataset.p==cur));
document.querySelectorAll('nav a').forEach(a=>a.classList.toggle('on',a.id=='n_'+cur));
const pg=PAGES.find(p=>p[0]==cur);$('desc').innerHTML='<h2>'+pg[1]+'</h2>'+pg[2];
$('n_'+cur).scrollIntoView({inline:'center',block:'nearest'});render();if(needPipe())loadPipe()}
window.addEventListener('hashchange',route);
const needPipe=()=>['pipe','crypto','world','news','poly','matrix','flow','engines'].includes(cur);

const GC={scout:'#3ef0ff',analyst:'#58a6ff',quant:'#a371f7',copy:'#ffb86b',predictor:'#3fb950',macro:'#ff7b72',platform:'#d2a8ff',pipe:'#ff3ea5',desk:'#f2cc60',improver:'#c9d1d9'};
const PRE={S:'scout',A:'analyst',Q:'quant',C:'copy',P:'predictor',M:'macro',X:'platform',Y:'pipe',T:'desk',I:'improver'};
const DPR=Math.min(2,window.devicePixelRatio||1);
function rnd(seed){let s=(seed%2147483646)+1;return()=>(s=s*16807%2147483647)/2147483647}
let CL=null,clPage='',clBuilt=0;
function clusters(){const pg=PAGES.find(p=>p[0]==cur);if(!S||!pg[3].length){$('clusters').innerHTML='';CL=null;clPage=cur;return}
 if(clPage!=cur){clPage=cur;$('clusters').innerHTML='<div class=clwrap><canvas id=clc style="height:'+(cur=='map'?380:230)+'px"></canvas><div class=hudl>CLUSTERS ON THIS PAGE · '+pg[3].length+' teams · lines = shared signals &amp; data flow</div></div><div class=chips id=clchips></div>';clBuilt=0}
 const c=$('clc');if(Date.now()-clBuilt>8000||!CL){c.width=c.clientWidth*DPR;c.height=c.clientHeight*DPR;CL=buildCL(pg[3],c.width,c.height);clBuilt=Date.now()}
 const ch=S.charters||{};$('clchips').innerHTML=pg[3].map(g=>{const x=(S.groups||[]).find(r=>r.group==g)||{};return '<span style="border-left-color:'+GC[g]+'" title="'+esc((ch[g]||{}).role)+'">'+g+' <b>'+(x.active||0)+'</b>/'+(x.total||0)+' · hit '+(x.avg_acc==null?'-':f(x.avg_acc*100,0)+'%')+' · wt '+f(x.avg_weight)+'</span>'}).join('')}
function buildCL(gs,W,H){const n=gs.length,cx=W/2,cy=H/2,rx=W*.34,ry=H*.30;
 const cl=gs.map((g,i)=>{const a=-Math.PI/2+i/n*6.283,x=n==1?cx:cx+rx*Math.cos(a),y=n==1?cy:cy+ry*Math.sin(a),G=(S.groups.find(r=>r.group==g)||{}),r=rnd(g.charCodeAt(0)*7919+g.length*104729);
  const k=Math.max(10,Math.min(90,(G.active||0)*2+10)),rad=Math.min(W/(n>4?5:3),H/3)*(.45+.35*Math.min(1,(G.active||0)/40)),pts=[];
  for(let j=0;j<k;j++){const t=r()*6.283,d=Math.sqrt(-2*Math.log(r()+1e-9))*rad*.38;pts.push([x+Math.cos(t)*d,y+Math.sin(t)*d*.75])}return{g,x,y,pts,G,c:GC[g]||'#888'}});
 const cnt={},by={};(S.feed||[]).forEach(e=>{const g=PRE[e.agent[0]];if(g)(by[e.symbol]=by[e.symbol]||new Set()).add(g)});
 Object.values(by).forEach(st=>{const a=[...st];for(let i=0;i<a.length;i++)for(let j=i+1;j<a.length;j++){const k=[a[i],a[j]].sort().join('|');cnt[k]=(cnt[k]||0)+2}});
 [['pipe','macro'],['analyst','quant'],['scout','desk'],['predictor','desk'],['quant','desk'],['macro','desk'],['pipe','desk'],['copy','desk'],['improver','desk'],['platform','desk'],['improver','quant'],['analyst','desk']].forEach(([a,b])=>{const k=[a,b].sort().join('|');cnt[k]=(cnt[k]||0)+2});
 const links=[];Object.entries(cnt).forEach(([k,v])=>{const[a,b]=k.split('|'),A=cl.find(c=>c.g==a),B=cl.find(c=>c.g==b);if(A&&B)links.push({A,B,w:Math.min(16,v)})});
 return{cl,links,W,H,t0:performance.now()}}
function drawCL(){requestAnimationFrame(drawCL);const c=$('clc');if(!c||!CL||document.hidden)return;const x=c.getContext('2d'),W=CL.W,H=CL.H,t=(performance.now()-CL.t0)/1000;
 if(c.width!=W){clBuilt=0;return}x.clearRect(0,0,W,H);
 x.strokeStyle='rgba(120,140,220,.14)';x.setLineDash([4*DPR,9*DPR]);x.beginPath();x.ellipse(W/2,H/2,W*.45,H*.44,0,0,6.283);x.stroke();x.setLineDash([]);
 CL.links.forEach((l,li)=>{const r=rnd(li*97+13);x.lineWidth=.6*DPR;for(let i=0;i<l.w*3;i++){const p=l.A.pts[Math.floor(r()*l.A.pts.length)],q=l.B.pts[Math.floor(r()*l.B.pts.length)];x.strokeStyle='rgba(225,230,255,'+(.04+.07*r())+')';x.beginPath();x.moveTo(p[0],p[1]);x.lineTo(q[0],q[1]);x.stroke()}
  const ph=(t*.3+li*.173)%1;x.fillStyle=l.A.c;x.shadowColor=l.A.c;x.shadowBlur=8*DPR;x.beginPath();x.arc(l.A.x+(l.B.x-l.A.x)*ph,l.A.y+(l.B.y-l.A.y)*ph,2.2*DPR,0,6.283);x.fill();x.shadowBlur=0});
 CL.cl.forEach(k=>{x.strokeStyle=k.c+'40';x.lineWidth=.5*DPR;for(let i=2;i<k.pts.length;i+=2){x.beginPath();x.moveTo(k.pts[i][0],k.pts[i][1]);x.lineTo(k.pts[i-2][0],k.pts[i-2][1]);x.stroke()}
  k.pts.forEach((p,i)=>{const j=Math.sin(t*1.3+i)*1.1*DPR;x.globalAlpha=.45+.55*Math.abs(Math.sin(t*.8+i));x.fillStyle=i%6?k.c:'#fff';x.fillRect(p[0]+j,p[1]-j,1.7*DPR,1.7*DPR)});x.globalAlpha=1;
  x.font='600 '+(11*DPR)+'px ui-monospace,Menlo,monospace';x.fillStyle='#fff';x.fillText(k.g.toUpperCase(),k.x+12*DPR,k.y-6*DPR);
  x.font=(10*DPR)+'px ui-monospace,Menlo,monospace';x.fillStyle='#9aa4bf';x.fillText((k.G.active||0)+' agents · '+(k.G.avg_acc==null?'learning':'hit '+(k.G.avg_acc*100).toFixed(0)+'%'),k.x+12*DPR,k.y+8*DPR)})}
requestAnimationFrame(drawCL);window.addEventListener('resize',()=>{clBuilt=0});
function pipebar(){const p=S&&S.pipe;if(!p){const ago=p.last_fetch?Math.max(0,Math.round(Date.now()/1000-p.last_fetch)):null,fa=S.fast||{},fago=fa.last?Math.round(Date.now()/1000-fa.last):null;
const tp=(p.latest||[]).map(h=>'<span><span class=mut>'+new Date(h.t*1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})+' '+esc(h.src)+':</span> <span class='+cls(h.s)+'>'+esc(h.title)+'</span></span>').join('')+(p.top||[]).map(c=>'<span>'+c.coin+' $'+px(c.price)+' '+pct(c.chg24,1)+'</span>').join('');
if(tp&&$('tape').dataset.k!==String((p.latest||[{}])[0].t)){$('tape').innerHTML=tp;$('tape').dataset.k=String((p.latest||[{}])[0].t)}
$('pipebar').innerHTML='<span class=live></span><b>MARKET PIPE</b><span class=mut>updated '+(ago==null?'-':ago+'s ago')+' · fast lane '+(fago==null?'waiting':fago+'s ago'+(fa.ms!=null?' ('+fa.ms+' ms to decide)':''))+(fa.closed||fa.opened?' · '+fa.opened+' fast entries, '+fa.closed+' fast exits':'')+'</span><span class=mut>off</span>';return}
const t=p.top.slice(0,4).map(c=>'<span>'+c.coin+' <b style="color:var(--tx)">$'+px(c.price)+'</b> <span class=mut>('+c.sources+' src)</span> '+pct(c.chg24,1)+'</span>').join('');
$('pipebar').innerHTML='<b>MARKET PIPE</b><span><b>'+(p.sources||0)+'</b> sources answering</span><span><b>'+p.live+'</b> live feeds</span><span>'+p.providers_ok+'/'+p.providers+' platforms OK · '+(p.publishers||0)+' news publishers</span><span><b>'+(p.news_per_hour||0)+'</b> stories/hour</span>'+t+
(p.fng?'<span>Fear&amp;Greed <b style="color:var(--tx)">'+f(p.fng.value,0)+'</b></span>':'')+'<span>news mood <span class='+cls(p.news.mood)+'>'+f(p.news.mood,2)+'</span> <span class=mut>('+p.news.n+')</span></span>'+
'<span>world '+pct(p.world.risk)+'</span>'+(p.warming_up?'<span class=mut>warming up...</span>':'')}

async function tick(){try{S=await (await fetch('/api/state'+Q)).json();head();render()}catch(e){}}
async function loadPipe(){try{const j=await (await fetch('/api/pipe'+Q)).json();if(!j.providers)return;P=j;lastPipe=Date.now();render()}catch(e){}}
function head(){const s=S;$('eq').textContent='$'+f(s.equity);$('pnl').innerHTML='<span class='+cls(s.pnl)+'>'+(s.pnl>=0?'+':'')+f(s.pnl)+'</span>';
$('ddk').textContent=f(s.drawdown*100,1)+'%';$('tr').textContent=s.totals.trades+' / '+(s.totals.win_rate==null?'-':f(s.totals.win_rate*100,0)+'%');
$('cy').textContent=s.cycle;$('mode').textContent=s.phase+' · '+s.mode;
const l=$('llm');l.textContent=s.llm.on?'Claude ON · '+s.llm.calls+' calls':'Claude OFF (no API key)';l.className='chip '+(s.llm.on?'on':'');
const hq=(s.council&&s.council.queue.length)||0,hb=$('hbadge');hb.style.display=hq?'inline-block':'none';hb.textContent=hq+' waiting for your YES';
const r=$('risk');r.textContent=s.halted?'KILL SWITCH: '+s.halt_reason:s.day_blocked?'daily limit reached':s.paused?'PAUSED':'risk manager OK';r.className='chip '+(s.halted||s.day_blocked?'bad':'on')}

function render(){if(!S)return;clusters();pipebar();const s=S;try{({council,map:sitemap,home,trades,desks,decision,matrix,brain,flow,pipe:renderPipe,crypto,world,news,poly,engines,academy,accounts,manager,help}[cur]||(()=>{}))()}catch(e){console.log(e)}}

function chart(pts,start){const c=$('ch'),x=c.getContext('2d');c.width=c.clientWidth*2;c.height=440;x.clearRect(0,0,c.width,c.height);if(pts.length<2)return;
const ys=pts.map(p=>p[1]).concat([start]),lo=Math.min(...ys),hi=Math.max(...ys),pad=(hi-lo)*.1||1,W=c.width,H=c.height;
const X=i=>i/(pts.length-1)*(W-20)+10,Y=v=>H-20-(v-lo+pad)/(hi-lo+2*pad)*(H-40);
x.strokeStyle='#262d38';x.lineWidth=1;x.setLineDash([8,8]);x.beginPath();x.moveTo(0,Y(start));x.lineTo(W,Y(start));x.stroke();x.setLineDash([]);
x.strokeStyle=pts[pts.length-1][1]>=start?'#3fb950':'#f85149';x.lineWidth=3;x.beginPath();pts.forEach((p,i)=>i?x.lineTo(X(i),Y(p[1])):x.moveTo(X(i),Y(p[1])));x.stroke();
x.fillStyle='#8b949e';x.font='22px sans-serif';x.fillText(f(hi),12,24);x.fillText(f(lo),12,H-4)}
const groupsHTML=s=>s.groups.map(g=>'<div class=g><small>'+g.group+'</small><b>'+g.active+'</b><span class=mut> / '+g.total+'</span><small>hit '+(g.avg_acc==null?'-':f(g.avg_acc*100,1)+'%')+' · wt '+f(g.avg_weight)+'</small></div>').join('');
const openRows=s=>s.open_trades.map(t=>[esc(t.desk),t.symbol,side(t.side),px(t.entry),px(t.stop),px(t.target),'<span class=mut>'+esc(t.reason).slice(0,60)+'</span>']);
const hourRows=s=>(s.hours||[]).slice().reverse().map(h=>[h.hour,'<span class='+cls(h.pnl)+'>'+f(h.pnl)+'</span>',esc(h.best_desk||'')]);

const PIPEUSE={home:'pipe bar + market note',trades:'pipe bar',desks:'pipe bar',decision:'pipe bar',matrix:'pipe price, sources, 24h per market',brain:'pipe agents in the brain',flow:'funding, premium, exchange spread',pipe:'every provider and feed',crypto:'60-coin consensus, stocks',world:'indices, FX, commodities, on-chain',news:'all news feeds + mood',poly:'Polymarket, Kalshi, Manifold odds',engines:'SCAN engine = pipe',academy:'pipe bar',accounts:'pipe bar',manager:'manager reads the pipe summary',help:'explains the pipe'};
function sitemap(){const s=S,p=s.pipe||{},G=g=>(s.groups.find(x=>x.group==g)||{});
$('mappipe').innerHTML=p.live==null?'<span class=mut>pipe off</span>':'<div><b class="big pp">'+p.live+'</b><span>live feeds</span></div><div><b class=big>'+p.providers_ok+'/'+p.providers+'</b><span>providers OK</span></div>'+Object.entries(p.by_cat||{}).map(([k,v])=>'<div><b class=big>'+v+'</b><span>'+k+'</span></div>').join('');
$('sitemap').innerHTML=PAGES.filter(x=>x[0]!='map').map((x,i)=>'<div class=tile onclick="go(\''+x[0]+'\')"><span class=num>'+(i+1)+'</span><h4>'+x[1]+'</h4><p>'+esc(x[2]).slice(0,110)+(x[2].length>110?'…':'')+'</p><div class=mini>'+
(x[3].length?x[3].map(g=>'<span>'+g+' <b>'+(G(g).active||0)+'</b></span>').join(''):'<span class=mut>no agents</span>')+'</div><div class=pl>◆ pipe: '+esc(PIPEUSE[x[0]]||'pipe bar')+'</div></div>').join('')}
function home(){const s=S;chart(s.equity_curve,s.start);
$('note').textContent=s.note||(s.llm.on?'(waiting for a strong enough signal)':'Claude is off: decisions are pure quant votes.');
$('dec').innerHTML=s.decisions.map(d=>'<div><b>'+d.symbol+'</b> quant '+f(d.quant,2)+' → '+f(d.final,2)+(d.claude?' · Claude '+esc(d.claude):'')+' · <span class=mut>'+esc(d.result)+'</span></div>').join('');
$('reg').innerHTML=Object.entries(s.regimes).map(([k,v])=>'<span class=chip>'+k+': '+v.label+(v.vol_high?' · volatile':'')+'</span>').join('');
$('mnote').textContent=s.market_note+' · '+s.agents_active+' of '+s.agents_total+' agents active';
$('groups').innerHTML=groupsHTML(s);tbl('open',['desk','sym','side','entry','stop','target','why'],openRows(s));tbl('hours',['hr','P/L','best desk'],hourRows(s))}
function trades(){const s=S;tbl('open2',['desk','sym','side','entry','stop','target','why'],openRows(s));
tbl('closed',['#','desk','sym','side','P/L','regime','why'],s.closed_trades.map(t=>[t.id,esc(t.desk),t.symbol,side(t.side),'<span class='+cls(t.pnl)+'>'+f(t.pnl)+'</span>',esc(t.regime),'<span class=mut>'+esc(t.reason).slice(0,70)+'</span>']))}
function desks(){const s=S;tbl('desks',['desk','style','share','open','trades 24h','win','P/L 24h','per hour','status'],(s.desks||[]).map(r=>[esc(r.desk),esc(r.style),f((r.share||0)*100,1)+'%',r.open,r.n,r.win==null?'-':f(r.win*100,0)+'%','<span class='+cls(r.pnl24)+'>'+f(r.pnl24)+'</span>','<span class='+cls(r.pph)+'>'+f(r.pph)+'</span>',r.paused?'cooling off':'trading']));
tbl('hours2',['hr','P/L','best desk'],hourRows(s));
$('dlog').innerHTML=(s.desk_log||[]).map(e=>'<div>'+(typeof e==='string'?esc(e):'<span class=mut>#'+e.cycle+'</span> '+esc(e.desk)+' '+e.symbol+' '+(e.side>0?'LONG':'SHORT')+' · '+esc(e.result))+'</div>').join('')||'<span class=mut>Nothing yet.</span>'}
function arc(cx,cy,r,a1,a2,w){const p=(a,rr)=>[cx+rr*Math.cos(a),cy+rr*Math.sin(a)],[x1,y1]=p(a1,r),[x2,y2]=p(a2,r),[x3,y3]=p(a2,r-w),[x4,y4]=p(a1,r-w);return 'M'+x1+' '+y1+' A'+r+' '+r+' 0 0 1 '+x2+' '+y2+' L'+x3+' '+y3+' A'+(r-w)+' '+(r-w)+' 0 0 0 '+x4+' '+y4+'Z'}
function ring(){const dd=S.decision_desk||{},ds=S.desks||[],log=(dd.log||[]).slice(0,72),C=210;let s='<svg viewBox="0 0 420 420" width="100%" style="max-width:520px;display:block;margin:auto">';
 s+='<defs><radialGradient id=rg><stop offset=0 stop-color="#ff3ea5" stop-opacity=.25 /><stop offset=1 stop-color="#ff3ea5" stop-opacity=0 /></radialGradient></defs><circle cx=210 cy=210 r=95 fill="url(#rg)"/>';
 for(let i=0;i<72;i++){const a=i/72*6.283-Math.PI/2,e=log[i],col=!e?'#1a2030':e.result==='OPENED'?'#3fb950':'#f85149';s+='<path d="'+arc(C,C,128,a,a+6.283/72*.72,16)+'" fill="'+col+'"/>'}
 s+='<circle cx=210 cy=210 r=104 fill=none stroke="#3ef0ff" stroke-opacity=.25 stroke-dasharray="2 5"/>';
 ds.forEach((d,i)=>{const a=i/ds.length*6.283-Math.PI/2,x=C+176*Math.cos(a),y=C+176*Math.sin(a),col=d.paused?'#8b949e':d.pph>0?'#3fb950':d.pph<0?'#f85149':'#3ef0ff';
  s+='<line x1="'+(C+132*Math.cos(a))+'" y1="'+(C+132*Math.sin(a))+'" x2="'+x+'" y2="'+y+'" stroke="'+col+'" stroke-opacity=.35 stroke-dasharray="2 3"/>';
  s+='<rect x="'+(x-38)+'" y="'+(y-17)+'" width=76 height=34 rx=6 fill="#0b0f1a" stroke="'+col+'" stroke-opacity=.8 /><text x="'+x+'" y="'+(y-3)+'" fill="#fff" font-size=9 font-family="ui-monospace,Menlo" text-anchor=middle>'+esc(String(d.desk).replace(/^T\d+\./,'')).slice(0,12)+'</text><text x="'+x+'" y="'+(y+10)+'" fill="'+col+'" font-size=8.5 font-family="ui-monospace,Menlo" text-anchor=middle>'+(d.pph>=0?'+':'')+f(d.pph)+'/h · '+d.open+' open</text>'});
 s+='<rect x=150 y=178 width=120 height=64 rx=8 fill="#0b0f1a" stroke="#ff3ea5" stroke-width=1.5 /><text x=210 y=203 fill="#fff" font-size=15 font-weight=700 font-family="ui-monospace,Menlo" text-anchor=middle letter-spacing="2">RISK GATE</text><text x=210 y=222 fill="#ff3ea5" font-size=10 font-family="ui-monospace,Menlo" text-anchor=middle>yes rate '+(dd.yes_rate==null?'-':f(dd.yes_rate*100,0)+'%')+'</text><text x=210 y=235 fill="#9aa4bf" font-size=8.5 font-family="ui-monospace,Menlo" text-anchor=middle>'+(dd.approved||0)+' yes · '+(dd.rejected||0)+' no</text></svg>';
 $('ring').innerHTML=s+'<div class=mut style="text-align:center;font-size:11.5px">ring = last 72 proposals (green approved, red rejected) · boxes = the 10 desks, profit per hour</div>'}
const RULES=[['1 · Kill switch (12% drawdown)',['halted']],['2 · Daily loss limit (3%)',['daily loss limit reached']],['3 · Position limits',['max positions','desk position limit','already in position']],['4 · Portfolio heat (4% at risk)',['portfolio heat limit']],['5 · Exposure caps (no leverage)',['exposure cap']],['6 · Move must beat fees',['move too small to beat fees','no volatility data']]];
function rules(){const dd=S.decision_desk||{},R=Object.fromEntries(dd.reasons||[]),tot=Math.max(1,dd.requests||0);
 $('rules').innerHTML=RULES.map(([n,ks])=>{const b=ks.reduce((a,k)=>a+(R[k]||0),0);return '<div class=rule><div style="flex:1">'+n+'<div class=bar><i style="width:'+Math.min(100,b/tot*100)+'%"></i></div></div><span class="'+(b?'dn':'ok')+'" style="margin-left:10px">'+(b?b+' blocked':'pass')+'</span></div>'}).join('')+'<div class=mut style="font-size:11.5px;margin-top:6px">'+(dd.approved||0)+' of '+(dd.requests||0)+' proposals passed all six. Nothing upstream can override these.</div>'}
function decision(){const dd=S.decision_desk;if(!dd)return;ring();rules();const k=(n,l,c)=>'<div><b class="big '+(c||'')+'">'+n+'</b><span>'+l+'</span></div>';
$('ddstat').innerHTML=k(dd.requests,'proposals')+k(dd.approved,'approved','up')+k(dd.rejected,'rejected','dn')+k(dd.yes_rate==null?'-':f(dd.yes_rate*100,0)+'%','approval rate')+k((dd.session_pnl>=0?'+':'')+f(dd.session_pnl),'P/L (paper)',cls(dd.session_pnl));
$('ddr').textContent='Rejected because: '+((dd.reasons||[]).map(r=>r[0]+' ×'+r[1]).join(' · ')||'nothing rejected yet');
$('ddl').innerHTML=(dd.log||[]).map(e=>'<div><span class=mut>#'+e.cycle+'</span> '+esc(e.desk)+' · '+e.symbol+' '+(e.side>0?'LONG':'SHORT')+' → '+(e.result==='OPENED'?'<span class=up>APPROVED</span>':'<span class=dn>REJECTED: '+esc(e.result)+'</span>')+' <span class=mut>'+esc(e.reason)+'</span></div>').join('')||'<span class=mut>No proposals yet.</span>'}
function votes(sym){const v={};(S.feed||[]).filter(e=>e.symbol==sym).forEach(e=>{const g=e.agent.split('.')[0][0];v[e.kind]=(v[e.kind]||0)+e.direction});return v}
function coinOf(sym){return P&&P.coins?P.coins.find(c=>c.coin==sym):(S.pipe&&S.pipe.top||[]).find(c=>c.coin==sym)}
const SEATS=[['sources','SOURCES','do enough exchanges agree, and is there a story?','like Perplexity: find sources, check the story'],['sentiment','SENTIMENT','headlines, fear & greed, funding','like Grok: read the market conversation'],['charts','CHARTS','does the chart regime support this side?','like Gemini: map the chart setup'],['thesis','THESIS','case FOR vs the strongest case AGAINST','like ChatGPT: build the thesis, argue the other side'],['risk','RISK','six hard rules; any failure = veto','like Claude: review risks and missing info']];
const sideTxt=s=>s>0?'<span class=up>LONG</span>':'<span class=dn>SHORT</span>';
function seatCells(st){return SEATS.map(([k])=>{const v=(st[k]||{}).v;return v==null?'<span class=mut>-</span>':'<span class="'+(v>=.66?'up':v<=.34?'dn':'mut')+'" title="'+esc((st[k]||{}).why)+'">'+f(v,2)+'</span>'})}
function council(){const c=S.council;if(!c)return;const last=c.log[0]||{seats:{}};
 $('seats').innerHTML=SEATS.map(([k,n,q,l])=>{const s=last.seats[k]||{};return '<div class=card><span class=n>'+(s.v==null?'-':f(s.v,2))+'</span><h3>'+n+'</h3><div>'+q+'</div><div class=mut style="margin-top:6px;font-size:11.5px">'+esc(s.why||'waiting for the first proposal')+'</div><div class=mut style="font-size:11px;margin-top:4px">'+l+'</div></div>'}).join('')+
 '<div class=card style="border-top-color:var(--mag)"><span class=n style="color:var(--mag)">'+(last.score==null?'-':f(last.score,2))+'</span><h3>GATE</h3><div>auto ≥ '+c.gate+' · you decide '+c.floor+'–'+c.gate+' · drop &lt; '+c.floor+'</div><div class=mut style="font-size:11px">'+(c.calibration?'calibrated on '+c.calibration.ideas+' training ideas':'default settings (calibrates after the academy)')+'</div><div class=mut style="margin-top:6px;font-size:11.5px">last: '+(last.symbol?esc(last.desk)+' '+last.symbol+' → '+esc(last.verdict):'none yet')+'</div></div>';
 const n=c.counts,k=(v,l,cl)=>'<div><b class="big '+(cl||'')+'">'+v+'</b><span>'+l+'</span></div>';
 $('cstat').innerHTML=k(n.auto,'auto (≥ gate)','up')+k(n.handoff,'handed to you','pp')+k(n.owner_yes,'you said YES','up')+k(n.owner_no,'you said NO','dn')+k(n.expired,'expired, not chased')+k(n.weak,'weak, dropped')+k(n.veto,'risk veto','dn');
 $('crev').textContent=(c.practice?'PRACTICE MODE (paper, learning fast) · ':'')+'Human review is '+(c.human_review?'ON':'OFF')+(S.phase!='live'?' · (the academy runs without hand-offs)':'');
 $('cq').innerHTML=c.queue.length?c.queue.map(q=>'<div><b>'+q.id+'</b> '+esc(q.desk)+' · <b>'+q.symbol+'</b> '+sideTxt(q.side)+' · council <b class=pp>'+f(q.score,2)+'</b> · expires after candle '+q.expires+'<br>'+SEATS.map(([kk,nn])=>nn+' '+f((q.seats[kk]||{}).v,2)).join(' · ')+'<br><button onclick="ctl(\'yes:'+q.id+'\')" style="border-color:var(--up)">YES (paper)</button><button onclick="ctl(\'no:'+q.id+'\')" style="border-color:var(--dn)">NO</button></div>').join(''):'<span class=mut>Nothing waiting. Medium-confidence ideas appear here for your YES or NO.</span>';
 tbl('clog',['#','desk','market','side','council'].concat(SEATS.map(s=>s[1])).concat(['verdict']),c.log.map(e=>[e.cycle,esc(e.desk),e.symbol,sideTxt(e.side),'<b>'+f(e.score,2)+'</b>'].concat(seatCells(e.seats)).concat(['<span class="'+(/AUTO|YES/.test(e.verdict)?'up':/VETO|NO|REJECT/.test(e.verdict)?'dn':'pp')+'">'+esc(e.verdict)+'</span>'])))}
function heat(){const s=S,gs=['scout','predictor','copy','macro','platform','pipe'],m={};(s.feed||[]).forEach(e=>{const g=PRE[e.agent[0]];if(!g)return;const k=e.symbol+'|'+g;m[k]=(m[k]||0)+e.direction*(e.conf||.5)});
 tbl('heat',['market'].concat(gs),s.symbols.map(sym=>['<b>'+sym+'</b>'].concat(gs.map(g=>{const v=m[sym+'|'+g]||0,a=Math.min(.9,Math.abs(v)/2.5);return '<div style="padding:8px 4px;border-radius:4px;background:'+(v>0?'rgba(63,185,80,'+a+')':v<0?'rgba(248,81,73,'+a+')':'#141927')+'">'+(v?(v>0?'+':'')+f(v,1):'·')+'</div>'}))))}
function matrix(){const s=S;heat();const fa=s.fast||{};$('fastlog').innerHTML=(fa.actions||[]).map(a=>'<div><span class=mut>'+new Date(a.t*1000).toLocaleTimeString()+'</span> '+esc(a.text)+'</div>').join('')||'<span class=mut>'+(fa.ticks?fa.ticks+' fast checks so far, nothing needed doing yet.':'Starts once the academy is finished and live trading begins.')+'</span>';tbl('matrix',['market','chart price','pipe price','sources','24h','regime','scouts','predictors','pipe','quant score','final','decision','open'],
s.symbols.map(sym=>{const c=coinOf(sym)||{},v=votes(sym),d=(s.decisions||[]).find(x=>x.symbol==sym)||{},r=s.regimes[sym]||{},o=s.open_trades.filter(t=>t.symbol==sym).length;
const vv=n=>n==null?'<span class=mut>0</span>':'<span class='+cls(n)+'>'+(n>0?'+':'')+n+'</span>';
return['<b>'+sym+'</b>',px(s.prices[sym]),px(c.price),c.sources||'-',pct(c.chg24),esc(r.label||'-')+(r.vol_high?' ⚡':''),vv(v.scout),vv(v.predict),vv(v.platform),f(d.quant),f(d.final),'<span class=mut>'+esc(d.result||'-')+'</span>',o]}));
$('pipevotes').innerHTML=(s.feed||[]).filter(e=>e.agent.startsWith('Y.')).map(e=>'<div><span class=mut>#'+e.cycle+'</span> <span class=pp>'+esc(e.agent)+'</span> → <b>'+e.symbol+'</b> '+side(e.direction)+' <span class=mut>('+e.conf+')</span></div>').join('')||'<span class=mut>Pipe agents vote on every live 1-hour candle; the fast lane reacts to news within ~1 s, and only on real prices.</span>'}
function feedHTML(s){return s.feed.map(e=>'<div><span class=mut>#'+e.cycle+'</span> '+esc(e.agent)+' → <b>'+e.symbol+'</b> '+side(e.direction)+' <span class=mut>('+e.conf+', '+e.kind+')</span></div>').join('')||'<span class=mut>No signals yet.</span>'}
function brain(){const s=S;$('groups2').innerHTML=groupsHTML(s);const ar=a=>[esc(a.name),a.grp,f(a.acc*100,1)+'%',a.n,f(a.weight)];
tbl('top',['agent','team','hit','calls','weight'],s.top_agents.map(ar));tbl('bot',['agent','team','hit','calls','weight'],s.bottom_agents.map(ar));
$('feed').innerHTML=feedHTML(s);$('less').innerHTML=s.lessons.map(e=>'<div><span class=mut>#'+e.cycle+' '+esc(e.author)+'</span> '+esc(e.text)+'</div>').join('')||'<span class=mut>No lessons yet.</span>';
$('set').textContent=Object.entries(s.settings).map(([k,v])=>k+' = '+v).join('  ·  ')}
function flow(){const s=S;tbl('flowt',['market','buy votes','sell votes','net','lean'],s.symbols.map(sym=>{const fs=s.feed.filter(e=>e.symbol==sym),b=fs.filter(e=>e.direction>0).length,se=fs.filter(e=>e.direction<0).length;
return['<b>'+sym+'</b>','<span class=up>'+b+'</span>','<span class=dn>'+se+'</span>','<span class='+cls(b-se)+'>'+(b-se)+'</span>',b>se*1.5?'<span class=up>buy cluster</span>':se>b*1.5?'<span class=dn>sell cluster</span>':'<span class=mut>mixed</span>']}));
tbl('research',['market','pipe price','exchanges','disagree','funding','USD premium','24h'],s.symbols.map(sym=>{const c=coinOf(sym)||{};return['<b>'+sym+'</b>',px(c.price),c.sources||'-',c.spread==null?'-':f(c.spread*100,3)+'%',c.funding==null?'-':f(c.funding*100,4)+'%',pct(c.usd_premium,3),pct(c.chg24)]}));
$('feed2').innerHTML=feedHTML(s)}
function renderPipe(){if(cur!='pipe')return;const p=S.pipe;if(p){const k=(n,l,c)=>'<div><b class="big '+(c||'')+'">'+n+'</b><span>'+l+'</span></div>';
$('pstat').innerHTML=k(p.sources||0,'distinct sources answering (platforms + news publishers)','pp')+k(p.publishers||0,'news publishers seen')+k(p.news_per_hour||0,'new stories in the last hour')+k(p.live,'live feeds (answered in last 15 min)','pp')+k(p.declared,'feeds requested')+k(p.providers_ok+' / '+p.providers,'providers answering','up')+k(p.providers_failing,'providers failing',p.providers_failing?'dn':'')+(p.warming_up?k('…','first round still loading'):'');
tbl('pcat',['category','live feeds'],Object.entries(p.by_cat).sort((a,b)=>b[1]-a[1]).map(([c,n])=>[c,'<b>'+n+'</b>']))}
if(!P)return;tbl('pprov',['provider','type','status','feeds','ms','error'],P.providers.map(r=>[esc(r.name),r.cat,r.ok==null?'<span class=mut>waiting</span>':r.ok?'<span class=up>OK</span>':'<span class=dn>FAIL</span>',r.n,r.ms,'<span class=mut>'+esc(r.err)+'</span>']));
const q=($('pfind').value||'').toLowerCase();tbl('pfeeds',['feed','type','what','value','change','age'],P.feeds.filter(x=>!q||(x.id+' '+x.label+' '+x.cat).toLowerCase().includes(q)).slice(0,800).map(x=>[esc(x.id),x.cat,'<span class=mut>'+esc(x.label).slice(0,70)+'</span>',big(x.value),pct(x.chg),(x.age>900?'<span class=dn>':'<span class=mut>')+x.age+'s</span>']))}
function crypto(){if(!P)return;tbl('coins',['coin','price (median)','exchanges','disagree','24h','funding','USD premium'],P.coins.map(c=>['<b>'+c.coin+'</b>','$'+px(c.price),c.sources,f(c.spread*100,3)+'%',pct(c.chg24),c.funding==null?'-':f(c.funding*100,4)+'%',pct(c.usd_premium,3)]));
tbl('newtok',['source','what','price','24h'],(P.newtokens||[]).map(x=>[esc(x.provider),'<span class=w>'+esc(x.label)+'</span>',x.value==1?'-':px(x.value),pct(x.chg)]));
const btc=(P.coins.find(c=>c.coin=='BTC')||{}).price;tbl('regional',['exchange','quote','BTC in USD','vs world price'],P.feeds.filter(x=>x.id.endsWith(':BTC')&&x.cat=='crypto'&&!x.id.startsWith('global')).sort((a,b)=>b.value-a.value).map(x=>[esc(x.id.split(':')[0]),esc((x.label.match(/\(([^)]+)\)/)||[])[1]||''),'$'+px(x.value),btc?pct(x.value/btc-1,2):'-']));
tbl('stocks',['name','symbol','price','day'],P.world.filter(w=>w.extra.kind=='stock').map(w=>[esc(w.label),w.extra.symbol,px(w.value),pct(w.chg)]))}
const SESS=[['Sydney','Australia/Sydney',[10,0],[16,0],'^AXJO'],['Tokyo','Asia/Tokyo',[9,0],[15,30],'^N225'],['Hong Kong','Asia/Hong_Kong',[9,30],[16,0],'^HSI'],['Shanghai','Asia/Shanghai',[9,30],[15,0],'000001.SS'],['Mumbai','Asia/Kolkata',[9,15],[15,30],'^NSEI'],['Riyadh','Asia/Riyadh',[10,0],[15,0],'^TASI.SR'],['Frankfurt','Europe/Berlin',[9,0],[17,30],'^GDAXI'],['London','Europe/London',[8,0],[16,30],'^FTSE'],['New York','America/New_York',[9,30],[16,0],'^GSPC']];
function sessions(){const now=new Date(),out=[],moves=[];SESS.forEach(([n,tz,o,c,sym])=>{const p=new Intl.DateTimeFormat('en-AU',{timeZone:tz,hour:'2-digit',minute:'2-digit',weekday:'short',hour12:false}).formatToParts(now),g=t=>(p.find(x=>x.type==t)||{}).value;
 const wd=g('weekday'),hh=+g('hour')%24,mm=+g('minute'),mins=hh*60+mm,wk=tz=='Asia/Riyadh'?!['Fri','Sat'].includes(wd):!['Sat','Sun'].includes(wd),open=wk&&mins>=o[0]*60+o[1]&&mins<c[0]*60+c[1];
 const w=P&&P.world.find(x=>x.extra.symbol==sym);if(w&&open)moves.push([n,w.chg]);
 out.push('<div class="'+(open?'open':'')+'"><b>'+n+'</b> '+(open?'<span class=up>OPEN</span>':'<span class=mut>closed</span>')+'<br><span class=mut>'+wd+' '+String(hh).padStart(2,'0')+':'+String(mm).padStart(2,'0')+' local</span><br>'+(w?pct(w.chg):'<span class=mut>-</span>')+'</div>')});
 out.push('<div class=open><b>Crypto</b> <span class=up>24/7</span><br><span class=mut>BTC 24h</span><br>'+pct((((S.pipe||{}).top||[])[0]||{}).chg24)+'</div>');$('sess').innerHTML=out.join('');
 moves.sort((a,b)=>b[1]-a[1]);$('tzread').innerHTML=moves.length?'Open right now, strongest to weakest: '+moves.map(m=>m[0]+' '+pct(m[1])).join(' · ')+'. When one region moves on news before another opens, that\'s the "timezone" idea: the pipe agents read it as a risk-on/off vote, scored like any other agent.':'No major stock market is open at this moment; crypto keeps trading.'}
function world(){sessions();if(!P)return;const wm=P.summary.world;$('wstat').innerHTML='<div><b class="big '+cls(wm.risk)+'">'+(wm.risk==null?'-':f(wm.risk*100,2)+'%')+'</b><span>average move of '+wm.n+' major indices</span></div><div><b class="big">'+(wm.vix==null?'-':f(wm.vix*100,1)+'%')+'</b><span>VIX change</span></div><div><b class="big pp">'+P.world.length+'</b><span>world feeds live</span></div><div><b class="big pp">'+P.fx.length+'</b><span>currency feeds live</span></div>';
const row=w=>[esc(w.label),'<span class=mut>'+esc(w.extra.symbol)+'</span>',px(w.value),pct(w.chg)];
tbl('widx',['market','symbol','level','day'],P.world.filter(w=>w.extra.kind=='index'||w.extra.kind=='vol').map(row));
tbl('wcom',['market','symbol','level','day'],P.world.filter(w=>['commodity','rates','fx'].includes(w.extra.kind)).map(row));
tbl('wfx',['pair','source','rate'],P.fx.map(x=>[esc(x.label),esc(x.provider),px(x.value)]));
tbl('wother',['gauge','source','value','change'],P.other.map(x=>[esc(x.label),esc(x.provider),big(x.value),pct(x.chg)]))}
function news(){const s=S;if(P){const nm=P.summary.news;$('nstat').innerHTML='<div><b class="big pp">'+(P.summary.publishers||0)+'</b><span>different publishers</span></div><div><b class="big">'+(P.summary.news_per_hour||0)+'</b><span>stories in the last hour</span></div><div><b class="big '+cls(nm.mood)+'">'+f(nm.mood,2)+'</b><span>mood (-1 to +1), last 6h</span></div><div><b class="big pp">'+nm.n+'</b><span>headlines, last 6h</span></div><div><b class="big">'+P.feeds.filter(x=>x.cat=='news').length+'</b><span>news feeds answering</span></div>';
$('heads').innerHTML=P.headlines.map(h=>'<div><span class=mut>'+new Date(h.t*1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})+' · '+esc(h.src)+'</span> <span class='+cls(h.s)+'>'+esc(h.title)+'</span></div>').join('')||'<span class=mut>Loading the first round of feeds...</span>'}
const m=s.macro;$('macro').innerHTML=m?esc(JSON.stringify(m).slice(0,1500)):'Macro team is off.'}
function poly(){const p=S.polybook;if(p){$('poly').textContent='bankroll $'+f(p.equity)+' ('+(p.pnl>=0?'+':'')+f(p.pnl)+') · closed '+p.closed+' · hit '+(p.hit_rate==null?'-':f(p.hit_rate*100,0)+'%')+(p.synthetic?' · SYNTHETIC markets (sim)':'');
tbl('polyt',['market','side','price','our view'],p.open.map(t=>['<span class=w>'+esc(t.q)+'</span>',t.side,f(t.price,2),f(t.fair,2)]))}
if(P)tbl('preds',['venue','question','YES chance'],P.prediction.map(x=>[esc(x.provider),'<span class=w>'+esc(x.label)+'</span>',x.value==null?'-':f(x.value*100,0)+'%']))}
function guard(){const s=S,dd=s.decision_desk||{};const G=[['Paper money only','no real orders can be sent from this app','ON'],['Kill switch','stops everything at 12% drawdown · now '+f(s.drawdown*100,1)+'%',s.halted?'TRIPPED':'armed'],['Daily loss limit','3% a day, then no new trades until tomorrow',s.day_blocked?'HIT':'armed'],['One approval layer','risk manager approved '+(dd.approved||0)+' / rejected '+(dd.rejected||0),'ON'],['Claude spend','calls this run: '+s.llm.calls+(s.llm.on?'':' (off, no key)'),s.llm.on?'ON':'OFF'],['Outside text is data','headlines and market names are never treated as instructions','ON'],['Broker mirrors','demo accounts only, off unless you switch them on',(s.brokers||[]).some(b=>b.ready)?'demo':'OFF']];
 $('guard').innerHTML=G.map(g=>'<div class=rule><div><b>'+g[0]+'</b><br><span class=mut style="font-family:system-ui">'+esc(g[1])+'</span></div><span class="'+(['TRIPPED','HIT'].includes(g[2])?'dn':'ok')+'">'+g[2]+'</span></div>').join('')}
function engines(){guard();const s=S,p=s.pipe||{},dd=s.decision_desk||{},G=g=>(s.groups.find(x=>x.group==g)||{}),tot=(...gs)=>gs.reduce((a,g)=>a+(G(g).active||0),0);
const E=[['1 · SCAN',p.live||0,'live feeds in the market pipe from '+(p.providers_ok||0)+' providers, plus '+s.symbols.length+' charts the robot trades.','TradingAgents: data tools'],
['2 · ANALYSE',tot('analyst','quant'),'analyst + quant agents read the charts and vote the regime: '+Object.entries(s.regimes).map(([k,v])=>k+' '+v.label).join(', ')+'.','TradingAgents: technical analyst'],
['3 · RESEARCH',tot('macro','pipe','platform'),'macro, pipe and platform agents read news, prediction markets, funding, world markets.','TradingAgents: news + sentiment analysts'],
['4 · FLOW',tot('scout','predictor','copy'),'scouts, predictors and copy agents post buy/sell votes; '+s.feed.length+' recent votes in the brain.','TradingAgents: bull vs bear researchers'],
['5 · DECIDE',((s.council||{}).counts||{}).handoff||0,'hand-offs to you so far; the council of 5 seats scores every idea, then the gate decides: auto, you, or drop. Weighted vote'+(s.llm.on?' and the Claude chief strategist.':' (Claude off: pure quant vote).'),'TradingAgents: trader'],
['6 · RISK',dd.rejected||0,'proposals rejected by the risk manager out of '+(dd.requests||0)+'. Drawdown '+f(s.drawdown*100,1)+'%; kill switch at 12%.','TradingAgents: risk team'],
['7 · EXECUTE',s.open_trades.length,'open paper positions across '+(s.desks||[]).length+' desks. Real-money orders: none (paper only).','TradingAgents: simulated exchange'],
['8 · LEARN',(s.lessons||[]).length,'lessons on file; improvers re-weight agents every '+10+' cycles and retire ones that don\'t beat chance.','freqtrade: hyperopt / FinRL: feedback']];
$('eng').innerHTML=E.map(e=>'<div class=card><span class=n>'+e[1]+'</span><h3>'+e[0]+'</h3><div>'+esc(e[2])+'</div><div class=mut style="margin-top:6px;font-size:11.5px">like '+e[3]+'</div></div>').join('');
$('oss').innerHTML=['<b>TradingAgents</b> (Apache-2.0): analysts → bull/bear debate → trader → risk team → manager. Ours: the same chain, but every agent is scored on real outcomes and loses its vote if it doesn\'t beat chance.',
'<b>ai-hedge-fund</b>: investor-persona agents and a portfolio manager; no execution. Ours executes paper trades and tracks profit per hour per desk.',
'<b>freqtrade / Hummingbot</b>: mature single-strategy bots with dry-run and exchange connectors. Ours borrows the dry-run-first rule and protections (daily loss limit, cool-off).',
'<b>FinRL</b>: reinforcement learning on simulated markets. Ours learns more simply: hit-rate weighting plus an exam on unseen data.',
'None of these, and not this app, has shown reliable profit. Paper results first; real money is your decision.'].map(t=>'<div>'+t+'</div>').join('')}
function academy(){const g=S.graduation;$('grad').textContent=g?g.summary:'No exam yet.';const sd=S.selfdev||{reports:[],top:[],bottom:[]};
$('sdstat').innerHTML='<div><b class="big pp">'+sd.reports.length+'</b><span>hourly reports</span></div><div><b class=big>'+sd.publishers_rated+'</b><span>publishers with a track record</span></div><div><b class=big>'+sd.pending+'</b><span>headlines waiting to be graded (1h later)</span></div>';
tbl('sdlog',['time','equity','hour P/L','news tracked / graded','what changed','team hit rates'],sd.reports.map(r=>[new Date(r.t*1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}),'$'+f(r.equity),'<span class='+cls(r.hour_pnl)+'>'+f(r.hour_pnl)+'</span>',r.news_tracked+' / '+r.news_graded,'<span class=w>'+esc((r.settings_changed.concat(r.lessons)).join(' · ')||'no change needed')+(r.gate?' · gate '+r.gate[0]+'/'+r.gate[1]:'')+'</span>','<span class=mut>'+Object.entries(r.team_hit).map(([k,v])=>k+' '+f(v*100,0)+'%').join(' ')+'</span>']));
const pr=x=>[esc(x[0]),x[1]+' / '+x[2],f(x[1]/x[2]*100,0)+'%','×'+f(x[3],2)];tbl('pubtop',['publisher','right / judged','hit','weight'],sd.top.map(pr));tbl('pubbot',['publisher','right / judged','hit','weight'],sd.bottom.map(pr));
tbl('gradg',['team','info'],g&&g.groups?Object.entries(g.groups).map(([k,v])=>[k,'<span class=mut>'+esc(JSON.stringify(v))+'</span>']):[])}
function accounts(){const s=S;tbl('brk',['broker','ready','sent','failed','last'],(s.brokers||[]).map(b=>[esc(b.name),b.ready?'<span class=up>yes</span>':'<span class=mut>no</span>',b.sent,b.failed,esc(b.last)]));
tbl('trd',['trader','trades','win','mean P/L','skill (conservative)'],s.traders.map(t=>[t.trader,t.n,f(t.wr*100,0)+'%',f(t.mean*100,2)+'%',f(t.wilson*100,0)+'%']));
const p=s.polybook;$('polyacc').textContent=p?'bankroll $'+f(p.equity)+' ('+(p.pnl>=0?'+':'')+f(p.pnl)+')':'-'}
function manager(){const s=S;tbl('org',['team','agents','job'],(s.org||[]).map(o=>[o.team,o.agents,'<span class=w>'+esc(o.job)+'</span>']));
$('ctlmsg').textContent=(s.paused?'PAUSED · ':'')+'session now: '+((s.session||{}).now||'-').toUpperCase()+' (Asia 00-07, London 07-13, NY 13-21 UTC)';
const dv=s.dev||{};$('dev').innerHTML=((dv.findings?'<div><b>Latest post-mortem:</b> '+esc(dv.findings.items.join('; '))+'</div>':'')+(dv.proposals||[]).map(p=>'<div><b>'+esc(p.title)+'</b> — '+esc(p.change)+' <span class=mut>Test: '+esc(p.test)+' ['+esc(p.status)+']</span></div>').join(''))||'<span class=mut>Nothing yet.</span>'}
function help(){$('help').innerHTML=['<b>Paper only.</b> Every trade here uses pretend money on real (or simulated) prices. Nothing is sent to a real account.',
'<b>Clusters</b> (top of each page) are the agent teams that work on that page. "a / b agents" = active / total. Hit = how often their calls were right. Weight = how much their vote counts (earned, not given).',
'<b>Market pipe</b> (purple bar) is one shared intake of public data that every page and team can read. Tap it to see every provider and feed, which ones work and which fail. "Requested" counts every feed asked for; "live" counts only feeds that answered in the last 15 minutes.',
'<b>Why some feeds fail:</b> some sites block cloud servers or rate-limit them (Binance blocks this server, for example). Failing providers back off and retry; the robot uses whichever answer.',
'<b>Teams:</b> scouts and predictors call direction; analysts and quants read the chart; macro reads world events; pipe agents read the pipe; platform agents take TradingView-style webhooks; desks trade; improvers tune settings within hard limits; the risk manager approves every trade.',
'<b>Kill switch:</b> at 12% drawdown everything stops until you clear it. Daily loss limit 3%.',
'<b>Free hosting:</b> the server sleeps after ~15 minutes without visitors and forgets its memory when it restarts.'].map(t=>'<div>'+t+'</div>').join('')}

async function ctl(a){const r=await fetch('/api/control'+Q,{method:'POST',body:JSON.stringify({action:a})});$('ctlmsg').textContent=(await r.json()).message;tick()}
async function ask(t){const q=(t||$('q').value).trim();if(!q)return;$('q').value='';$('chat').innerHTML+='<div><b>You:</b> '+esc(q)+'</div>';
const r=await fetch('/api/ask'+Q,{method:'POST',body:JSON.stringify({question:q})});const a=(await r.json()).answer||'';say(a);$('chat').innerHTML+='<div><b>Manager:</b> '+esc(a)+'</div>';$('chat').scrollTop=1e9}
async function brief(){$('chat').innerHTML+='<div class=mut>Asking for the daily briefing...</div>';const r=await fetch('/api/briefing'+Q,{method:'POST',body:'{}'});const a=(await r.json()).answer||'';say(a);$('chat').innerHTML+='<div><b>Manager:</b> '+esc(a)+'</div>'}
function say(t){if(!$('spk').checked||!window.speechSynthesis||!t)return;speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(t);u.lang='en-AU';speechSynthesis.speak(u)}
function listen(){const R=window.SpeechRecognition||window.webkitSpeechRecognition;if(!R){$('micmsg').textContent='Voice input needs Chrome or Safari.';return}
speechSynthesis&&speechSynthesis.cancel();const r=new R();r.lang='en-AU';r.interimResults=false;$('micmsg').textContent='listening...';
r.onresult=e=>{const t=e.results[0][0].transcript;$('micmsg').textContent='heard: '+t;ask(t)};r.onerror=e=>{$('micmsg').textContent='mic error: '+e.error};r.start()}
route();tick();setInterval(tick,2500);setInterval(()=>{if(needPipe())loadPipe()},10000);
</script></body></html>"""


def serve(engine, port=8765, host="127.0.0.1", token=None):
    """token: if set, every request must carry ?token=<token> (use this whenever host is not localhost)."""
    from urllib.parse import parse_qs, urlparse

    cache = {"t": 0.0, "body": b"{}"}
    scache = {"t": 0.0, "body": b"{}"}
    slock = threading.Lock()

    def state_json():
        import time
        with slock:                                # many phones share one snapshot (refreshed every 2 s)
            if time.time() - scache["t"] > 2:
                scache["body"] = json.dumps(engine.state()).encode()
                scache["t"] = time.time()
            return scache["body"]

    def pipe_json():
        import time
        if time.time() - cache["t"] > 5:          # many phones/tabs share one snapshot
            p = engine.pipe
            cache["body"] = json.dumps(p.full() if p else {"error": "market pipe is off"}).encode()
            cache["t"] = time.time()
        return cache["body"]

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _auth(self):
            if not token:
                return True
            h = self.headers.get("Authorization", "")
            return parse_qs(urlparse(self.path).query).get("token") == [token] or h == "Bearer " + token

        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_HEAD(self):
            self.send_response(200 if self.path.split("?")[0] == "/healthz" else 401)
            self.end_headers()

        def do_POST(self):
            if not self._auth():
                return self._send(401, b'{"error":"unauthorized"}', "application/json")
            try:
                n = min(int(self.headers.get("Content-Length", 0)), 20000)
                data = json.loads(self.rfile.read(n) or b"{}")
                path = self.path.split("?")[0]
                if path == "/api/control":
                    out = {"message": engine.control(str(data.get("action", "")))}
                elif path == "/api/ask":
                    out = {"answer": engine.ask(data.get("question", ""))}
                elif path == "/api/briefing":
                    out = {"answer": engine.briefing()}
                elif path == "/api/signal":
                    ok, msg = engine.submit_signal(data)
                    out = {"ok": ok, "message": msg}
                else:
                    out = {"error": "not found"}
            except Exception as e:
                out = {"error": str(e)[:200]}
            self._send(200, json.dumps(out).encode(), "application/json")

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/healthz":            # public, says nothing about the account
                return self._send(200, b"ok", "text/plain")
            if not self._auth():
                return self._send(401, b"unauthorized: open the page with ?token=YOUR_TOKEN", "text/plain")
            try:
                if path.startswith("/api/state"):
                    return self._send(200, state_json(), "application/json")
                if path.startswith("/api/pipe"):
                    return self._send(200, pipe_json(), "application/json")
            except Exception as e:
                return self._send(200, json.dumps({"error": str(e)[:200]}).encode(), "application/json")
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")

    srv = ThreadingHTTPServer((host, port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
