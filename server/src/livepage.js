// The live page (/live): everyone on a stage right now, in one place. Today's two stages (as the home page has them),
// the week's time trial stages (as /tt) and every league event, 1V1 and cup match being driven (GET /api/events/live:
// a stage each, its map drawn once its road is in): each a map with the drivers on it gliding along the road a few
// seconds late (src/stagemap.js, src/glide.js) and who is on it. The app's LIVE tab shows the same (liveui.py).
// Each part is asked for on its own, every few seconds while someone is on it, less often while nobody is (the
// server's timing, as the home page), and nothing while the tab is hidden.

import { shell } from './leaguepages.js';
import { STAGE_MAP_CSS, STAGE_MAP_JS } from './stagemap.js';

const CSS = `<style>
.lvs{display:grid;grid-template-columns:1fr 1fr;gap:26px 36px;margin-top:14px}
.lvc{border-top:3px solid var(--m,var(--fg));padding-top:12px;min-width:0}
.lvc .hd{display:flex;align-items:center;gap:10px}
.lvc .chip{font:700 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.08em;background:var(--m,var(--fg));color:var(--bg);padding:4px 7px}
.lvc h3{font-size:22px;margin:0;flex:1;min-width:0;overflow-wrap:anywhere}
.lvc .cnt{font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.1em;color:var(--fg3);text-transform:uppercase;white-space:nowrap}
.lvc .cnt.on{color:#fff;background:var(--acc);padding:4px 7px}
.lvc .sub{color:var(--fg2);font-size:14px;margin-top:6px}
.lvc .map{margin:12px 0 6px}
.lvc .who .r{display:flex;gap:10px;align-items:center;padding:6px 0;border-bottom:1px solid var(--line)}
.lvc .who .r a{text-decoration:none;flex:1;min-width:0}
.lvc .who .r .p{font:600 14px/1 'Barlow Condensed',sans-serif;color:var(--fg2);white-space:nowrap}
.lvc .who .r.finished .p{color:var(--fg)}.lvc .who .r.dnf .p{color:var(--acc)}
.lvc .who .none{color:var(--fg3);font-size:14px;padding:4px 0}
.lvc .links{display:flex;gap:16px;margin-top:10px;font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;text-transform:uppercase}
.lvc .links a{color:var(--fg2);text-decoration:none}.lvc .links a:hover{color:var(--fg)}
.lvempty{color:var(--fg3);margin-top:12px}
.m-tt{--m:#BF5AF2}.m-leagues{--m:#5BA8FF}.m-1v1{--m:#FF9F43}.m-cups{--m:#FFD60A}
${STAGE_MAP_CSS}
@media (max-width:900px){.lvs{grid-template-columns:1fr}}
</style>`;

