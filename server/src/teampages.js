// The team competitions' pages: /team1v1 (team 1V1s), /tcups (team cups) and /tcup/:id (a team cup). In the 1V1s' and
// cups' look (src/socialpages.js), signed in with the website's Steam sign-in; their data from src/teamh2h.js and
// teamcups.js. A match's teams, their lineups and scores (SCORING_JS) are on its event page too (src/leaguepages.js).
// Every name a driver wrote is put in with textContent (el, add), never as HTML.

import { BUILDER_JS, shell } from './leaguepages.js';
import { SOCIAL_CSS, SOCIAL_JS } from './socialpages.js';
import { MATCH_PRESETS } from './teamscore.js';
import { TH2H } from './teamh2h.js';
import { t, tq, tqp } from './i18n.js';

const CSS = `<style>
.ticks{display:flex;flex-wrap:wrap;gap:6px 16px;margin-top:8px}
.ticks label{display:flex;gap:6px;align-items:center;margin:0;text-transform:none;letter-spacing:0;font:500 14px Barlow,sans-serif;color:var(--fg)}
.ticks input{width:auto}
.lineup{margin-top:12px;padding:12px 14px;border:1px solid var(--line2);background:#0E0E10}
.lineup h3{margin:0 0 4px}
.tmrow{display:flex;justify-content:space-between;gap:16px;padding:12px 0;border-bottom:1px solid var(--line)}
.tmrow .t{font:700 18px/1.1 'Barlow Condensed',sans-serif;text-transform:uppercase}
.tmrow .s{color:var(--fg2);font-size:13px;margin-top:4px}
.tmrow .r{flex:none;text-align:right;color:var(--fg2);font-size:13px}
.mt .tl{padding:6px 10px;border-top:1px solid var(--line);font-size:12px;color:var(--fg2)}
.mt .tl b{color:var(--fg);font-weight:600}
</style>`;

