// A replay's page: /r/<code> (src/replays.js). The run played back on the stage's road (the car moving, its speed,
// pedals and gear under it), what the server's checks found, another replay to race it against (its code: the gap at
// the same place on the road), the file to download (ACR DAILY plays it in the game: REPLAY > OPEN A CODE), and its
// driver's SHARE (public once the stage no longer counts). Its link shows its driver, stage and time where it is
// posted (meta, for a public one).
import { FAVICON, logoSvg } from './logo.js';
import { langTag, t } from './i18n.js';

const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = (ms) => {
  if (ms == null) return '-';
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}.${String(ms % 1000).padStart(3, '0')}`;
};

/** meta: a public replay's row ({name, track, car, fin_ms, penalty_ms, status}) for the link's preview, else null. */
export function replayPage(code, meta = null) {
  const total = meta && meta.fin_ms != null ? meta.fin_ms + (meta.penalty_ms || 0) : null;
  const title = meta ? `${meta.name || t('A driver')} · ${meta.track} · ${total != null ? fmt(total) : meta.status.toUpperCase()}` : t('ACR DAILY replay');
  const desc = meta ? `${meta.car}. ${t('Watch the run on the stage, race it against yours.')}` : t('A run on ACR DAILY, played back on the stage.');
  const L = {
    loading: t('Loading the replay…'), gone: t('This replay is private, or no longer kept. Sign in if it is yours.'),
    play: t('PLAY'), pause: t('PAUSE'), against: t('Race it against another replay (its code)'), go: t('ADD'),
    clean: t('CHECKS CLEAN'), review: t('CHECKS WANT A LOOK'), live: t('Recorded live: its rows sent to the server as the stage ran'),
    notLive: t('Not followed by the server while driven'), signed: t('Signed by its driver\'s ACR DAILY, unchanged since'),
    km: t('km driven'), top: t('top speed'), avg: t('average'), resets: t('jumps (resets)'), off: t('off the road'),
    cps: t('checkpoints passed'), gap: t('gap'), download: t('DOWNLOAD'), copy: t('COPY LINK'), copied: t('COPIED'),
    share: t('MAKE PUBLIC'), unshare: t('MAKE PRIVATE'), ingame: t('In the game: ACR DAILY > REPLAY > OPEN A CODE:'),
    speed: t('SPEED'), pedals: t('THROTTLE / BRAKE'), noRoad: t('No road known for this stage: the run is drawn alone.'),
    views: t('views'), action: t('What it did'), finish: t('FINISH'), dnf: t('NOT FINISHED'), penalty: t('penalty'),
  };
  return `<!doctype html>
