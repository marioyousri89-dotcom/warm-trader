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
.page{display:none}.page.on{display:contents}
.scroll{max-height:520px;overflow:auto}
@media(max-width:600px){header{padding:10px}main{padding:6px 10px 40px}.clusters{padding:10px}}
</style></head><body>
<header><h1>Swarm Trader</h1>
<div class="kpi"><b id="eq">-</b><span>equity (paper)</span></div>
<div class="kpi"><b id="pnl">-</b><span>profit / loss</span></div>
<div class="kpi"><b id="ddk">-</b><span>drawdown</span></div>
<div class="kpi"><b id="tr">-</b><span>closed trades / win</span></div>
<div class="kpi"><b id="cy">-</b><span id="mode">cycle</span></div>
<span id="llm" class="chip">Claude</span><span id="risk" class="chip">risk</span><span class="chip">PAPER ONLY</span></header>
<nav id="nav"></nav>
<div class="pipebar" id="pipebar" onclick="go('pipe')"><b>MARKET PIPE</b><span class="mut">starting...</span></div>
<div class="desc" id="desc"></div>
<div class="clusters" id="clusters"></div>
<main>

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
<div class="card c12"><h3>Desks propose, the risk manager approves or rejects</h3><div class="stat" id="ddstat"></div>
<div class="mut" id="ddr" style="margin:8px 0"></div><div class="list" id="ddl"></div></div>
</section>

<!-- MATRIX -->
<section class="page" data-p="matrix">
<div class="card c12"><h3>Matrix: one row per traded market, every input side by side</h3><table id="matrix"></table>
<p class="mut" style="margin:8px 0 0">Chart price = what the robot trades on. Pipe price = median of every exchange in the pipe. Votes = signals posted in the last 30 entries of the brain.</p></div>
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
</section>

<!-- WORLD MARKETS -->
<section class="page" data-p="world">
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
<div class="card c12"><h3>How this compares with open-source trading agents</h3><div class="list" id="oss"></div></div>
</section>