// A match's scoring in words, a score, a team's tag and name, the scoring's form and a match's teams (the team pages
// and the event page of a team match)
export const SCORING_JS = () => `
var SPRESETS=${JSON.stringify(Object.fromEntries(Object.entries(MATCH_PRESETS).map(([k, v]) => [k, { label: t(v.label), value: v.value }])))};
function scoringAbout(s){if(!s)return '';var o=[];
  o.push(s.lineup==='named'?P(${tqp('each team names {0} driver', 'each team names {0} drivers')},s.size):${tq('any driver of the team drives it')});
  o.push(s.count==='best'?F(${tq('the best {0} count')},s.best):s.min>1?F(${tq('everyone who drove counts (at least {0})')},s.min):${tq('everyone who drove counts')});
  o.push(s.by==='time'?${tq('their times added up, lowest wins')}:s.by==='avg'?${tq('their average time, lowest wins')}:s.by==='places'?${tq('their places added up, lowest wins')}:
    F(${tq('points by place ({0}) added up, highest wins')},(s.points||[]).join('-')));
  o.push(s.short==='slowest'?F(${tq("a missing finisher counts as the slowest finisher's time{0}")},(s.plusPct?' + '+s.plusPct+' %':'')+(s.plusS?' + '+s.plusS+' s':'')):${tq('a team short of finishers ranks behind')});
  return o.join(' · ')}
function score(s,v){if(v==null)return '–';return s.by==='time'||s.by==='avg'?ms(v):s.by==='places'?P(${tqp('{0} place', '{0} places')},v):P(${tqp('{0} point', '{0} points')},v)}
function teamName(p,x){if(x&&x.tag)tmInto(p,x.tagFmt,x.tag,x.color,'teamtag');add(p,x?x.name:${tq('a team')});return p}
var ROLE={captain:${tq('captain')},manager:${tq('manager')},member:${tq('driver')}};
function scoringForm(box,maxSize){var f=el('div');box.appendChild(f);var g=el('div','twocol');f.appendChild(g);
  function fld(label,node,cls){var l=el('label',cls||null);add(l,el('span',null,label),node);g.appendChild(l);return l}
  function num(id,min,max,v){var i=el('input');i.type='number';i.id=id;i.min=min;i.max=max;i.value=String(v);return i}
  function sel(id,opts,v){var s=el('select');s.id=id;opts.forEach(function(o){var x=el('option',null,o[1]);x.value=o[0];s.appendChild(x)});s.value=v;return s}
  fld(${tq('How the teams are scored')},sel('scp',Object.keys(SPRESETS).map(function(k){return[k,SPRESETS[k].label]}).concat([['custom',${tq('Your own…')}]]),'top'));
  fld(${tq('Drivers each team names')},num('scsz',1,maxSize,3),'sc-size');
  fld(${tq('X: the best how many count')},num('scbest',1,20,3),'sc-best');
  fld(${tq('At least this many count (the rest: missing)')},num('scmin',1,8,2),'sc-min');
  fld(${tq('Who drives')},sel('sclu',[['open',${tq('Any driver of the team')}],['named',${tq('The drivers the team names')}]],'open'),'sc-c');
  fld(${tq('Who counts')},sel('sccount',[['all',${tq('Everyone who drove')}],['best',${tq('The best X')}]],'best'),'sc-c');
  fld(${tq('Added up by')},sel('scby',[['time',${tq('Times added up')}],['avg',${tq('Average time')}],['places',${tq('Places added up (lowest wins)')}],['points',${tq('Points by place')}]],'time'),'sc-c');
  var pt=el('input');pt.type='text';pt.id='scpts';pt.value='10, 8, 6, 5, 4, 3, 2, 1';fld(${tq('Points by place, from P1')},pt,'sc-pts');
  fld(${tq('A team short of finishers')},sel('scshort',[['fewer',${tq('Ranks behind the teams with more')}],['slowest',${tq("Each missing one: the slowest finisher's time + a penalty")}]],'fewer'),'sc-c');
  fld(${tq('Penalty: seconds')},num('scps',0,3600,60),'sc-pen');fld(${tq('Penalty: % of the slowest time')},num('scpp',0,100,0),'sc-pen');
  var ab=el('p','note');f.appendChild(ab);
  function sh(c,on){[].forEach.call(g.querySelectorAll('.'+c),function(x){x.style.display=on?'':'none'})}
  function val(){var p=$('scp').value,v;
    if(p!=='custom'){v=JSON.parse(JSON.stringify(SPRESETS[p].value));if(v.lineup==='named')v.size=+$('scsz').value;if(v.count==='best')v.best=+$('scbest').value;if(p==='average')v.min=+$('scmin').value;return v}
    v={lineup:$('sclu').value,count:$('sccount').value,by:$('scby').value,short:$('scshort').value,min:+$('scmin').value};
    if(v.lineup==='named')v.size=+$('scsz').value;if(v.count==='best')v.best=+$('scbest').value;if(v.by==='points')v.points=$('scpts').value.split(/[\\s,;-]+/).filter(Boolean).map(Number);
    if(v.short==='slowest'){v.plusS=+$('scps').value;v.plusPct=+$('scpp').value}return v}
  function vis(){var p=$('scp').value,c=p==='custom',v=val();sh('sc-c',c);sh('sc-size',v.lineup==='named');sh('sc-best',v.count==='best');
    sh('sc-min',p==='average'||(c&&v.count==='all'));sh('sc-pts',c&&v.by==='points');sh('sc-pen',c&&v.short==='slowest');ab.textContent=scoringAbout(v);if(f.onscoring)f.onscoring(v)}
  [].forEach.call(g.querySelectorAll('input,select'),function(x){x.addEventListener('change',vis);x.addEventListener('input',vis)});
  var out=function(){var v=val();return $('scp').value==='custom'?v:{preset:$('scp').value,size:v.size,best:v.best,min:v.min}};out.value=val;out.box=f;setTimeout(vis,0);return out}
// a match's teams: each its lineup (who counts in bold, their time or how far they are) and its score
function matchTable(box,teams,s){var tw=el('div','tablewrap'),tb=el('table');tw.appendChild(tb);box.appendChild(tw);
  var h=el('tr');add(h,el('th',null,${tq('Pos')}),el('th',null,${tq('Team')}),el('th',null,${tq('Drivers')}),el('th','r',${tq('Score')}));tb.appendChild(h);
  teams.slice().sort(function(a,b){return (a.rank||9)-(b.rank||9)}).forEach(function(x){var tr=el('tr',x.rank===1?'p1':'');add(tr,el('td','pos',x.rank?String(x.rank):''));
    tr.appendChild(teamName(el('td','drv'),x));var dd=el('td');if(!x.drivers.length)dd.textContent=${tq('nobody named yet')};
    x.drivers.forEach(function(d,i){if(i)add(dd,', ');var st=d.totalMs!=null?ms(d.totalMs):d.status==='finished'?'✓':d.status==='dnf'?${tq('DNF')}:d.status==='dsq'?${tq('DSQ')}:d.status==='running'?'…':
      d.status==='not started'?'('+${tq('not started')}+')':'';
      add(dd,d.counted?el('b',null,d.name||${tq('a driver')}):(d.name||${tq('a driver')}),st?' '+st:'')});tr.appendChild(dd);
    var sc=el('td','r tot',x.score===undefined?${tq('hidden')}:score(s,x.score));if(x.missing&&x.score!=null)sc.appendChild(el('small','muted',' '+P(${tqp('{0} missing', '{0} missing')},x.missing)));
    tr.appendChild(sc);tb.appendChild(tr)})}
// drivers to tick (a lineup, a roster): -> function giving the ticked steam ids
function ticks(box,drivers,on,max){var tk=el('div','ticks');drivers.forEach(function(d){var l=el('label'),c=el('input');c.type='checkbox';c.value=d.steamId;c.checked=on.indexOf(d.steamId)>=0;
    c.onchange=function(){if(max&&tk.querySelectorAll('input:checked').length>max)c.checked=false};add(l,c,d.name);tk.appendChild(l)});box.appendChild(tk);
  return function(){return [].map.call(tk.querySelectorAll('input:checked'),function(c){return c.value})}}
`;

