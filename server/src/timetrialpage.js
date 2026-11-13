// The time trial's page (/tt, ?week=<its Monday> for a past week): the week's two stages, each with its map (everyone
// on it live, as the home page's dailies: src/stagemap.js) and its board (every driver's best time, their runs and the
// prize their place pays), entering, and how it works. Data: /api/tt... (src/timetrial.js).

import { shell } from './leaguepages.js';
import { STAGE_MAP_CSS, STAGE_MAP_JS } from './stagemap.js';
import { t, tq, tqp } from './i18n.js';

const CSS = `<style>
.tts{display:grid;grid-template-columns:1fr 1fr;gap:28px 40px;margin-top:30px}
.ttc{border-top:3px solid var(--tt);padding-top:16px;min-width:0}
.ttc .ss{font:700 15px/1 'Barlow Condensed',sans-serif;letter-spacing:.08em;color:var(--tt);text-transform:uppercase}
.ttc .ss span{color:var(--fg3);margin-left:10px;letter-spacing:.12em;font-size:13px}
.ttc h2{margin:10px 0 6px;font-size:30px;overflow-wrap:anywhere}
.ttc .car{font-size:16px}
.ttc .cond{color:var(--fg2);font-size:14px}
.ttc .acts{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin:14px 0 6px;min-height:34px}
.ttc .mine{color:var(--fg2);font-size:14px}
.ttc .mine b{color:var(--fg);font-weight:600}
.ttc .pot{color:var(--fg2);font-size:14px;margin-bottom:6px}
.ttc table{margin-top:6px}
.ttc td.prize{color:var(--good);font:600 15px/1 'Barlow Condensed',sans-serif}
.ttc td.runs{color:var(--fg3);font-size:13px}
.ttc tr.paid td.pos{color:var(--fg)}
.ttc tr.p1 td.pos{color:var(--tt)}
.ttc tr.cut td{border-bottom:1px dashed var(--fg3)}
.weeknav{display:flex;gap:18px;margin-top:18px;font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;text-transform:uppercase}
.weeknav a{color:var(--fg2);text-decoration:none}.weeknav a:hover{color:var(--fg)}
.how{max-width:760px;color:var(--fg2);padding-left:18px}.how li{margin:6px 0}.how b{color:var(--fg)}
.ttc .map{margin:14px 0 4px}
.ttc .onstage{color:var(--fg2);font-size:13px;min-height:20px}
.ttc .onstage b{color:var(--tt);font-weight:600}
${STAGE_MAP_CSS}
:root{--tt:#BF5AF2}
.top .kick{color:var(--tt)}
@media (max-width:900px){.tts{grid-template-columns:1fr}}
</style>`;

