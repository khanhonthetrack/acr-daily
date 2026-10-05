// /stage/:date/:slot - the statistics of one daily: records, the field, a speed map of the stage,
// the spread of finishing times and the section times. Same look as the main page.
// Speed map colour: one-hue sequential ramp, dark (slow) -> WRC yellow (fast), on the black ground.

const FAVICON = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Crect width='16' height='16' fill='%230A0A0B'/%3E%3Cpath d='M3 3h5v5H3zM8 8h5v5H8z' fill='%23FFD100'/%3E%3C/svg%3E";

export function statsPage(date, slot) {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stage Statistics</title>
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
header .wrap{display:flex;align-items:center;justify-content:space-between;height:64px;padding-bottom:0}
.brand{display:flex;align-items:center;gap:10px;font:700 20px/1 'Barlow Condensed',sans-serif;letter-spacing:.06em;text-decoration:none}
.flag{width:14px;height:14px;background:conic-gradient(var(--acc) 25%,transparent 0 50%,var(--acc) 0 75%,transparent 0) 0 0/7px 7px;outline:1px solid var(--acc)}
.back{font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;text-transform:uppercase;text-decoration:none;color:var(--fg2)}
.back:hover{color:var(--fg)}
.k{font:600 11px/1.3 Barlow,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:var(--fg3)}
.plate{display:flex;gap:14px;align-items:baseline;margin-top:28px;padding-top:20px;border-top:2px solid var(--fg)}
.ss{font:700 15px/1 'Barlow Condensed',sans-serif;letter-spacing:.08em;color:var(--acc)}
.where{font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.14em;text-transform:uppercase;color:var(--fg2)}
h1{font:700 clamp(40px,6vw,72px)/.95 'Barlow Condensed',sans-serif;text-transform:uppercase;margin:12px 0 18px}
.spec{display:flex;flex-wrap:wrap;gap:6px 28px;color:var(--fg2);font-size:14px;padding-bottom:20px;border-bottom:1px solid var(--line)}
.spec b{color:var(--fg);font-weight:500}
h2{font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.16em;text-transform:uppercase;color:var(--fg2);margin:44px 0 14px}
.jtiles{grid-template-columns:repeat(3,minmax(0,1fr))!important;margin-bottom:8px}
.tiles{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.tile{padding:16px 0 18px}
.tile+.tile{padding-left:20px;border-left:1px solid var(--line)}
.tile .v{font:600 34px/1 'Barlow Condensed',sans-serif;font-feature-settings:'tnum';margin:10px 0 6px;white-space:nowrap}
.tile .v small{font-size:16px;color:var(--fg2);margin-left:4px}
.tile .who{font-size:13px;color:var(--fg2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.fieldline{display:flex;flex-wrap:wrap;gap:8px 28px;font-size:14px;color:var(--fg2);margin-top:14px}
.fieldline b{color:var(--fg);font-weight:500;font-feature-settings:'tnum'}
.grid2{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(0,1fr);gap:40px}
.speedmap{position:relative;aspect-ratio:16/10}
.speedmap svg{position:absolute;inset:0;width:100%;height:100%;overflow:visible}
.legend{display:flex;align-items:center;gap:10px;font-size:12px;color:var(--fg3);margin-top:8px;font-feature-settings:'tnum'}
.legend i{flex:0 0 160px;height:6px;background:linear-gradient(90deg,#2B2B31,#7A6A1E,#FFD100)}
.side p{color:var(--fg2);font-size:14px;margin-bottom:12px;max-width:40ch}
.fastslow{border-top:1px solid var(--line)}
.fastslow div{display:flex;justify-content:space-between;padding:9px 0;border-bottom:1px solid var(--line);font-size:14px;color:var(--fg2)}
.fastslow b{color:var(--fg);font-weight:500;font-feature-settings:'tnum'}
.spread{position:relative;height:86px;border-bottom:1px solid var(--line2);margin-top:6px}
.spread .dot{position:absolute;bottom:14px;width:10px;height:10px;margin-left:-5px;border-radius:50%;background:var(--fg2);border:2px solid var(--bg);cursor:default}
.spread .dot.p1{background:var(--acc)}
.spread .tick{position:absolute;bottom:-20px;font-size:12px;color:var(--fg3);transform:translateX(-50%);font-feature-settings:'tnum';white-space:nowrap}
.spread .med{position:absolute;bottom:0;top:6px;border-left:1px dashed var(--fg3)}
.spread .med span{position:absolute;top:-2px;left:6px;font-size:11px;color:var(--fg3);white-space:nowrap}
.tablewrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-feature-settings:'tnum'}
th{font:600 11px/1 Barlow,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:var(--fg3);text-align:right;padding:10px 0 10px 12px;border-bottom:1px solid var(--line2);white-space:nowrap}
th:first-child,td:first-child{text-align:left;padding-left:0}
td{padding:10px 0 10px 12px;border-bottom:1px solid var(--line);text-align:right;color:var(--fg2);font:500 15px/1 'Barlow Condensed',sans-serif;white-space:nowrap}
td:first-child{font:500 14px/1.2 Barlow,sans-serif;color:var(--fg)}
td.best{color:var(--acc);font-weight:700}
tr.ideal td{color:var(--fg);border-bottom:1px solid var(--line2)}
tr.ideal td:first-child{font-weight:600}
.flagimg{width:18px;height:12px;margin-right:8px;vertical-align:-1px;object-fit:cover;box-shadow:0 0 0 1px rgba(255,255,255,.12)}
.tip{position:fixed;pointer-events:none;background:#111113;border:1px solid var(--line2);padding:7px 10px;font-size:13px;display:none;z-index:5;white-space:nowrap}
.tip b{color:var(--fg);font-weight:600;font-feature-settings:'tnum'}
.empty{color:var(--fg3);padding:20px 0;border-bottom:1px solid var(--line)}
@media (max-width:900px){.tiles{grid-template-columns:repeat(2,minmax(0,1fr))}.tile:nth-child(odd){padding-left:0;border-left:0}.tile:nth-child(n+3){border-top:1px solid var(--line)}.grid2{grid-template-columns:1fr;gap:20px}.wrap{padding:0 16px 48px}}
</style>
</head>
<body>
<header><div class="wrap"><a class="brand" href="/"><i class="flag"></i>ACR DAILY</a><a class="back" href="/">‹ All stages</a></div></header>
<main class="wrap" id="app"><p class="empty" style="margin-top:40px">Loading the stage…</p></main>
<div class="tip" id="tip"></div>
<script>
(function(){
  var DATE='${date}',SLOT=${Number(slot)};
  function $(id){return document.getElementById(id)}
  function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
  var NS='http://www.w3.org/2000/svg';
  function sv(tag,a){var e=document.createElementNS(NS,tag);for(var k in a||{})e.setAttribute(k,a[k]);return e}
  function fmt(ms){if(ms==null)return'–';var m=Math.floor(ms/60000),s=(ms%60000)/1000;return m+':'+(s<10?'0':'')+s.toFixed(3)}
  function secs(ms){return ms==null?'–':(ms/1000).toFixed(2)}
  function flag(p,c){if(!c)return;var i=el('img','flagimg');i.src='https://flagcdn.com/w40/'+c+'.png';i.alt=c.toUpperCase();p.appendChild(i)}
  var tip=$('tip');
  function showTip(e,html){tip.innerHTML=html;tip.style.display='block';var x=Math.min(window.innerWidth-tip.offsetWidth-8,e.clientX+14);tip.style.left=x+'px';tip.style.top=(e.clientY+14)+'px'}
  function hideTip(){tip.style.display='none'}
  function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
  // sequential ramp: #2B2B31 (slow) -> #FFD100 (fast)
  function ramp(t){t=Math.max(0,Math.min(1,t));var a=[43,43,49],b=[255,209,0];return'rgb('+a.map(function(v,i){return Math.round(v+(b[i]-v)*Math.pow(t,0.85))}).join(',')+')'}

  fetch('/api/stats?date='+DATE+'&slot='+SLOT,{cache:'no-store'}).then(function(r){return r.json()}).then(render);

  function render(d){
    var app=$('app');app.innerHTML='';
    if(d.error){app.appendChild(el('p','empty','No stage for this day.'));return}
    var ch=d.challenge;document.title=(ch.menuName||ch.stageName||ch.track)+' · Stage Statistics';
    var p=el('div','plate');p.appendChild(el('span','ss','SS'+ch.slot));
    p.appendChild(el('span','where',[ch.rally,ch.surface,(d.lengthM/1000).toFixed(2)+' km',new Date(DATE+'T00:00:00Z').toLocaleDateString('en-GB',{day:'2-digit',month:'short',year:'numeric',timeZone:'UTC'})].filter(Boolean).join('  ·  ')));
    app.appendChild(p);app.appendChild(el('h1',null,ch.menuName||ch.stageName||ch.track));
    var spec=el('div','spec');[['Car',ch.car+(ch.carClass?' · '+ch.carClass:'')],['Weather',ch.weatherLabel],['Start',ch.timeLabel]].forEach(function(x){
      var s=el('span');s.appendChild(document.createTextNode(x[0]+'  '));s.appendChild(el('b',null,x[1]||'–'));spec.appendChild(s)});app.appendChild(spec);

    // ---- records
    app.appendChild(el('h2',null,'Records'));
    var R=d.records,tiles=el('div','tiles');
    function tile(k,v,unit,who,country){var t=el('div','tile');t.appendChild(el('div','k',k));var vv=el('div','v',v);if(unit)vv.appendChild(el('small',null,unit));t.appendChild(vv);
      var w=el('div','who');flag(w,country);w.appendChild(document.createTextNode(who||''));t.appendChild(w);tiles.appendChild(t)}
    tile('Fastest',R.fastest?fmt(R.fastest.totalMs):'–','',R.fastest?R.fastest.name:'No finishers yet',R.fastest&&R.fastest.country);
    tile('Top speed',R.topSpeed?Math.round(R.topSpeed.kmh):'–','km/h',R.topSpeed?R.topSpeed.name+' · at km '+R.topSpeed.km.toFixed(1):'',R.topSpeed&&R.topSpeed.country);
    tile('Winning average',R.avgSpeed!=null?R.avgSpeed.toFixed(1):'–','km/h',R.fastest?R.fastest.name:'',R.fastest&&R.fastest.country);
    tile('Longest flat out',R.longestFlatOut?(R.longestFlatOut.ms/1000).toFixed(1):'–','s',R.longestFlatOut?R.longestFlatOut.name+' · from km '+R.longestFlatOut.km.toFixed(1):'',R.longestFlatOut&&R.longestFlatOut.country);
    tile('Ideal run',R.ideal?fmt(R.ideal.ms):'–','',R.ideal&&R.ideal.gainMs!=null?'best sections · −'+(R.ideal.gainMs/1000).toFixed(2)+' s vs P1':'best sections combined');
    app.appendChild(tiles);
    var F=d.field,fl=el('div','fieldline');
    [['drivers',F.drivers],['finished',F.finishers],['DNF',F.dnfs],['clean runs (no reset)',F.cleanRuns],['median',fmt(F.medianMs)]].forEach(function(x){
      var s=el('span');s.appendChild(el('b',null,String(x[1])));s.appendChild(document.createTextNode(' '+x[0]));fl.appendChild(s)});
    app.appendChild(fl);

    // ---- speed map
    app.appendChild(el('h2',null,'Where it is fast'));
    var g2=el('div','grid2');var mapCol=el('div');var mapBox=el('div','speedmap');mapCol.appendChild(mapBox);g2.appendChild(mapCol);var side=el('div','side');g2.appendChild(side);app.appendChild(g2);
    var segs=d.speedMap.filter(function(s){return s.avg!=null});
    if(!segs.length){mapBox.appendChild(el('p','empty','The speed map appears with the first finished run.'))}
    else drawSpeedMap(mapBox,ch.route,d.speedMap,side,(d.air&&d.air.spots)||[]);

    // ---- jumps
    app.appendChild(el('h2',null,'Jumps'));
    var A=d.air||{};
    if(!A.runsWithData){app.appendChild(el('p','empty','Jumps are measured by app version 0.11 and newer. They appear here with the first run from it.'))}
    else{
      var jt=el('div','tiles jtiles');
      function jtile(k,v,unit,who,country){var t=el('div','tile');t.appendChild(el('div','k',k));var vv=el('div','v',v);if(unit)vv.appendChild(el('small',null,unit));t.appendChild(vv);
        var w=el('div','who');flag(w,country);w.appendChild(document.createTextNode(who||''));t.appendChild(w);jt.appendChild(t)}
      var LJ=A.longestJump,MA=A.mostAirtime;
      jtile('Longest jump',LJ?(LJ.ms/1000).toFixed(2):'–','s',LJ?LJ.name+' · km '+LJ.km.toFixed(2)+' · '+Math.round(LJ.kmh)+' km/h':'No jumps yet',LJ&&LJ.country);
      jtile('Most airtime in a run',MA?(MA.ms/1000).toFixed(2):'–','s',MA?MA.name+' · '+MA.count+' jumps':'',MA&&MA.country);
      jtile('Jump spots',String((A.spots||[]).length),'',(A.spots||[]).length?'places where most drivers fly':'');
      app.appendChild(jt);
      if((A.spots||[]).length){
        var tw=el('div','tablewrap'),tb=el('table'),hr=el('tr');['Spot','Where','Drivers in the air','Average airtime','Longest'].forEach(function(h){hr.appendChild(el('th',null,h))});tb.appendChild(hr);
        A.spots.forEach(function(s,i){var tr=el('tr');tr.appendChild(el('td',null,'J'+(i+1)));tr.appendChild(el('td',null,'km '+(s.m/1000).toFixed(2)));
          tr.appendChild(el('td',null,String(s.drivers)));tr.appendChild(el('td',null,(s.avgMs/1000).toFixed(2)+' s'));
          var b=el('td');b.appendChild(document.createTextNode((s.best.ms/1000).toFixed(2)+' s  ·  '+s.best.name));tr.appendChild(b);tb.appendChild(tr)});
        tw.appendChild(tb);app.appendChild(tw);
      }
    }

    // ---- spread of finishing times
    app.appendChild(el('h2',null,'The field'));
    var T=F.totals;
    if(T.length<1){app.appendChild(el('p','empty','No finishers yet.'))}
    else{
      var sp=el('div','spread'),lo=T[0].totalMs,hi=Math.max(lo+1000,T[T.length-1].totalMs);
      function X(ms){return 2+96*(ms-lo)/(hi-lo)}
      if(F.medianMs!=null&&T.length>2){var md=el('div','med');md.style.left=X(F.medianMs)+'%';md.appendChild(el('span',null,'median '+fmt(F.medianMs)));sp.appendChild(md)}
      T.forEach(function(t,i){var dt=el('div','dot'+(i===0?' p1':''));dt.style.left=X(t.totalMs)+'%';dt.style.bottom=(14+(i%3)*14)+'px';
        dt.addEventListener('pointermove',function(e){showTip(e,'<b>'+fmt(t.totalMs)+'</b>  P'+t.rank+'  '+esc(t.name)+(t.resets?'  · +'+t.resets*60+' s':''))});
        dt.addEventListener('pointerleave',hideTip);sp.appendChild(dt)});
      [[lo,'P1 '+fmt(lo)],[hi,'+'+((hi-lo)/1000).toFixed(1)+' s']].forEach(function(x){var tk=el('div','tick',x[1]);tk.style.left=X(x[0])+'%';sp.appendChild(tk)});
      app.appendChild(sp);app.appendChild(el('div',null,'')).style.height='24px';
    }

    // ---- sections
    app.appendChild(el('h2',null,'Sections (tenths of the stage)'));
    var S=d.sections;
    if(!S.table.length){app.appendChild(el('p','empty','No section times yet.'))}
    else{
      var tw=el('div','tablewrap'),t=el('table'),hr=el('tr');hr.appendChild(el('th',null,'Driver'));
      for(var i=0;i<10;i++)hr.appendChild(el('th',null,'S'+(i+1)));hr.appendChild(el('th',null,'Clock'));t.appendChild(hr);
      var ir=el('tr','ideal');ir.appendChild(el('td',null,'Best of everyone'));
      S.best.forEach(function(b){var c=el('td','best',b?secs(b.ms):'–');if(b)c.title=b.name;ir.appendChild(c)});
      ir.appendChild(el('td',null,R.ideal?fmt(R.ideal.ms):'–'));t.appendChild(ir);
      S.table.forEach(function(r){var tr=el('tr'),n=el('td');flag(n,r.country);n.appendChild(document.createTextNode(r.name));tr.appendChild(n);
        r.durs.forEach(function(v,i){var b=S.best[i];tr.appendChild(el('td',b&&v===b.ms?'best':'',secs(v)))});
        var tot=r.durs.reduce(function(a,b){return b==null?a:a+b},0);tr.appendChild(el('td',null,fmt(tot)));t.appendChild(tr)});
      tw.appendChild(t);app.appendChild(tw);
    }
  }

  function drawSpeedMap(box,pts,segs,side,spots){
    var W=800,H=500,pad=30,mx=0,mz=0,i;for(i=0;i<pts.length;i++){mx+=pts[i][0];mz+=pts[i][1]}mx/=pts.length;mz/=pts.length;
    var sxx=0,szz=0,sxz=0;for(i=0;i<pts.length;i++){var dx=pts[i][0]-mx,dz=pts[i][1]-mz;sxx+=dx*dx;szz+=dz*dz;sxz+=dx*dz}
    var a=-0.5*Math.atan2(2*sxz,sxx-szz),c=Math.cos(a),s=Math.sin(a);
    function rot(p){return[(p[0]-mx)*c-(p[1]-mz)*s,(p[0]-mx)*s+(p[1]-mz)*c]}
    var R=pts.map(rot),x0=1e9,x1=-1e9,y0=1e9,y1=-1e9;R.forEach(function(p){x0=Math.min(x0,p[0]);x1=Math.max(x1,p[0]);y0=Math.min(y0,p[1]);y1=Math.max(y1,p[1])});
    var k=Math.min((W-2*pad)/(x1-x0||1),(H-2*pad)/(y1-y0||1)),ox=(W-(x1-x0)*k)/2-x0*k,oy=(H-(y1-y0)*k)/2-y0*k;
    function P(i){var r=R[i];return[r[0]*k+ox,r[1]*k+oy]}
    var cum=[0];for(i=1;i<pts.length;i++)cum.push(cum[i-1]+Math.hypot(pts[i][0]-pts[i-1][0],pts[i][1]-pts[i-1][1]));
    var vals=segs.filter(function(x){return x.avg!=null}).map(function(x){return x.avg});
    // colour scale from the 10th to the 90th percentile, so one crash or one straight doesn't flatten it
    var sorted=vals.slice().sort(function(a,b){return a-b});
    var vmin=sorted[Math.floor(sorted.length*0.1)],vmax=sorted[Math.min(sorted.length-1,Math.floor(sorted.length*0.9))];
    var svg=sv('svg',{viewBox:'0 0 '+W+' '+H,role:'img','aria-label':'Stage map coloured by average speed'});
    // casing
    var all=pts.map(function(_,j){var q=P(j);return q[0].toFixed(1)+','+q[1].toFixed(1)}).join(' ');
    svg.appendChild(sv('polyline',{points:all,fill:'none',stroke:'#16161A','stroke-width':12,'stroke-linejoin':'round','stroke-linecap':'round'}));
    segs.forEach(function(sg){
      var idx=[];for(var j=0;j<pts.length;j++)if(cum[j]>=sg.from-2&&cum[j]<=sg.to+2)idx.push(j);
      if(idx.length<2)return;
      var line=idx.map(function(j){var q=P(j);return q[0].toFixed(1)+','+q[1].toFixed(1)}).join(' ');
      var col=sg.avg==null?'#2B2B31':ramp((sg.avg-vmin)/((vmax-vmin)||1));
      var pl=sv('polyline',{points:line,fill:'none',stroke:col,'stroke-width':5,'stroke-linecap':'round','stroke-linejoin':'round'});
      var hit=sv('polyline',{points:line,fill:'none',stroke:'transparent','stroke-width':22});
      hit.addEventListener('pointermove',function(e){showTip(e,'km <b>'+(sg.from/1000).toFixed(2)+'–'+(sg.to/1000).toFixed(2)+'</b> · average <b>'+(sg.avg==null?'–':Math.round(sg.avg))+' km/h</b>'+(sg.max?' · fastest '+Math.round(sg.max)+' ('+esc(sg.maxBy)+')':''));pl.setAttribute('stroke-width',8)});
      hit.addEventListener('pointerleave',function(){hideTip();pl.setAttribute('stroke-width',5)});
      svg.appendChild(pl);svg.appendChild(hit);
    });
    // jump spots: a ring and a label
    (spots||[]).forEach(function(sp,n){var j=0;while(j<cum.length-1&&cum[j]<sp.m)j++;var q=P(j);
      svg.appendChild(sv('circle',{cx:q[0],cy:q[1],r:8,fill:'none',stroke:'#F4F4F5','stroke-width':1.5}));
      var tx=sv('text',{x:q[0]+12,y:q[1]-8,fill:'#F4F4F5','font-size':13,'font-family':'Barlow Condensed','font-weight':600});tx.textContent='J'+(n+1);svg.appendChild(tx)});
    var A=P(0),Z=P(pts.length-1);
    svg.appendChild(sv('circle',{cx:A[0],cy:A[1],r:5,fill:'#F4F4F5'}));
    var fin=sv('g',{transform:'translate('+(Z[0]-7)+','+(Z[1]-7)+')'});fin.appendChild(sv('rect',{width:14,height:14,fill:'#F4F4F5'}));
    fin.appendChild(sv('rect',{width:7,height:7,fill:'#0A0A0B'}));fin.appendChild(sv('rect',{x:7,y:7,width:7,height:7,fill:'#0A0A0B'}));svg.appendChild(fin);
    box.appendChild(svg);
    var lg=el('div','legend');lg.appendChild(el('span',null,Math.round(vmin)+' km/h'));lg.appendChild(el('i'));lg.appendChild(el('span',null,Math.round(vmax)+' km/h average'));
    box.parentNode.appendChild(lg);
    // fastest and slowest parts
    var ranked=segs.filter(function(x){return x.avg!=null}).slice().sort(function(a,b){return b.avg-a.avg});
    side.appendChild(el('p',null,'Average speed of every finisher through each part of the stage. Hover the road for details.'));
    var fs=el('div','fastslow');
    [['Fastest part',ranked[0]],['Slowest part',ranked[ranked.length-1]]].forEach(function(x){if(!x[1])return;var r=el('div');r.appendChild(el('span',null,x[0]+' · km '+(x[1].from/1000).toFixed(1)));r.appendChild(el('b',null,Math.round(x[1].avg)+' km/h'));fs.appendChild(r)});
    side.appendChild(fs);
  }
})();
</script>
</body>
</html>`;
}
