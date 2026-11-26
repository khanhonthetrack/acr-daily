// /ranked: RANKED on the website, as the app's RANKED page in the game shows it (the user, 24 Nov 2026: "In Ranked the
// view should be like in the game. The next 4 events, how many signed up, logos of the championship"): the next four
// sessions as cards (the series' tile, its hour, rally, class, how many registered, a countdown), the four series, and
// the last sessions' winners. From /api/liverallies (src/liverallies.js), as the app reads it; registering stays in the
// app (the car is picked there, from the player's game).

import { N_, t, tq } from './i18n.js';
import { shell } from './leaguepages.js';
import { SPECIALS } from './liverallies.js';

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

// (the words its script shows, in the reader's language)
N_('registration open'); N_('under way'); N_('upcoming'); N_('{0} registered'); N_('starts in {0}'); N_('closes in {0}');
N_('No ranked sessions in the next hours.'); N_('Winner'); N_('{0} drivers'); N_('Results'); N_('you are in');

const CSS = `<style>
.rk h2{margin:34px 0 10px}
.rkn{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
@media (max-width:1000px){.rkn{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:560px){.rkn{grid-template-columns:1fr}}
.rkc{background:var(--panel);border:1px solid var(--line);border-top:3px solid var(--acc);display:flex;flex-direction:column}
.rkc.run{border-top-color:#30D158}
.rkc img.tile{display:block;width:100%;aspect-ratio:16/9;object-fit:cover}
.rkc .b{padding:12px 14px 14px;display:flex;flex-direction:column;gap:4px}
.rkc .at{font:700 30px/1 "Barlow Condensed",sans-serif;letter-spacing:.02em}
.rkc .nm{font:700 18px/1.15 "Barlow Condensed",sans-serif;letter-spacing:.04em;text-transform:uppercase}
.rkc .ln{color:var(--fg2);font-size:14px}
.rkc .reg{display:flex;align-items:baseline;gap:6px;margin-top:6px}
.rkc .reg b{font:700 34px/1 "Barlow Condensed",sans-serif}.rkc .reg span{color:var(--fg2);font-size:14px}
.chip{display:inline-block;font:700 11px/1 Barlow,sans-serif;letter-spacing:.1em;text-transform:uppercase;padding:4px 7px;border:1px solid var(--line);color:var(--fg2);align-self:flex-start}
.chip.open{border-color:var(--acc);color:#fff;background:var(--acc)}.chip.run{border-color:#30D158;color:#30D158}
.cd{color:var(--fg2);font-size:13px;font-variant-numeric:tabular-nums}
.rks{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
@media (max-width:1000px){.rks{grid-template-columns:repeat(2,minmax(0,1fr))}}
.rks .s{background:var(--panel);border:1px solid var(--line);padding:14px;display:flex;flex-direction:column;align-items:flex-start;gap:6px}
.rks img{width:100%;max-width:220px;height:auto}.rks b{font:700 18px/1.1 "Barlow Condensed",sans-serif;text-transform:uppercase;letter-spacing:.04em}
.rks small{color:var(--fg2)}
.rkr{width:100%;border-collapse:collapse}.rkr td{border-top:1px solid var(--line);padding:8px 10px 8px 0;vertical-align:middle}
.rkr img.lg{width:64px;height:auto;display:block}.rkr .w{font-weight:600}.rkr .t{font-variant-numeric:tabular-nums;color:var(--fg2)}
.rkhow{color:var(--fg2);max-width:760px}
.sphero{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:0;background:var(--panel);border:1px solid var(--line);
  border-top:3px solid #78FAAE;margin-top:18px;text-decoration:none;color:inherit}
.sphero:hover{border-color:#78FAAE}
@media (max-width:820px){.sphero{grid-template-columns:1fr}}
.sphero img{display:block;width:100%;height:100%;object-fit:cover;aspect-ratio:1200/630}
.sphero .b{padding:18px 22px;display:flex;flex-direction:column;gap:8px;justify-content:center}
.sphero .k{font:700 12px/1 Barlow,sans-serif;letter-spacing:.16em;text-transform:uppercase;color:#78FAAE}
.sphero .n{font:700 34px/1.05 "Barlow Condensed",sans-serif;letter-spacing:.02em;text-transform:uppercase}
.sphero .w{font:600 20px/1.2 "Barlow Condensed",sans-serif}
.sphero .f{color:var(--fg2);font-size:15px}
.sphero .go{align-self:flex-start;margin-top:6px;background:#78FAAE;color:#04140E;font:700 14px/1 Barlow,sans-serif;letter-spacing:.08em;
  text-transform:uppercase;padding:10px 14px}
</style>`;

