// Run viewer: /run/:id. The run on the map against the day's #1 (or #2), speed / gap / inputs along the
// stage with one shared crosshair, section times, and a "report this run" button.
// Chart colours: this run = blue, comparison = orange (validated on the #141418 panel).

import { FAVICON, logoSvg } from './logo.js';
import { EARTH_JS } from './earth.js';

export function viewerPage(id) {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ACR Daily Run</title>
<link rel="icon" href="${FAVICON}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700;800&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{--ink:#0A0A0B;--bg:#0A0A0B;--panel:#0A0A0B;--line:#1F1F23;--line2:#2B2B31;--white:#F4F4F5;--soft:#D4D4D8;--muted:#6B6B74;--fg2:#A1A1AA;
  --acc:#E30613;--warn:#FF9F0A;--crit:#FF453A;--s1:#3987e5;--s2:#d95926;--grid:#1A1A1E;--axis:#2B2B31}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg2);font:15px/1.5 Barlow,system-ui,sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:1200px;margin:0 auto;padding:0 24px 64px}
a{color:var(--white)}
.disp,h1,h2{font-family:'Barlow Condensed',sans-serif;color:var(--white);margin:0}
.top{display:flex;align-items:center;justify-content:space-between;gap:12px;height:76px;border-bottom:1px solid var(--line);margin:0 -24px 28px;padding:0 24px}
.logo{display:flex;align-items:center;gap:10px;font:700 20px/1 'Barlow Condensed',sans-serif;letter-spacing:.06em;text-decoration:none;color:var(--white)}
.brandmark{display:block;height:60px;width:auto}
.top>a:last-child{font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;text-transform:uppercase;text-decoration:none;color:var(--fg2)}
.top>a:last-child:hover{color:var(--white)}
.card{background:none}
.head{display:flex;flex-wrap:wrap;gap:20px 40px;align-items:flex-end;padding:20px 0 22px;border-top:2px solid var(--white);border-bottom:1px solid var(--line)}
.head>div:first-child{flex:1 1 320px}
.head h1{font:700 clamp(38px,5vw,56px)/.95 'Barlow Condensed',sans-serif;text-transform:uppercase;margin-top:10px}
.lbl{font:600 11px/1.3 Barlow,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}
.big{font:600 30px/1 'Barlow Condensed',sans-serif;color:var(--white);font-feature-settings:'tnum';margin-top:6px}
.notice{margin:14px 0 0;padding:4px 0 4px 12px;display:flex;gap:12px;align-items:baseline;border-left:2px solid var(--warn);color:var(--white);font-size:14px}
.notice.crit{border-color:var(--crit)}
.notice .ic{font:600 11px/1 Barlow,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:var(--warn)}.notice.crit .ic{color:var(--crit)}
.grid2{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(0,1fr);gap:40px;margin-top:24px}
.map{min-height:300px;position:relative}
.map svg{width:100%;height:100%;display:block;overflow:visible}
.stats{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-content:start;border-top:1px solid var(--line)}
.stat{padding:12px 0;border-bottom:1px solid var(--line)}
.stat .v{font:600 22px/1.1 'Barlow Condensed',sans-serif;color:var(--white);font-feature-settings:'tnum';margin-top:4px}
.legend{display:flex;gap:24px;flex-wrap:wrap;padding:28px 0 8px;font-size:14px;color:var(--fg2);border-bottom:1px solid var(--line)}
.key{display:inline-block;width:16px;height:0;border-top:2px solid;vertical-align:middle;margin-right:8px}
.charts{padding:6px 0 10px;position:relative;outline:none}
.charts:focus-visible{box-shadow:0 0 0 1px var(--acc)}
.chart{position:relative;border-bottom:1px solid var(--line)}
.chart .t{position:absolute;left:62px;top:8px;font:600 11px Barlow,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);pointer-events:none}
svg text{font:12px Barlow,sans-serif;fill:var(--muted)}
.tip{position:absolute;pointer-events:none;background:#111113;border:1px solid var(--line2);padding:8px 10px;font-size:13px;min-width:170px;display:none;z-index:2}
.tip .row{display:flex;justify-content:space-between;gap:14px;align-items:center}
.tip .row b{color:var(--white);font-feature-settings:'tnum'}
.tip .k{display:inline-block;width:12px;border-top:2px solid;margin-right:6px;vertical-align:middle}
h2{font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.16em;text-transform:uppercase;color:var(--fg2);margin:40px 0 10px}
.tablewrap{overflow-x:auto}
table{width:100%;border-collapse:collapse}
th{font:600 11px/1 Barlow,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);text-align:left;padding:10px 12px 10px 0;border-bottom:1px solid var(--line2)}
td{padding:10px 12px 10px 0;border-bottom:1px solid var(--line);font-feature-settings:'tnum';color:var(--soft)}
td.n,th.n{text-align:right}
.report{margin-top:40px;padding-top:16px;border-top:1px solid var(--line)}
.report textarea{width:100%;max-width:640px;display:block;min-height:70px;background:none;border:1px solid var(--line2);color:var(--white);font:inherit;padding:10px;margin:10px 0}
.report textarea:focus{outline:none;border-color:var(--fg2)}
.btn{background:none;color:var(--white);border:1px solid var(--line2);font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;text-transform:uppercase;padding:10px 16px;cursor:pointer}
.btn:hover{border-color:var(--white)}
@media (max-width:760px){.grid2{grid-template-columns:1fr;gap:16px}.map{min-height:220px}.wrap{padding:0 16px 48px}.top{margin:0 -16px 20px;padding:0 16px}}.beta{display:inline-block;margin-left:8px;padding:2px 6px;border:1px solid #E30613;border-radius:3px;color:#E30613;font:700 12px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;vertical-align:middle;text-decoration:none}
</style>
</head>
<body>
<div class="wrap">
  <div class="top"><a class="logo" href="/">${logoSvg()}<b class="beta" title="ACR Daily is in beta: things may change and bugs are expected. Report them on Discord.">BETA</b></a><a href="/">‹ All stages</a></div>
  <div id="app"><div class="card head"><div class="lbl">Loading run…</div></div></div>
</div>
<script>
(function(){
  ${EARTH_JS}
  var RUN_ID = ${Number(id)};
  var $ = function(id){return document.getElementById(id)};
  function el(tag, attrs, text){var e=document.createElement(tag);for(var k in attrs||{})e.setAttribute(k,attrs[k]);if(text!=null)e.textContent=text;return e}
  var NS='http://www.w3.org/2000/svg';
  function sv(tag, attrs){var e=document.createElementNS(NS,tag);for(var k in attrs||{})e.setAttribute(k,attrs[k]);return e}
  function fmt(ms){if(ms==null)return'–';var neg=ms<0;ms=Math.abs(ms);var m=Math.floor(ms/60000),s=(ms%60000)/1000;return(neg?'-':'')+m+':'+(s<10?'0':'')+s.toFixed(3)}
  function sgn(ms,d){return ms==null?'–':(ms>=0?'+':'−')+(Math.abs(ms)/1000).toFixed(d==null?2:d)}

  // distance along the route for every sample (nearest route point, moving forwards)
  function along(trace, route, penalty){
    var cum=[0],i;for(i=1;i<route.length;i++)cum.push(cum[i-1]+Math.hypot(route[i][0]-route[i-1][0],route[i][1]-route[i-1][1]));
    var idx=0,best=0,out=[];
    trace.forEach(function(s){
      var bi=idx,bd=Infinity;for(var j=Math.max(0,idx-10);j<Math.min(route.length,idx+80);j++){var d=Math.pow(route[j][0]-s[1],2)+Math.pow(route[j][1]-s[2],2);if(d<bd){bd=d;bi=j}}
      if(bd<=3600){idx=bi;best=Math.max(best,cum[bi])}
      out.push({d:best,t:s[0]+(s[4]||0)*penalty,clock:s[0],v:s[3],x:s[1],z:s[2],thr:s[7],brk:s[8],steer:s[9],gear:s[10],rpm:s[11],resets:s[4]||0});
    });
    return {pts:out,length:cum[cum.length-1]};
  }
  function firsts(pts){ // the first moment each distance was reached (a reset parks the car while its time jumps)
    var out=[],max=-1;pts.forEach(function(p){if(p.d>max){out.push(p);max=p.d}});return out;
  }
  function at(series, d, key){ // linear interpolation by distance
    var a=null,b=null;for(var i=0;i<series.length;i++){if(series[i].d<=d)a=series[i];if(series[i].d>=d){b=series[i];break}}
    if(!a)return b?b[key]:null;if(!b||b.d===a.d)return a[key];
    return a[key]+(b[key]-a[key])*(d-a.d)/(b.d-a.d);
  }

  fetch('/api/runs/'+RUN_ID).then(function(r){return r.json()}).then(function(run){
    if(run.error){$('app').innerHTML='';$('app').appendChild(el('div',{class:'card head'},'Run not found'));return}
    render(run);
  });

  function render(run){
    var app=$('app');app.innerHTML='';
    document.title=run.name+' '+fmt(run.totalMs)+' · ACR Daily';
    var me=along(run.trace,run.route,run.penaltyMs);
    var cmp=run.compare?along(run.compare.trace,run.route,run.penaltyMs):null;
    var L=me.length;

    // ---- header
    var head=el('div',{class:'card head'});
    var who=el('div');who.appendChild(el('div',{class:'lbl'},'SS'+(run.slot||1)+'  ·  '+run.date+'  ·  '+(run.menuName||run.track)+'  ·  '+run.car));who.appendChild(el('h1',{},run.name));head.appendChild(who);
    [['Time',fmt(run.totalMs)],['Place',run.rank?'P'+run.rank:'–'],['Stage clock',fmt(run.clockMs)],['Resets',run.resets+(run.resets?' (+'+run.resets*run.penaltyMs/1000+' s)':'')]].forEach(function(p){
      var d=el('div');d.appendChild(el('div',{class:'lbl'},p[0]));d.appendChild(el('div',{class:'big'},p[1]));head.appendChild(d)});
    app.appendChild(head);
    if(run.status==='rejected'){var n=el('div',{class:'notice crit'});n.appendChild(el('span',{class:'ic'},'Removed'));n.appendChild(el('span',{},run.reason||'removed by an admin'));app.appendChild(n)}
    else if(run.review){var n2=el('div',{class:'notice'});n2.appendChild(el('span',{class:'ic'},'Under review'));
      n2.appendChild(el('span',{},(run.flags.length?run.flags.join(' · '):'')+(run.reports?(run.flags.length?' · ':'')+run.reports+' report(s)':'')));app.appendChild(n2)}

    // ---- map + key numbers
    var g2=el('div',{class:'grid2'});var mapCard=el('div',{class:'card map'});var statCard=el('div',{class:'card stats'});g2.appendChild(mapCard);g2.appendChild(statCard);app.appendChild(g2);
    var vmax=Math.max.apply(null,me.pts.map(function(p){return p.v}));
    var avg=L/1000/(run.clockMs/3600000);
    var stats=[['Top speed',Math.round(vmax)+' km/h'],['Average',avg.toFixed(1)+' km/h'],['Stage length',(L/1000).toFixed(2)+' km'],
      ['Car',run.car]];
    if(cmp)stats.push(['Compared with',(run.compare.rank?'P'+run.compare.rank+' ':'')+run.compare.name],['Gap',sgn(run.totalMs-run.compare.totalMs,3)+' s']);
    stats.forEach(function(p){var d=el('div',{class:'stat'});d.appendChild(el('div',{class:'lbl'},p[0]));d.appendChild(el('div',{class:'v'},p[1]));statCard.appendChild(d)});
    var mapDots=drawMap(mapCard,run.route,me,cmp,EARTH[run.track]);

    // ---- legend
    var lg=el('div',{class:'legend'});
    function key(color,text){var s=el('span');var k=el('span',{class:'key'});k.style.borderColor=color;s.appendChild(k);s.appendChild(document.createTextNode(text));return s}
    lg.appendChild(key('var(--s1)','This run · '+run.name));if(cmp)lg.appendChild(key('var(--s2)',(run.compare.rank?'P'+run.compare.rank+' · ':'')+run.compare.name));
    app.appendChild(lg);

    // ---- charts along the stage
    var box=el('div',{class:'card charts',tabindex:'0','aria-label':'Charts along the stage. Use the arrow keys to move along it.'});app.appendChild(box);
    var cmpFirst=cmp?firsts(cmp.pts):null;
    var gapSeries=cmp?firsts(me.pts).map(function(p){var o=at(cmpFirst,p.d,'t');return{d:p.d,gap:o==null?null:(p.t-o)/1000}}).filter(function(p){return p.gap!=null}):null;
    var charts=[];
    charts.push(lineChart(box,'Speed · km/h',110,[{pts:me.pts,key:'v',color:'var(--s1)'}].concat(cmp?[{pts:cmp.pts,key:'v',color:'var(--s2)'}]:[]),L,{min:0}));
    if(gapSeries)charts.push(lineChart(box,'Gap to '+run.compare.name+' · s (above 0 = behind)',100,[{pts:gapSeries,key:'gap',color:'var(--s1)'}],L,{zero:true}));
    charts.push(lineChart(box,'Throttle',56,[{pts:me.pts,key:'thr',color:'var(--s1)',area:true}],L,{min:0,max:1,noTicks:true}));
    charts.push(lineChart(box,'Brake',56,[{pts:me.pts,key:'brk',color:'var(--s1)',area:true}],L,{min:0,max:1,noTicks:true}));
    charts.push(lineChart(box,'Steering (left / right)',70,[{pts:me.pts,key:'steer',color:'var(--s1)'}],L,{min:-1,max:1,zero:true,noTicks:true,xAxis:true}));
    var tip=el('div',{class:'tip'});box.appendChild(tip);

    function show(d, px, py){
      charts.forEach(function(c){c.cross(d)});
      var rows=[['km',(d/1000).toFixed(2),null],['Speed',Math.round(at(me.pts,d,'v'))+' km/h','var(--s1)']];
      if(cmp)rows.push(['Speed',Math.round(at(cmp.pts,d,'v'))+' km/h','var(--s2)']);
      if(gapSeries){var gp=at(gapSeries,d,'gap');rows.push(['Gap',gp==null?'–':(gp>=0?'+':'−')+Math.abs(gp).toFixed(2)+' s',null])}
      var near=me.pts.reduce(function(a,b){return Math.abs(b.d-d)<Math.abs(a.d-d)?b:a});
      var gear=near.gear===0?'R':near.gear===1?'N':String(near.gear-1);
      rows.push(['Throttle',Math.round(near.thr*100)+' %',null],['Brake',Math.round(near.brk*100)+' %',null],['Gear · rpm',gear+' · '+near.rpm,null]);
      tip.innerHTML='';rows.forEach(function(r){var row=el('div',{class:'row'});var l=el('span');if(r[2]){var k=el('span',{class:'k'});k.style.borderColor=r[2];l.appendChild(k)}
        l.appendChild(document.createTextNode(r[0]));row.appendChild(el('b',{},r[1]));row.appendChild(l);tip.appendChild(row)});
      tip.style.display='block';
      var bw=box.clientWidth,tw=tip.offsetWidth;tip.style.left=Math.min(bw-tw-8,Math.max(8,px+16))+'px';tip.style.top=Math.max(8,py-20)+'px';
      mapDots(d);
    }
    var cur=null;
    box.addEventListener('pointermove',function(e){var c=charts[0],r=box.getBoundingClientRect();var d=c.dAt(e.clientX);if(d==null)return;cur=d;show(d,e.clientX-r.left,e.clientY-r.top)});
    box.addEventListener('pointerleave',function(){tip.style.display='none';charts.forEach(function(c){c.cross(null)});mapDots(null)});
    box.addEventListener('keydown',function(e){if(e.key!=='ArrowRight'&&e.key!=='ArrowLeft')return;e.preventDefault();cur=Math.max(0,Math.min(L,(cur==null?0:cur)+(e.key==='ArrowRight'?1:-1)*L/100));show(cur,charts[0].xOf(cur),20)});

    // ---- sections table
    app.appendChild(el('h2',{},'Sections'));
    var tw=el('div',{class:'card tablewrap'});var t=el('table');tw.appendChild(t);app.appendChild(tw);
    var hr=el('tr');['Section','This run'].concat(cmp?[run.compare.name,'Difference']:[]).forEach(function(h,i){hr.appendChild(el('th',{class:i?'n':''},h))});t.appendChild(hr);
    var ms=run.sections||[],os=(run.compare&&run.compare.sections)||[];
    for(var i=0;i<ms.length;i++){
      var a=ms[i]!=null&&(i===0||ms[i-1]!=null)?ms[i]-(i?ms[i-1]:0):null;
      var b=os[i]!=null&&(i===0||os[i-1]!=null)?os[i]-(i?os[i-1]:0):null;
      var tr=el('tr');tr.appendChild(el('td',{},(i*10)+'–'+((i+1)*10)+' %'));tr.appendChild(el('td',{class:'n'},a==null?'–':(a/1000).toFixed(2)+' s'));
      if(cmp){tr.appendChild(el('td',{class:'n'},b==null?'–':(b/1000).toFixed(2)+' s'));tr.appendChild(el('td',{class:'n'},a==null||b==null?'–':sgn(a-b)+' s'))}
      t.appendChild(tr);
    }

    // ---- report
    var rep=el('div',{class:'card report'});rep.appendChild(el('div',{class:'lbl'},'Something wrong with this run?'));
    var ta=el('textarea',{maxlength:'300',placeholder:'What looks wrong? (optional)','aria-label':'Reason'});rep.appendChild(ta);
    var bt=el('button',{class:'btn',type:'button'},'Report this run');rep.appendChild(bt);var msg=el('span',{style:'margin-left:12px'});rep.appendChild(msg);
    bt.onclick=function(){bt.disabled=true;fetch('/api/runs/'+RUN_ID+'/report',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reason:ta.value})})
      .then(function(r){return r.json()}).then(function(r){msg.textContent=r.ok?'Thanks, an admin will look at it.':'Could not send the report.'})};
    app.appendChild(rep);
  }

  // ---------------------------------------------------------------- map
  function drawMap(card, route, me, cmp, g){
    // as the stage is on Earth when it is lined up (g, earth.js), else in the game's own (mirrored) frame
    var T=earthScreen(g),W=640,H=360,pad=22,pts=route.map(T),i,mx=0,mz=0;
    for(i=0;i<pts.length;i++){mx+=pts[i][0];mz+=pts[i][1]}mx/=pts.length;mz/=pts.length;
    var a=earthAngle(pts,W,H,pad,!!g),c=Math.cos(a),s=Math.sin(a);
    function rot(p){return[(p[0]-mx)*c-(p[1]-mz)*s,(p[0]-mx)*s+(p[1]-mz)*c]}
    var R=pts.map(rot),x0=1e9,x1=-1e9,y0=1e9,y1=-1e9;R.forEach(function(p){x0=Math.min(x0,p[0]);x1=Math.max(x1,p[0]);y0=Math.min(y0,p[1]);y1=Math.max(y1,p[1])});
    var k=Math.min((W-2*pad)/(x1-x0||1),(H-2*pad)/(y1-y0||1)),ox=(W-(x1-x0)*k)/2-x0*k,oy=(H-(y1-y0)*k)/2-y0*k;
    function Pt(p){var r=rot(p);return[r[0]*k+ox,r[1]*k+oy]}   // already on screen axes
    function P(p){return Pt(T(p))}                               // game (x, z): the runs' samples
    function line(list){return list.map(function(p){var q=P(p);return q[0].toFixed(1)+','+q[1].toFixed(1)}).join(' ')}
    var svg=sv('svg',{viewBox:'0 0 '+W+' '+H,role:'img','aria-label':'Map of the stage with both runs'});
    svg.appendChild(sv('polyline',{points:pts.map(function(p){var q=Pt(p);return q[0].toFixed(1)+','+q[1].toFixed(1)}).join(' '),fill:'none',stroke:'#55555E','stroke-width':2.5,'stroke-linejoin':'round','stroke-linecap':'round'}));
    function split(series){ // break the line at resets so a teleport is not drawn as a road
      var segs=[[]];series.pts.forEach(function(p,j){if(j&&p.resets!==series.pts[j-1].resets)segs.push([]);segs[segs.length-1].push([p.x,p.z])});return segs}
    if(cmp)split(cmp).forEach(function(sg){svg.appendChild(sv('polyline',{points:line(sg),fill:'none',stroke:'var(--s2)','stroke-width':2,'stroke-linejoin':'round'}))});
    split(me).forEach(function(sg){svg.appendChild(sv('polyline',{points:line(sg),fill:'none',stroke:'var(--s1)','stroke-width':2,'stroke-linejoin':'round'}))});
    me.pts.forEach(function(p,j){if(j&&p.resets!==me.pts[j-1].resets){var q=P([p.x,p.z]);var g=sv('g');g.appendChild(sv('circle',{cx:q[0],cy:q[1],r:6,fill:'#050506',stroke:'#d03b3b','stroke-width':2}));
      var tx=sv('text',{x:q[0]+10,y:q[1]+4});tx.textContent='Reset +'+(60)+' s';tx.setAttribute('style','fill:#F1F6F2;font-weight:600');g.appendChild(tx);svg.appendChild(g)}});
    var A=Pt(pts[0]),Z=Pt(pts[pts.length-1]);
    svg.appendChild(sv('circle',{cx:A[0],cy:A[1],r:7,fill:'#F1F6F2',stroke:'#07120D','stroke-width':3}));
    var fin=sv('g',{transform:'translate('+(Z[0]-8)+','+(Z[1]-8)+')'});fin.appendChild(sv('rect',{width:16,height:16,fill:'#F1F6F2',stroke:'#07120D','stroke-width':2}));
    fin.appendChild(sv('rect',{width:8,height:8,fill:'#07120D'}));fin.appendChild(sv('rect',{x:8,y:8,width:8,height:8,fill:'#07120D'}));svg.appendChild(fin);
    var d1=sv('circle',{r:7,fill:'var(--s1)',stroke:'#07120D','stroke-width':2,visibility:'hidden'}),d2=sv('circle',{r:7,fill:'var(--s2)',stroke:'#07120D','stroke-width':2,visibility:'hidden'});
    svg.appendChild(d2);svg.appendChild(d1);card.appendChild(svg);
    return function(d){
      [[d1,me],[d2,cmp]].forEach(function(pair){if(!pair[1])return;if(d==null){pair[0].setAttribute('visibility','hidden');return}
        var x=at(pair[1].pts,d,'x'),z=at(pair[1].pts,d,'z');if(x==null)return;var q=P([x,z]);pair[0].setAttribute('cx',q[0]);pair[0].setAttribute('cy',q[1]);pair[0].setAttribute('visibility','visible')});
    };
  }

  // ---------------------------------------------------------------- line chart (x = distance along the stage)
  function lineChart(parent, title, h, series, L, o){
    var wrap=el('div',{class:'chart'});parent.appendChild(wrap);wrap.appendChild(el('div',{class:'t'},title));
    var W=Math.max(320,parent.clientWidth||900),ml=56,mr=14,mt=22,mb=o.xAxis?24:6;
    var svg=sv('svg',{width:'100%',height:h+mt+mb,viewBox:'0 0 '+W+' '+(h+mt+mb),preserveAspectRatio:'none'});wrap.appendChild(svg);
    var vals=[];series.forEach(function(s){s.pts.forEach(function(p){if(p[s.key]!=null)vals.push(p[s.key])})});
    var lo=o.min!=null?o.min:Math.min.apply(null,vals),hi=o.max!=null?o.max:Math.max.apply(null,vals);
    if(o.zero){var m=Math.max(Math.abs(lo),Math.abs(hi))||1;if(o.min==null){lo=Math.min(lo,0);hi=Math.max(hi,0)}else{lo=o.min;hi=o.max}}
    if(hi===lo)hi=lo+1;
    var pw=W-ml-mr;
    function X(d){return ml+d/L*pw}function Y(v){return mt+h-(v-lo)/(hi-lo)*h}
    // grid + ticks (recessive)
    if(!o.noTicks){for(var i=0;i<=3;i++){var v=lo+(hi-lo)*i/3,y=Y(v);svg.appendChild(sv('line',{x1:ml,x2:W-mr,y1:y,y2:y,stroke:'var(--grid)','stroke-width':1}));
      var tx=sv('text',{x:ml-8,y:y+4,'text-anchor':'end'});tx.textContent=Math.abs(hi-lo)<10?v.toFixed(1):Math.round(v);svg.appendChild(tx)}}
    if(o.zero){svg.appendChild(sv('line',{x1:ml,x2:W-mr,y1:Y(0),y2:Y(0),stroke:'var(--axis)','stroke-width':1}))}
    svg.appendChild(sv('line',{x1:ml,x2:W-mr,y1:mt+h,y2:mt+h,stroke:'var(--axis)','stroke-width':1}));
    if(o.xAxis){for(var km=0;km<=L/1000;km+=L>8000?2:1){var t2=sv('text',{x:X(km*1000),y:mt+h+17,'text-anchor':'middle'});t2.textContent=km+' km';svg.appendChild(t2)}}
    series.slice().reverse().forEach(function(s){   // first series (this run) is drawn last, on top
      var pts=s.pts.filter(function(p){return p[s.key]!=null});
      var d=pts.map(function(p,j){return(j?'L':'M')+X(p.d).toFixed(1)+','+Y(p[s.key]).toFixed(1)}).join('');
      if(s.area)svg.appendChild(sv('path',{d:d+'L'+X(pts[pts.length-1].d).toFixed(1)+','+Y(lo)+'L'+X(pts[0].d).toFixed(1)+','+Y(lo)+'Z',fill:s.color,opacity:.18}));
      svg.appendChild(sv('path',{d:d,fill:'none',stroke:s.color,'stroke-width':2,'stroke-linejoin':'round','vector-effect':'non-scaling-stroke'}));
    });
    var cross=sv('line',{y1:mt,y2:mt+h,stroke:'var(--soft)','stroke-width':1,visibility:'hidden','vector-effect':'non-scaling-stroke'});svg.appendChild(cross);
    return {
      cross:function(d){if(d==null){cross.setAttribute('visibility','hidden');return}cross.setAttribute('x1',X(d));cross.setAttribute('x2',X(d));cross.setAttribute('visibility','visible')},
      dAt:function(clientX){var r=svg.getBoundingClientRect();var x=(clientX-r.left)/r.width*W;if(x<ml||x>W-mr)return null;return(x-ml)/pw*L},
      xOf:function(d){var r=svg.getBoundingClientRect();return X(d)/W*r.width}
    };
  }
})();
</script>
</body>
</html>`;
}
