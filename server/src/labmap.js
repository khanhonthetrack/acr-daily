// EXPERIMENTAL (/lab/map): today's two stages on real satellite imagery, with the drivers on stage moving on it; with
// ?event=<id>, a league event's stages instead (a cup match followed live: the cup page's Watch link), each a tab,
// following the stage its drivers are on (/api/events/<id>/live).
// Each stage's route is in game metres; GEO_FITS (geofits.js, made by tools/gamefiles/geo, see its README) holds
// where the start line is on Earth and how the stage is turned, so a game point (x, z) becomes a latitude and
// longitude. Imagery: Esri World Imagery (free with attribution for this non-commercial use), OpenTopoMap as the
// other layer. Not linked from the site yet: a page to try things on.
import { FAVICON } from './logo.js';
import { GEO_FITS } from './geofits.js';

export function labMapPage() {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>ACR Daily Satellite</title>
<meta name="description" content="Experimental: today's ACR Daily stages and the drivers on them, on satellite imagery.">
<meta name="robots" content="noindex">
<link rel="icon" href="${FAVICON}">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#0A0A0B;--line:#1F1F23;--fg:#F4F4F5;--fg2:#A1A1AA;--fg3:#6B6B74;--acc:#E30613}
*{box-sizing:border-box;margin:0}
html,body{height:100%;background:var(--bg);color:var(--fg);font:14px/1.4 Barlow,system-ui,sans-serif}
#map{position:fixed;inset:0;background:#111}
.bar{position:fixed;left:0;right:0;top:0;z-index:1000;display:flex;align-items:center;gap:8px;flex-wrap:wrap;
  padding:calc(8px + env(safe-area-inset-top)) 12px 8px;background:linear-gradient(#0A0A0BEE,#0A0A0B99 70%,#0A0A0B00)}
.bar a.home{font:700 18px/1 'Barlow Condensed',sans-serif;letter-spacing:.06em;text-decoration:none;color:var(--fg)}
.bar a.back{font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;text-transform:uppercase;text-decoration:none;
  color:var(--fg);background:#0A0A0BCC;border:1px solid #2B2B31;border-radius:4px;padding:8px 10px}
.bar a.back:hover{border-color:var(--acc);color:var(--acc)}
.lab{font:700 11px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;color:var(--acc);border:1px solid var(--acc);border-radius:3px;padding:2px 5px}
.tabs{display:flex;gap:6px;margin-left:auto}
.tabs button{font:600 14px/1 'Barlow Condensed',sans-serif;letter-spacing:.06em;color:var(--fg2);background:#0A0A0BCC;
  border:1px solid #2B2B31;border-radius:4px;padding:7px 10px;cursor:pointer}
.tabs button.on{background:var(--acc);border-color:var(--acc);color:#fff}
.tabs select{font:600 13px/1 Barlow,sans-serif;color:var(--fg2);background:#0A0A0BCC;border:1px solid #2B2B31;border-radius:4px;padding:6px;max-width:150px}
.info{position:fixed;left:12px;right:12px;bottom:calc(12px + env(safe-area-inset-bottom));z-index:1000;max-width:520px;
  background:#0A0A0BE6;border:1px solid var(--line);border-radius:6px;padding:10px 12px}
.info h1{font:700 22px/1.1 'Barlow Condensed',sans-serif;letter-spacing:.02em}
.info .sub{color:var(--fg2);font-size:13px}
.info .who{margin-top:6px;display:flex;flex-wrap:wrap;gap:4px 12px;font-size:13px}
.info .who span b{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;vertical-align:0}
.info .note{margin-top:6px;color:var(--fg3);font-size:12px}
.info button{font:600 12px/1 Barlow,sans-serif;color:var(--fg);background:none;border:1px solid #2B2B31;border-radius:4px;padding:5px 8px;margin-top:8px;cursor:pointer}
.car{border-radius:50%;border:2px solid #fff;box-shadow:0 0 0 2px #0008;background:#888 center/cover no-repeat}
.car.finished{border-color:#F4F4F5}.car.dnf{border-color:#FF453A}
.tag{font:600 12px/1 Barlow,sans-serif;color:#fff;text-shadow:0 1px 2px #000,0 0 4px #000;white-space:nowrap}
.flag{font:700 11px/1 'Barlow Condensed',sans-serif;color:#fff;background:var(--acc);padding:2px 4px;border-radius:2px}
.leaflet-control-attribution{font-size:10px}
.leaflet-top{top:calc(52px + env(safe-area-inset-top))}   /* below the bar */
@media (max-width:480px){.bar a.home{display:none}.tabs select{max-width:96px}.tabs button{padding:7px 8px}.lab{display:none}}
</style>
</head>
<body>
<div id="map"></div>
<div class="bar"><a class="back" id="back" href="/" aria-label="Back">‹ Back</a><a class="home" href="/">ACR DAILY</a><span class="lab">EXPERIMENTAL</span>
  <div class="tabs"><button id="t1" class="on" data-s="1">SS1</button><button id="t2" data-s="2">SS2</button>
  <select id="pick" aria-label="Another stage"><option value="">Other stages…</option></select></div></div>
<div class="info" id="info"><h1>Loading…</h1></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script>
// Back: to the page you came from on this site (keeps its place), else the home page
document.getElementById('back').onclick=function(e){
  try{if(document.referrer&&new URL(document.referrer).origin===location.origin&&history.length>1){e.preventDefault();history.back()}}catch(_){}
};
var FITS=${JSON.stringify(GEO_FITS)};
var PAL=['#5BA8FF','#FF7AB6','#4CD6C0','#FF9F43','#B48CFF','#7BE07B','#FFD60A','#3DD5F3','#F2A0FF','#C8E06B'];
// a colour each (by Steam id, the next free one on a clash); one bought in the shop (chosen: {steamId: colour}) first
function colours(ids,chosen){chosen=chosen||{};var out={},used={};
  ids.forEach(function(id){if(chosen[id]){out[id]=chosen[id];var c=PAL.indexOf(chosen[id]);if(c>=0)used[c]=1}});
  ids.slice().sort().forEach(function(id){if(out[id])return;var k=Number(String(id).slice(-6))%PAL.length;
  for(var n=0;n<PAL.length&&used[k];n++)k=(k+1)%PAL.length;used[k]=1;out[id]=PAL[k]});return out}
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}

// game metres (x, z) -> [lat, lon]: mirror, turn by rotDeg (metres east / north), then from where (0, 0) is
function toLL(fit,x,z){
  var k=fit.scale||1,xm=(fit.mirror==='x'?-x:x)*k,zm=(fit.mirror==='z'?-z:z)*k;   // scale: a stage built a bit off 1:1
  var a=fit.rotDeg*Math.PI/180,c=Math.cos(a),s=Math.sin(a);
  var e=xm*c-zm*s,n=xm*s+zm*c;
  return [fit.lat+n/111132.954,fit.lon+e/(111319.49*Math.cos(fit.lat*Math.PI/180))];
}

var map=L.map('map',{zoomControl:false,attributionControl:true});
L.control.zoom({position:'topright'}).addTo(map);
var sat=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  {maxZoom:19,attribution:'Imagery &copy; Esri, Maxar, Earthstar Geographics'}).addTo(map);
var topo=L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
  {maxZoom:17,attribution:'&copy; OpenStreetMap contributors, SRTM | OpenTopoMap (CC-BY-SA)'});
L.control.layers({'Satellite':sat,'Topo':topo},null,{position:'topright'}).addTo(map);
map.setView([50,5],4);

var stages={},slot=1,layer=L.layerGroup().addTo(map),cars={},demo=/[?&]demo=1/.test(location.search),demoT0=Date.now(),fitted={};
function route(ch){return (ch&&ch.route)||[]}
var EV=(new URLSearchParams(location.search).get('event')||'').replace(/\\D/g,''),EVNAME='',FOLLOW=true,ELSE=[];
function show(s){   // s: 1 or 2 (today's dailies, with live drivers; an event's SS1, SS2...) or 0 (a stage from the picker, no drivers)
  slot=s;[].forEach.call(document.querySelectorAll('.tabs button'),function(b){b.className=+b.getAttribute('data-s')===s?'on':''});
  var pk=document.getElementById('pick');if(s&&pk)pk.value='';
  layer.clearLayers();cars={};
  var ch=stages[s],fit=ch&&FITS[ch.track];
  var info=document.getElementById('info');
  if(!ch){info.innerHTML='<h1>No stage</h1>';return}
  if(EV&&s&&!ch.route){fetch('/api/route?track='+encodeURIComponent(ch.track)).then(function(r){return r.json()}).then(function(j){ch.route=j.route||[];if(slot===s)show(s)})
    .catch(function(){ch.route=[];if(slot===s)show(s)});info.innerHTML='<h1>Loading…</h1>';return}
  var head='<h1>'+(s?'SS'+s+' · ':'')+''+esc(ch.menuName||ch.stageName||ch.track)+'</h1><div class="sub">'+[EVNAME,ch.rally,ch.lengthM?(ch.lengthM/1000).toFixed(1)+' km':'',ch.car].filter(Boolean).map(esc).join(' · ')+'</div>';
  if(!fit||!fit.ok){info.innerHTML=head+'<div class="note">This stage is not lined up with the real map yet'+(fit?' (fit off by about '+Math.round(fit.p90M)+' m)':'')+'.</div>';
    map.setView(fit?[fit.lat,fit.lon]:[50,5],fit?13:4);return}
  var pts=route(ch).map(function(p){return toLL(fit,p[0],p[1])});
  L.polyline(pts,{color:'#000',weight:7,opacity:.45}).addTo(layer);
  L.polyline(pts,{color:'#E30613',weight:4}).addTo(layer);
  L.marker(pts[0],{icon:L.divIcon({className:'',html:'<span class="flag">START</span>',iconAnchor:[18,8]})}).addTo(layer);
  L.marker(pts[pts.length-1],{icon:L.divIcon({className:'',html:'<span class="flag">FINISH</span>',iconAnchor:[20,8]})}).addTo(layer);
  var q='<div class="note">'+(fit.p90M>25?'Roughly lined up (the game changed parts of this road)':'Lined up with the real roads')+': half the route within '+Math.round(fit.medianM)+' m, 90 % within '+Math.round(fit.p90M)+' m.</div>';
  info.innerHTML=head+q+'<div class="who" id="who"></div><div class="note" id="note">'+(s?'Nobody on this stage right now.':'')+'</div>'+
    '<button id="demo">'+(demo?'Stop the demo':'Show demo cars')+'</button>';
  document.getElementById('demo').onclick=function(){demo=!demo;demoT0=Date.now();show(slot);tick()};
  // the whole route in view, clear of the top bar and the info box
  map.fitBounds(L.latLngBounds(pts),{paddingTopLeft:[30,70],paddingBottomRight:[30,info.offsetHeight+30]});
  tick();
}
function carIcon(d,col){
  var R=d.avatar?13:8,fr=d.look&&d.look.frame,ring=fr?'border-color:'+fr.color+';border-width:'+fr.width+'px;'+(fr.dash?'border-style:dashed;':''):'border-color:'+col+';';
  return L.divIcon({className:'',iconSize:[2*R,2*R],iconAnchor:[R,R],
    html:'<div class="car '+esc(d.state||'')+'" style="width:'+2*R+'px;height:'+2*R+'px;'+ring+(d.avatar?'background-image:url('+esc(d.avatar)+')':'background:'+col)+'"></div>'+
      '<div class="tag" style="position:absolute;left:'+(2*R+4)+'px;top:'+(R-7)+'px">'+esc((d.look&&d.look.tag?'['+d.look.tag.text+'] ':'')+(d.look&&d.look.badge?d.look.badge+' ':'')+d.name)+'</div>'});
}
function place(list){
  var ch=stages[slot],fit=ch&&FITS[ch.track];if(!fit||!fit.ok)return;
  var chosen={};list.forEach(function(d){if(d.look&&d.look.color)chosen[d.steamId]=d.look.color});   // (the shop)
  var col=colours(list.map(function(d){return d.steamId}),chosen),seen={};
  list.forEach(function(d){
    seen[d.steamId]=1;var ll=toLL(fit,d.x,d.z),m=cars[d.steamId];
    if(!m){m=cars[d.steamId]=L.marker(ll,{icon:carIcon(d,col[d.steamId]),zIndexOffset:1000}).addTo(layer)}else m.setLatLng(ll);
  });
  Object.keys(cars).forEach(function(id){if(!seen[id]){layer.removeLayer(cars[id]);delete cars[id]}});
  var who=document.getElementById('who'),note=document.getElementById('note');
  if(who)who.innerHTML=list.map(function(d){return '<span><b style="background:'+col[d.steamId]+'"></b>'+esc(d.name)+
    (d.state==='finished'?' · finished':d.state==='dnf'?' · DNF':' · '+Math.round((d.progress||0)*100)+' %')+'</span>'}).join('');
  if(note)note.textContent=(list.length?(demo?'Demo cars: not real drivers.':''):'Nobody on this stage right now.')+
    (ELSE.length?' '+ELSE.map(function(d){return d.name+' is on SS'+(d.stageNo+1)+(d.state==='live'?' ('+Math.round(100*d.progress)+' %)':d.state==='finished'?' (finished)':' (DNF)')}).join(', ')+'.':'');
}
function demoCars(){   // three made-up drivers going round the route at slightly different paces
  var r=route(stages[slot]);if(r.length<2)return [];
  var t=(Date.now()-demoT0)/1000;
  return [['Demo A',0.010,0.05,'7000001'],['Demo B',0.009,0.30,'7000004'],['Demo C',0.011,0.55,'7000007']].map(function(c){
    var p=(c[2]+t*c[1]/10)%1,i=Math.min(r.length-1,Math.floor(p*(r.length-1)));
    return {steamId:c[3],name:c[0],x:r[i][0],z:r[i][1],progress:p,state:'live'};
  });
}
var busy=false,n=0,anyCars=false,BUSY=5,IDLE=15;   // seconds between polls (the server's timing, from today's dailies)
function tick(){
  if(demo){place(demoCars());return}
  if(!slot)return;
  if(busy)return;busy=true;
  if(EV){   // an event: its drivers on the stage shown; the first time someone is on another stage, that one shown
    fetch('/api/events/'+EV+'/live').then(function(r){return r.json()}).then(function(j){var l=j.drivers||[];anyCars=l.length>0;
      var on=l.filter(function(d){return d.state==='live'});
      if(FOLLOW&&on.length&&on[0].stageNo+1!==slot&&stages[on[0].stageNo+1]){FOLLOW=false;busy=false;show(on[0].stageNo+1);return}
      if(on.length)FOLLOW=false;
      ELSE=l.filter(function(d){return d.stageNo+1!==slot});place(l.filter(function(d){return d.stageNo+1===slot}))})
      .catch(function(){}).then(function(){busy=false});
    return}
  fetch('/api/live?slot='+slot).then(function(r){return r.json()}).then(function(j){var l=j.drivers||[];anyCars=l.length>0;place(l)})
    .catch(function(){}).then(function(){busy=false});
}
// every BUSY s while someone is on the stage, every IDLE s otherwise; nothing while the tab is hidden
setInterval(function(){if(!document.hidden&&n++%(anyCars?BUSY:IDLE)===0)tick()},1000);
setInterval(function(){if(demo)tick()},200);
var pick=document.getElementById('pick');
Object.keys(FITS).sort(function(a,b){return (FITS[b].ok-FITS[a].ok)||a.localeCompare(b)}).forEach(function(t){
  var o=document.createElement('option');o.value=t;o.textContent=t+(FITS[t].ok?'':' (not lined up)');pick.appendChild(o)});
pick.onchange=function(){var t=pick.value;if(!t)return;
  fetch('/api/route?track='+encodeURIComponent(t)).then(function(r){return r.json()}).then(function(j){
    stages[0]={track:t,menuName:t,car:'',route:j.route||[]};fitted[0]=0;show(0)})};
document.getElementById('t1').onclick=function(){FOLLOW=false;show(1)};
document.getElementById('t2').onclick=function(){FOLLOW=false;show(2)};
if(EV){   // a league event (a cup match): a tab a stage
  fetch('/api/events/'+EV).then(function(r){if(!r.ok)throw r;return r.json()}).then(function(ev){
    EVNAME=ev.name;document.title=ev.name+' · ACR Daily';var tabs=document.querySelector('.tabs');tabs.innerHTML='';
    ev.stages.forEach(function(s,k){stages[k+1]={track:s.track,menuName:s.name,lengthM:s.lengthM,rally:ev.rally,car:ev.car||(ev.carClass?ev.carClass+' class':''),route:null};
      var b=document.createElement('button');b.textContent='SS'+(k+1);b.setAttribute('data-s',k+1);b.onclick=function(){FOLLOW=false;show(k+1)};tabs.appendChild(b)});
    var bk=document.getElementById('back');bk.href=ev.league&&ev.league.kind==='cup'?'/cup/'+ev.league.id:'/e/'+ev.id;
    show(1)}).catch(function(){document.getElementById('info').innerHTML='<h1>No such event</h1>'});
}else fetch('/api/challenges/today').then(function(r){return r.json()}).then(function(j){
  (j.challenges||[]).forEach(function(c){stages[c.slot]=c;if(c.timing){BUSY=c.timing.livePollS;IDLE=c.timing.liveIdleS}});
  var want=new URLSearchParams(location.search).get('stage');   // ?stage=<name>: open that stage
  if(want&&FITS[want]){pick.value=want;pick.onchange()}else show(/[?&]ss=2/.test(location.search)?2:1);
}).catch(function(){document.getElementById('info').innerHTML='<h1>Could not load today\\'s stages</h1>'});
</script>
</body>
</html>`;
}