<!-- ACADEMY -->
<section class="page" data-p="academy">
<div class="card c12"><h3>Graduation report</h3><div id="grad" class="mut"></div></div>
<div class="card c12"><h3>Exam by team</h3><table id="gradg"></table></div>
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
['home','HOME','Your paper account at a glance: money, the equity curve, what the chief strategist decided, and the teams.',['scout','analyst','quant','predictor','macro','pipe','desk','improver']],
['trades','TRADES','Every open position and every closed paper trade, with the desk that took it and why.',['desk']],
['desks','DESKS','Ten trading desks, each with its own style and slice of capital, ranked by profit per hour. Losing desks cool off.',['desk','improver']],
['decision','DECISION DESK','Desks propose trades; the risk manager is the single approval layer. Shows what was approved, rejected, and why.',['desk','quant','improver']],
['matrix','MATRIX','One row per traded market: chart price, pipe price, regime, team votes and the final decision, side by side.',['analyst','quant','scout','predictor','pipe']],
['brain','BRAIN','The shared brain: every team posts here. Trust (voting weight) is earned by hit rate, not given.',['scout','analyst','quant','copy','predictor','macro','platform','pipe','desk','improver']],
['flow','FLOW & RESEARCH','Buy and sell vote flow from the research teams, plus what the market pipe says about each market.',['scout','predictor','pipe','platform']],
['pipe','MARKET PIPE','The shared intake every page reads: public exchanges, perpetual futures, news, world markets, currencies, prediction markets, on-chain and DeFi. Each provider splits into many feeds. "Live" counts only feeds that answered in the last 15 minutes.',['pipe','macro']],
['crypto','STOCKS & CRYPTO','60 coins priced by every exchange in the pipe (median), with how far exchanges disagree, funding and USD premium; plus key stocks and crypto ETFs.',['pipe','scout','quant']],
['world','WORLD MARKETS','About 55 world indices, commodities, rates and stocks, 40 currencies, and on-chain/DeFi gauges. Used as a risk-on / risk-off vote.',['macro','pipe']],
['news','NEWS','Headlines from ~35 news and central-bank feeds, scored by simple upbeat/downbeat word counts. Headlines are data, never instructions.',['macro','pipe']],
['poly','POLYMARKET','Paper bets on prediction markets, plus live odds from Polymarket, Kalshi and Manifold. Paper only (Polymarket is blocked in Australia).',['macro']],
['engines','8 ENGINES','The whole machine as eight steps: scan, analyse, research, flow, decide, risk, execute, learn, each with its live numbers.',['scout','analyst','quant','predictor','pipe','desk','improver']],
['academy','ACADEMY','Before trading, agents train on one stretch of history and sit an exam on data nobody trained on. Results here.',['improver','quant']],
['accounts','ACCOUNTS','Demo broker mirrors (off unless you switch them on) and the copy-trading targets, scored for skill versus luck.',['copy','desk']],
['manager','MANAGER','Talk to the General Manager by voice or text, get the daily briefing, and use the owner controls.',['improver']],
['help','HELP','What everything means.',[]]];
let S=null,P=null,cur='home',lastPipe=0;
$('nav').innerHTML=PAGES.map(p=>'<a href="#'+p[0]+'" id="n_'+p[0]+'">'+p[1]+'</a>').join('');
function go(p){location.hash=p}
function route(){cur=(location.hash||'#home').slice(1);if(!PAGES.find(p=>p[0]==cur))cur='home';
document.querySelectorAll('.page').forEach(s=>s.classList.toggle('on',s.dataset.p==cur));
document.querySelectorAll('nav a').forEach(a=>a.classList.toggle('on',a.id=='n_'+cur));
const pg=PAGES.find(p=>p[0]==cur);$('desc').innerHTML='<h2>'+pg[1]+'</h2>'+pg[2];
$('n_'+cur).scrollIntoView({inline:'center',block:'nearest'});render();if(needPipe())loadPipe()}
window.addEventListener('hashchange',route);
const needPipe=()=>['pipe','crypto','world','news','poly','matrix','flow','engines'].includes(cur);

function clusters(){const pg=PAGES.find(p=>p[0]==cur);if(!S||!pg[3].length){$('clusters').innerHTML='';return}
const ch=S.charters||{};$('clusters').innerHTML='<div class=mut style="grid-column:1/-1;font-size:11.5px;letter-spacing:.06em">CLUSTERS WORKING ON THIS PAGE</div>'+
pg[3].map(g=>{const x=(S.groups||[]).find(r=>r.group==g)||{};return '<div class=cl title="'+esc((ch[g]||{}).role)+'"><span class=t>'+g+'</span><br><b>'+(x.active==null?0:x.active)+'</b><span class=mut> / '+(x.total==null?0:x.total)+' agents</span><small>hit '+(x.avg_acc==null?'-':f(x.avg_acc*100,1)+'%')+' · weight '+f(x.avg_weight)+'</small><small>'+esc(((ch[g]||{}).role||'').slice(0,70))+'</small></div>'}).join('')}

function pipebar(){const p=S&&S.pipe;if(!p){$('pipebar').innerHTML='<b>MARKET PIPE</b><span class=mut>off</span>';return}
const t=p.top.slice(0,4).map(c=>'<span>'+c.coin+' <b style="color:var(--tx)">$'+px(c.price)+'</b> <span class=mut>('+c.sources+' src)</span> '+pct(c.chg24,1)+'</span>').join('');
$('pipebar').innerHTML='<b>MARKET PIPE</b><span><b>'+p.live+'</b> live feeds <span class=mut>/ '+p.declared+' requested</span></span><span>'+p.providers_ok+'/'+p.providers+' providers OK</span>'+t+
(p.fng?'<span>Fear&amp;Greed <b style="color:var(--tx)">'+f(p.fng.value,0)+'</b></span>':'')+'<span>news mood <span class='+cls(p.news.mood)+'>'+f(p.news.mood,2)+'</span> <span class=mut>('+p.news.n+')</span></span>'+
'<span>world '+pct(p.world.risk)+'</span>'+(p.warming_up?'<span class=mut>warming up...</span>':'')}