export function livePage(env) {
  return shell('Live · ACR Daily', `${CSS}
  <div class="top"><div class="kick" style="color:var(--acc)">● Live</div><h1>Driving now</h1>
  <p class="note">Everyone on a stage right now: today's dailies, the time trial, league events, 1V1s and cup matches.
  The cars run a few seconds behind, along the road. The app's <b>LIVE</b> tab shows the same.</p>
  <div class="msg" id="m"></div></div>
  <h2>Today's stages</h2><div class="lvs" id="daily"></div>
  <div id="ttpart"><h2>Time trial</h2><div class="lvs" id="tt"></div></div>
  <h2>Matches</h2><div class="lvs" id="match"></div><div class="lvempty" id="nomatch">Looking…</div>`, `
  navOn('live');
  var NS='http://www.w3.org/2000/svg',maps={};
  function sv(tag,a){var e=document.createElementNS(NS,tag);for(var k in a||{})e.setAttribute(k,a[k]);return e}
  ${STAGE_MAP_JS}
  var DAY=null,WEEK=null,ROUTES={},KIND={league:['League','m-leagues'],h2h:['1V1','m-1v1'],cup:['Cup','m-cups']};
  function km(m){return m?(m/1000).toFixed(1)+' km':''}
  // a stage's card: its chip and name, a line under it, its map (drawn once its road is in) and who is on it
  function card(key,chip,cls,title,sub,route,track,links){
    var c=el('div','lvc'+(cls?' '+cls:'')),hd=el('div','hd'),cnt=el('span','cnt','');
    add(hd,el('span','chip',chip),el('h3',null,title),cnt);c.appendChild(hd);c.appendChild(el('div','sub',sub));
    var mb=el('div','map');c.appendChild(mb);var who=el('div','who');c.appendChild(who);
    if(links&&links.length){var l=el('div','links');links.forEach(function(x){var a=el('a',null,x[0]);a.href=x[1];l.appendChild(a)});c.appendChild(l)}
    var x={slot:key,cnt:cnt,who:who,mb:mb,track:track,node:c};maps[key]=x;
    road(x,route);
    return x}
  function road(x,route){if(!route||route.length<2){x.mb.innerHTML='';x.mb.appendChild(el('div','empty','Loading the map…'));return}
    x.m=drawMap(x.mb,route,EARTH[x.track],0)}
  // who is on a stage: on it first (the furthest along), then the finishers (the quickest), then the DNFs
  function order(ds){var k=function(d){return d.state==='live'?[0,-(d.progress||0)]:d.state==='finished'?[1,d.totalMs||0]:[2,0]};
    return ds.slice().sort(function(a,b){var x=k(a),y=k(b);return x[0]-y[0]||x[1]-y[1]})}
  function fill(x,ds,now){drawLive(x,{drivers:ds},now);x.who.innerHTML='';
    var on=ds.filter(function(d){return d.state==='live'}).length;
    x.cnt.textContent=on?'● '+on+' on stage':'Nobody on stage';x.cnt.className='cnt'+(on?' on':'');
    if(!ds.length){x.who.appendChild(el('div','none','Nobody on this stage right now.'));return}
    order(ds).forEach(function(d){var r=el('div','r '+d.state),a=el('a');a.href='/d/'+d.steamId;flag(a,d.country);teamTag(a,d);
      add(a,(d.look&&d.look.badge?d.look.badge+' ':'')+(d.name||'a driver'));if(d.look&&d.look.color)a.style.color=d.look.color;
      r.appendChild(a);r.appendChild(el('span','p',d.state==='live'?Math.round(100*(d.progress||0))+' %':d.state==='finished'?ms(d.totalMs):'DNF'));
      x.who.appendChild(r)})}
  function timing(tm){if(tm){BUSY=Math.min(tm.livePollS,Math.ceil(tm.liveSendS/2));IDLE=tm.liveIdleS;
    LIVE_DELAY=(tm.liveSendS+BUSY+1)*1000;LIVE_GAP=3*tm.liveSendS*1000}}
  function load(){
    api('/api/challenges/today').then(function(r){var box=$('daily');box.innerHTML='';
      (r.challenges||[]).forEach(function(ch){DAY=ch.date;timing(ch.timing);
        box.appendChild(card('d'+ch.slot,'SS'+ch.slot,'',ch.menuName||ch.stageName||ch.track,
          [ch.car,[ch.weatherLabel,ch.timeLabel].filter(Boolean).join(' · '),km(ch.lengthM)].filter(Boolean).join(' · '),ch.route,ch.track).node)});
      poll('daily',true)},function(e){msg('m',e.message)});
    api('/api/tt').then(function(t){var box=$('tt');box.innerHTML='';
      if(!t.on||t.week!==t.current||!t.stages.length){$('ttpart').hidden=true;return}
      WEEK=t.week;t.stages.forEach(function(s){box.appendChild(card('t'+s.slot,'TT'+s.slot,'m-tt',s.menuName||s.stageName,
        [s.car,[s.weatherLabel,s.timeLabel].filter(Boolean).join(' · '),km(s.lengthM)].filter(Boolean).join(' · '),s.route,s.track,[['Time trial ›','/tt']]).node)});
      poll('tt',true)},function(){$('ttpart').hidden=true});
    poll('match',true)}
  // the matches: a card for each stage someone is on, gone once nobody is
  function matches(d){var box=$('match'),seen={},evs={};(d.events||[]).forEach(function(e){evs[e.id]=e});
    (d.events||[]).forEach(function(e){e.stages.forEach(function(s){var key='e'+e.id+'s'+(s.no-1),
        ds=(d.drivers||[]).filter(function(x){return x.eventId===e.id&&x.stageNo===s.no-1});if(!ds.length)return;seen[key]=1;
      var x=maps[key];
      if(!x){var k=KIND[e.kind]||KIND.league,links=[['Standings ›','/e/'+e.id]];if(e.kind==='cup')links.push(['Cup ›','/cup/'+e.leagueId]);
        x=card(key,k[0],k[1],e.name,[e.kind==='h2h'?'':e.league,'SS'+s.no+' '+(s.name||''),e.car||(e.carClass?e.carClass+' class':''),km(s.lengthM)].filter(Boolean).join(' · '),
          ROUTES[s.track],s.track,links);box.appendChild(x.node);
        if(!ROUTES[s.track])api('/api/route?track='+encodeURIComponent(s.track)).then(function(j){ROUTES[s.track]=j.route||[];
          Object.keys(maps).forEach(function(q){var y=maps[q];if(y.track===s.track&&!y.m){road(y,ROUTES[s.track]);if(y.last)fill(y,y.last,d.now)}})},function(){})}
      x.last=ds;fill(x,ds,d.now)})});
    Object.keys(maps).forEach(function(q){if(q[0]==='e'&&!seen[q]){maps[q].node.remove();delete maps[q];delete PB[q]}});
    $('nomatch').textContent=Object.keys(seen).length?'':'Nobody is driving a league event, a 1V1 or a cup match right now.'}
  // each part on its own: every BUSY s while someone is on it, every IDLE s otherwise, nothing while the tab is hidden
  var BUSY=3,IDLE=15,ANY={},LAST={},ASKING={};
  function poll(part,force){if(document.hidden||ASKING[part])return;var now=Date.now();
    if(!force&&now-(LAST[part]||0)<1000*(ANY[part]?BUSY:IDLE))return;
    var url=part==='daily'?(DAY&&'/api/live?date='+DAY+'&slot=all'):part==='tt'?(WEEK&&'/api/tt/live?week='+WEEK+'&slot=all'):'/api/events/live';
    if(!url)return;LAST[part]=now;ASKING[part]=true;
    api(url).then(function(d){var all=d.drivers||[];ANY[part]=all.some(function(x){return x.state==='live'});
      if(part==='match')matches(d);
      else Object.keys(maps).forEach(function(q){if(q[0]!==part[0])return;var slot=+q.slice(1);
        fill(maps[q],all.filter(function(x){return x.slot===slot}),d.now)})},
      function(){}).then(function(){ASKING[part]=false})}
  setInterval(function(){poll('daily');poll('tt');poll('match')},1000);
  document.addEventListener('visibilitychange',function(){if(!document.hidden){poll('daily',true);poll('tt',true);poll('match',true)}});
  account().then(load,load);
  `, env);
}