// (the words of a special event's card and page, in the reader's language)
N_('SPECIAL EVENT'); N_('Register ›'); N_('Registration open'); N_('{0} registered'); N_('Under way'); N_('Results ›');
N_('Watch it live ›'); N_('Free entry'); N_('{0} credits for every driver who finishes'); N_('{0} stages of {1}');
N_('The stages, the weather and the time of day are drawn at the start: nobody can prepare them.');

/** A special event's card (the RANKED page's top, the home page's strip), drawn by the page's script from
 *  /api/liverallies `specials`. */
const SPECIAL_JS = `
  var SW={sp:${tq('SPECIAL EVENT')},reg:${tq('Register ›')},open:${tq('Registration open')},n:${tq('{0} registered')},run:${tq('Under way')},
    res:${tq('Results ›')},free:${tq('Free entry')},prize:${tq('{0} credits for every driver who finishes')},st:${tq('{0} stages of {1}')}};
  function spWhen(ms){var d=new Date(ms);return d.toLocaleDateString([],{weekday:'long',day:'numeric',month:'long'})+' · '+
    d.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}
  function spCard(s){var a=el('a','sphero');a.href='/ranked/'+s.key;var i=el('img');i.src='/series/'+s.key+'-banner.webp';i.alt=s.name;add(a,i);
    var b=el('div','b');add(b,el('div','k',SW.sp+' · '+(s.phase==='running'?SW.run:s.phase==='over'?SW.res.replace(' ›',''):SW.open)),
      el('div','n',s.name),el('div','w',spWhen(s.starts)),
      el('div','f',[SW.st.replace('{0}',s.stages).replace('{1}',s.rally),s.cars&&s.cars[0]?s.cars[0].name:'',SW.free].join(' · ')),
      s.prize?el('div','f',SW.prize.replace('{0}',s.prize)):null,el('div','f',SW.n.replace('{0}',s.signups||0)),
      el('span','go',s.phase==='signup'?SW.reg:s.phase==='running'?${tq('Watch it live ›')}:SW.res));add(a,b);return a}`;