<html lang="${langTag()}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)}</title>
<meta property="og:title" content="${esc(title)}">
<meta property="og:description" content="${esc(desc)}">
<meta property="og:type" content="video.other">
<meta name="twitter:card" content="summary">
<meta name="description" content="${esc(desc)}">
<link rel="icon" href="${FAVICON}">
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700;800&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#0A0A0B;--line:#1F1F23;--line2:#2B2B31;--white:#F4F4F5;--muted:#85858E;--fg2:#A1A1AA;--acc:#E30613;--ok:#30D158;--warn:#FF9F0A;--s1:#3987e5;--s2:#d95926}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg2);font:15px/1.5 Barlow,system-ui,sans-serif}
.wrap{max-width:1200px;margin:0 auto;padding:0 16px 64px}
a{color:var(--white)}
.top{display:flex;align-items:center;justify-content:space-between;height:76px;border-bottom:1px solid var(--line);margin-bottom:24px}
.logo{display:flex;align-items:center;gap:10px;text-decoration:none}.brandmark{height:56px;width:auto}
h1{font:700 clamp(32px,5vw,52px)/.95 'Barlow Condensed',sans-serif;color:var(--white);text-transform:uppercase;margin:8px 0 0}
.lbl{font:600 11px/1.3 Barlow,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}
.head{display:flex;flex-wrap:wrap;gap:16px 40px;align-items:flex-end;padding:18px 0;border-top:2px solid var(--white);border-bottom:1px solid var(--line)}
.head>div:first-child{flex:1 1 300px}
.big{font:600 34px/1 'Barlow Condensed',sans-serif;color:var(--white);font-feature-settings:'tnum';margin-top:6px}
.chip{display:inline-block;font:700 12px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;padding:6px 10px;border-radius:2px;color:#000;margin-right:8px}
.grid{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(0,1fr);gap:32px;margin-top:22px}
@media (max-width:860px){.grid{grid-template-columns:1fr}}
canvas{width:100%;display:block;background:#0E0E10;border:1px solid var(--line)}
#map{aspect-ratio:4/3}
.bar{display:flex;gap:10px;align-items:center;margin:10px 0;flex-wrap:wrap}
button,.btn{font:700 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;background:var(--white);color:#000;border:0;padding:10px 14px;cursor:pointer;text-decoration:none;border-radius:2px}
button.ghost,.btn.ghost{background:none;color:var(--white);border:1px solid var(--line2)}
input[type=range]{flex:1;accent-color:var(--acc)}
input[type=text]{background:#111113;border:1px solid var(--line2);color:var(--white);padding:9px 10px;font:15px Barlow,sans-serif;width:150px}
.dash{display:flex;gap:22px;font:600 22px/1 'Barlow Condensed',sans-serif;color:var(--white);font-feature-settings:'tnum';flex-wrap:wrap}
.dash span{display:block}.dash .lbl{margin-bottom:4px}
.stats{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));border-top:1px solid var(--line)}
.stat{padding:10px 0;border-bottom:1px solid var(--line)}.stat .v{font:600 22px/1.1 'Barlow Condensed',sans-serif;color:var(--white)}
ul.checks{list-style:none;padding:0;margin:14px 0}ul.checks li{padding:6px 0 6px 14px;border-left:2px solid var(--line2);margin:4px 0;color:var(--white);font-size:14px}
ul.checks li.ok{border-color:var(--ok)}ul.checks li.bad{border-color:var(--warn)}
.note{color:var(--muted);font-size:13px}
code{color:var(--white);font-size:16px;letter-spacing:.05em}
</style>
</head>
<body><div class="wrap">
<div class="top"><a class="logo" href="/">${logoSvg('brandmark')}</a><a class="lbl" href="/">ACR DAILY</a></div>
<div id="app"><p>${esc(L.loading)}</p></div>
</div>
<script>
const CODE=${JSON.stringify(code)}, L=${JSON.stringify(L)};
const $=(s)=>document.querySelector(s);
const esc=(s)=>String(s==null?'':s).replace(/[&<>"']/g,(c)=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(ms)=>{if(ms==null)return'-';const n=Math.max(0,Math.round(ms)),s=Math.floor(n/1000);return Math.floor(s/60)+':'+String(s%60).padStart(2,'0')+'.'+String(n%1000).padStart(3,'0');};
async function unzip(buf){const u=new Uint8Array(buf);if(u[0]!==0x1f)return JSON.parse(new TextDecoder().decode(u));
  const r=new Response(new Blob([u]).stream().pipeThrough(new DecompressionStream('gzip')));return JSON.parse(await r.text());}
// (the admin page's key, in this tab only: a private replay opened from /admin's list)
const AK=(()=>{try{return sessionStorage.getItem('acr-admin-key')}catch(e){return null}})();
const H=AK?{Authorization:'Bearer '+AK}:{};
async function loadOne(code){
  const m=await fetch('/api/replays/'+code,{credentials:'same-origin',headers:H});if(!m.ok)return null;
  const meta=await m.json();const f=await fetch('/api/replays/'+code+'/file',{credentials:'same-origin',headers:H});if(!f.ok)return null;
  const doc=await unzip(await f.arrayBuffer());return {meta,doc,rows:doc.rows};
}
// where each row is along the road (m), for the gap at the same place
function progressOf(rows,pts){if(!pts)return null;const cum=[0];for(let i=1;i<pts.length;i++)cum.push(cum[i-1]+Math.hypot(pts[i][0]-pts[i-1][0],pts[i][1]-pts[i-1][1]));
  let at=1;return rows.map((r)=>{const x=r[1]/100,z=r[3]/100;let best=1e18,bi=at,bt=0;const scan=(lo,hi)=>{for(let i=Math.max(1,lo);i<Math.min(pts.length,hi);i++){const a=pts[i-1],b=pts[i],dx=b[0]-a[0],dz=b[1]-a[1],l2=dx*dx+dz*dz;
    const tt=l2?Math.max(0,Math.min(1,((x-a[0])*dx+(z-a[1])*dz)/l2)):0,d=Math.hypot(x-a[0]-tt*dx,z-a[1]-tt*dz);if(d<best){best=d;bi=i;bt=tt;}}};
    scan(at-8,at+60);if(best>40)scan(1,pts.length);at=bi;return cum[bi-1]+bt*(cum[bi]-cum[bi-1]);});}
function rowAt(rows,ms){let lo=0,hi=rows.length-1;if(ms<=rows[0][0])return rows[0];if(ms>=rows[hi][0])return rows[hi];
  while(hi-lo>1){const m=(lo+hi)>>1;if(rows[m][0]<=ms)lo=m;else hi=m;}const a=rows[lo],b=rows[hi],u=(ms-a[0])/(b[0]-a[0]);return a.map((v,i)=>i===0?ms:v+(b[i]-v)*u);}
function idxAt(rows,ms){let lo=0,hi=rows.length-1;while(hi-lo>1){const m=(lo+hi)>>1;if(rows[m][0]<=ms)lo=m;else hi=m;}return lo;}
function timeAtProgress(rows,prog,p){let lo=0,hi=prog.length-1;if(p<=prog[0])return rows[0][0];
  for(let i=1;i<prog.length;i++){if(prog[i]>=p){const u=(p-prog[i-1])/Math.max(1e-6,prog[i]-prog[i-1]);return rows[i-1][0]+(rows[i][0]-rows[i-1][0])*Math.max(0,Math.min(1,u));}}return null;}
(async()=>{
  const A=await loadOne(CODE);
  if(!A){$('#app').innerHTML='<p>'+esc(L.gone)+'</p>';return;}
  const m=A.meta,h=A.doc.head||{};
  let pts=null;try{const r=await fetch('/api/route?track='+encodeURIComponent(m.track));if(r.ok)pts=(await r.json()).route;}catch(e){}
  A.prog=progressOf(A.rows,pts);
  const total=m.finMs!=null?m.finMs+(m.penaltyMs||0):null, rep=m.report||{}, road=rep.road||null;
  const chips=(m.verdict==='clean'?'<span class="chip" style="background:var(--ok)">'+esc(L.clean)+'</span>':'<span class="chip" style="background:var(--warn)">'+esc(L.review)+'</span>');
  const checks=[[rep.live,rep.live?L.live:L.notLive],[rep.signed,L.signed]].map(([ok,s])=>'<li class="'+(ok?'ok':'bad')+'">'+esc(s)+'</li>').join('')
    +(rep.notes||[]).map((n)=>'<li class="bad">'+esc(n)+'</li>').join('');
  const ev=m.event?'<a href="/e/'+m.event.id+'">'+esc(m.event.name)+'</a> · SS'+m.event.stage+' · ':'';
  $('#app').innerHTML='<div class="head"><div><div class="lbl">'+ev+esc(h.kind==='daily'?('DAILY '+(h.ref||'')):(h.title||h.kind||''))+'</div><h1>'+esc(m.track)+'</h1>'
    +'<div class="note">'+(m.name?'<a href="/d/'+esc(m.steamId)+'">'+esc(m.name)+'</a> · ':'')+esc(m.car)+'</div></div>'
    +'<div><div class="lbl">'+esc(m.finMs!=null?L.finish:L.dnf)+'</div><div class="big">'+fmt(total)+'</div>'+(m.penaltyMs?'<div class="note">+'+(m.penaltyMs/1000).toFixed(1)+' s '+esc(L.penalty)+'</div>':'')+'</div>'
    +'<div>'+chips+'</div></div>'
    +'<div class="grid"><div><canvas id="map" width="1200" height="900"></canvas>'
    +'<div class="bar"><button id="play">'+esc(L.play)+'</button><button class="ghost" id="rate">1×</button><input type="range" id="scrub" min="0" max="1000" value="0"><span id="clock" class="dash">0:00.000</span></div>'
    +'<div class="dash" id="dash"></div>'
    +'<canvas id="chart" width="1200" height="260" style="margin-top:12px"></canvas>'
    +'<div class="bar"><input type="text" id="other" placeholder="code" maxlength="10"><button class="ghost" id="add">'+esc(L.go)+'</button><span class="note">'+esc(L.against)+'</span><span id="gap" class="dash"></span></div></div>'
    +'<div><div class="stats" id="stats"></div><ul class="checks">'+checks+'</ul>'+(m.action?'<p class="note">'+esc(L.action)+': <b style="color:var(--white)">'+esc(m.action)+'</b></p>':'')
    +'<div class="bar"><a class="btn" href="/api/replays/'+CODE+'/file">'+esc(L.download)+'</a><button class="ghost" id="copy">'+esc(L.copy)+'</button>'+(m.mine?'<button class="ghost" id="share">'+esc(m.public?L.unshare:L.share)+'</button>':'')+'</div>'
    +'<p class="note">'+esc(L.ingame)+' <code>'+CODE+'</code></p><p class="note">'+(m.views||0)+' '+esc(L.views)+'</p>'+(pts?'':'<p class="note">'+esc(L.noRoad)+'</p>')+'</div></div>';
  const st=[[L.km,road?road.km.toFixed(2):'-'],[L.top,road?road.topKmh+' km/h':'-'],[L.avg,(road&&m.finMs)?(road.km/(m.finMs/3600000)).toFixed(1)+' km/h':'-'],
    [L.resets,road?road.jumps:'-'],[L.off,road?(road.offMs/1000).toFixed(1)+' s':'-'],[L.cps,road?Math.round(road.checkpoints*100)+' %':'-']];
  $('#stats').innerHTML=st.map(([k,v])=>'<div class="stat"><div class="lbl">'+esc(k)+'</div><div class="v">'+esc(v)+'</div></div>').join('');
  $('#copy').onclick=()=>{navigator.clipboard.writeText(location.href).then(()=>{$('#copy').textContent=L.copied;});};
  if($('#share'))$('#share').onclick=async()=>{const r=await fetch('/api/replays/'+CODE+'/share',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({public:!m.public})});
    const j=await r.json();if(r.ok){m.public=j.public;$('#share').textContent=m.public?L.unshare:L.share;}else alert(j.error);};
  // ---- the map
  const map=$('#map'),cx=map.getContext('2d'),W=map.width,H=map.height;
  const all=(pts||[]).concat(A.rows.map((r)=>[r[1]/100,r[3]/100]));
  let x0=Infinity,x1=-Infinity,z0=Infinity,z1=-Infinity;for(const[x,z]of all){x0=Math.min(x0,x);x1=Math.max(x1,x);z0=Math.min(z0,z);z1=Math.max(z1,z);}
  const sc=Math.min((W-80)/Math.max(1,x1-x0),(H-80)/Math.max(1,z1-z0)),ox=(W-(x1-x0)*sc)/2,oz=(H-(z1-z0)*sc)/2;
  const P=(x,z)=>[ox+(x-x0)*sc,H-(oz+(z-z0)*sc)];
  const others=[];
  const speedCol=(k)=>{const u=Math.max(0,Math.min(1,k/180));return 'hsl('+(220-220*u)+',80%,55%)';};
  function drawBase(){cx.fillStyle='#0E0E10';cx.fillRect(0,0,W,H);
    if(pts){cx.strokeStyle='#2B2B31';cx.lineWidth=14;cx.lineCap='round';cx.lineJoin='round';cx.beginPath();pts.forEach(([x,z],i)=>{const[p,q]=P(x,z);i?cx.lineTo(p,q):cx.moveTo(p,q);});cx.stroke();
      const[a,b]=P(pts[0][0],pts[0][1]),[c,d]=P(pts[pts.length-1][0],pts[pts.length-1][1]);cx.fillStyle='#30D158';cx.fillRect(a-6,b-6,12,12);cx.fillStyle='#F4F4F5';cx.fillRect(c-6,d-6,12,12);}
    cx.lineWidth=3;for(let i=1;i<A.rows.length;i++){const a=A.rows[i-1],b=A.rows[i];if(Math.hypot(b[1]-a[1],b[3]-a[3])>6000)continue;
      cx.strokeStyle=speedCol(b[7]/10);cx.beginPath();cx.moveTo(...P(a[1]/100,a[3]/100));cx.lineTo(...P(b[1]/100,b[3]/100));cx.stroke();}
    if(road)for(const c of road.cuts||[]){const r=rowAt(A.rows,c.ms);const[p,q]=P(r[1]/100,r[3]/100);cx.strokeStyle='#FF9F0A';cx.lineWidth=3;cx.beginPath();cx.arc(p,q,22,0,7);cx.stroke();}}
  drawBase();const base=cx.getImageData(0,0,W,H);
  function car(rows,ms,col){const r=rowAt(rows,ms),b=rowAt(rows,ms-300);const[p,q]=P(r[1]/100,r[3]/100),[p0,q0]=P(b[1]/100,b[3]/100);
    const a=Math.atan2(q-q0,p-p0);cx.save();cx.translate(p,q);cx.rotate(a);cx.fillStyle=col;cx.strokeStyle='#000';cx.lineWidth=2;cx.beginPath();cx.moveTo(14,0);cx.lineTo(-10,-9);cx.lineTo(-10,9);cx.closePath();cx.fill();cx.stroke();cx.restore();}
  // ---- the chart: speed, and throttle / brake under it
  const ch=$('#chart'),gx=ch.getContext('2d'),CW=ch.width,CH=ch.height,T0=A.rows[0][0],T1=A.rows[A.rows.length-1][0];
  const top=Math.max(60,...A.rows.map((r)=>r[7]/10));
  function drawChart(ms){gx.fillStyle='#0E0E10';gx.fillRect(0,0,CW,CH);const X=(t)=>((t-T0)/(T1-T0))*CW;
    gx.fillStyle='#85858E';gx.font='13px Barlow';gx.fillText(L.speed,8,16);gx.fillText(L.pedals,8,CH-56);
    gx.strokeStyle='#3987e5';gx.lineWidth=2;gx.beginPath();A.rows.forEach((r,i)=>{const y=(CH-80)-(r[7]/10/top)*(CH-110);i?gx.lineTo(X(r[0]),y):gx.moveTo(X(r[0]),y);});gx.stroke();
    for(const o of others){gx.strokeStyle='#d95926';gx.beginPath();o.rows.forEach((r,i)=>{const y=(CH-80)-(r[7]/10/top)*(CH-110);i?gx.lineTo(X(r[0]),y):gx.moveTo(X(r[0]),y);});gx.stroke();}
    for(const r of A.rows){const x=X(r[0]);gx.fillStyle='rgba(48,209,88,.8)';gx.fillRect(x,CH-40-r[10]/1000*30,2,r[10]/1000*30);gx.fillStyle='rgba(227,6,19,.9)';gx.fillRect(x,CH-40,2,r[11]/1000*30);}
    gx.strokeStyle='#F4F4F5';gx.lineWidth=1;gx.beginPath();gx.moveTo(X(ms),0);gx.lineTo(X(ms),CH);gx.stroke();}
  // ---- playback
  let ms=T0,playing=false,rate=1,last=null;const RATES=[1,2,4,8,16,0.5];
  function frame(){cx.putImageData(base,0,0);for(const o of others){const om=o.rows[0][0]+(ms-T0);if(om<=o.rows[o.rows.length-1][0])car(o.rows,om,'#d95926');}car(A.rows,ms,'#F4F4F5');
    drawChart(ms);const r=rowAt(A.rows,ms);$('#clock').textContent=fmt(ms);$('#scrub').value=Math.round((ms-T0)/(T1-T0)*1000);
    $('#dash').innerHTML='<span><span class="lbl">km/h</span>'+Math.round(r[7]/10)+'</span><span><span class="lbl">gear</span>'+(Math.round(r[8])<=0?'R':Math.round(r[8])===1?'N':Math.round(r[8])-1)+'</span><span><span class="lbl">rpm</span>'+Math.round(r[9])+'</span>';
    if(others.length&&A.prog&&others[0].prog){const i=idxAt(A.rows,ms),p=A.prog[i];const t2=timeAtProgress(others[0].rows,others[0].prog,p);
      $('#gap').textContent=t2==null?'':(L.gap+' '+((A.rows[i][0]-T0)-(t2-others[0].rows[0][0])>=0?'+':'-')+(Math.abs((A.rows[i][0]-T0)-(t2-others[0].rows[0][0]))/1000).toFixed(2)+' s');}}
  function loop(ts){if(playing){if(last!=null)ms=Math.min(T1,ms+(ts-last)*rate);last=ts;if(ms>=T1)playing=false,$('#play').textContent=L.play;}frame();requestAnimationFrame(loop);}
  $('#play').onclick=()=>{if(ms>=T1)ms=T0;playing=!playing;last=null;$('#play').textContent=playing?L.pause:L.play;};
  $('#rate').onclick=()=>{rate=RATES[(RATES.indexOf(rate)+1)%RATES.length];$('#rate').textContent=rate+'×';};
  $('#scrub').oninput=(e)=>{ms=T0+(T1-T0)*e.target.value/1000;};
  map.onclick=(e)=>{const b=map.getBoundingClientRect(),x=(e.clientX-b.left)*W/b.width,y=(e.clientY-b.top)*H/b.height;let best=1e18,bi=0;
    A.rows.forEach((r,i)=>{const[p,q]=P(r[1]/100,r[3]/100),d=(p-x)**2+(q-y)**2;if(d<best){best=d;bi=i;}});ms=A.rows[bi][0];};
  $('#add').onclick=async()=>{const c=$('#other').value.trim().toLowerCase();if(!/^[a-z0-9]{10}$/.test(c))return;const B=await loadOne(c);if(!B){alert(L.gone);return;}
    B.prog=progressOf(B.rows,pts);others.splice(0,others.length,B);};
  requestAnimationFrame(loop);
})();
</script>
</body></html>`;
}
