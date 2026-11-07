// The stage map, as the home page draws each daily and the time trial's page each of its stages (src/site.js,
// src/timetrialpage.js): the route turned to fill its box (north up when the stage is lined up with the real roads,
// src/geofits.js), its start and finish, the drivers on it live (each in their own colour, with their flag and name,
// gliding along the road a few seconds late: src/glide.js), and a satellite thumbnail in the corner.
// STAGE_MAP_JS goes inside a page's script, which defines el(tag, cls, text), sv(tag, attrs) (an SVG element) and
// `maps` ({slot: {m: drawMap's map, slot}}: the maps whose cars the frame loop moves); STAGE_MAP_CSS in its style.

import { TM_JS } from './tmtext.js';
import { EARTH_JS } from './earth.js';
import { GLIDE_JS } from './glide.js';

export const STAGE_MAP_CSS = `
/* map */
.map{position:relative;aspect-ratio:16/9;margin:18px 0 10px}
.map svg{position:absolute;inset:0;width:100%;height:100%;overflow:visible}
.map .route{fill:none;stroke:#55555E;stroke-width:2.5;stroke-linejoin:round;stroke-linecap:round}
.map .done{fill:none;stroke:var(--fg);stroke-width:1.5;stroke-linejoin:round;stroke-linecap:round}
/* the stage's real place: a satellite thumbnail in the map's corner, the way to the live satellite view */
.satbtn{position:absolute;right:0;bottom:0;z-index:2;width:92px;height:92px;border-radius:6px;overflow:hidden;
  border:1px solid var(--line2);background:#16161a;text-decoration:none;box-shadow:0 2px 10px #0009;transition:border-color .15s}
.satbtn img,.satbtn svg{position:absolute;inset:0;width:100%;height:100%}
.satbtn img{object-fit:cover;filter:saturate(.9) brightness(.9)}
.satbtn svg polyline{fill:none;stroke:var(--acc);stroke-width:2.2;stroke-linejoin:round;stroke-linecap:round;vector-effect:non-scaling-stroke}
.satbtn span{position:absolute;left:0;right:0;bottom:0;padding:14px 0 5px;text-align:center;font:700 10px/1 'Barlow Condensed',sans-serif;
  letter-spacing:.16em;color:#fff;background:linear-gradient(transparent,#000c)}
.satbtn:hover,.satbtn:focus-visible{border-color:var(--acc)}
.satbtn:hover span{color:var(--acc)}
@media (max-width:700px){.satbtn{width:74px;height:74px}}
.dot text{font:600 12px 'Barlow Condensed',sans-serif;letter-spacing:.04em;fill:var(--fg);paint-order:stroke;stroke:var(--bg);stroke-width:4px}
.mark{font:600 10px 'Barlow Condensed',sans-serif;letter-spacing:.14em;fill:var(--fg3)}
`;