export function rankedPage(env) {
  return shell(`${esc(t('Ranked'))} · ACR Daily`, `${CSS}
  <div class="rk">
  <div class="top"><div class="kick">${esc(t('Competitions'))}</div><h1>${esc(t('Ranked'))}</h1>
  <p class="note rkhow">${esc(t('Official rallies every hour, the four series in turn: three stages, one car at a time, 20 s to start on your turn. Register in the ACR DAILY app in the 30 minutes before the hour; your rating moves with every result.'))}</p></div>
  <div id="rksp"></div>
  <h2>${esc(t('Next sessions'))}</h2>
  <div class="rkn" id="rkn"><div class="note">${esc(t('Loading…'))}</div></div>
  <h2>${esc(t('The series'))}</h2>
  <div class="rks" id="rks"></div>
  <h2>${esc(t('Latest results'))}</h2>
  <table class="rkr" id="rkr"></table>
  </div>`, `
  function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
  function add(p){for(var i=1;i<arguments.length;i++)if(arguments[i]!=null)p.appendChild(arguments[i]);return p}
  function T(w,a){return String(w).replace('{0}',a)}
  function img(src,cls){var i=el('img',cls);i.src=src;i.alt='';i.loading='lazy';return i}
  function span(ms){ms=Math.max(0,ms);var s=Math.floor(ms/1000),h=Math.floor(s/3600),m=Math.floor(s%3600/60),x=s%60;
    return (h?h+':'+String(m).padStart(2,'0'):String(m))+':'+String(x).padStart(2,'0')}
  function ms(v){if(v==null)return '';var m=Math.floor(v/60000),s=((v%60000)/1000).toFixed(3);return m+':'+s.padStart(6,'0')}
  var W={open:${tq('registration open')},run:${tq('under way')},up:${tq('upcoming')},reg:${tq('{0} registered')},starts:${tq('starts in {0}')},
    closes:${tq('closes in {0}')},none:${tq('No ranked sessions in the next hours.')},win:${tq('Winner')},drivers:${tq('{0} drivers')},res:${tq('Results')},
    mine:${tq('you are in')}};
  var cds=[];
  ${SPECIAL_JS}
  function draw(j){var names={},about={},cls={};(j.series||[]).forEach(function(s){names[s.key]=s.name;about[s.key]=s.about;cls[s.key]=s.carClass});
    var sp=document.getElementById('rksp');sp.innerHTML='';(j.specials||[]).forEach(function(s){add(sp,spCard(s))});
    var now=Date.now(),list=(j.sessions||[]).filter(function(s){return !s.special&&s.phase!=='over'&&s.closes>now}).sort(function(a,b){return a.starts-b.starts}).slice(0,4);
    var n=document.getElementById('rkn');n.innerHTML='';cds=[];
    if(!list.length)add(n,el('div','note',W.none));
    list.forEach(function(s){var run=s.phase==='running',c=el('div','rkc'+(run?' run':''));
      add(c,img('/series/'+s.series+'.webp','tile'));var b=el('div','b');
      add(b,el('span','chip'+(s.phase==='signup'?' open':run?' run':''),s.phase==='signup'?W.open:run?W.run:W.up));
      add(b,el('div','at',new Date(s.starts).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})));
      add(b,el('div','nm',names[s.series]||s.series));
      add(b,el('div','ln',[s.rally,cls[s.series]].filter(Boolean).join(' · ')));
      var r=add(el('div','reg'),el('b',null,String(s.signups||0)),el('span',null,T(W.reg,'').trim()));add(b,r);
      if(s.signedUp)add(b,el('span','chip open',W.mine));
      var cd=el('div','cd');cds.push([cd,s]);add(b,cd);add(c,b);add(n,c)});
    var ss=document.getElementById('rks');ss.innerHTML='';
    (j.series||[]).filter(function(s){return !s.special}).forEach(function(s){add(ss,add(el('div','s'),img('/series/'+s.key+'-logo.webp'),el('b',null,s.name),el('small',null,[s.carClass,s.about].filter(Boolean).join(' · '))))});
    var r=document.getElementById('rkr');r.innerHTML='';
    (j.recent||[]).slice(0,12).forEach(function(x){var tr=el('tr'),w=x.winner;
      var a=el('a',null,W.res+' ›');a.href='/e/'+x.eventId;
      add(tr,add(el('td'),img('/series/'+x.series+'-logo.webp','lg')),
        el('td','t',new Date(x.starts).toLocaleString([],{weekday:'short',hour:'2-digit',minute:'2-digit'})+' · '+(x.rally||'')),
        el('td','w',w?w.name:''),el('td','t',T(W.drivers,x.drivers||0)),add(el('td'),a));add(r,tr)});
    tick()}
  function tick(){var now=Date.now();cds.forEach(function(p){var s=p[1];p[0].textContent=s.phase==='running'?T(W.closes,span(s.closes-now)):T(W.starts,span(s.starts-now))})}
  function load(){fetch('/api/liverallies',{credentials:'same-origin',cache:'no-store'}).then(function(r){return r.ok?r.json():null}).then(function(j){if(j)draw(j)},function(){})}
  load();setInterval(tick,1000);setInterval(load,60000);
  navOn('ranked');`, env);
}

// ------------------------------------------------------------------ a special event's own page (/ranked/<key>)
// Its banner, when (the reader's time and the UK's), the rules, REGISTER here or in the app (its one car: nothing to
// pick), who is in, and from its start its stages, standings and each stage's queue, the live overlay for a stream
// (/broadcast/ranked/<key>) and its results.