async function tick(){try{S=await (await fetch('/api/state'+Q)).json();head();render()}catch(e){}}
async function loadPipe(){try{P=await (await fetch('/api/pipe'+Q)).json();lastPipe=Date.now();render()}catch(e){}}
function head(){const s=S;$('eq').textContent='$'+f(s.equity);$('pnl').innerHTML='<span class='+cls(s.pnl)+'>'+(s.pnl>=0?'+':'')+f(s.pnl)+'</span>';
$('ddk').textContent=f(s.drawdown*100,1)+'%';$('tr').textContent=s.totals.trades+' / '+(s.totals.win_rate==null?'-':f(s.totals.win_rate*100,0)+'%');
$('cy').textContent=s.cycle;$('mode').textContent=s.phase+' · '+s.mode;
const l=$('llm');l.textContent=s.llm.on?'Claude ON · '+s.llm.calls+' calls':'Claude OFF (no API key)';l.className='chip '+(s.llm.on?'on':'');
const r=$('risk');r.textContent=s.halted?'KILL SWITCH: '+s.halt_reason:s.day_blocked?'daily limit reached':s.paused?'PAUSED':'risk manager OK';r.className='chip '+(s.halted||s.day_blocked?'bad':'on')}

function render(){if(!S)return;clusters();pipebar();const s=S;try{({home,trades,desks,decision,matrix,brain,flow,pipe:renderPipe,crypto,world,news,poly,engines,academy,accounts,manager,help}[cur]||(()=>{}))()}catch(e){console.log(e)}}