// ------------------------------------------------------------------ /team1v1
export function teamH2hPage(env) {
  const hours = Math.round(TH2H.answerMs / 3600000), days = TH2H.windowDays;
  return shell(t('Team 1V1') + ' · ACR Daily', `${SOCIAL_CSS}${CSS}
  <div class="top"><div class="kick"><a href="/1v1">1V1</a> · <a href="/teams">${t('Teams')}</a></div><h1>${t('Team 1V1')}</h1>
  <p class="note">${t("A team's captain or a manager challenges another team: the stages, the car, who drives and how the teams are scored. The other team's captain or a manager has {0} hours to accept. Then the drivers drive it in the app's <b>1V1</b> tab. No credits, not rated.", hours)}</p>
  <div class="facts" id="facts"></div><div class="row" style="margin-top:18px" id="acts"></div><div class="msg" id="m"></div></div>
  <h2>${t('Waiting for your team')}</h2><div id="incoming"></div>
  <h2>${t('Sent')}</h2><div id="outgoing"></div>
  <h2>${t('Under way')}</h2><div id="active"></div>
  <h2>${t('Finished')}</h2><div id="past"></div>
  <h2 id="new">${t('Challenge a team')}</h2><div class="formcard" id="form"></div>`, `${SOCIAL_JS()}${BUILDER_JS()}${SCORING_JS()}
  var H=null,CAT=null,B=null,SF=null,FORM=false,HS={name:'',opens:null,closes:null};
  function fact(k){var d=el('div'),b=el('b');for(var i=1;i<arguments.length;i++)add(b,arguments[i]);add(d,el('span','k',k),b);$('facts').appendChild(d)}
  function load(){return api('/api/th2h').then(render,function(e){msg('m',e.message)})}
  function render(h){H=h;$('facts').innerHTML='';
    if(!h.team){['incoming','outgoing','active','past'].forEach(function(id){$(id).innerHTML=''});
      $('incoming').appendChild(el('div','empty',${tq('You are in no team: join or make one on the Teams page.')}));$('form').innerHTML='';
      var tl=el('a','btn',${tq('Teams')});tl.href='/teams';$('acts').innerHTML='';$('acts').appendChild(tl);return}
    var tn=el('a');tn.href='/t/'+h.team.id;tn.style.textDecoration='none';teamName(tn,h.team);fact(${tq('Your team')},tn);fact(${tq('You')},ROLE[h.team.role]||h.team.role);
    list('incoming',h.incoming,${tq('No challenges for your team right now.')});list('outgoing',h.outgoing,${tq('Nothing sent and waiting.')});
    list('active',h.active,${tq('No team 1V1 under way.')});list('past',h.past,${tq('None yet.')});if(!FORM){FORM=true;form()}}
  function list(id,xs,empty){var box=$(id);box.innerHTML='';if(!xs.length){box.appendChild(el('div','empty',empty));return}xs.forEach(function(x){box.appendChild(item(x,id))})}
  function other(x){return x.mine==='challenger'?x.opponent:x.challenger}
  function mine(x){return x.mine==='challenger'?x.challenger:x.opponent}
  function item(x,kind){var it=el('div','hh'),g=el('div','grow'),o=other(x);add(g,el('div','t',x.name));
    var s1=el('div','s');add(s1,FN(kind==='incoming'?${tq('From {0}')}:kind==='outgoing'?${tq('To {0}')}:${tq('Against {0}')},teamName(el('b'),o)),' · '+F(${tq('sent by {0}')},x.by.name));
    add(g,s1,el('div','s',scoringAbout(x.scoring)));var s2=el('div','s');add(s2,el('b',null,TD(x.rally)),' · '+carText(x));
    add(g,s2,el('div','s',stagesText(x)),el('div','s',F(${tq('Open {0} – {1}')},when(x.opens),when(x.closes))),ruleChips(x.rules));
    if(x.teams)matchTable(g,x.teams,x.scoring);
    var r=el('div','hr'),runs=H.team.runs;
    if(kind==='incoming'){add(r,el('span',null,F(${tq('Answer by {0}')},when(x.answerBy))+(left(x.answerBy)?' ('+F(${tq('{0} left')},left(x.answerBy))+')':'')));
      if(runs){var a=el('div','actions'),ok=el('button','btn',${tq('Accept')}),no=el('button','btn ghost',${tq('Decline')});
        ok.onclick=function(){if(!confirm(F(${tq('Accept {0} against {1}?')},x.name,o.name)))return;ok.disabled=no.disabled=true;
          api('/api/th2h/'+x.id+'/accept',{}).then(function(){msg('m',${tq('Accepted: your drivers drive it in the app, under 1V1.')},true);load()},function(e){ok.disabled=no.disabled=false;msg('m',e.message)})};
        no.onclick=function(){if(!confirm(F(${tq('Decline {0}?')},x.name)))return;ok.disabled=no.disabled=true;
          api('/api/th2h/'+x.id+'/decline',{}).then(load,function(e){ok.disabled=no.disabled=false;msg('m',e.message)})};add(a,ok,no);r.appendChild(a)}
      else add(r,el('span','muted',${tq('Your captain or a manager answers it.')}))}
    else if(kind==='outgoing'){add(r,el('span',null,F(${tq('Waiting for {0} · until {1}')},o.name,when(x.answerBy))));
      if(runs){var cb=el('button','btn ghost small',${tq('Cancel')});cb.onclick=function(){if(!confirm(F(${tq('Cancel {0}?')},x.name)))return;cb.disabled=true;
        api('/api/th2h/'+x.id+'/cancel',{}).then(load,function(e){cb.disabled=false;msg('m',e.message)})};r.appendChild(cb)}}
    else if(kind==='active'){var on=Date.now()>=x.opens;
      add(r,el('span',null,on?F(${tq('Closes {0}')},when(x.closes))+(left(x.closes)?' ('+F(${tq('{0} left')},left(x.closes))+')':''):F(${tq('Opens {0}')},when(x.opens))));
      if(x.eventId){var mt=el('a','btn small',${tq('The match ›')});mt.href='/e/'+x.eventId;r.appendChild(mt)}else add(r,el('span','muted',${tq('The match is being set up.')}));
      if(runs&&x.scoring.lineup==='named'&&x.eventId)lineupEd(g,x)}
    else{r.appendChild(result(x));if(x.eventId){var lk=el('a','btn ghost small',${tq('The match ›')});lk.href='/e/'+x.eventId;r.appendChild(lk)}
      if(x.status==='settled'&&runs){var rb=el('button','btn small',${tq('Rematch')});rb.onclick=function(){if(!confirm(F(${tq('Rematch {0}: the same stages, car, rules and scoring?')},o.name)))return;rb.disabled=true;
        api('/api/th2h/'+x.id+'/rematch',{}).then(function(){msg('m',F(${tq('Rematch sent to {0}.')},o.name),true);load()},function(e){rb.disabled=false;msg('m',e.message)})};r.appendChild(rb)}}
    add(it,g,r);return it}
  function lineupEd(g,x){var me=mine(x),cur=(x.teams||[]).filter(function(t){return t.id===me.id})[0],have=cur?cur.drivers.map(function(d){return d.steamId}):[];
    var box=el('div','lineup');add(box,el('h3',null,${tq('Your lineup')}),el('p','note',F(${tq('Up to {0} drivers. A driver who has started stays in it.')},x.scoring.size)));
    var pick=ticks(box,H.team.drivers,have,x.scoring.size);var sv=el('button','btn small',${tq('Save the lineup')});sv.style.marginTop='10px';
    sv.onclick=function(){sv.disabled=true;api('/api/th2h/'+x.id+'/lineup',{steamIds:pick()}).then(function(){msg('m',${tq('Lineup saved: its drivers are told.')},true);load()},function(e){sv.disabled=false;msg('m',e.message)})};
    box.appendChild(sv);g.appendChild(box)}
  function result(x){var my=mine(x),o=other(x);
    if(x.status==='settled'){if(!x.winner)return el('span','res off',F(${tq('No contest ({0})')},x.note||''));
      return el('span','res'+(x.winner===my.id?' won':''),(x.winner===my.id?${tq('Your team won')}:F(${tq('{0} won')},o.name))+(x.note?' ('+x.note+')':''))}
    if(x.status==='declined')return el('span','res off',x.mine==='challenger'?F(${tq('{0} declined')},o.name):${tq('Your team declined')});
    if(x.status==='expired')return el('span','res off',${tq('Not answered in time')});
    if(x.status==='cancelled')return el('span','res off',x.mine==='challenger'?${tq('Your team cancelled it')}:F(${tq('{0} cancelled it')},o.name));
    return el('span','res off',x.status)}
  // ---- the challenge: which team, how it is scored, the event (the league event builder, with its window)
  function form(){var f=$('form');f.innerHTML='';
    if(!H.team.runs){add(f,el('p','muted',${tq("Your team's captain and managers challenge other teams.")}));return}
    var g=el('div','twocol');f.appendChild(g);var ol=el('label'),os=el('select');os.id='oppt';add(ol,el('span',null,${tq('The team you challenge')}),os);g.appendChild(ol);
    api('/api/teams').then(function(r){var o0=el('option',null,${tq('Pick a team…')});o0.value='';os.appendChild(o0);
      r.teams.filter(function(x){return x.id!==H.team.id}).forEach(function(x){var o=el('option',null,(x.tag?'['+x.tag+'] ':'')+x.name+' · '+P(${tqp('{0} driver', '{0} drivers')},x.members));o.value=x.id;os.appendChild(o)});
      var q=new URLSearchParams(location.search).get('team');if(q)os.value=q},function(){});
    add(f,el('h3',null,${tq('How the teams are scored')}));SF=scoringForm(f,H.maxSize);
    add(f,el('h3',null,${tq('The event')}));var bx=el('div','builder');f.appendChild(bx);add(bx,el('div','empty',${tq('Loading…')}));
    api('/api/catalog').then(function(c){CAT=c;var now=Date.now();HS.opens=Math.ceil(now/900000)*900000;HS.closes=HS.opens+3*86400000;
      B=eventBuilder(bx,{cat:CAT,state:HS,name:{label:${tq('Name (optional)')},placeholder:${tq('e.g. Friday team duel')}},window:true,
        windowNote:${tq('Up to {0} days. They have {1} hours to answer.', days, hours)},
        after:function(b){var sb=el('button','btn',${tq('Send the challenge')});sb.style.marginTop='22px';sb.onclick=send;b.appendChild(sb);add(b,el('div','msg'));b.lastChild.id='hm'}});
      B.draw();if(new URLSearchParams(location.search).get('team'))$('new').scrollIntoView()},function(e){bx.innerHTML='';add(bx,el('div','empty',e.message))})}
  function send(){var b=this,to=$('oppt').value;if(!to){msg('hm',${tq('Pick the team you challenge first.')});return}
    b.disabled=true;api('/api/th2h',{opponent:to,event:B.body(),scoring:SF()}).then(function(){b.disabled=false;msg('hm',${tq('Sent: their captain and managers are told.')},true);
      load().then(function(){$('outgoing').scrollIntoView({behavior:'smooth',block:'center'})})},function(e){b.disabled=false;msg('hm',e.message)})}
  account().then(function(me){if(!me){['incoming','outgoing','active','past'].forEach(function(id){$(id).innerHTML=''});
      $('incoming').appendChild(el('div','empty',${tq('Sign in with Steam to see your team 1V1s.')}));$('acts').appendChild(steamBtn());$('form').innerHTML='';return}
    var nb=el('a','btn',${tq('Challenge a team')});nb.href='#new';$('acts').appendChild(nb);load()});
  `, env);
}