N_('When'); N_('Rally'); N_('Stages'); N_('Car'); N_('Entry'); N_('Prize'); N_('Format'); N_('Register'); N_('Withdraw');
N_('You are registered.'); N_('Sign in with Steam to register'); N_('Registered drivers'); N_('Nobody yet: be the first.');
N_('Starts in {0}'); N_('One car at a time, as a real rally: 20 s to start on your turn, the start list by rating.');
N_('On the day: start the game with the ACR DAILY app; at the start DRIVE takes you to SS1.');
N_('Standings'); N_('Start list'); N_('SS{0} queue'); N_('Full results ›'); N_('For streamers: the live overlay ›');
N_('{0} UK time'); N_('drawn at the start'); N_('Rating'); N_('World rank'); N_('Driving'); N_('Done'); N_('On turn');
N_('Waiting'); N_('Break'); N_('Out');

const SPECIAL_CSS = `<style>
.spg .ban{display:block;width:100%;aspect-ratio:1200/630;object-fit:cover;border:1px solid var(--line);border-top:3px solid #78FAAE}
.spg .facts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;background:var(--line);border:1px solid var(--line);margin-top:16px}
@media (max-width:820px){.spg .facts{grid-template-columns:repeat(2,minmax(0,1fr))}}
.spg .fa{background:var(--panel);padding:12px 14px}.spg .fa b{display:block;font:700 11px/1 Barlow,sans-serif;letter-spacing:.14em;
  text-transform:uppercase;color:var(--fg2);margin-bottom:6px}.spg .fa span{font:600 19px/1.2 "Barlow Condensed",sans-serif}
.spg .reg{display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin-top:16px;padding:16px 18px;background:var(--panel);border:1px solid var(--line)}
.spg .reg .cd{font:700 30px/1 "Barlow Condensed",sans-serif;font-variant-numeric:tabular-nums}
.spg .btn{background:#78FAAE;color:#04140E;border:0;font:700 15px/1 Barlow,sans-serif;letter-spacing:.08em;text-transform:uppercase;
  padding:12px 18px;cursor:pointer;text-decoration:none}.spg .btn.q{background:transparent;color:var(--fg2);border:1px solid var(--line)}
.spg table{width:100%;border-collapse:collapse;margin-top:6px}.spg td,.spg th{border-top:1px solid var(--line);padding:7px 10px 7px 0;text-align:left}
.spg th{font:700 11px/1 Barlow,sans-serif;letter-spacing:.12em;text-transform:uppercase;color:var(--fg2)}
.spg td.r,.spg th.r{text-align:right}.spg .fl{width:20px;height:14px;vertical-align:-2px;margin-right:8px}
.spg .tabs{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}.spg .tabs button{background:var(--panel);color:var(--fg2);border:1px solid var(--line);
  padding:7px 12px;font:700 13px/1 Barlow,sans-serif;letter-spacing:.08em;cursor:pointer}.spg .tabs button.on{background:#78FAAE;color:#04140E}
.spg .links{display:flex;gap:18px;flex-wrap:wrap;margin-top:14px}
</style>`;

