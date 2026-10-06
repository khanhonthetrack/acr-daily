// /week - the weekly hall of fame: points from all 14 stages of the week (Mon-Sun, SS1 + SS2 each day).

import { FAVICON, logoSvg } from './logo.js';

export function weekPage() {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Weekly Hall of Fame</title>
<link rel="icon" href="${FAVICON}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#0A0A0B;--line:#1F1F23;--line2:#2B2B31;--fg:#F4F4F5;--fg2:#A1A1AA;--fg3:#6B6B74;--acc:#FFD100;--bad:#FF453A}
*{box-sizing:border-box;margin:0}
html{background:var(--bg)}
body{color:var(--fg);font:15px/1.5 Barlow,system-ui,sans-serif;-webkit-font-smoothing:antialiased}
a{color:inherit}
.wrap{max-width:1200px;margin:0 auto;padding:0 24px 64px}
header{border-bottom:1px solid var(--line)}
header .wrap{display:flex;align-items:center;justify-content:space-between;height:76px;padding-bottom:0}
.brand{display:flex;align-items:center;gap:10px;font:700 20px/1 'Barlow Condensed',sans-serif;letter-spacing:.06em;text-decoration:none}
.brandmark{display:block;height:60px;width:auto}
.back{font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;text-transform:uppercase;text-decoration:none;color:var(--fg2)}
.back:hover{color:var(--fg)}
.top{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-top:28px;padding-top:20px;border-top:2px solid var(--fg)}
.kick{font:700 15px/1 'Barlow Condensed',sans-serif;letter-spacing:.08em;color:var(--acc)}
h1{font:700 clamp(40px,6vw,72px)/.95 'Barlow Condensed',sans-serif;text-transform:uppercase;margin-top:12px}
.nav{display:flex;align-items:center;gap:6px}
.nav button{background:none;border:0;color:var(--fg2);font:500 22px/1 Barlow,sans-serif;width:34px;height:34px;cursor:pointer}
.nav button:hover:not(:disabled){color:var(--fg)}
.nav button:disabled{color:var(--line2);cursor:default}
#range{font:600 14px/1 'Barlow Condensed',sans-serif;letter-spacing:.1em;text-transform:uppercase;min-width:150px;text-align:center}
.note{color:var(--fg2);font-size:14px;margin:16px 0 26px}
.tablewrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-feature-settings:'tnum'}
th{font:600 11px/1 Barlow,sans-serif;letter-spacing:.12em;text-transform:uppercase;color:var(--fg3);padding:8px 0;white-space:nowrap}
th.day{text-align:center;border-bottom:1px solid var(--line2);padding-bottom:8px}
th.day.today{color:var(--acc)}
th.ss{text-align:center;padding:8px 0 10px;border-bottom:1px solid var(--line2)}
th.ss a{text-decoration:none}
th.ss a:hover{color:var(--fg)}
th.l{text-align:left}
th.r{text-align:right}
td{padding:11px 0;border-bottom:1px solid var(--line);white-space:nowrap}
td.pos{width:44px;font:600 18px/1 'Barlow Condensed',sans-serif;color:var(--fg2)}
tr.p1 td.pos{color:var(--acc)}
td.drv{font-weight:500;padding-right:16px;min-width:150px}
td.c{text-align:center;width:46px;font:600 15px/1 'Barlow Condensed',sans-serif;color:var(--fg)}
td.c a{text-decoration:none;display:block}
td.c.win{color:var(--acc)}
td.c.none{color:var(--line2);font-weight:500}
td.c.dnf{color:var(--bad);font-size:12px;letter-spacing:.06em}
td.c.future{color:transparent}
td.c.daystart,th.daystart{border-left:1px solid var(--line)}
td.tot{text-align:right;font:700 22px/1 'Barlow Condensed',sans-serif;padding-left:18px;width:70px}
td.cnt{text-align:right;color:var(--fg3);font-size:13px;padding-left:14px;width:52px}
.flagimg{width:18px;height:12px;margin-right:8px;vertical-align:-1px;object-fit:cover;box-shadow:0 0 0 1px rgba(255,255,255,.12)}
.empty{color:var(--fg3);padding:22px 0;border-bottom:1px solid var(--line)}
.legend{display:flex;flex-wrap:wrap;gap:6px 22px;color:var(--fg3);font-size:13px;margin-top:18px}
.legend b{color:var(--fg2);font-weight:500}
.tip{position:fixed;pointer-events:none;background:#111113;border:1px solid var(--line2);padding:7px 10px;font-size:13px;display:none;z-index:5;white-space:nowrap}
@media (max-width:760px){.wrap{padding:0 16px 48px}}
</style>
</head>
<body>
<header><div class="wrap"><a class="brand" href="/">${logoSvg()}</a><a class="back" href="/">‹ Today's stages</a></div></header>
<main class="wrap">
  <div class="top">
    <div><div class="kick" id="kick">WEEK</div><h1>Hall of Fame</h1></div>
    <div class="nav"><button id="prev" aria-label="Previous week">‹</button><div id="range"></div><button id="next" aria-label="Next week">›</button></div>
  </div>
  <p class="note">Every daily stage scores points. The week runs Monday to Sunday (UTC): 7 days, 2 stages a day, 14 chances to score.</p>
  <div class="tablewrap"><table id="t"></table></div>
  <div class="legend" id="legend"></div>
</main>
<div class="tip" id="tip"></div>
<script>
(function(){
  var q=new URLSearchParams(location.search),cur=q.get('date')||new Date().toISOString().slice(0,10);
  function $(id){return document.getElementById(id)}
  function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
  function flag(p,c){if(!c)return;var i=el('img','flagimg');i.src='https://flagcdn.com/w40/'+c+'.png';i.alt=c.toUpperCase();p.appendChild(i)}
  function dshort(d){return new Date(d+'T00:00:00Z').toLocaleDateString('en-GB',{day:'2-digit',month:'short',timeZone:'UTC'})}
  function wday(d){return new Date(d+'T00:00:00Z').toLocaleDateString('en-GB',{weekday:'short',timeZone:'UTC'})}
  var tip=$('tip');
  function tipOn(e,t){tip.textContent=t;tip.style.display='block';tip.style.left=Math.min(innerWidth-tip.offsetWidth-8,e.clientX+14)+'px';tip.style.top=(e.clientY+14)+'px'}
  function tipOff(){tip.style.display='none'}
  function load(){fetch('/api/week?date='+cur,{cache:'no-store'}).then(function(r){return r.json()}).then(render)}
  function render(w){
    $('kick').textContent='WEEK '+w.week;$('range').textContent=dshort(w.start)+' – '+dshort(w.end);
    $('prev').disabled=!w.prev;$('next').disabled=!w.next;
    $('prev').onclick=function(){if(w.prev){cur=w.prev;history.replaceState(null,'','?date='+cur);load()}};
    $('next').onclick=function(){if(w.next){cur=w.next;history.replaceState(null,'','?date='+cur);load()}};
    var t=$('t');t.innerHTML='';
    var h1=el('tr');h1.appendChild(el('th','l',''));h1.appendChild(el('th','l',''));
    var days=[];w.stages.forEach(function(s){if(days.indexOf(s.date)<0)days.push(s.date)});
    days.forEach(function(d){var th=el('th','day daystart'+(d===w.today?' today':''),wday(d)+' '+new Date(d+'T00:00:00Z').getUTCDate());th.colSpan=2;h1.appendChild(th)});
    h1.appendChild(el('th','r','Points'));h1.appendChild(el('th','r','Stages'));t.appendChild(h1);
    var h2=el('tr');h2.appendChild(el('th','l','Pos'));h2.appendChild(el('th','l','Driver'));
    w.stages.forEach(function(s){var th=el('th','ss'+(s.slot===1?' daystart':''));
      if(s.future){th.textContent='SS'+s.slot}else{var a=el('a',null,'SS'+s.slot);a.href='/stage/'+s.date+'/'+s.slot;th.appendChild(a);
        th.addEventListener('pointermove',function(e){tipOn(e,(s.stageName||'')+' · '+(s.car||'')+' · '+s.drivers+' drivers')});th.addEventListener('pointerleave',tipOff)}
      h2.appendChild(th)});
    h2.appendChild(el('th','r',''));h2.appendChild(el('th','r',''));t.appendChild(h2);
    if(!w.standings.length){var tr=el('tr'),td=el('td','empty','No results this week yet.');td.colSpan=4+w.stages.length;tr.appendChild(td);t.appendChild(tr)}
    var played=w.stages.filter(function(s){return!s.future}).length;
    w.standings.forEach(function(p){
      var tr=el('tr',p.rank===1?'p1':'');tr.appendChild(el('td','pos',String(p.rank)));
      var d=el('td','drv');flag(d,p.country);d.appendChild(document.createTextNode(p.name));tr.appendChild(d);
      w.stages.forEach(function(s){var c=p.cells[s.date+'/'+s.slot],cls='c'+(s.slot===1?' daystart':''),td;
        if(s.future){td=el('td',cls+' future','')}
        else if(!c){td=el('td',cls+' none','·')}
        else if(c.dnf){td=el('td',cls+' dnf','DNF')}
        else{td=el('td',cls+(c.pos===1?' win':''));var a=el('a',null,String(c.pts));if(c.runId)a.href='/run/'+c.runId;td.appendChild(a);
          td.addEventListener('pointermove',function(e){tipOn(e,'P'+c.pos+' · '+c.pts+' pts · '+(s.stageName||''))});td.addEventListener('pointerleave',tipOff)}
        tr.appendChild(td)});
      tr.appendChild(el('td','tot',String(p.total)));tr.appendChild(el('td','cnt',p.scored+' / '+played));t.appendChild(tr)});
    var lg=$('legend');lg.innerHTML='';
    var sp=el('span');sp.appendChild(el('b',null,'Points'));sp.appendChild(document.createTextNode('  '+w.points.join(' · ')+' for P1–P10, then 1 for every finisher. DNF 0.'));lg.appendChild(sp);
    var s2=el('span');s2.appendChild(el('b',null,'Ties'));s2.appendChild(document.createTextNode('  more stage wins, then more stages scored.'));lg.appendChild(s2);
  }
  load();
})();
</script>
</body>
</html>`;
}