export function timeTrialPage(env) {
  return shell(t('Time trial') + ' · ACR Daily', `${CSS}
  <div class="top"><div class="kick" id="kick">${t('Time trial')}</div><h1>${t('Time trial')}</h1>
  <p class="note">${t("Two stages all week, Monday to Monday (UTC). Drive them as often as you like from the app's <b>TIME TRIAL</b> tab: your best time is the one on the sheet.")}</p>
  <div class="facts" id="facts"></div><nav class="weeknav" id="weeknav"></nav><div class="msg" id="m"></div></div>
  <div class="tts" id="stages"></div>
  <h2>${t('How it works')}</h2>
  <ul class="how" id="how"></ul>`, `
  var Q=new URLSearchParams(location.search),WEEK=Q.get('week')||'',T=null;
  // the maps (src/stagemap.js): each stage's, by slot; everyone on the stage live this week
  var NS='http://www.w3.org/2000/svg',maps={};
  function sv(tag,a){var e=document.createElementNS(NS,tag);for(var k in a||{})e.setAttribute(k,a[k]);return e}
  ${STAGE_MAP_JS()}
  function names(ss){return ss.map(function(s){return 'TT'+s.slot}).join(' '+${tq('and')}+' ')}
  function stageLine(s){return [TD(s.rally),TD(s.surface),s.lengthM?km(s.lengthM):''].filter(Boolean).join(' · ')}
  function how(t){var h=$('how');h.innerHTML='';var li=function(){var l=el('li');add.apply(null,[l].concat([].slice.call(arguments)));h.appendChild(l)};
    li(el('b',null,${tq('Two stages a week')}),${tq(", new every Monday at 00:00 UTC, each with its car, weather and time of day. DRIVE in the app sets it up in the game as a one-stage Rally Weekend; the game's own stage time + penalty goes on the sheet.")});
    li(el('b',null,${tq('As many runs as you like')}),${tq(": after each run go on from the game's results screen (it saves its time), then Rally Weekend › Start Rally again. Only your best time counts; restarts and DNFs are not sent.")});
    var free=t.stages.filter(function(s){return !s.fee}),paid=t.stages.filter(function(s){return s.fee});
    if(free.length&&paid.length)li(el('b',null,P(${tqp('{1} is free', '{1} are free')},free.length,names(free))),${tq(': no entry fee and no prizes. Sign in and drive.')});
    paid.forEach(function(s){li(el('b',null,F(${tq('TT{0} entry')},s.slot)+' '),cr(s.fee),${tq(', paid before your first run on it (DRIVE asks, or Enter here).')})});
    if(paid.length)li(el('b',null,free.length?F(${tq('Prizes on {0}')},names(paid)):${tq('Prizes')}),${tq(": once the week is over, the top half of the drivers with a time (rounded up) get their fee back plus a share of everyone else's fees, more for each place higher up: with 5 places paid, P1 gets 5 shares, P2 4 ... P5 1. Set no time and your fee comes back.")});
    else li(el('b',null,${tq('Free')}),${tq(': no entry fee and no prizes this week.')});
    li(${tq('Everyone on a stage shows on its map live, as on the dailies. Not rated.')})}
  function load(){return api('/api/tt'+(WEEK?'?week='+encodeURIComponent(WEEK):'')).then(render,function(e){msg('m',e.message)})}
  function render(t){T=t;var f=$('facts'),n=$('weeknav'),box=$('stages');f.innerHTML='';n.innerHTML='';box.innerHTML='';maps={};PB={};
    if(t.prev){var p=el('a',null,${tq('‹ Week before')});p.href='/tt?week='+t.prev;n.appendChild(p)}
    if(t.next){var x=el('a',null,t.next===t.current?${tq('This week ›')}:${tq('Week after ›')});x.href=t.next===t.current?'/tt':'/tt?week='+t.next;n.appendChild(x)}
    if(t.on===false){add(f,el('div','muted',t.startsAt?F(${tq('The time trial starts {0}.')},new Date(t.startsAt).toLocaleDateString(LOC,{weekday:'long',day:'numeric',month:'long'})):${tq('The time trial is off on this server.')}));return}
    $('kick').textContent=t.week===t.current?F(${tq('Time trial · week {0}')},t.isoWeek.no):F(${tq('Time trial · week {0} of {1}')},t.isoWeek.no,t.isoWeek.year);
    var open=Date.now()<t.endsAt;
    function fact(k,v){var d=el('div');add(d,el('span','k',k),add(el('b'),v));f.appendChild(d)}
    fact(open?${tq('Closes in')}:${tq('Closed')},open?left(t.endsAt):when(t.endsAt));
    fact(${tq('Week')},new Date(t.startsAt).toLocaleDateString(LOC,{day:'numeric',month:'short',timeZone:'UTC'})+' – '+new Date(t.endsAt-1).toLocaleDateString(LOC,{day:'numeric',month:'short',timeZone:'UTC'}));
    var paid=t.stages.filter(function(s){return s.fee}),entry=el('span');
    t.stages.forEach(function(s,i){add(entry,(i?' · ':'')+'TT'+s.slot+' ',s.fee?cr(s.fee):${tq('free')})});
    fact(${tq('Entry')},paid.length?entry:${tq('Free')});
    if(paid.length)fact(${tq('Prizes')},paid.length<t.stages.length?F(${tq('{0} · top half')},names(paid)):${tq('Top half')});
    how(t);
    if(!t.stages.length){box.appendChild(el('div','empty',${tq('No stages this week.')}));return}
    var tm=t.stages[0].timing;   // how often the server wants the live map asked (wrangler.toml), as on the home page
    if(tm){LIVE_BUSY=Math.min(tm.livePollS,Math.ceil(tm.liveSendS/2));LIVE_IDLE=tm.liveIdleS;
      LIVE_DELAY=(tm.liveSendS+LIVE_BUSY+1)*1000;LIVE_GAP=3*tm.liveSendS*1000}
    t.stages.forEach(function(s){box.appendChild(stage(t,s,open))});
    pollLive(true)}
  function stage(t,s,open){var c=el('div','ttc');
    var ss=el('div','ss','TT'+s.slot);add(ss,el('span',null,stageLine(s)));c.appendChild(ss);
    add(c,el('h2',null,s.menuName||s.stageName),el('div','car',s.car+(s.carClass?' · '+s.carClass:'')),
      el('div','cond',[TD(s.weatherLabel),TD(s.timeLabel)].filter(Boolean).join(' · ')));
    var mb=el('div','map');c.appendChild(mb);var on=el('div','onstage');c.appendChild(on);
    var x={slot:s.slot,on:on};maps[s.slot]=x;
    x.m=drawMap(mb,s.route,EARTH[s.track],EARTH[s.track]?(window.innerWidth<=700?74:92):0);
    satButton(mb,s,false);
    var acts=el('div','acts');c.appendChild(acts);
    if(open&&s.fee){if(!t.signedIn)acts.appendChild(steamBtn(${tq('Sign in to enter')}));
      else if(s.me&&!s.me.entered){var b=el('button','btn small');add(b,${tq('Enter')}+' · ',cr(s.fee));b.onclick=function(){enter(s,b)};acts.appendChild(b)}}
    if(s.me&&(s.me.entered||!s.fee)){var mn=el('span','mine');
      if(s.me.bestMs!=null)add(mn,FN(P(${tqp('Your best {1} · {0} run', 'Your best {1} · {0} runs')},s.me.runs,'{1}'),'',el('b',null,ms(s.me.bestMs))));
      else add(mn,s.fee?${tq('You are in: drive it from the app')}:${tq('Drive it from the app')});acts.appendChild(mn)}
    var pot=el('div','pot');c.appendChild(pot);
    if(s.fee)add(pot,FN(P(${tqp('{0} driver entered · pot {1}', '{0} drivers entered · pot {1}')},s.entrants,'{1}'),'',cr(s.pot)));
    var tw=el('div','tablewrap');c.appendChild(tw);tw.appendChild(el('div','empty',${tq('Loading…')}));
    api('/api/tt/board?week='+t.week+'&slot='+s.slot).then(function(b){sheet(tw,b,s)},function(e){tw.innerHTML='';tw.appendChild(el('div','empty',e.message))});
    return c}
  function sheet(tw,b,s){tw.innerHTML='';if(!b.entries.length){tw.appendChild(el('div','empty',${tq('No times yet.')}));return}
    var tb=el('table'),hr=el('tr');[[${tq('Pos')}],[${tq('Driver')}],[${tq('Time')},'r'],[${tq('Gap')},'r'],[${tq('Runs')},'r']].concat(b.prizes?[[${tq('Prize')},'r']]:[]).forEach(function(h){hr.appendChild(el('th',h[1]||null,h[0]))});
    var th=el('thead');th.appendChild(hr);tb.appendChild(th);var body=el('tbody');tb.appendChild(body);
    var paid=b.stats.paidPlaces;
    b.entries.forEach(function(e){var tr=el('tr',(e.rank===1?'p1 ':'')+(b.prizes&&e.rank<=paid?'paid ':'')+(b.prizes&&e.rank===paid&&b.entries.length>paid?'cut ':'')+(ME&&e.steamId===ME.steamId?'me':''));
      tr.appendChild(el('td','pos',String(e.rank)));
      var d=el('td','drv'),a=el('a');a.href='/d/'+e.steamId;a.style.textDecoration='none';flag(a,e.country);teamTag(a,e);add(a,(e.look&&e.look.badge?e.look.badge+' ':'')+(e.name||${tq('a driver')}));
      if(e.look&&e.look.color)a.style.color=e.look.color;d.appendChild(a);tr.appendChild(d);
      var tm=el('td','t r',ms(e.totalMs));if(e.totalMs>e.clockMs)tm.appendChild(el('small','pen',F(${tq('{0} penalty')},pen(e.totalMs-e.clockMs))));if(e.appTime){var ap=el('small','pen',${tq('APP')});ap.title=${tq("The game lost this run\'s official result: the app\'s stage clock counts, + 10 s a respawn.")};tm.appendChild(ap)}tr.appendChild(tm);
      tr.appendChild(el('td','t r',e.rank===1?'':gap(e.gapMs)));
      tr.appendChild(el('td','runs r',String(e.runs)));
      if(b.prizes){var pz=el('td','prize r');if(e.prize)pz.appendChild(cr(e.prize));tr.appendChild(pz)}
      body.appendChild(tr)});
    tw.appendChild(tb);
    if(b.prizes)tw.appendChild(el('p','note',b.settled?F(${tq('Paid out {0}.')},when(b.settled)):F(${tq('The prizes as the pot stands now: paid once the week is over (the top {0} of {1}).')},paid,b.entries.length)))}
  function enter(s,b){if(!confirm(F(${tq('Enter TT{0} ({1}) for {2} credits?')},s.slot,s.menuName||s.stageName,s.fee)+'\\n\\n'+${tq('Drive it as often as you like this week: your best time counts. The top half of the drivers with a time win a share of the pot.')}))return;
    b.disabled=true;api('/api/tt/enter',{slot:s.slot}).then(function(){msg('m',F(${tq("You are in TT{0}. Drive it from the app's TIME TRIAL tab.")},s.slot),true);load()},
      function(e){b.disabled=false;msg('m',e.message)})}
  // the live maps: both stages in one request, every LIVE_BUSY s while someone is on one, every LIVE_IDLE s otherwise,
  // this week only and nothing while the tab is hidden; the cars played back between the apps' updates (drawLive)
  var liveN=0,anyLive=false,liveBusy=false,LIVE_BUSY=3,LIVE_IDLE=15;
  function pollLive(force){if(!T||!T.on||T.week!==T.current||document.hidden||liveBusy)return;
    if(force!==true&&liveN++%(anyLive?LIVE_BUSY:LIVE_IDLE))return;
    liveBusy=true;
    api('/api/tt/live?week='+T.week+'&slot=all').then(function(d){var all=d.drivers||[];anyLive=all.length>0;
      Object.keys(maps).forEach(function(slot){var x=maps[slot],mine=all.filter(function(y){return String(y.slot)===slot}),
          driving=mine.filter(function(y){return y.state==='live'}).length;
        drawLive(x,{drivers:mine},d.now);x.on.innerHTML='';
        if(driving)add(x.on,FN(P(${tqp('{1} driver on the stage now', '{1} drivers on the stage now')},driving,'{1}'),el('b',null,'● '+driving)))})},
      function(){}).then(function(){liveBusy=false})}
  setInterval(pollLive,1000);
  document.addEventListener('visibilitychange',function(){if(!document.hidden)pollLive(true)});
  account().then(load,load);
  `, env);
}