function chart(pts,start){const c=$('ch'),x=c.getContext('2d');c.width=c.clientWidth*2;c.height=440;x.clearRect(0,0,c.width,c.height);if(pts.length<2)return;
const ys=pts.map(p=>p[1]).concat([start]),lo=Math.min(...ys),hi=Math.max(...ys),pad=(hi-lo)*.1||1,W=c.width,H=c.height;
const X=i=>i/(pts.length-1)*(W-20)+10,Y=v=>H-20-(v-lo+pad)/(hi-lo+2*pad)*(H-40);
x.strokeStyle='#262d38';x.lineWidth=1;x.setLineDash([8,8]);x.beginPath();x.moveTo(0,Y(start));x.lineTo(W,Y(start));x.stroke();x.setLineDash([]);
x.strokeStyle=pts[pts.length-1][1]>=start?'#3fb950':'#f85149';x.lineWidth=3;x.beginPath();pts.forEach((p,i)=>i?x.lineTo(X(i),Y(p[1])):x.moveTo(X(i),Y(p[1])));x.stroke();
x.fillStyle='#8b949e';x.font='22px sans-serif';x.fillText(f(hi),12,24);x.fillText(f(lo),12,H-4)}
const groupsHTML=s=>s.groups.map(g=>'<div class=g><small>'+g.group+'</small><b>'+g.active+'</b><span class=mut> / '+g.total+'</span><small>hit '+(g.avg_acc==null?'-':f(g.avg_acc*100,1)+'%')+' · wt '+f(g.avg_weight)+'</small></div>').join('');
const openRows=s=>s.open_trades.map(t=>[esc(t.desk),t.symbol,side(t.side),px(t.entry),px(t.stop),px(t.target),'<span class=mut>'+esc(t.reason).slice(0,60)+'</span>']);
const hourRows=s=>(s.hours||[]).slice().reverse().map(h=>[h.hour,'<span class='+cls(h.pnl)+'>'+f(h.pnl)+'</span>',esc(h.best_desk||'')]);

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
function decision(){const dd=S.decision_desk;if(!dd)return;const k=(n,l,c)=>'<div><b class="big '+(c||'')+'">'+n+'</b><span>'+l+'</span></div>';
$('ddstat').innerHTML=k(dd.requests,'proposals')+k(dd.approved,'approved','up')+k(dd.rejected,'rejected','dn')+k(dd.yes_rate==null?'-':f(dd.yes_rate*100,0)+'%','approval rate')+k((dd.session_pnl>=0?'+':'')+f(dd.session_pnl),'P/L (paper)',cls(dd.session_pnl));
$('ddr').textContent='Rejected because: '+((dd.reasons||[]).map(r=>r[0]+' ×'+r[1]).join(' · ')||'nothing rejected yet');
$('ddl').innerHTML=(dd.log||[]).map(e=>'<div><span class=mut>#'+e.cycle+'</span> '+esc(e.desk)+' · '+e.symbol+' '+(e.side>0?'LONG':'SHORT')+' → '+(e.result==='OPENED'?'<span class=up>APPROVED</span>':'<span class=dn>REJECTED: '+esc(e.result)+'</span>')+' <span class=mut>'+esc(e.reason)+'</span></div>').join('')||'<span class=mut>No proposals yet.</span>'}
function votes(sym){const v={};(S.feed||[]).filter(e=>e.symbol==sym).forEach(e=>{const g=e.agent.split('.')[0][0];v[e.kind]=(v[e.kind]||0)+e.direction});return v}
function coinOf(sym){return P&&P.coins?P.coins.find(c=>c.coin==sym):(S.pipe&&S.pipe.top||[]).find(c=>c.coin==sym)}
function matrix(){const s=S;tbl('matrix',['market','chart price','pipe price','sources','24h','regime','scouts','predictors','pipe','quant score','final','decision','open'],
s.symbols.map(sym=>{const c=coinOf(sym)||{},v=votes(sym),d=(s.decisions||[]).find(x=>x.symbol==sym)||{},r=s.regimes[sym]||{},o=s.open_trades.filter(t=>t.symbol==sym).length;
const vv=n=>n==null?'<span class=mut>0</span>':'<span class='+cls(n)+'>'+(n>0?'+':'')+n+'</span>';
return['<b>'+sym+'</b>',px(s.prices[sym]),px(c.price),c.sources||'-',pct(c.chg24),esc(r.label||'-')+(r.vol_high?' ⚡':''),vv(v.scout),vv(v.predict),vv(v.platform),f(d.quant),f(d.final),'<span class=mut>'+esc(d.result||'-')+'</span>',o]}));
$('pipevotes').innerHTML=(s.feed||[]).filter(e=>e.agent.startsWith('Y.')).map(e=>'<div><span class=mut>#'+e.cycle+'</span> <span class=pp>'+esc(e.agent)+'</span> → <b>'+e.symbol+'</b> '+side(e.direction)+' <span class=mut>('+e.conf+')</span></div>').join('')||'<span class=mut>Pipe agents vote on every 15-minute candle once the academy is done, and only on real prices.</span>'}
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
$('pstat').innerHTML=k(p.live,'live feeds (answered in last 15 min)','pp')+k(p.declared,'feeds requested')+k(p.providers_ok+' / '+p.providers,'providers answering','up')+k(p.providers_failing,'providers failing',p.providers_failing?'dn':'')+(p.warming_up?k('…','first round still loading'):'');
tbl('pcat',['category','live feeds'],Object.entries(p.by_cat).sort((a,b)=>b[1]-a[1]).map(([c,n])=>[c,'<b>'+n+'</b>']))}
if(!P)return;tbl('pprov',['provider','type','status','feeds','ms','error'],P.providers.map(r=>[esc(r.name),r.cat,r.ok==null?'<span class=mut>waiting</span>':r.ok?'<span class=up>OK</span>':'<span class=dn>FAIL</span>',r.n,r.ms,'<span class=mut>'+esc(r.err)+'</span>']));
const q=($('pfind').value||'').toLowerCase();tbl('pfeeds',['feed','type','what','value','change','age'],P.feeds.filter(x=>!q||(x.id+' '+x.label+' '+x.cat).toLowerCase().includes(q)).slice(0,800).map(x=>[esc(x.id),x.cat,'<span class=mut>'+esc(x.label).slice(0,70)+'</span>',big(x.value),pct(x.chg),(x.age>900?'<span class=dn>':'<span class=mut>')+x.age+'s</span>']))}
function crypto(){if(!P)return;tbl('coins',['coin','price (median)','exchanges','disagree','24h','funding','USD premium'],P.coins.map(c=>['<b>'+c.coin+'</b>','$'+px(c.price),c.sources,f(c.spread*100,3)+'%',pct(c.chg24),c.funding==null?'-':f(c.funding*100,4)+'%',pct(c.usd_premium,3)]));
tbl('stocks',['name','symbol','price','day'],P.world.filter(w=>w.extra.kind=='stock').map(w=>[esc(w.label),w.extra.symbol,px(w.value),pct(w.chg)]))}
function world(){if(!P)return;const wm=P.summary.world;$('wstat').innerHTML='<div><b class="big '+cls(wm.risk)+'">'+(wm.risk==null?'-':f(wm.risk*100,2)+'%')+'</b><span>average move of '+wm.n+' major indices</span></div><div><b class="big">'+(wm.vix==null?'-':f(wm.vix*100,1)+'%')+'</b><span>VIX change</span></div><div><b class="big pp">'+P.world.length+'</b><span>world feeds live</span></div><div><b class="big pp">'+P.fx.length+'</b><span>currency feeds live</span></div>';
const row=w=>[esc(w.label),'<span class=mut>'+esc(w.extra.symbol)+'</span>',px(w.value),pct(w.chg)];
tbl('widx',['market','symbol','level','day'],P.world.filter(w=>w.extra.kind=='index'||w.extra.kind=='vol').map(row));
tbl('wcom',['market','symbol','level','day'],P.world.filter(w=>['commodity','rates','fx'].includes(w.extra.kind)).map(row));
tbl('wfx',['pair','source','rate'],P.fx.map(x=>[esc(x.label),esc(x.provider),px(x.value)]));
tbl('wother',['gauge','source','value','change'],P.other.map(x=>[esc(x.label),esc(x.provider),big(x.value),pct(x.chg)]))}
function news(){const s=S;if(P){const nm=P.summary.news;$('nstat').innerHTML='<div><b class="big '+cls(nm.mood)+'">'+f(nm.mood,2)+'</b><span>mood (-1 to +1), last 6h</span></div><div><b class="big pp">'+nm.n+'</b><span>headlines, last 6h</span></div><div><b class="big">'+P.feeds.filter(x=>x.cat=='news').length+'</b><span>news feeds answering</span></div>';
$('heads').innerHTML=P.headlines.map(h=>'<div><span class=mut>'+esc(h.src)+'</span> <span class='+cls(h.s)+'>'+esc(h.title)+'</span></div>').join('')||'<span class=mut>Loading the first round of feeds...</span>'}
const m=s.macro;$('macro').innerHTML=m?esc(JSON.stringify(m).slice(0,1500)):'Macro team is off.'}
function poly(){const p=S.polybook;if(p){$('poly').textContent='bankroll $'+f(p.equity)+' ('+(p.pnl>=0?'+':'')+f(p.pnl)+') · closed '+p.closed+' · hit '+(p.hit_rate==null?'-':f(p.hit_rate*100,0)+'%')+(p.synthetic?' · SYNTHETIC markets (sim)':'');
tbl('polyt',['market','side','price','our view'],p.open.map(t=>['<span class=w>'+esc(t.q)+'</span>',t.side,f(t.price,2),f(t.fair,2)]))}
if(P)tbl('preds',['venue','question','YES chance'],P.prediction.map(x=>[esc(x.provider),'<span class=w>'+esc(x.label)+'</span>',x.value==null?'-':f(x.value*100,0)+'%']))}
function engines(){const s=S,p=s.pipe||{},dd=s.decision_desk||{},G=g=>(s.groups.find(x=>x.group==g)||{}),tot=(...gs)=>gs.reduce((a,g)=>a+(G(g).active||0),0);
const E=[['1 · SCAN',p.live||0,'live feeds in the market pipe from '+(p.providers_ok||0)+' providers, plus '+s.symbols.length+' charts the robot trades.','TradingAgents: data tools'],
['2 · ANALYSE',tot('analyst','quant'),'analyst + quant agents read the charts and vote the regime: '+Object.entries(s.regimes).map(([k,v])=>k+' '+v.label).join(', ')+'.','TradingAgents: technical analyst'],
['3 · RESEARCH',tot('macro','pipe','platform'),'macro, pipe and platform agents read news, prediction markets, funding, world markets.','TradingAgents: news + sentiment analysts'],
['4 · FLOW',tot('scout','predictor','copy'),'scouts, predictors and copy agents post buy/sell votes; '+s.feed.length+' recent votes in the brain.','TradingAgents: bull vs bear researchers'],
['5 · DECIDE',(s.decisions||[]).length,'markets scored this cycle by the weighted vote'+(s.llm.on?' and the Claude chief strategist.':' (Claude off: pure quant vote).'),'TradingAgents: trader'],
['6 · RISK',dd.rejected||0,'proposals rejected by the risk manager out of '+(dd.requests||0)+'. Drawdown '+f(s.drawdown*100,1)+'%; kill switch at 12%.','TradingAgents: risk team'],
['7 · EXECUTE',s.open_trades.length,'open paper positions across '+(s.desks||[]).length+' desks. Real-money orders: none (paper only).','TradingAgents: simulated exchange'],
['8 · LEARN',(s.lessons||[]).length,'lessons on file; improvers re-weight agents every '+10+' cycles and retire ones that don\'t beat chance.','freqtrade: hyperopt / FinRL: feedback']];
$('eng').innerHTML=E.map(e=>'<div class=card><span class=n>'+e[1]+'</span><h3>'+e[0]+'</h3><div>'+esc(e[2])+'</div><div class=mut style="margin-top:6px;font-size:11.5px">like '+e[3]+'</div></div>').join('');
$('oss').innerHTML=['<b>TradingAgents</b> (Apache-2.0): analysts → bull/bear debate → trader → risk team → manager. Ours: the same chain, but every agent is scored on real outcomes and loses its vote if it doesn\'t beat chance.',
'<b>ai-hedge-fund</b>: investor-persona agents and a portfolio manager; no execution. Ours executes paper trades and tracks profit per hour per desk.',
'<b>freqtrade / Hummingbot</b>: mature single-strategy bots with dry-run and exchange connectors. Ours borrows the dry-run-first rule and protections (daily loss limit, cool-off).',
'<b>FinRL</b>: reinforcement learning on simulated markets. Ours learns more simply: hit-rate weighting plus an exam on unseen data.',
'None of these, and not this app, has shown reliable profit. Paper results first; real money is your decision.'].map(t=>'<div>'+t+'</div>').join('')}
function academy(){const g=S.graduation;$('grad').textContent=g?g.summary:'No exam yet.';
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
                    return self._send(200, json.dumps(engine.state()).encode(), "application/json")
                if path.startswith("/api/pipe"):
                    return self._send(200, pipe_json(), "application/json")
            except Exception as e:
                return self._send(200, json.dumps({"error": str(e)[:200]}).encode(), "application/json")
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")

    srv = ThreadingHTTPServer((host, port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