// ------------------------------------------------------------------ /tcups
export function teamCupsPage(env) {
  return shell(t('Team cups') + ' · ACR Daily', `${SOCIAL_CSS}${CSS}
  <div class="top"><div class="kick"><a href="/cups">${t('Cups')}</a> · <a href="/teams">${t('Teams')}</a></div><h1>${t('Team cups')}</h1>
  <p class="note">${t("Knockouts of team matches. A team's captain or a manager signs it up with its drivers; each match, the teams' results are added up as the cup says (the best few times, the average, the drivers the team names...). Drive your matches in the app's <b>CUPS</b> tab. No entry fee, not rated.")}</p>
  <div class="row" style="margin-top:18px" id="acts"></div><div class="msg" id="m"></div></div>
  <h2>${t('Open for entries')}</h2><div id="open"></div>
  <h2>${t('Under way')}</h2><div id="running"></div>
  <h2>${t('Finished')}</h2><div id="finished"></div>
  <h2 id="new">${t('Create a team cup')}</h2><div class="formcard" id="form"></div>`, `${SOCIAL_JS()}${BUILDER_JS()}${SCORING_JS()}
  var C=null,CAT=null,B=null,SF=null,FORM=false,CS={};
  function bsize(n){var b=2;while(b<n)b*=2;return b}
  function load(){return api('/api/tcups').then(render,function(e){msg('m',e.message)})}
  function render(c){C=c;list('open',c.open,${tq('No team cup open for entries right now: create one below.')});list('running',c.running,${tq('No team cup under way.')});
    list('finished',c.finished,${tq('None yet.')});if(!FORM){FORM=true;form()}}
  function list(id,xs,empty){var box=$(id);box.innerHTML='';if(!xs.length){box.appendChild(el('div','empty',empty));return}xs.forEach(function(x){box.appendChild(item(x,id))})}
  function item(c,kind){var it=el('div','cupi'+(c.official?' official':'')),a=el('a','grow');a.href='/tcup/'+c.id;
    var tt=el('div','t',c.name+' ');if(c.official)add(tt,officialBadge(),' ');if(C.mine.indexOf(c.id)>=0)tt.appendChild(el('span','badge upcoming',${tq('your team is in')}));
    add(a,tt,el('div','s',TD(c.rally)+' · '+P(${tqp('{0} stage', '{0} stages')},c.stages.length)+' · '+(c.car||F(${tq('{0} class')},c.carClass))+' · '+F(${tq('rounds of {0}')},roundLength(c.roundHours))+' · '+F(${tq('by {0}')},c.owner.name)),
      el('div','s',scoringAbout(c.scoring)));
    var r=el('div','r'),d=el('div');
    if(kind==='open')add(d,F(${tq('{0} of {1} teams')},c.teams,c.size),el('br'),F(${tq('starts {0}')},when(c.starts)));
    else if(kind==='running')add(d,F(${tq('{0} under way')},roundName(c.round,Math.log2(bsize(c.teams)))),el('br'),P(${tqp('{0} team', '{0} teams')},c.teams));
    else add(d,P(${tqp('{0} team', '{0} teams')},c.teams),el('br'),F(${tq('started {0}')},when(c.starts)));
    r.appendChild(d);add(it,a,r);return it}
  function radios(name,vals,labels,cur){var d=el('div','radio');vals.forEach(function(v,i){var l=el('label'),inp=el('input');inp.type='radio';inp.name=name;inp.value=String(v);inp.checked=v===cur;
    add(l,inp,el('span',null,labels[i]));d.appendChild(l)});return d}
  function picked(name){var x=document.querySelector('input[name='+name+']:checked');return x?x.value:''}
  function field(p,label,node,cls){var l=el('label',cls||null);add(l,el('span',null,label),node);p.appendChild(l);return l}
  function form(){var f=$('form');f.innerHTML='';var L=C.limits;
    if(!ME){add(f,el('p','muted',${tq('Sign in with Steam to create a team cup.')}));f.appendChild(steamBtn());return}
    var g=el('div','twocol');f.appendChild(g);
    var nm=el('input');nm.type='text';nm.id='cn';nm.maxLength=60;nm.placeholder=${tq('e.g. Autumn Team Cup')};field(g,${tq('Name')},nm);
    var sz=el('div');sz.appendChild(radios('csz',L.sizes,L.sizes.map(function(n){return P(${tqp('{0} team', '{0} teams')},n)}),8));field(g,${tq('Size (at most)')},sz);
    var ab=el('textarea');ab.id='ca';ab.maxLength=600;ab.placeholder=${tq('Who it is for, your Discord...')};field(f,${tq('About (optional)')},ab);
    var g2=el('div','twocol');f.appendChild(g2);
    var stt=el('input');stt.type='datetime-local';stt.id='cst';stt.value=localInput(Math.ceil(Date.now()/3600000)*3600000+2*86400000);field(g2,${tq('Starts (your time): entries close, round 1 opens')},stt);
    var rh=el('div');rh.appendChild(radios('crh',L.roundHours,L.roundHours.map(function(h){return roundLength(h)}),48));field(g2,${tq('Each round is open')},rh);
    add(f,el('h3',null,${tq('How a match is scored')}));SF=scoringForm(f,L.maxSize);
    var g3=el('div','twocol');f.appendChild(g3);
    var lf=el('select');lf.id='clf';[['match',${tq('Named for each match, from its roster')}],['cup',${tq('Its roster, for the whole cup')}]].forEach(function(o){var x=el('option',null,o[1]);x.value=o[0];lf.appendChild(x)});
    var lfl=field(g3,${tq('Who a team names to drive')},lf);
    var rmin=el('input');rmin.type='number';rmin.id='crmin';rmin.min=L.roster[0];rmin.max=L.roster[1];rmin.value='3';var rminl=field(g3,${tq('Drivers a team signs up: at least')},rmin);
    var rmax=el('input');rmax.type='number';rmax.id='crmax';rmax.min=L.roster[0];rmax.max=L.roster[1];rmax.value='6';var rmaxl=field(g3,${tq('… and at most')},rmax);
    var rn=el('p','note');f.appendChild(rn);
    function rost(){var v=SF.value(),named=v.lineup==='named',whole=named&&lf.value==='cup';lfl.style.display=named?'':'none';rminl.style.display=rmaxl.style.display=whole?'none':'';
      rn.textContent=whole?P(${tqp('Each team signs up exactly {0} driver: they drive every match.', 'Each team signs up exactly {0} drivers: they drive every match.')},v.size):
        named?F(${tq("For each match, the team's captain or a manager names {0} of its roster.")},v.size):${tq('Any driver on the roster can drive each match.')}}
    SF.box.onscoring=rost;lf.onchange=rost;setTimeout(rost,0);
    add(f,el('h3',null,${tq('All matches')}),el('p','note',${tq('The stages, car and settings for all matches.')}));
    var bx=el('div','builder');f.appendChild(bx);add(bx,el('div','empty',${tq('Loading…')}));
    api('/api/catalog').then(function(c){CAT=c;B=eventBuilder(bx,{cat:CAT,state:CS,name:false,window:false,after:function(b){
      var sb=el('button','btn',${tq('Create the team cup')});sb.style.marginTop='22px';sb.onclick=create;b.appendChild(sb);add(b,el('div','msg'));b.lastChild.id='cm'}});B.draw()},
      function(e){bx.innerHTML='';add(bx,el('div','empty',e.message))})}
  function create(){var b=this,st=new Date($('cst').value).getTime();if(!st){msg('cm',${tq('Set when the cup starts.')});return}
    b.disabled=true;api('/api/tcups',{name:$('cn').value,about:$('ca').value,size:+picked('csz'),event:B.body(),starts:st,roundHours:+picked('crh'),
      scoring:SF(),lineupFor:$('clf').value,rosterMin:+$('crmin').value,rosterMax:+$('crmax').value})
      .then(function(j){location.href='/tcup/'+j.id},function(e){b.disabled=false;msg('cm',e.message)})}
  account().then(function(me){var nb=el('a','btn',${tq('Create a team cup')});nb.href='#new';$('acts').appendChild(nb);if(!me)$('acts').appendChild(steamBtn());load()},
    function(){$('acts').appendChild(steamBtn());load()});
  `, env);
}

