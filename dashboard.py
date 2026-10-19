"""Live dashboard: a tiny web server (standard library only). Open http://localhost:8765"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Swarm Trader</title>
<style>
:root{--bg:#0d1117;--card:#161b22;--line:#262d38;--tx:#e6edf3;--mut:#8b949e;--up:#3fb950;--dn:#f85149;--ac:#58a6ff;--warn:#d29922}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.45 system-ui,Segoe UI,sans-serif}
header{display:flex;flex-wrap:wrap;gap:18px;align-items:center;padding:14px 20px;border-bottom:1px solid var(--line)}
h1{font-size:17px;margin:0 10px 0 0}.kpi b{display:block;font-size:20px}.kpi span{color:var(--mut);font-size:12px}
.chip{padding:3px 9px;border-radius:20px;font-size:12px;border:1px solid var(--line);color:var(--mut)}
.chip.on{color:var(--up);border-color:var(--up)}.chip.bad{color:var(--dn);border-color:var(--dn)}
main{display:grid;grid-template-columns:repeat(12,1fr);gap:14px;padding:16px 20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;overflow:auto}
.card h2{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--mut);margin:0 0 8px}
.c12{grid-column:span 12}.c8{grid-column:span 8}.c6{grid-column:span 6}.c4{grid-column:span 4}
@media(max-width:900px){.c8,.c6,.c4{grid-column:span 12}}
table{width:100%;border-collapse:collapse;font-size:12.5px}th{color:var(--mut);font-weight:500;text-align:left}
td,th{padding:3px 6px;border-bottom:1px solid var(--line);white-space:nowrap}.up{color:var(--up)}.dn{color:var(--dn)}.mut{color:var(--mut)}
.groups{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.g{border:1px solid var(--line);border-radius:8px;padding:8px 10px}.g b{font-size:18px}.g small{color:var(--mut);display:block}
.feed div,.less div{padding:3px 0;border-bottom:1px solid var(--line);font-size:12.5px}
canvas{width:100%;height:220px;display:block}
button{background:#21262d;color:var(--tx);border:1px solid var(--line);border-radius:8px;padding:9px 14px;font-size:14px;margin:2px}input{background:var(--bg);color:var(--tx);border:1px solid var(--line);border-radius:8px;padding:9px;width:70%;font-size:14px}
@media(max-width:600px){main{padding:10px}header{padding:10px}}
</style></head><body>
<header><h1>Swarm Trader</h1>
<div class="kpi"><b id="eq">-</b><span>equity (paper)</span></div>
<div class="kpi"><b id="pnl">-</b><span>profit / loss</span></div>
<div class="kpi"><b id="dd">-</b><span>drawdown</span></div>
<div class="kpi"><b id="tr">-</b><span>closed trades / win rate</span></div>
<div class="kpi"><b id="cy">-</b><span id="mode">cycle</span></div>
<span id="llm" class="chip">Claude</span><span id="risk" class="chip">risk</span><span class="chip">PAPER ONLY</span></header>
<main>
<div class="card c8"><h2>Equity curve</h2><canvas id="ch" width="900" height="220"></canvas></div>
<div class="card c4"><h2>Chief strategist (Claude) &amp; decisions this cycle</h2><div id="note" class="mut" style="margin-bottom:6px"></div><div id="dec"></div><h2 style="margin-top:10px">Regimes</h2><div id="reg"></div><h2 style="margin-top:10px">Settings (self-tuned)</h2><div id="set" class="mut"></div></div>
<div class="card c12"><h2>The 80 agents, six groups, one brain</h2><div class="groups" id="groups"></div></div>
<div class="card c6"><h2>Most trusted agents (voting weight)</h2><table id="top"></table></div>
<div class="card c6"><h2>Least trusted agents</h2><table id="bot"></table></div>
<div class="card c6"><h2>Open positions</h2><table id="open"></table><h2 style="margin-top:12px">Recent closed trades</h2><table id="closed"></table></div>
<div class="card c6"><h2>Shared brain: live signal feed</h2><div class="feed" id="feed"></div></div>
<div class="card c6"><h2>Improver lessons</h2><div class="less" id="less"></div></div>
<div class="card c6"><h2>Copy-trading targets (skill vs luck)</h2><table id="trd"></table></div>
<div class="card c12" id="ctl"><h2>Owner controls</h2>
<button onclick="ctl('pause')">Pause trading</button> <button onclick="ctl('resume')">Resume</button>
<button onclick="if(confirm('Close ALL positions and pause?'))ctl('flatten')">Flatten all</button>
<button onclick="if(confirm('Clear the kill switch?'))ctl('reset_halt')">Clear kill switch</button>
<span id="ctlmsg" class="mut"></span></div>
<div class="card c12"><h2>General Manager (talk to the AI running the whole operation)</h2>
<div style="margin-bottom:8px"><button id="mic" onclick="listen()" style="font-size:18px">🎤 Speak</button> <button onclick="brief()">Daily briefing</button>
<label class="mut"><input type="checkbox" id="spk" checked style="width:auto"> read replies aloud</label> <span id="micmsg" class="mut"></span></div>
<div id="chat" class="mut" style="max-height:260px;overflow:auto"></div>
<input id="q" placeholder="e.g. why did we lose on ETH today?" onkeydown="if(event.key=='Enter')ask()"><button onclick="ask()">Ask</button></div>
<div class="card c12"><h2>Organisation: teams linked to one brain, run by the General Manager</h2><table id="org"></table></div>
<div class="card c12"><h2>Education: graduation report</h2><div id="grad" class="mut"></div></div>
<div class="card c8"><h2>Trading desks: ranked by profit per hour (24h)</h2><table id="desks"></table></div>
<div class="card c4"><h2>Profit each hour</h2><table id="hours"></table></div>
<div class="card c6"><h2>Polymarket prediction desk (paper money)</h2><div id="poly" class="mut"></div><table id="polyt"></table></div>
<div class="card c6"><h2>Broker mirrors (demo accounts only)</h2><table id="brk"></table></div>
<div class="card c12"><h2>Development team: post-mortem and proposals (need your approval)</h2><div id="dev" class="less"></div></div>
<div class="card c12"><h2>Decision desk: desks propose, the risk manager approves or rejects (paper fills)</h2>
<div id="dd" style="display:flex;gap:18px;flex-wrap:wrap;margin-bottom:8px"></div>
<div class="mut" id="ddr" style="margin-bottom:6px"></div><div class="less" id="ddl"></div></div>
<div class="card c12"><h2>Desk log</h2><div class="less" id="dlog"></div></div>
</main>
<script>
const $=id=>document.getElementById(id),f=(n,d=2)=>n==null?'-':Number(n).toFixed(d);
const cls=v=>v>0?'up':v<0?'dn':'mut',side=s=>s>0?'<span class=up>LONG</span>':'<span class=dn>SHORT</span>';
function tbl(el,head,rows){$(el).innerHTML='<tr>'+head.map(h=>'<th>'+h+'</th>').join('')+'</tr>'+rows.map(r=>'<tr>'+r.map(c=>'<td>'+c+'</td>').join('')+'</tr>').join('')}
function chart(pts,start){const c=$('ch'),x=c.getContext('2d');c.width=c.clientWidth*2;c.height=440;x.clearRect(0,0,c.width,c.height);if(pts.length<2)return;
const ys=pts.map(p=>p[1]).concat([start]),lo=Math.min(...ys),hi=Math.max(...ys),pad=(hi-lo)*.1||1,W=c.width,H=c.height;
const X=i=>i/(pts.length-1)*(W-20)+10,Y=v=>H-20-(v-lo+pad)/(hi-lo+2*pad)*(H-40);
x.strokeStyle='#262d38';x.lineWidth=1;x.setLineDash([8,8]);x.beginPath();x.moveTo(0,Y(start));x.lineTo(W,Y(start));x.stroke();x.setLineDash([]);
x.strokeStyle=pts[pts.length-1][1]>=start?'#3fb950':'#f85149';x.lineWidth=3;x.beginPath();pts.forEach((p,i)=>i?x.lineTo(X(i),Y(p[1])):x.moveTo(X(i),Y(p[1])));x.stroke();
x.fillStyle='#8b949e';x.font='22px sans-serif';x.fillText(f(hi),12,24);x.fillText(f(lo),12,H-4)}
async function tick(){try{const s=await (await fetch('/api/state'+location.search)).json();
$('eq').textContent='$'+f(s.equity);$('pnl').innerHTML='<span class='+cls(s.pnl)+'>'+(s.pnl>=0?'+':'')+f(s.pnl)+'</span>';
$('dd').textContent=f(s.drawdown*100,1)+'%';$('tr').textContent=s.totals.trades+' / '+(s.totals.win_rate==null?'-':f(s.totals.win_rate*100,0)+'%');
$('cy').textContent=s.cycle;$('mode').textContent='cycle · '+s.mode;
const l=$('llm');l.textContent=s.llm.on?'Claude ON · '+s.llm.calls+' calls'+(s.llm.errors?' · '+s.llm.errors+' errors':''):'Claude OFF (no API key)';l.className='chip '+(s.llm.on?'on':'');
const r=$('risk');r.textContent=s.halted?'KILL SWITCH: '+s.halt_reason:s.day_blocked?'daily limit reached':'risk manager OK';r.className='chip '+(s.halted||s.day_blocked?'bad':'on');
chart(s.equity_curve,s.start);
$('note').textContent=s.note||(s.llm.on?'(waiting for a strong enough signal)':'Claude is off: decisions are pure quant votes.');
$('dec').innerHTML=s.decisions.map(d=>'<div><b>'+d.symbol+'</b> quant '+f(d.quant,2)+' → '+f(d.final,2)+(d.claude?' · Claude '+d.claude:'')+' · <span class=mut>'+d.result+'</span></div>').join('');
$('reg').innerHTML=Object.entries(s.regimes).map(([k,v])=>'<span class=chip>'+k+': '+v.label+(v.vol_high?' · volatile':'')+'</span> ').join('');
$('set').textContent=Object.entries(s.settings).map(([k,v])=>k+' = '+v).join('  ·  ');
$('groups').innerHTML=s.groups.map(g=>'<div class=g><small>'+g.group+'s</small><b>'+g.active+'</b><span class=mut> / '+g.total+'</span><small>hit rate '+(g.avg_acc==null?'-':f(g.avg_acc*100,1)+'%')+' · wt '+f(g.avg_weight)+'</small></div>').join('');
const ar=a=>[a.name,a.grp,f(a.acc*100,1)+'%',a.n,f(a.weight)];
tbl('top',['agent','group','hit','calls','weight'],s.top_agents.map(ar));tbl('bot',['agent','group','hit','calls','weight'],s.bottom_agents.map(ar));
tbl('open',['sym','side','entry','stop','target'],s.open_trades.map(t=>[t.symbol,side(t.side),f(t.entry,2),f(t.stop,2),f(t.target,2)]));
tbl('closed',['#','sym','side','P/L','regime'],s.closed_trades.map(t=>[t.id,t.symbol,side(t.side),'<span class='+cls(t.pnl)+'>'+f(t.pnl)+'</span>',t.regime]));
$('feed').innerHTML=s.feed.map(e=>'<div><span class=mut>#'+e.cycle+'</span> '+e.agent+' → <b>'+e.symbol+'</b> '+side(e.direction)+' <span class=mut>('+e.conf+')</span></div>').join('');
$('less').innerHTML=s.lessons.map(e=>'<div><span class=mut>#'+e.cycle+' '+e.author+'</span> '+e.text+'</div>').join('')||'<span class=mut>No lessons yet; improvers review every 10 cycles.</span>';
extra(s);tbl('trd',['trader','trades','win','mean P/L','conservative skill'],s.traders.map(t=>[t.trader,t.n,f(t.wr*100,0)+'%',f(t.mean*100,2)+'%',f(t.wilson*100,0)+'%']));
}catch(e){}}

const Q=location.search;
async function ctl(a){const r=await fetch('/api/control'+Q,{method:'POST',body:JSON.stringify({action:a})});$('ctlmsg').textContent=(await r.json()).message;tick()}
async function ask(t){const q=(t||$('q').value).trim();if(!q)return;$('q').value='';$('chat').innerHTML+='<div><b>You:</b> '+q.replace(/</g,'&lt;')+'</div>';
const r=await fetch('/api/ask'+Q,{method:'POST',body:JSON.stringify({question:q})});const a=(await r.json()).answer||'';say(a);$('chat').innerHTML+='<div><b>Manager:</b> '+a.replace(/</g,'&lt;')+'</div>';$('chat').scrollTop=1e9}
async function brief(){$('chat').innerHTML+='<div class=mut>Asking for the daily briefing...</div>';const r=await fetch('/api/briefing'+Q,{method:'POST',body:'{}'});const a=(await r.json()).answer||'';say(a);$('chat').innerHTML+='<div><b>Manager:</b> '+a.replace(/</g,'&lt;')+'</div>'}
function say(t){if(!$('spk').checked||!window.speechSynthesis||!t)return;speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(t);u.lang='en-AU';speechSynthesis.speak(u)}
function listen(){const R=window.SpeechRecognition||window.webkitSpeechRecognition;if(!R){$('micmsg').textContent='Voice input needs Chrome or Safari (and https when not on localhost).';return}
speechSynthesis&&speechSynthesis.cancel();const r=new R();r.lang='en-AU';r.interimResults=false;$('micmsg').textContent='listening...';
r.onresult=e=>{const t=e.results[0][0].transcript;$('micmsg').textContent='heard: '+t;$('chat').innerHTML+='<div><b>You (voice):</b> '+t.replace(/</g,'&lt;')+'</div>';ask(t)};
r.onerror=e=>{$('micmsg').textContent='mic error: '+e.error};r.onend=()=>{if($('micmsg').textContent=='listening...')$('micmsg').textContent=''};r.start()}
function extra(s){
tbl('org',['team','agents','job'],(s.org||[]).map(o=>[o.team,o.agents,o.job]));
$('ctlmsg').textContent=(s.paused?' PAUSED · ':' ')+'session now: '+((s.session||{}).now||'-').toUpperCase()+' (Asia 00-07, London 07-13, NY 13-21 UTC)';
const g=s.graduation;$('grad').textContent=g?g.summary+(g.techniques&&g.techniques.length?' Techniques on the exam (hit rate): '+g.techniques.map(t=>t.technique+' '+f(t.hit*100,0)+'%').join(', ')+'.':''):(s.phase==='live'?'':'No exam taken yet. Start with --academy.');
tbl('desks',['desk','style','share','open','trades 24h','win','P/L 24h','per hour','status'],(s.desks||[]).map(r=>[r.desk,r.style,f((r.share||0)*100,1)+'%',r.open,r.n,r.win==null?'-':f(r.win*100,0)+'%','<span class='+cls(r.pnl24)+'>'+f(r.pnl24)+'</span>','<span class='+cls(r.pph)+'>'+f(r.pph)+'</span>',r.paused?'cooling off':'trading']));
tbl('hours',['hr','P/L','best desk'],(s.hours||[]).slice().reverse().map(h=>[h.hour,'<span class='+cls(h.pnl)+'>'+f(h.pnl)+'</span>',h.best_desk||'']));
const p=s.polybook;if(p){$('poly').textContent='bankroll $'+f(p.equity)+' ('+(p.pnl>=0?'+':'')+f(p.pnl)+') · closed '+p.closed+' · hit '+(p.hit_rate==null?'-':f(p.hit_rate*100,0)+'%')+(p.synthetic?' · SYNTHETIC markets (sim)':'');
tbl('polyt',['market','side','price','our view'],p.open.map(t=>[t.q,t.side,f(t.price,2),f(t.fair,2)]))}
tbl('brk',['broker','ready','sent','failed','last'],(s.brokers||[]).map(b=>[b.name,b.ready?'<span class=up>yes</span>':'<span class=mut>no</span>',b.sent,b.failed,b.last]));
const dv=s.dev||{};$('dev').innerHTML=((dv.findings?'<div><b>Latest post-mortem:</b> '+dv.findings.items.join('; ')+'</div>':'')+(dv.proposals||[]).map(p=>'<div><b>'+p.title+'</b> — '+p.change+' <span class=mut>Test: '+p.test+' ['+p.status+']</span></div>').join(''))||'<span class=mut>Nothing yet.</span>';
const dd=s.decision_desk;if(dd){const k=(n,l,c)=>'<div><b class="'+(c||'')+'" style="font-size:20px">'+n+'</b><br><span class=mut>'+l+'</span></div>';
$('dd').innerHTML=k(dd.requests,'proposals')+k(dd.approved,'approved','up')+k(dd.rejected,'rejected','dn')+k(dd.yes_rate==null?'-':f(dd.yes_rate*100,0)+'%','approval rate')+k((dd.session_pnl>=0?'+':'')+f(dd.session_pnl),'session P/L (paper)',cls(dd.session_pnl));
$('ddr').textContent='Rejected because: '+((dd.reasons||[]).map(r=>r[0]+' ×'+r[1]).join(' · ')||'nothing rejected yet');
$('ddl').innerHTML=(dd.log||[]).map(e=>'<div><span class=mut>#'+e.cycle+'</span> '+e.desk+' · '+e.symbol+' '+(e.side>0?'LONG':'SHORT')+' → '+(e.result==='OPENED'?'<span class=up>APPROVED</span>':'<span class=dn>REJECTED: '+e.result+'</span>')+' <span class=mut>'+e.reason+'</span></div>').join('')||'<span class=mut>No proposals yet.</span>'}
$('dlog').innerHTML=(s.desk_log||[]).map(e=>'<div>'+(typeof e==='string'?e:'<span class=mut>#'+e.cycle+'</span> '+e.desk+' '+e.symbol+' '+(e.side>0?'LONG':'SHORT')+' · '+e.result)+'</div>').join('')}
tick();setInterval(tick,2000);
</script></body></html>"""


def serve(engine, port=8765, host="127.0.0.1", token=None):
    """token: if set, every request must carry ?token=<token> (use this whenever host is not localhost)."""
    from urllib.parse import parse_qs, urlparse

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _auth(self):
            from urllib.parse import parse_qs, urlparse
            if not token:
                return True
            h = self.headers.get("Authorization", "")
            return parse_qs(urlparse(self.path).query).get("token") == [token] or h == "Bearer " + token

        def do_POST(self):
            if not self._auth():
                self.send_response(401)
                self.end_headers()
                return
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
            body = json.dumps(out).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self._auth():
                self.send_response(401)
                self.end_headers()
                self.wfile.write(b"unauthorized: open the page with ?token=YOUR_TOKEN")
                return
            if self.path.startswith("/api/state"):
                try:
                    body, ctype = json.dumps(engine.state()).encode(), "application/json"
                except Exception as e:
                    body, ctype = json.dumps({"error": str(e)}).encode(), "application/json"
            else:
                body, ctype = PAGE.encode(), "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    srv = ThreadingHTTPServer((host, port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