export function specialPage(env, key) {
  const s = SPECIALS.find((x) => x.key === key);
  return shell(`${esc(t(s.name))} · ACR Daily`, `${CSS}${SPECIAL_CSS}
  <div class="rk spg">
  <div class="top"><div class="kick"><a href="/ranked">${esc(t('Ranked'))}</a> · ${esc(t('SPECIAL EVENT'))}</div><h1>${esc(s.name)}</h1></div>
  <img class="ban" src="/series/${esc(s.key)}-banner.webp" alt="${esc(s.name)}">
  <div class="facts" id="facts"></div>
  <div class="reg" id="reg"><span class="note">${esc(t('Loading…'))}</span></div>
  <p class="note">${esc(t('The stages, the weather and the time of day are drawn at the start: nobody can prepare them.'))}
    ${esc(t('One car at a time, as a real rally: 20 s to start on your turn, the start list by rating.'))}
    ${esc(t('On the day: start the game with the ACR DAILY app; at the start DRIVE takes you to SS1.'))}</p>
  <div id="rally"></div>
  <h2 id="enth">${esc(t('Registered drivers'))}</h2>
  <table id="ent"></table>
  </div>`, `
  function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
  function add(p){for(var i=1;i<arguments.length;i++)if(arguments[i]!=null)p.appendChild(arguments[i]);return p}
  var SP=${JSON.stringify({ key: s.key, starts: s.starts, stages: s.stages, rally: s.rally, car: s.car, prize: s.prize || 0 })};
  var W={when:${tq('When')},rally:${tq('Rally')},stages:${tq('Stages')},car:${tq('Car')},entry:${tq('Entry')},prize:${tq('Prize')},
    free:${tq('Free entry')},each:${tq('{0} credits for every driver who finishes')},drawn:${tq('drawn at the start')},
    reg:${tq('Register')},wd:${tq('Withdraw')},youre:${tq('You are registered.')},signin:${tq('Sign in with Steam to register')},
    none:${tq('Nobody yet: be the first.')},starts:${tq('Starts in {0}')},uk:${tq('{0} UK time')},rating:${tq('Rating')},rank:${tq('World rank')},
    driver:${tq('DRIVER')},stand:${tq('Standings')},sl:${tq('Start list')},q:${tq('SS{0} queue')},res:${tq('Full results ›')},
    bc:${tq('For streamers: the live overlay ›')},run:${tq('Under way')},open:${tq('Registration open')},n:${tq('{0} registered')},
    st:{driving:${tq('Driving')},done:${tq('Done')},turn:${tq('On turn')},waiting:${tq('Waiting')},'break':${tq('Break')},dnf:'DNF',dns:'DNS',retired:${tq('Out')}}};
  var P='/api/liverallies/'+SP.key+'/'+SP.starts,V=null,QN=0,busy=false;
  function flag(c){if(!c)return null;var i=el('img','fl');i.src='https://flagcdn.com/w40/'+String(c).toLowerCase()+'.png';i.alt=String(c).toUpperCase();return i}
  function who(x){var d=el('span');add(d,flag(x.country));if(x.team&&x.team.tag)add(d,el('b',null,'['+String(x.team.tag).replace(/\\$[0-9a-fA-F]{3}|\\$[a-zA-Z<>]/g,'')+'] '));
    add(d,document.createTextNode(x.name||''));return d}
  function ms(v){if(v==null)return '';var m=Math.floor(v/60000),s=((v%60000)/1000).toFixed(3);return m+':'+s.padStart(6,'0')}
  function span(v){v=Math.max(0,v);var s=Math.floor(v/1000),d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60),x=s%60;
    return (d?d+'d ':'')+(d||h?h+':'+String(m).padStart(2,'0'):String(m))+':'+String(x).padStart(2,'0')}
  function facts(){var f=document.getElementById('facts');f.innerHTML='';var d=new Date(SP.starts);
    var uk=d.toLocaleTimeString('en-GB',{timeZone:'Europe/London',hour:'2-digit',minute:'2-digit'});
    [[W.when,d.toLocaleDateString([],{weekday:'long',day:'numeric',month:'long'})+' · '+d.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})+' ('+W.uk.replace('{0}',uk)+')'],
     [W.rally,SP.rally],[W.stages,SP.stages+' · '+W.drawn],[W.car,SP.car],[W.entry,W.free],[W.prize,SP.prize?W.each.replace('{0}',SP.prize):'–']]
      .forEach(function(x){add(f,add(el('div','fa'),el('b',null,x[0]),el('span',null,x[1])))})}
  function post(a){if(busy)return;busy=true;fetch(P+'/'+a,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:'{}'})
    .then(function(r){return r.json().then(function(j){if(!r.ok)throw new Error(j.error||r.status);return j})}).then(function(j){V=j;draw()})
    .catch(function(e){alert(e.message)}).then(function(){busy=false})}
  function regBox(){var r=document.getElementById('reg');r.innerHTML='';var now=Date.now(),me=V.me||{};
    if(V.phase==='signup'||V.phase==='upcoming'){add(r,el('span','cd',W.starts.replace('{0}',span(SP.starts-now))));r.cd=r.lastChild;
      if(!me.signedIn){var a=el('a','btn',W.signin);a.href='/login?next='+encodeURIComponent(location.pathname);add(r,a)}
      else if(me.signedUp){add(r,el('span',null,'✓ '+W.youre));var b=el('button','btn q',W.wd);b.onclick=function(){post('withdraw')};add(r,b)}
      else if(V.phase==='signup'){var c=el('button','btn',W.reg);c.onclick=function(){post('signup')};add(r,c)}}
    else{add(r,el('span','cd',V.phase==='running'&&!V.resultsOut?W.run:W.res.replace(' ›','')))}
    var l=el('div','links');if(V.eventId)add(l,(function(){var a=el('a',null,W.res);a.href='/e/'+V.eventId;return a})());
    var b2=el('a',null,W.bc);b2.href='/broadcast/ranked/'+SP.key+'?bg=1';add(l,b2);add(r,l)}
  function table(head,rows){var t=el('table'),h=el('tr');head.forEach(function(x){add(h,el('th',x[1]||null,x[0]))});add(t,h);
    rows.forEach(function(r){var tr=el('tr');r.forEach(function(c){var td=el('td',c&&c.cls||null);if(c&&c.node)add(td,c.node);else td.textContent=c&&c.text!=null?c.text:(c==null?'':c);add(tr,td)});add(t,tr)});return t}
  function rally(){var w=document.getElementById('rally');w.innerHTML='';if(!V.event)return;var ev=V.event;
    add(w,el('h2',null,(ev.stages||[]).map(function(s){return 'SS'+s.no+' '+(s.name||'')}).join('  ·  ')));
    var st=(V.standings||[]).filter(function(r){return r.rank||r.status});
    add(w,el('h2',null,W.stand));
    add(w,table([['#','r'],[W.driver]].concat((ev.stages||[]).map(function(s){return ['SS'+s.no,'r']})).concat([['TOTAL','r']]),
      st.map(function(r){return [{text:r.rank?String(r.rank):r.status==='dnf'?'DNF':r.status==='dsq'?'DSQ':'–',cls:'r'},{node:who(r)}]
        .concat((ev.stages||[]).map(function(s,k){var x=(r.stages||[])[k];return {text:x&&x.totalMs!=null?ms(x.totalMs):'',cls:'r'}}))
        .concat([{text:r.totalMs!=null&&r.status!=='dnf'?ms(r.totalMs):'',cls:'r'}])})));
    var qs=V.queues||[],tb=el('div','tabs');qs.forEach(function(q,k){var b=el('button',k===QN?'on':null,k?W.q.replace('{0}',k+1):W.sl);b.onclick=function(){QN=k;rally()};add(tb,b)});
    add(w,tb);var q=qs[QN]||[];
    add(w,table([['#','r'],[W.driver],['','r']],q.map(function(x,i){return [{text:String(i+1),cls:'r'},{node:who(x)},
      {text:x.timeMs!=null?ms(x.timeMs):(W.st[x.state]||x.state||''),cls:'r'}]})))}
  function entrants(){var t=document.getElementById('ent'),h=document.getElementById('enth');t.innerHTML='';
    var list=V.entrants;if(!Array.isArray(list)){t.hidden=true;h.hidden=true;return}t.hidden=false;h.hidden=false;
    h.textContent=W.n.replace('{0}',list.length);
    if(!list.length){t.appendChild(table([],[[W.none]]));return}
    t.replaceWith(Object.assign(table([['#','r'],[W.driver],[W.rating,'r'],[W.rank,'r']],list.map(function(e,i){return [{text:String(i+1),cls:'r'},{node:who(e)},
      {text:e.rating!=null?String(e.rating):'–',cls:'r'},{text:e.rank?'#'+e.rank:'–',cls:'r'}]})),{id:'ent'}))}
  function draw(){if(!V)return;regBox();rally();entrants()}
  function load(){fetch(P,{credentials:'same-origin',cache:'no-store'}).then(function(r){return r.ok?r.json():null}).then(function(j){if(j){V=j;draw()}},function(){})}
  facts();load();setInterval(load,30000);
  setInterval(function(){var r=document.getElementById('reg');if(r.cd&&V&&(V.phase==='signup'||V.phase==='upcoming'))r.cd.textContent=W.starts.replace('{0}',span(SP.starts-Date.now()))},1000);
  navOn('ranked');`, env, { title: s.name, description: `${s.stages} stages of ${s.rally} · ${s.car} · free entry`,
    image: `/series/${s.key}-banner.webp`, large: true });
}
