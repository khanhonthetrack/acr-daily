// The time trial's page (/tt, ?week=<its Monday> for a past week): the week's two stages, each with its board (every
// driver's best time, their runs and the prize their place pays), entering, and how it works. Data: /api/tt... (src/timetrial.js).

import { shell } from './leaguepages.js';

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
:root{--tt:#BF5AF2}
.top .kick{color:var(--tt)}
@media (max-width:900px){.tts{grid-template-columns:1fr}}
</style>`;

export function timeTrialPage(env) {
  return shell('Time trial · ACR Daily', `${CSS}
  <div class="top"><div class="kick" id="kick">Time trial</div><h1>Time trial</h1>
  <p class="note">Two stages all week, Monday to Monday (UTC). Drive them as often as you like from the app's
  <b>TIME TRIAL</b> tab: your best time is the one on the sheet.</p>
  <div class="facts" id="facts"></div><nav class="weeknav" id="weeknav"></nav><div class="msg" id="m"></div></div>
  <div class="tts" id="stages"></div>
  <h2>How it works</h2>
  <ul class="how" id="how"></ul>`, `
  var Q=new URLSearchParams(location.search),WEEK=Q.get('week')||'',T=null;
  function stageLine(s){return [s.rally,s.surface,s.lengthM?km(s.lengthM):''].filter(Boolean).join(' · ')}
  function how(t){var h=$('how');h.innerHTML='';var li=function(){var l=el('li');add.apply(null,[l].concat([].slice.call(arguments)));h.appendChild(l)};
    li(el('b',null,'Two stages a week'),', new every Monday at 00:00 UTC, each with its car, weather and time of day. DRIVE in the app sets it up in the game as a one-stage Rally Weekend; the game\\'s own stage time + penalty goes on the sheet.');
    li(el('b',null,'As many runs as you like'),': after each run go on from the game\\'s results screen (it saves its time), then Rally Weekend › Start Rally again. Only your best time counts; restarts and DNFs are not sent.');
    if(t.credits){li(el('b',null,'Entry '),cr(t.fee),' a stage, paid before your first run on it (DRIVE asks, or Enter here).');
      li(el('b',null,'Prizes'),': once the week is over, the top half of the drivers with a time (rounded up) get their fee back plus a share of everyone else\\'s fees, more for each place higher up: with 5 places paid, P1 gets 5 shares, P2 4 ... P5 1. Set no time and your fee comes back.')}
    else li(el('b',null,'Free'),': no entry fee and no prizes this week.');
    li('Not rated, and not on the live map.')}
  function load(){return api('/api/tt?lite=1'+(WEEK?'&week='+encodeURIComponent(WEEK):'')).then(render,function(e){msg('m',e.message)})}
  function render(t){T=t;var f=$('facts'),n=$('weeknav'),box=$('stages');f.innerHTML='';n.innerHTML='';box.innerHTML='';
    if(t.prev){var p=el('a',null,'‹ Week before');p.href='/tt?week='+t.prev;n.appendChild(p)}
    if(t.next){var x=el('a',null,t.next===t.current?'This week ›':'Week after ›');x.href=t.next===t.current?'/tt':'/tt?week='+t.next;n.appendChild(x)}
    if(t.on===false){add(f,el('div','muted',t.startsAt?'The time trial starts '+new Date(t.startsAt).toLocaleDateString(undefined,{weekday:'long',day:'numeric',month:'long'})+'.':'The time trial is off on this server.'));return}
    $('kick').textContent='Time trial · week '+t.isoWeek.no+(t.week===t.current?'':' of '+t.isoWeek.year);
    var open=Date.now()<t.endsAt;
    function fact(k,v){var d=el('div');add(d,el('span','k',k),add(el('b'),v));f.appendChild(d)}
    fact(open?'Closes in':'Closed',open?left(t.endsAt):when(t.endsAt));
    fact('Week',new Date(t.startsAt).toLocaleDateString(undefined,{day:'numeric',month:'short',timeZone:'UTC'})+' – '+new Date(t.endsAt-1).toLocaleDateString(undefined,{day:'numeric',month:'short',timeZone:'UTC'}));
    fact('Entry',t.credits?add(el('span'),cr(t.fee),' a stage'):'Free');
    if(t.credits)fact('Prizes','Top half');
    how(t);
    if(!t.stages.length){box.appendChild(el('div','empty','No stages this week.'));return}
    t.stages.forEach(function(s){box.appendChild(stage(t,s,open))})}
  function stage(t,s,open){var c=el('div','ttc');
    var ss=el('div','ss','TT'+s.slot);add(ss,el('span',null,stageLine(s)));c.appendChild(ss);
    add(c,el('h2',null,s.menuName||s.stageName),el('div','car',s.car+(s.carClass?' · '+s.carClass:'')),
      el('div','cond',[s.weatherLabel,s.timeLabel].filter(Boolean).join(' · ')));
    var acts=el('div','acts');c.appendChild(acts);
    if(open&&s.fee){if(!t.signedIn)acts.appendChild(steamBtn('Sign in to enter'));
      else if(s.me&&!s.me.entered){var b=el('button','btn small');add(b,'Enter · ',cr(s.fee));b.onclick=function(){enter(s,b)};acts.appendChild(b)}}
    if(s.me&&(s.me.entered||!s.fee)){var mn=el('span','mine');
      if(s.me.bestMs!=null)add(mn,'Your best ',el('b',null,ms(s.me.bestMs)),' · '+s.me.runs+(s.me.runs===1?' run':' runs'));
      else add(mn,s.fee?'You are in: drive it from the app':'Drive it from the app');acts.appendChild(mn)}
    var pot=el('div','pot');c.appendChild(pot);
    if(s.fee)add(pot,s.entrants+(s.entrants===1?' driver':' drivers')+' entered · pot ',cr(s.pot));
    var tw=el('div','tablewrap');c.appendChild(tw);tw.appendChild(el('div','empty','Loading…'));
    api('/api/tt/board?week='+t.week+'&slot='+s.slot).then(function(b){sheet(tw,b,s)},function(e){tw.innerHTML='';tw.appendChild(el('div','empty',e.message))});
    return c}
  function sheet(tw,b,s){tw.innerHTML='';if(!b.entries.length){tw.appendChild(el('div','empty','No times yet.'));return}
    var tb=el('table'),hr=el('tr');[['Pos'],['Driver'],['Time','r'],['Gap','r'],['Runs','r']].concat(b.credits?[['Prize','r']]:[]).forEach(function(h){hr.appendChild(el('th',h[1]||null,h[0]))});
    var th=el('thead');th.appendChild(hr);tb.appendChild(th);var body=el('tbody');tb.appendChild(body);
    var paid=b.stats.paidPlaces;
    b.entries.forEach(function(e){var tr=el('tr',(e.rank===1?'p1 ':'')+(b.credits&&e.rank<=paid?'paid ':'')+(b.credits&&e.rank===paid&&b.entries.length>paid?'cut ':'')+(ME&&e.steamId===ME.steamId?'me':''));
      tr.appendChild(el('td','pos',String(e.rank)));
      var d=el('td','drv'),a=el('a');a.href='/d/'+e.steamId;a.style.textDecoration='none';flag(a,e.country);teamTag(a,e);add(a,(e.look&&e.look.badge?e.look.badge+' ':'')+(e.name||'a driver'));
      if(e.look&&e.look.color)a.style.color=e.look.color;d.appendChild(a);tr.appendChild(d);
      var tm=el('td','t r',ms(e.totalMs));if(e.totalMs>e.clockMs)tm.appendChild(el('small','pen',pen(e.totalMs-e.clockMs)+' penalty'));tr.appendChild(tm);
      tr.appendChild(el('td','t r',e.rank===1?'':gap(e.gapMs)));
      tr.appendChild(el('td','runs r',String(e.runs)));
      if(b.credits){var pz=el('td','prize r');if(e.prize)pz.appendChild(cr(e.prize));tr.appendChild(pz)}
      body.appendChild(tr)});
    tw.appendChild(tb);
    if(b.credits)tw.appendChild(el('p','note',b.settled?'Paid out '+when(b.settled)+'.':'The prizes as the pot stands now: paid once the week is over (the top '+paid+' of '+b.entries.length+').'))}
  function enter(s,b){if(!confirm('Enter TT'+s.slot+' ('+(s.menuName||s.stageName)+') for '+s.fee+' credits?\\n\\nDrive it as often as you like this week: your best time counts. The top half of the drivers with a time win a share of the pot.'))return;
    b.disabled=true;api('/api/tt/enter',{slot:s.slot}).then(function(){msg('m','You are in TT'+s.slot+'. Drive it from the app\\'s TIME TRIAL tab.',true);load()},
      function(e){b.disabled=false;msg('m',e.message)})}
  account().then(load,load);
  `, env);
}