// ------------------------------------------------------------------ /tcup/:id
export function teamCupPage(id, env) {
  return shell(t('Team cup') + ' · ACR Daily', `${SOCIAL_CSS}${CSS}
  <img class="banner" id="banner" alt="" hidden>
  <div class="top"><div class="kick" id="kick"><a href="/tcups">${t('Team cups')}</a></div><h1 id="name"></h1><p class="about" id="about"></p>
    <div class="facts" id="facts"></div><p class="note" id="how"></p><div class="chips" id="rules"></div>
    <div class="row" style="margin-top:18px" id="acts"></div><div class="msg" id="m"></div><div id="sign"></div></div>
  <h2>${t('Bracket')}</h2><div id="bracket"></div><div id="mymatch"></div>
  <h2>${t('Teams')}</h2><div id="teams"></div>`, `${SOCIAL_JS()}${SCORING_JS()}
  var ID=${JSON.stringify(id)},C=null;
  function fact(k){var d=el('div'),b=el('b');for(var i=1;i<arguments.length;i++)add(b,arguments[i]);add(d,el('span','k',k),b);$('facts').appendChild(d)}
  function load(){return api('/api/tcups/'+ID).then(render,function(e){$('name').textContent=e.status===404?${tq('No such team cup')}:${tq('Team cup')};msg('m',e.message)})}
  function render(c){C=c;document.title=c.name+' · ACR Daily';$('name').textContent=c.name;$('about').textContent=c.about||'';showBanner($('banner'),c.banner);
    var k=$('kick');k.innerHTML='';var ca=el('a',null,${tq('Team cups')});ca.href='/tcups';add(k,ca,' · ');if(c.official)add(k,officialBadge(),' ');add(k,F(${tq('by {0}')},c.owner.name));
    $('facts').innerHTML='';var open=c.status==='open';
    fact(${tq('Teams')},F(${tq('{0} of {1}')},c.teams.length,c.size));fact(open?${tq('Starts')}:${tq('Started')},when(c.starts));fact(${tq('Each round')},roundLength(c.roundHours));
    fact(${tq('Rosters')},c.rosterMin===c.rosterMax?P(${tqp('{0} driver', '{0} drivers')},c.rosterMin):F(${tq('{0} to {1} drivers')},c.rosterMin,c.rosterMax));
    fact(${tq('Status')},open?${tq('open for entries')}:c.status==='running'?roundName(c.round,c.rounds||1):c.status==='finished'?${tq('finished')}:${tq('called off')});
    $('how').textContent=TD(c.rally)+' · '+carText(c)+' · '+stagesText(c)+' · '+scoringAbout(c.scoring)+(c.lineupFor==='cup'?' · '+${tq('the rosters drive every match')}:c.lineupFor==='match'?' · '+${tq("each match, the team's captain or a manager names who drives")}:'');
    var r=$('rules');r.innerHTML='';r.appendChild(ruleChips(c.rules));
    acts(c);bracket(c);myMatch(c);teams(c)}
  function acts(c){var a=$('acts');a.innerHTML='';$('sign').innerHTML='';var me=c.me,open=c.status==='open'&&Date.now()<c.starts;
    if(!me.signedIn){a.appendChild(steamBtn());return}
    var T=me.team;
    if(open&&T&&T.runs&&!T.entered&&c.teams.length<c.size){var j=el('button','btn',${tq('Sign up your team')});j.onclick=function(){rosterForm(c,true)};a.appendChild(j)}
    if(open&&T&&T.runs&&T.entered){var ch=el('button','btn ghost small',${tq('Change the roster')});ch.onclick=function(){rosterForm(c,false)};
      var lv=el('button','btn ghost small',${tq('Take the team out')});lv.onclick=function(){if(!confirm(F(${tq('Take {0} out of {1}?')},T.name,c.name)))return;
        api('/api/tcups/'+ID+'/leave',{}).then(load,function(e){msg('m',e.message)})};add(a,ch,lv)}
    if(open&&me.onRoster){var wd=el('button','btn ghost small',${tq('Take me off the roster')});wd.onclick=function(){if(!confirm(${tq("Take yourself off your team's roster?")}))return;
      api('/api/tcups/'+ID+'/withdraw',{}).then(load,function(e){msg('m',e.message)})};a.appendChild(wd)}
    if(open&&!T)add(a,el('span','muted',${tq("Join a team to take part: its captain or a manager signs it up.")}));
    else if(open&&T&&!T.runs&&!T.entered)add(a,el('span','muted',${tq("Your team's captain or a manager signs it up.")}));
    if(open&&me.owner){var cb=el('button','btn danger small',${tq('Call it off')});cb.onclick=function(){if(!confirm(F(${tq('Call {0} off? Every team is told.')},c.name)))return;
      api('/api/tcups/'+ID+'/cancel',{}).then(load,function(e){msg('m',e.message)})};a.appendChild(cb)}}
  function rosterForm(c,join){var box=$('sign');box.innerHTML='';var T=c.me.team,mine=c.teams.filter(function(t){return t.id===T.id})[0];
    var f=el('div','lineup');add(f,el('h3',null,join?F(${tq('Sign up {0}')},T.name):${tq('The roster')}),
      el('p','note',c.rosterMin===c.rosterMax?P(${tqp('Tick {0} driver of your team.', 'Tick {0} drivers of your team.')},c.rosterMin):F(${tq('Tick {0} to {1} drivers of your team.')},c.rosterMin,c.rosterMax)));
    var pick=ticks(f,T.drivers||[],mine?mine.roster.map(function(r){return r.steamId}):[],c.rosterMax);
    var sv=el('button','btn small',join?${tq('Sign up')}:${tq('Save the roster')});sv.style.marginTop='10px';
    sv.onclick=function(){sv.disabled=true;api('/api/tcups/'+ID+(join?'/join':'/roster'),{steamIds:pick()}).then(function(){msg('m',join?${tq('Your team is in. Its drivers are told.')}:${tq('Saved.')},true);load()},
      function(e){sv.disabled=false;msg('m',e.message)})};f.appendChild(sv);box.appendChild(f)}
  function teams(c){var box=$('teams');box.innerHTML='';if(!c.teams.length){box.appendChild(el('div','empty',${tq('No team has signed up yet.')}));return}
    c.teams.forEach(function(x){var it=el('div','tmrow'),d=el('div'),h=el('div','t');var a=el('a');a.href='/t/'+x.id;a.style.textDecoration='none';teamName(a,x);h.appendChild(a);
      if(c.me.team&&x.id===c.me.team.id)add(h,' ',el('span','badge upcoming',${tq('your team')}));
      add(d,h,el('div','s',x.roster.map(function(r){return r.name+(r.rating!=null?' ('+r.rating+')':'')}).join(', ')));
      var r=el('div','r');add(r,x.place?el('b',null,F(${tq('{0} place')},nth(x.place))):x.seed?F(${tq('seed {0}')},x.seed):'',el('br'),F(${tq('team rating {0}')},x.rating));add(it,d,r);box.appendChild(it)})}
  function bracket(c){var box=$('bracket');box.innerHTML='';if(!c.matches.length){box.appendChild(el('div','empty',c.status==='open'?F(${tq('The bracket is drawn when the cup starts, {0}.')},when(c.starts)):${tq('No matches.')}));return}
    var br=el('div','bracket');box.appendChild(br);
    for(var rd=1;rd<=c.rounds;rd++){var col=el('div','rnd'+(rd===c.round&&c.status==='running'?' now':''));add(col,el('div','rh',roundName(rd,c.rounds)));var rl=el('div','rl');col.appendChild(rl);
      c.matches.filter(function(m){return m.round===rd}).forEach(function(m){var mt=el('div','mt');
        [m.a,m.b].forEach(function(s,i){var x=m.teams&&s?m.teams.filter(function(y){return y.id===s.id})[0]:null;
          var sd=el('div','sd'+(!s?' bye':m.winner?(m.winner===s.id?' won':' lost'):'')+(s&&c.me.team&&s.id===c.me.team.id?' me':''));
          add(sd,el('span','sn',s&&s.seed?String(s.seed):''),s?teamName(el('span','nm'),s):el('span','nm',${tq('bye')}),el('span','tm',x&&x.score!==undefined&&x.score!=null?score(c.scoring,x.score):''));mt.appendChild(sd)});
        var mf=el('div','mf');add(mf,el('span',null,m.note||(m.closes?F(${tq('closes {0}')},when(m.closes)):'')));
        if(m.eventId){var lk=el('a',null,${tq('Match ›')});lk.href='/e/'+m.eventId;mf.appendChild(lk)}mt.appendChild(mf);rl.appendChild(mt)});
      br.appendChild(col)}}
  // my team's match this round: its teams and lineups; named per match, its captain and managers name who drives
  function myMatch(c){var box=$('mymatch');box.innerHTML='';var T=c.me.team;if(!T||c.status!=='running')return;
    var m=c.matches.filter(function(x){return x.round===c.round&&x.teams&&!x.winner&&(x.a&&x.a.id===T.id||x.b&&x.b.id===T.id)})[0];if(!m)return;
    add(box,el('h2',null,F(${tq('Your match: {0}')},m.name)));matchTable(box,m.teams,c.scoring);
    if(c.lineupFor==='match'&&T.runs){var cur=m.teams.filter(function(x){return x.id===T.id})[0],have=cur?cur.drivers.map(function(d){return d.steamId}):[];
      var mine=c.teams.filter(function(x){return x.id===T.id})[0],f=el('div','lineup');add(f,el('h3',null,${tq('Your lineup')}),el('p','note',F(${tq('Up to {0} drivers of your roster. A driver who has started stays in it.')},c.scoring.size)));
      var pick=ticks(f,mine?mine.roster:[],have,c.scoring.size);var sv=el('button','btn small',${tq('Save the lineup')});sv.style.marginTop='10px';
      sv.onclick=function(){sv.disabled=true;api('/api/tcups/'+ID+'/lineup',{eventId:m.eventId,steamIds:pick()}).then(function(){msg('lm',${tq('Lineup saved: its drivers are told.')},true);load()},
        function(e){sv.disabled=false;msg('lm',e.message)})};f.appendChild(sv);add(f,el('div','msg'));f.lastChild.id='lm';box.appendChild(f)}}
  account().then(load,load);
  `, env);
}
