// The live map of a league event, a rally or a cup's round, as the home page draws each daily (src/stagemap.js): a tab
// a stage, the one its drivers are on shown (until a tab is clicked), the drivers on it live in their own colours, and
// the satellite thumbnail in the corner, the way to the stage on satellite imagery with the drivers on it (/lab/map).
// Drawn on the event's page (/e/:id), a championship's page (/l/:id: each open round) and a cup's (/cup/:id: the
// round's matches together, as they all race the same stages).
// The map only to a viewer who sees the stages: everyone while the event shows them; while it hides them (src/hidden.js),
// its league's staff and the drivers who pressed DRIVE (privateMap: a line says the others don't see it). Everyone else
// gets, in its place, who is on which stage (SS2: their names; nothing there tells the stage) and why there is no map.
// The weather and the time of day never show on it, so it is drawn whatever else the event hides; times hidden,
// nobody's time shows either.
// Data: GET /api/events/:id/live or /api/cups/:id/live -> {now, stages: [{no, track, name}] | null (hidden from this
// viewer), count (stages), privateMap, timing, drivers}.
// EVENT_LIVE_JS goes inside a page's script that has the shell's helpers (el, add, api, P, FN: src/leaguepages.js);
// liveMap(box, {url, sat(no) -> the satellite view's link, title (text or elements), names: [stage names], on() -> poll
// now?, onData(answer), secret: why there is no map while the stages are hidden (the event's words by default)}).

import { tq, tqp } from './i18n.js';
import { STAGE_MAP_CSS, STAGE_MAP_JS } from './stagemap.js';

export const EVENT_LIVE_CSS = `${STAGE_MAP_CSS}
.evlive{margin-top:22px}
.evlive[hidden]{display:none}
.evlive .lh{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.evlive .lt{font:700 12px/1 'Barlow Condensed',sans-serif;letter-spacing:.16em;color:var(--fg)}
.evlive .lt a{text-decoration:none}.evlive .lt a:hover{color:var(--acct,#FF4655)}
.evlive .pulse{display:none;width:7px;height:7px;border-radius:50%;background:var(--line2)}
.evlive.on .pulse{display:inline-block}
/* nobody on a stage: the map folded away (a 16:9 box the page's width, 648 px tall and empty, pushed the standings down
   to 2,000 px: a UI review, Nov 2026); it opens by itself when someone starts, or with Show the map */
.evlive.idle:not(.open) .map{display:none}
.evlive .mapbtn{background:none;border:0;padding:0 0 0 2px;color:var(--fg2);font:inherit;text-decoration:underline;cursor:pointer}
.evlive .mapbtn:hover{color:var(--fg)}
@media (pointer:coarse){.evlive .mapbtn{min-height:44px}}
.evlive.on .map{max-height:none}
@media (min-width:900px){.evlive .map{max-width:960px}}
.evlive.on .pulse{background:var(--acc);box-shadow:0 0 0 0 rgba(227,6,19,.6);animation:evp 1.6s infinite}
@keyframes evp{0%{box-shadow:0 0 0 0 rgba(227,6,19,.6)}70%{box-shadow:0 0 0 8px rgba(227,6,19,0)}100%{box-shadow:0 0 0 0 rgba(227,6,19,0)}}
.evlive .sst{display:flex;gap:6px;flex-wrap:wrap;margin-left:auto}
.evlive .sst button{font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.06em;color:var(--fg2);background:none;
  border:1px solid var(--line2);padding:6px 9px;cursor:pointer}
.evlive .sst button:hover{color:var(--fg)}
.evlive .sst button.on{border-color:var(--acc);color:var(--fg);background:#1A0B0C}
.evlive .sst button b,.evlive .sst span b{color:var(--acct,#FF4655);font-weight:700;margin-left:5px}
@media (pointer:coarse){.evlive .sst button{min-height:44px;min-width:44px;padding:6px 12px}}   /* (a finger's room: 44 px) */
.evlive .sst span{font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.06em;color:var(--fg3);border:1px solid var(--line);padding:6px 9px}
.evlive .sst span.on{border-color:var(--acc);color:var(--fg)}
.evlive .map{margin:12px 0 6px}
.evlive .onst{color:var(--fg2);font-size:13px;min-height:20px}
.evlive .onst b{color:var(--acct,#FF4655);font-weight:600}
.evlive .onst .nm{color:var(--fg);font-weight:600}
.evlive .onst .why{margin:10px 0 8px;color:var(--fg2)}
.evlive .onst .pv{margin-top:6px;color:var(--fg2);font-size:12px}
.evlive .onst .who{display:flex;flex-wrap:wrap;align-items:center;gap:4px 10px;padding:7px 0;border-top:1px solid var(--line)}
.evlive .onst .who>b{min-width:34px}
.evlive .onst .who .d{display:inline-flex;align-items:center;gap:5px}
.evlive .onst .who .flagimg{width:18px;height:12px}
.evlive .onst .who small{color:var(--fg3);text-transform:uppercase;letter-spacing:.08em;font-size:11px}
`;