export const STAGE_MAP_JS = `
  // ---- stage map: route rotated to fill the frame; a projector for the live dots
  function drawMap(box,raw,g,corner){   // corner: px kept clear at the bottom right (the satellite button)
    box.innerHTML='';
    if(!raw||raw.length<2)return null;
    // a stage lined up with the real roads (g, geofits.js) is drawn as it is on Earth: the game's coordinates are a
    // mirror image of it. North up when that still fills the box well, else turned to fill it (never mirrored).
    var T=earthScreen(g);
    var pts=raw.map(T);
    var W=640,H=360,pad=28,mx=0,mz=0,i;for(i=0;i<pts.length;i++){mx+=pts[i][0];mz+=pts[i][1]}mx/=pts.length;mz/=pts.length;
    var sxx=0,szz=0,sxz=0;for(i=0;i<pts.length;i++){var dx=pts[i][0]-mx,dz=pts[i][1]-mz;sxx+=dx*dx;szz+=dz*dz;sxz+=dx*dz}
    function fitFor(a){var c=Math.cos(a),s=Math.sin(a),x0=1e9,x1=-1e9,y0=1e9,y1=-1e9;
      pts.forEach(function(p){var x=(p[0]-mx)*c-(p[1]-mz)*s,y=(p[0]-mx)*s+(p[1]-mz)*c;x0=Math.min(x0,x);x1=Math.max(x1,x);y0=Math.min(y0,y);y1=Math.max(y1,y)});
      return {a:a,c:c,s:s,x0:x0,x1:x1,y0:y0,y1:y1,k:Math.min((W-2*pad)/(x1-x0||1),(H-2*pad)/(y1-y0||1))}}
    var f=fitFor(-0.5*Math.atan2(2*sxz,sxx-szz));
    if(g){var up=fitFor(0);if(up.k>=0.75*f.k)f=up}
    var c=f.c,s=f.s,k,ox,oy;
    function place(Wa){k=Math.min((Wa-2*pad)/(f.x1-f.x0||1),(H-2*pad)/(f.y1-f.y0||1));ox=(Wa-(f.x1-f.x0)*k)/2-f.x0*k;oy=(H-(f.y1-f.y0)*k)/2-f.y0*k}
    function Pt(p){var x=(p[0]-mx)*c-(p[1]-mz)*s,y=(p[0]-mx)*s+(p[1]-mz)*c;return[x*k+ox,y*k+oy]}
    place(W);
    if(corner&&box.clientWidth){   // the route would run under the button: draw it in the width left of it
      var r=(corner+8)*W/box.clientWidth;
      if(pts.some(function(p){var q=Pt(p);return q[0]>W-r&&q[1]>H-r}))place(W-r);
    }
    function P(p){return Pt(T(p))}   // game (x, z): the live cars
    var line=pts.map(function(p){var q=Pt(p);return q[0].toFixed(1)+','+q[1].toFixed(1)}).join(' ');
    var svg=sv('svg',{viewBox:'0 0 '+W+' '+H,role:'img','aria-label':'Stage map'});
    svg.appendChild(sv('polyline',{points:line,class:'route'}));
    var A=Pt(pts[0]),Z=Pt(pts[pts.length-1]);
    // start: a short bar across the road; finish: a small chequer
    svg.appendChild(sv('circle',{cx:A[0],cy:A[1],r:4,fill:'#F4F4F5'}));
    var ts=sv('text',{x:A[0]+9,y:A[1]+4,class:'mark'});ts.textContent='START';svg.appendChild(ts);
    var fin=sv('g',{transform:'translate('+(Z[0]-6)+','+(Z[1]-6)+')'});
    fin.appendChild(sv('rect',{width:12,height:12,fill:'#F4F4F5'}));fin.appendChild(sv('rect',{width:6,height:6,fill:'#0A0A0B'}));fin.appendChild(sv('rect',{x:6,y:6,width:6,height:6,fill:'#0A0A0B'}));
    svg.appendChild(fin);
    var tf=sv('text',{x:Z[0]+10,y:Z[1]+4,class:'mark'});tf.textContent='FINISH';svg.appendChild(tf);
    var dots=sv('g');svg.appendChild(dots);box.appendChild(svg);
    return {P:P,dots:dots,nodes:{},trk:routeTrack(raw)};
  }

  // ---- live cars: each driver has their own colour (same as in the app), a flag and a name; they move along the road,
  // a few seconds late (src/glide.js). Finished = white ring, retired = red ring.
  var PAL=['#5BA8FF','#FF7AB6','#4CD6C0','#FF9F43','#B48CFF','#7BE07B','#FFD60A','#3DD5F3','#F2A0FF','#C8E06B'];
  // a different colour for everyone on stage (by Steam id, next free one on a clash); a colour bought in the shop
  // (chosen: {steamId: colour}) comes first
  function colours(ids,chosen){chosen=chosen||{};var out={},used={};
    ids.forEach(function(id){if(chosen[id]){out[id]=chosen[id];var c=PAL.indexOf(chosen[id]);if(c>=0)used[c]=1}});
    ids.slice().sort().forEach(function(id){if(out[id])return;var k=Number(String(id).slice(-6))%PAL.length;
      for(var n=0;n<PAL.length&&used[k];n++)k=(k+1)%PAL.length;used[k]=1;out[id]=PAL[k]});return out}
  // a look from the shop: a name in its colour (or gradient)
  function paint(e,l){if(!l)return;if(l.grad){e.style.backgroundImage='linear-gradient(90deg,'+l.grad.join(',')+')';
    e.style.webkitBackgroundClip='text';e.style.backgroundClip='text';e.style.color='transparent'}else if(l.color)e.style.color=l.color}
  // a team's tag in its colour before the name (src/drivers.js)
  ${TM_JS}
  function tagEl(p,l){if(!l||!l.tag)return;tmInto(p,l.tag.fmt,l.tag.text,l.tag.color,'teamtag')}
  ${GLIDE_JS}
  // a driver's label on the map: their team's tag in its colours ([TAG] as tspans), then their badge and name
  function dotLabel(tx,d,colour){while(tx.firstChild)tx.removeChild(tx.firstChild);tx.style.fill=colour;var t=d.look&&d.look.tag;
    if(t){tx.appendChild(document.createTextNode('['));(t.fmt?tmSpans(t.fmt):[{t:t.text}]).forEach(function(x){var s=sv('tspan',x.b?{'font-weight':'800'}:{});
        s.textContent=x.u?x.t.toUpperCase():x.t;s.style.fill=x.c||t.color;tx.appendChild(s)});tx.appendChild(document.createTextNode('] '))}
    tx.appendChild(document.createTextNode((d.look&&d.look.badge?d.look.badge+' ':'')+d.name))}
  var RING={live:'#0A0A0B',finished:'#F4F4F5',dnf:'#FF453A'};
  // each map's playback (by slot); one frame loop moves every car. LIVE_DELAY: how late the cars run (an update of the
  // app's and a check of ours always ahead of them); LIVE_GAP: updates further apart are not driven between
  var PB={},LIVE_DELAY=9000,LIVE_GAP=15000,raf=0;
  function drawLive(x,data,srvNow){
    var chosen={};data.drivers.forEach(function(d){if(d.look&&d.look.color)chosen[d.steamId]=d.look.color});
    var m=x.m,col=colours(data.drivers.map(function(d){return d.steamId}),chosen);
    if(!m)return;
    var pb=PB[x.slot]||(PB[x.slot]=livePlayback(LIVE_DELAY,LIVE_GAP));
    pb.feed(data.drivers,srvNow||Date.now(),Date.now());
    data.drivers.forEach(function(d){
      var g=m.nodes[d.steamId];
      if(!g){g=sv('g',{class:'dot'});
        // the Steam avatar in a circle, ringed in the driver's colour (a plain coloured dot without an avatar)
        var R=d.avatar?11:6;g.appendChild(sv('circle',{r:R+2,'stroke-width':1.5}));
        if(d.avatar){var cid='av'+d.steamId+'s'+x.slot;var cp=sv('clipPath',{id:cid});cp.appendChild(sv('circle',{r:R}));g.appendChild(cp);
          var av=sv('image',{x:-R,y:-R,width:2*R,height:2*R,'clip-path':'url(#'+cid+')',preserveAspectRatio:'xMidYMid slice'});av.setAttribute('href',d.avatar);g.appendChild(av)}
        if(d.country){var im=sv('image',{x:R+6,y:-6,width:18,height:12,preserveAspectRatio:'xMidYMid slice'});im.setAttribute('href','https://flagcdn.com/w40/'+d.country+'.png');g.appendChild(im)}
        g.appendChild(sv('text',{x:d.country?R+28:R+6,y:4}));m.dots.appendChild(g);m.nodes[d.steamId]=g}
      g.col=col[d.steamId];g.fr=d.look&&d.look.frame;g.st=null;   // (its ring: the next frame)
      dotLabel(g.lastChild,d,col[d.steamId]);
    });
    if(!raf)raf=requestAnimationFrame(frame);
  }
  // ring: driver colour on stage (or their frame from the shop), white once finished, red when retired
  function ring(g,state){if(g.st===state)return;g.st=state;var fr=g.fr,live=state==='live';
    g.firstChild.setAttribute('fill',g.col);g.firstChild.setAttribute('stroke',live?(fr?fr.color:g.col):RING[state]||RING.live);
    g.firstChild.setAttribute('stroke-width',live&&fr?fr.width:1.5);g.firstChild.setAttribute('stroke-dasharray',live&&fr&&fr.dash?'3 2':'')}
  // every frame while there are cars: each where its playback has it (a car whose updates are all shown and that is
  // off the server's list goes)
  function frame(){var now=Date.now(),any=false;raf=0;
    Object.keys(maps).forEach(function(slot){var m=maps[slot].m,pb=PB[slot];if(!m||!pb)return;
      Object.keys(m.nodes).forEach(function(id){var g=m.nodes[id],st=pb.at(id,now);
        if(!st){g.remove();delete m.nodes[id];return}
        any=true;ring(g,st.state);var q=m.P(m.trk.at(st.p));
        g.setAttribute('transform','translate('+q[0].toFixed(2)+','+q[1].toFixed(2)+')')})});
    if(any)raf=requestAnimationFrame(frame)}

  // ---- the real place: satellite thumbnail of the stage (Esri World Imagery) with the route on it, linking the
  // satellite view (today: live drivers on it). Only for stages lined up with the real roads (geofits.js).
  ${EARTH_JS}
  function mercY(lat){return Math.log(Math.tan(Math.PI/4+lat*Math.PI/360))}
  function satButton(box,ch,live){   // live: the stage is on today (the satellite view follows its drivers)
    var g=EARTH[ch.track],r=ch.route;if(!g||!r||r.length<2)return;
    var step=Math.max(1,Math.floor(r.length/120)),pts=[];
    for(var i=0;i<r.length;i+=step)pts.push(earthLL(g,r[i]));pts.push(earthLL(g,r[r.length-1]));
    var la0=1e9,la1=-1e9,lo0=1e9,lo1=-1e9;pts.forEach(function(p){la0=Math.min(la0,p[0]);la1=Math.max(la1,p[0]);lo0=Math.min(lo0,p[1]);lo1=Math.max(lo1,p[1])});
    // a square around the route (in metres), with a margin
    var cl=(la0+la1)/2,mx=Math.cos(cl*Math.PI/180),h=(la1-la0)*111132.954,w=(lo1-lo0)*111319.49*mx,half=Math.max(h,w)*0.6+150;
    var dla=half/111132.954,dlo=half/(111319.49*mx),clo=(lo0+lo1)/2;
    la0=cl-dla;la1=cl+dla;lo0=clo-dlo;lo1=clo+dlo;
    var a=el('a','satbtn');a.title='The stage on satellite imagery'+(live?', with the drivers on it live':'');
    a.href=live?'/lab/map?ss='+ch.slot:'/lab/map?stage='+encodeURIComponent(ch.track);
    var img=el('img');img.alt='';img.loading='lazy';
    img.src='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?bbox='+[lo0,la0,lo1,la1].map(function(v){return v.toFixed(5)}).join(',')+
      '&bboxSR=4326&imageSR=3857&size=184,184&format=jpg&f=image';
    a.appendChild(img);
    var y0=mercY(la0),y1=mercY(la1),svg=sv('svg',{viewBox:'0 0 100 100',preserveAspectRatio:'none'});
    svg.appendChild(sv('polyline',{points:pts.map(function(p){return ((p[1]-lo0)/(lo1-lo0)*100).toFixed(1)+','+((y1-mercY(p[0]))/(y1-y0)*100).toFixed(1)}).join(' ')}));
    a.appendChild(svg);a.appendChild(el('span',null,'SATELLITE'));box.appendChild(a);
  }
`;