export const EVENT_LIVE_JS = () => `
  // ---- live maps (src/eventlive.js): the stage maps of src/stagemap.js, by key ('lm0', 'lm1'...: one a map on the page)
  var NS='http://www.w3.org/2000/svg',maps={};
  function sv(tag,a){var e=document.createElementNS(NS,tag);for(var k in a||{})e.setAttribute(k,a[k]);return e}
  ${STAGE_MAP_JS()}
  var ROUTES={},LMN=0;   // track -> its route (a promise: asked once a page)
  function routeOf(track){return ROUTES[track]||(ROUTES[track]=fetch('/api/route?track='+encodeURIComponent(track))
    .then(function(r){return r.ok?r.json():{}}).then(function(j){return j.route||[]},function(){return []}))}
  function liveMap(box,o){
    var key='lm'+(LMN++),S=null,sel=0,follow=true,last=null,n=0,busy=false,any=false,BUSY=3,IDLE=15,SEC=0;   // SEC: stages hidden from me (how many)
    box.className='evlive';box.hidden=true;
    var head=el('div','lh'),tabs=el('div','sst'),mb=el('div','map'),on=el('div','onst'),title=add(el('span','lt'),o.title||${tq('LIVE')});
    // (its own words: LIVE only while someone is on a stage, "Live map" otherwise: it said LIVE beside a grey dot)
    function label(live){var w=live?${tq('LIVE')}:${tq('Live map')},f=title.firstChild;
      if(f&&f.nodeType===3&&(f.nodeValue===${tq('LIVE')}||f.nodeValue===${tq('Live map')}))f.nodeValue=w;else if(!o.title)title.textContent=w}
    add(head,el('span','pulse'),title,tabs);add(box,head,mb,on);
    function sk(st){return st?st.map(function(s){return s.track}).join('|'):''}
    function nameOf(no){return (o.names&&o.names[no-1])||S[no-1].name||''}
    function show(no){sel=no;[].forEach.call(tabs.children,function(b,i){b.classList.toggle('on',i+1===no)});
      var s=S[no-1];delete PB[key];var x=maps[key]={slot:key,m:null};mb.innerHTML='';
      routeOf(s.track).then(function(r){if(maps[key]!==x)return;   // (another stage since)
        var g=EARTH[s.track];x.m=drawMap(mb,r,g,g?(window.innerWidth<=700?74:92):0);
        satButton(mb,{track:s.track,route:r},true,o.sat?o.sat(no):null);if(last)feed(last)})}
    function feed(j){var all=j.drivers||[],live=all.filter(function(d){return d.state==='live'}),c={};
      live.forEach(function(d){c[d.stageNo+1]=(c[d.stageNo+1]||0)+1});
      [].forEach.call(tabs.children,function(b,i){b.textContent='SS'+(i+1);if(c[i+1])b.appendChild(el('b',null,String(c[i+1])))});
      box.classList.toggle('on',live.length>0);box.classList.toggle('idle',!live.length);label(live.length>0);
      var x=maps[key];if(x&&x.m)drawLive(x,{drivers:all.filter(function(d){return d.stageNo+1===sel})},j.now);
      on.innerHTML='';add(on,'SS'+sel+(nameOf(sel)?' · ':''),nameOf(sel)?el('span','nm',nameOf(sel)):null,' · ');
      if(c[sel])add(on,FN(P(${tqp('{1} driver on the stage now', '{1} drivers on the stage now')},c[sel],'{1}'),'',el('b',null,'● '+c[sel])));
      else if(live.length)add(on,${tq('Nobody on this stage right now.')});
      else{add(on,${tq('Nobody is on a stage right now.')}+' ');var mbtn=el('button','mapbtn',box.classList.contains('open')?${tq('Hide the map')}:${tq('Show the map')});
        mbtn.type='button';mbtn.onclick=function(){box.classList.toggle('open');feed(last)};on.appendChild(mbtn)}
      if(j.privateMap)add(on,el('div','pv',${tq('Only the organisers and the drivers who have pressed DRIVE see this map: the stage names are hidden from everyone else until the event ends.')}))}
    // the stages hidden from me: no map (it would show them), but who is on which stage, and why
    function secret(j){var all=j.drivers||[],c={},by={};
      if(SEC!==j.count){SEC=j.count;S=null;sel=0;delete maps[key];delete PB[key];mb.innerHTML='';tabs.innerHTML='';
        for(var i=1;i<=SEC;i++)tabs.appendChild(el('span',null,'SS'+i))}
      mb.hidden=true;box.hidden=false;last=null;
      all.forEach(function(d){var k=d.stageNo+1;(by[k]=by[k]||[]).push(d);if(d.state==='live')c[k]=(c[k]||0)+1});
      [].forEach.call(tabs.children,function(b,i){b.textContent='SS'+(i+1);b.classList.toggle('on',!!c[i+1]);if(c[i+1])b.appendChild(el('b',null,String(c[i+1])))});
      var busy=Object.keys(c).length>0;box.classList.toggle('on',busy);box.classList.toggle('idle',!busy);label(busy);
      on.innerHTML='';add(on,el('div','why',o.secret||${tq('The live map stays hidden with the stage names until the event ends (a driver sees it once they press DRIVE in the app). Who is on which stage:')}));
      var ks=Object.keys(by).map(Number).sort(function(a,b){return a-b});
      if(!ks.length)add(on,el('div','who',${tq('Nobody is on a stage right now.')}));
      ks.forEach(function(k){var r=el('div','who');add(r,el('b',null,'SS'+k));
        by[k].forEach(function(d){var x=el('span','d');if(typeof flag==='function')flag(x,d.country);add(x,el('span','nm',d.name||'?'));
          if(d.state!=='live')add(x,el('small',null,d.state==='finished'?${tq('finished')}:${tq('DNF')}));r.appendChild(x)});
        on.appendChild(r)})}
    function got(j){if(o.onData)o.onData(j);var all=j.drivers||[];any=all.length>0;
      var tm=j.timing;if(tm){BUSY=Math.min(tm.livePollS,Math.ceil(tm.liveSendS/2));IDLE=tm.liveIdleS;
        LIVE_DELAY=(tm.liveSendS+BUSY+1)*1000;LIVE_GAP=3*tm.liveSendS*1000}
      // stages hidden from me: who is on which, without the map
      if(!j.stages&&j.hidden&&j.hidden.stages&&j.count){secret(j);return}
      // no stages (the cup's round has no match on): no map
      if(!j.stages||!j.stages.length){box.hidden=true;S=null;sel=0;SEC=0;last=null;delete maps[key];delete PB[key];return}
      if(SEC){SEC=0;tabs.innerHTML='';mb.hidden=false}
      if(sk(j.stages)!==sk(S)){S=j.stages;sel=0;follow=true;tabs.innerHTML='';
        S.forEach(function(s,i){var b=el('button',null,'SS'+(i+1));b.type='button';b.onclick=function(){follow=false;show(i+1);if(last)feed(last)};tabs.appendChild(b)})}
      box.hidden=false;last=j;
      // the stage most drivers are on, until a tab is clicked
      if(follow){var c={},best=0;all.forEach(function(d){if(d.state==='live')c[d.stageNo+1]=(c[d.stageNo+1]||0)+1});
        Object.keys(c).forEach(function(k){if(!best||c[k]>c[best])best=+k});if(best&&best<=S.length&&best!==sel)show(best)}
      if(!sel)show(1);
      feed(j)}
    // every BUSY s while someone is on a stage, every IDLE s otherwise (the server's timing), nothing while the tab is hidden
    function poll(force){if(busy||document.hidden||(o.on&&!o.on()))return;if(force!==true&&n++%(any?BUSY:IDLE))return;
      busy=true;api(o.url).then(got,function(){}).then(function(){busy=false})}
    setInterval(poll,1000);
    document.addEventListener('visibilitychange',function(){if(!document.hidden)poll(true)});
    poll(true);
    return {poll:poll,title:title}}
`;
