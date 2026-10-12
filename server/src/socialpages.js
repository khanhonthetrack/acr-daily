// The pages of messages, 1V1s (head-to-heads) and cups: /inbox, /1v1, /cups, /cup/:id. In the leagues' look (src/leaguepages.js
// shell), signed in with the website's Steam sign-in; their data comes from src/social.js, h2h.js and cups.js. A
// challenge's event and a cup's matches are made with the league event builder (leaguepages.js BUILDER_JS). Every
// name and message is put in with textContent (el, add), never as HTML.

import { WEATHER } from './conditions.js';
import { H2H } from './h2h.js';
import { MSG } from './social.js';
import { BUILDER_JS, shell } from './leaguepages.js';

const CSS = `<style>
.av{width:22px;height:22px;border-radius:50%;object-fit:cover;vertical-align:-6px;margin-right:8px}
.picks{border:1px solid var(--line2);border-top:0;background:#0E0E10}
.picks:empty{display:none}
.pick{display:flex;align-items:center;width:100%;background:none;border:0;border-bottom:1px solid var(--line);color:var(--fg);font:500 15px/1.2 Barlow,sans-serif;padding:10px;text-align:left;cursor:pointer}
.pick:last-child{border-bottom:0}
.pick:hover{background:var(--panel)}
.pick.none{color:var(--fg3);cursor:default}.pick.none:hover{background:none}
.who{display:inline-flex;align-items:center;min-width:0}
/* the inbox: conversations on the left, the one open (or ACR Daily's notices) on the right */
.inbox{display:grid;grid-template-columns:minmax(260px,340px) minmax(0,1fr);gap:36px;margin-top:28px;align-items:start}
.threads{margin-top:20px;border-top:1px solid var(--line2)}
.th{display:flex;gap:12px;align-items:center;padding:12px 10px 12px 12px;border-bottom:1px solid var(--line);border-left:2px solid transparent;text-decoration:none}
.th.on{border-left-color:var(--acc);background:var(--panel)}
.th .grow{flex:1;min-width:0}
.th .tn{font:700 17px/1.1 'Barlow Condensed',sans-serif;text-transform:uppercase;letter-spacing:.02em;color:var(--fg2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.th:hover .tn,.th.new .tn,.th.on .tn{color:var(--fg)}
.th .tl{color:var(--fg3);font-size:13px;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.th.new .tl{color:var(--fg2)}
.th .tr{flex:none;display:flex;flex-direction:column;align-items:flex-end;gap:6px}
.th .tt{font-size:12px;color:var(--fg3);white-space:nowrap}
.th .unread{margin-left:0}
.phead{display:flex;justify-content:space-between;align-items:center;gap:10px 14px;flex-wrap:wrap;padding-bottom:12px;border-bottom:1px solid var(--line2)}
.phead h2{margin:0;min-width:0;overflow-wrap:anywhere}
.phead .actions{flex-wrap:wrap}
.backl{display:none;margin-bottom:12px}
.nt{display:flex;gap:12px;padding:13px 0;border-bottom:1px solid var(--line);text-decoration:none;color:var(--fg2)}
.nt.new{color:var(--fg)}
.nt .dot{width:7px;height:7px;border-radius:50%;margin-top:8px;flex:none}
.nt.new .dot{background:var(--acc)}
.nt .grow{flex:1;min-width:0}
.nt .tt{font-size:12px;color:var(--fg3);margin-top:3px}
a.nt:hover .nb{text-decoration:underline}
.nt .chip{flex:none;align-self:flex-start;margin-top:2px}
.msgs{max-height:58vh;overflow-y:auto;padding-right:4px}
.m{max-width:80%;margin:12px 0;padding:10px 12px;border:1px solid var(--line)}
.m.mine{margin-left:auto;background:var(--panel);border-color:var(--line2)}
.mh{display:flex;justify-content:space-between;gap:12px;font:600 11px/1 Barlow,sans-serif;letter-spacing:.1em;text-transform:uppercase;color:var(--fg3)}
.mh .linkbtn{font:inherit;letter-spacing:inherit;text-transform:inherit;text-decoration:none}
.mb{margin-top:7px;white-space:pre-wrap;overflow-wrap:anywhere}
.blocked{margin-top:12px;padding:10px 12px;border:1px solid var(--line2);color:var(--fg2);font-size:14px}
.compose{margin-top:14px;padding-top:14px;border-top:1px solid var(--line2)}
.compose .row{justify-content:space-between;margin-top:8px}
.private{margin-top:12px;max-width:760px;padding:10px 12px;border-left:2px solid var(--slow);background:#151107;color:var(--fg2);font-size:14px}
.private b{color:var(--slow);font-weight:600}
/* head-to-heads */
.hh{display:flex;justify-content:space-between;gap:20px;padding:16px 0;border-bottom:1px solid var(--line)}
.hh .grow{flex:1;min-width:0}
.hh .t{font:700 20px/1.1 'Barlow Condensed',sans-serif;text-transform:uppercase;overflow-wrap:anywhere}
.hh .s{color:var(--fg2);font-size:14px;margin-top:5px}
.hh .s b{color:var(--fg);font-weight:600}
.hh .chips{margin-top:10px}
.hh .hr{flex:none;max-width:44%;display:flex;flex-direction:column;align-items:flex-end;gap:10px;text-align:right;font-size:13px;color:var(--fg2)}
.res{font:700 16px/1.2 'Barlow Condensed',sans-serif;letter-spacing:.04em;text-transform:uppercase;color:var(--fg)}
.res.won{color:var(--good)}
.res.off{color:var(--fg3)}
.opp{display:flex;align-items:center;justify-content:space-between;gap:10px;border:1px solid var(--line2);background:#0E0E10;padding:8px 10px}
.formcard{background:var(--panel);border:1px solid var(--line);padding:18px}
.formcard .builder .day{background:#0E0E10}
.formcard h3:first-child{margin-top:0}
/* cups */
.cupi{display:flex;justify-content:space-between;align-items:center;gap:14px;padding:13px 0;border-bottom:1px solid var(--line)}
.cupi a.grow{flex:1;min-width:0;text-decoration:none}
.cupi a.grow:hover .t{color:var(--acc)}
.cupi .t{font:700 20px/1.1 'Barlow Condensed',sans-serif;text-transform:uppercase;overflow-wrap:anywhere}
.cupi .s{color:var(--fg2);font-size:13px;margin-top:4px}
.cupi .r{flex:none;display:flex;align-items:center;gap:14px;text-align:right;color:var(--fg2);font-size:13px}
.split{display:flex;flex-wrap:wrap;gap:6px}
.bracket{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(230px,1fr);gap:0 22px;overflow-x:auto;padding-bottom:6px}
.rnd{display:flex;flex-direction:column;min-width:0}
.rh{font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;text-transform:uppercase;color:var(--fg2);padding-bottom:10px;border-bottom:1px solid var(--line2)}
.rnd.now .rh{color:var(--fg)}
.rl{display:flex;flex-direction:column;justify-content:space-around;flex:1;gap:14px;padding-top:14px}
.mt{border:1px solid var(--line);background:var(--panel)}
.mt .sd{display:grid;grid-template-columns:20px minmax(0,1fr) auto;gap:8px;align-items:center;padding:8px 10px;border-left:2px solid transparent}
.mt .sd+.sd{border-top:1px solid var(--line)}
.mt .sn{font:600 12px/1 'Barlow Condensed',sans-serif;color:var(--fg3);text-align:right}
.mt .nm{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:500}
.mt .tm{font:600 15px/1 'Barlow Condensed',sans-serif;font-feature-settings:'tnum';white-space:nowrap}
.mt .sd.won{border-left-color:var(--acc)}
.mt .sd.won .nm{font-weight:600}
.mt .sd.lost .nm,.mt .sd.lost .tm{color:var(--fg3)}
.mt .sd.me .nm{color:var(--acc)}
.mt .sd.bye .nm,.mt.tbd .nm{color:var(--fg3)}
.mt .mf{display:flex;justify-content:space-between;align-items:center;gap:8px;min-height:29px;padding:6px 10px;border-top:1px solid var(--line);font-size:12px;color:var(--fg3)}
.mt .mf a{color:var(--fg2);text-decoration:none;font:600 12px/1 'Barlow Condensed',sans-serif;letter-spacing:.1em;text-transform:uppercase;white-space:nowrap}
.mt .mf a:hover{color:var(--fg)}
@media (max-width:760px){
  .inbox{grid-template-columns:minmax(0,1fr);gap:22px}
  body.convopen .side{display:none}body.convopen .backl{display:inline-block}
  .m{max-width:92%}
  .hh{flex-direction:column;gap:12px}.hh .hr{max-width:none;align-items:flex-start;text-align:left}
  .cupi{flex-direction:column;align-items:flex-start}.cupi .r{text-align:left;flex-wrap:wrap}
  .bracket{grid-auto-flow:row;grid-auto-columns:auto;gap:26px}.rl{justify-content:flex-start}
  .formcard{padding:14px}
}
/* ACR Daily's own cups */
.badge.official{background:var(--acc);border-color:var(--acc);color:#fff}
.cupi.official{border-left:2px solid var(--acc);padding-left:12px}
</style>`;

// helpers of these pages' scripts (on top of the shell's: $, el, add, api, when, left, ms, cr, flag, steamBtn...)
const SOCIAL_JS = `
var WX=${JSON.stringify(Object.fromEntries(Object.entries(WEATHER).map(([k, w]) => [k, w.label])))};
function who(p,x){var w=el('span','who');if(x.avatar){var i=el('img','av');i.src=x.avatar;i.alt='';w.appendChild(i)}else flag(w,x.country);add(w,x.name||'a driver');p.appendChild(w);return p}
function short(t){var d=new Date(t);return d.toDateString()===new Date().toDateString()?d.toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit'}):d.toLocaleDateString(undefined,{day:'numeric',month:'short'})}
function nth(n){var s=n%100>10&&n%100<14?'th':({1:'st',2:'nd',3:'rd'})[n%10]||'th';return n+s}
function carText(x){return x.car||(x.carClass+' class: each picks a car of it')}
function stagesText(x){return x.stages.map(function(s,i){return 'SS'+(i+1)+' '+s.name+' ('+s.time+', '+(WX[s.weather]||s.weather).toLowerCase()+')'}).join(' · ')}
function ruleChips(R){var c=el('div','chips');[R.damage?'Damage '+R.damageIntensity:'No damage','Wear '+R.wear,'Failures '+R.failures,R.respawn?'Respawn on':'No respawn','Penalties '+R.penalty]
  .forEach(function(x){c.appendChild(el('span','chip',x))});return c}
// find a driver by name (GET /api/players): a text box and what it finds; onPick(player)
function picker(box,onPick,ph){box.innerHTML='';var inp=el('input'),res=el('div','picks'),t=null,seq=0;
  inp.type='text';inp.placeholder=ph||'Find a driver by name';inp.autocomplete='off';inp.maxLength=40;add(box,inp,res);
  inp.oninput=function(){clearTimeout(t);var q=inp.value.trim();if(q.length<2){seq++;res.innerHTML='';return}
    t=setTimeout(function(){var k=++seq;api('/api/players?q='+encodeURIComponent(q)).then(function(j){if(k!==seq)return;res.innerHTML='';
      var ps=j.players.filter(function(p){return !ME||p.steamId!==ME.steamId});
      if(!ps.length){res.appendChild(el('div','pick none','No driver by that name (they show here once they have signed in to ACR Daily).'));return}
      ps.forEach(function(p){var b=el('button','pick');b.type='button';who(b,p);b.onclick=function(){seq++;res.innerHTML='';inp.value='';onPick(p)};res.appendChild(b)})},function(){})},250)};
  return inp}
function roundName(r,n){return ['Final','Semi-final','Quarter-final'][n-r]||'Round of '+Math.pow(2,n-r+1)}
function roundLength(h){return h%24===0&&h>=48?(h/24)+' days':h+' hours'}
function officialBadge(){var b=el('span','badge official','official');b.title='Run by ACR Daily';return b}
`;

// ------------------------------------------------------------------ /inbox
export function inboxPage(env) {
  return shell('Inbox · ACR Daily', `${CSS}
  <div class="top"><div class="kick">ACR Daily</div><h1>Inbox</h1>
  <p class="note">Notices from ACR Daily (a challenge for you, a cup match ready, results) and short messages between
  drivers. Block a driver and they can't write to you or challenge you; report a message and the site's admins see it.</p>
  <p class="private"><b>Messages are not private.</b> They are kept as written (not end-to-end encrypted, gone after
  ${MSG.keepDays} days), and ACR Daily's admins can read them, which is how a report gets checked. Don't send passwords,
  contact details or anything you wouldn't want an admin to read.</p>
  <div class="row" style="margin-top:18px" id="acts"></div><div class="msg" id="m"></div></div>
  <div class="inbox" id="ib" hidden>
    <aside class="side"><label><span>New message</span></label><div id="find"></div><div class="threads" id="threads"></div></aside>
    <section class="pane" id="pane"></section>
  </div>`, `${SOCIAL_JS}
  var WITH=null,DATA=null,CONV=null,LAST=null;
  function target(ref){var m=/^(h2h|cup):(.+)$/.exec(ref||'');return !m?null:m[1]==='h2h'?'/1v1':'/cup/'+encodeURIComponent(m[2])}
  function fromUrl(){var w=new URLSearchParams(location.search).get('with');WITH=w&&/^\\d{17}$/.test(w)?w:null}
  function load(){return api('/api/inbox').then(function(j){DATA=j;threads();if(!WITH)notices();unread(j.unread)},function(e){msg('m',e.message)})}
  function open(sid){if(sid===WITH)return;WITH=sid;history.pushState(null,'',sid?'/inbox?with='+sid:'/inbox');show()}
  function show(){document.body.classList.toggle('convopen',!!WITH);CONV=null;LAST=null;if(!DATA)return;threads();if(WITH)conv();else notices()}

  // ---- the list: ACR Daily's notices first, then the conversations, newest first
  function threads(){var box=$('threads');box.innerHTML='';var N=DATA.notices,nu=N.filter(function(n){return !n.read}).length;
    var a=el('a','th'+(!WITH?' on':'')+(nu?' new':''));a.href='/inbox';a.onclick=function(ev){ev.preventDefault();open(null)};
    var d=el('div','grow');add(d,el('div','tn','ACR Daily'),el('div','tl',N.length?N[0].body:'Challenges, cup matches and results show here.'));
    var r=el('div','tr');if(N.length)r.appendChild(el('span','tt',short(N[0].created)));if(nu)r.appendChild(el('b','unread',String(nu)));add(a,d,r);box.appendChild(a);
    DATA.threads.forEach(function(t){var a=el('a','th'+(t.with.steamId===WITH?' on':'')+(t.unread?' new':''));a.href='/inbox?with='+t.with.steamId;
      a.onclick=function(ev){ev.preventDefault();open(t.with.steamId)};
      var d=el('div','grow'),n=el('div','tn');who(n,t.with);if(t.blocked)add(n,' ',el('span','badge','blocked'));
      add(d,n,el('div','tl',(t.last.mine?'You: ':'')+t.last.body.replace(/\\s+/g,' ')));
      var r=el('div','tr');r.appendChild(el('span','tt',short(t.last.created)));if(t.unread)r.appendChild(el('b','unread',String(t.unread)));
      add(a,d,r);box.appendChild(a)});
    if(!DATA.threads.length)box.appendChild(el('div','empty','No messages yet: find a driver above to write to them.'))}

  // ---- ACR Daily's notices: read ones grey, a click marks one read and goes to what it is about
  function notices(){var p=$('pane');p.innerHTML='';var N=DATA.notices,nu=N.filter(function(n){return !n.read});
    var h=el('div','phead');add(h,el('h2',null,'Notices'));
    if(nu.length){var all=el('button','btn ghost small','Mark all read');all.onclick=function(){all.disabled=true;api('/api/inbox/read',{}).then(load,function(e){all.disabled=false;msg('m',e.message)})};h.appendChild(all)}
    p.appendChild(h);
    if(!N.length){p.appendChild(el('div','empty','Nothing yet. A challenge for you, a cup match of yours and their results show here.'));return}
    N.forEach(function(n){var to=target(n.ref),it=el(to?'a':'div','nt'+(n.read?'':' new'));if(to)it.href=to;
      var d=el('div','grow');add(d,el('div','nb',n.body),el('div','tt',when(n.created)));
      add(it,el('span','dot'),el('span','chip',n.kind==='h2h'?'1V1':n.kind==='cup'?'Cup':'ACR Daily'),d);
      if(!n.read)it.onclick=function(ev){ev.preventDefault();api('/api/inbox/read',{ids:[n.id]}).then(function(){if(to)location.href=to;else load()},function(){if(to)location.href=to})};
      p.appendChild(it)})}

  // ---- a conversation: its messages (theirs read now), writing, block / unblock, report
  function conv(){var p=$('pane');p.innerHTML='';var sid=WITH;
    var bk=el('a','back backl','‹ Inbox');bk.href='/inbox';bk.onclick=function(ev){ev.preventDefault();open(null)};p.appendChild(bk);
    var h=el('div','phead');h.id='ch';add(h,el('h2',null,'…'));p.appendChild(h);
    add(p,el('div'));p.lastChild.id='blk';add(p,el('div','msgs'));p.lastChild.id='msgs';
    var c=el('div','compose'),ta=el('textarea');ta.id='body';ta.maxLength=500;ta.placeholder='Write a message (500 characters at most; not private: admins can read it)';
    var row=el('div','row'),cnt=el('span','muted','0 / 500'),sb=el('button','btn','Send');
    ta.oninput=function(){cnt.textContent=ta.value.length+' / 500'};
    ta.onkeydown=function(ev){if(ev.key==='Enter'&&(ev.ctrlKey||ev.metaKey)){ev.preventDefault();sb.click()}};
    sb.onclick=function(){var t=ta.value.trim();if(!t){msg('sm','Write something first.');return}sb.disabled=true;
      api('/api/inbox/send',{to:sid,body:ta.value}).then(function(){sb.disabled=false;ta.value='';cnt.textContent='0 / 500';msg('sm','');
        loadConv();load()},function(e){sb.disabled=false;msg('sm',e.message)})};
    add(row,cnt,sb);add(c,ta,row,el('div','msg'));c.lastChild.id='sm';p.appendChild(c);
    loadConv()}
  function loadConv(quiet){var sid=WITH;return api('/api/inbox/with/'+sid).then(function(j){if(sid!==WITH)return;
      var first=!CONV;CONV=j;if(first)head(j);else blocked(j);
      var last=j.messages.length?j.messages[j.messages.length-1].id:0;if(quiet&&last===LAST)return;LAST=last;msgs(j);
      if(first&&DATA&&DATA.threads.some(function(t){return t.with.steamId===sid&&t.unread}))load()},
    function(e){if(sid!==WITH)return;$('pane').innerHTML='';add($('pane'),el('div','empty',e.status===404?'No such driver.':e.message))})}
  function head(j){var h=$('ch');h.innerHTML='';var t=el('h2');who(t,j.with);h.appendChild(t);document.title=j.with.name+' · Inbox · ACR Daily';
    var a=el('div','actions'),ch=el('a','btn ghost small','Challenge');ch.href='/1v1?to='+j.with.steamId+'&name='+encodeURIComponent(j.with.name);
    ch.title='A 1V1: an event of your making, maybe with a stake';var pg=el('a','btn ghost small','Driver page');pg.href='/d/'+j.with.steamId;add(a,pg,ch);
    var bb=el('button','btn small '+(j.blocked?'ghost':'danger'),j.blocked?'Unblock':'Block');bb.id='bb';
    bb.onclick=function(){var on=!CONV.blocked;if(on&&!confirm('Block '+j.with.name+'? They can no longer write to you or challenge you. You can unblock them here later.'))return;
      bb.disabled=true;api('/api/inbox/block',{steamId:j.with.steamId,block:on}).then(function(){bb.disabled=false;CONV.blocked=on;head(CONV);load()},function(e){bb.disabled=false;msg('sm',e.message)})};
    a.appendChild(bb);h.appendChild(a);blocked(j)}
  function blocked(j){var b=$('blk');b.innerHTML='';if(j.blocked)add(b,el('div','blocked','You have blocked '+j.with.name+': they can\\'t write to you or challenge you.'))}
  function msgs(j){var box=$('msgs');box.innerHTML='';
    if(!j.messages.length){box.appendChild(el('div','empty','No messages yet. Say hello.'));return}
    j.messages.forEach(function(x){var m=el('div','m'+(x.mine?' mine':'')),h=el('div','mh');add(h,el('span',null,(x.mine?'You':j.with.name)+' · '+when(x.created)));
      if(!x.mine){var rb=el('button','linkbtn','Report');rb.title='Report this message to the site\\'s admins';
        rb.onclick=function(){var why=prompt('Report this message to the site\\'s admins. What is wrong with it? (optional)','');if(why==null)return;
          api('/api/inbox/report',{id:x.id,reason:why}).then(function(){rb.replaceWith(el('span',null,'reported'))},function(e){msg('sm',e.message)})};h.appendChild(rb)}
      add(m,h,el('div','mb',x.body));box.appendChild(m)});
    box.scrollTop=box.scrollHeight}

  window.addEventListener('popstate',function(){fromUrl();show()});
  fromUrl();
  account().then(function(me){
    if(!me){add($('acts'),el('span','muted','Sign in with Steam to see your inbox.'));$('acts').appendChild(steamBtn());return}
    $('ib').hidden=false;document.body.classList.toggle('convopen',!!WITH);
    picker($('find'),function(p){open(p.steamId)},'Find a driver by name');
    load().then(function(){if(WITH)conv()});
    setInterval(function(){if(document.hidden)return;load();if(WITH&&CONV)loadConv(true)},30000)});
  `, env);
}

// ------------------------------------------------------------------ /1v1 (head-to-heads: h2h in the code and the API)
export function h2hPage(env) {
  const days = H2H.windowDays, hours = Math.round(H2H.answerMs / 3600000);
  return shell('1V1 · ACR Daily', `${CSS}
  <div class="top"><div class="kick">ACR Daily</div><h1>1V1</h1>
  <p class="note">Challenge a driver to a rally of your making: one stage, or a short rally of several where the total
  counts; one car or a class; your settings; when it is open. Put up a stake each, or make it a friendly. They accept or
  decline; not answered within ${hours} hours, it lapses. Accepted, you both drive it from the app's <b>1V1</b>
  view, each whenever you like while it is open: the lower total wins (and takes both stakes). Nobody finishing, or a
  dead heat: no contest, the stakes go back.</p>
  <div class="facts" id="facts"></div><div class="row" style="margin-top:18px" id="acts"></div><div class="msg" id="m"></div></div>
  <h2>Waiting for your answer</h2><div id="incoming"></div>
  <h2>Sent</h2><div id="outgoing"></div>
  <h2>Under way</h2><div id="active"></div>
  <h2>Finished</h2><div id="past"></div>
  <h2 id="new">Challenge a driver</h2><div class="formcard" id="form"></div>`, `${SOCIAL_JS}${BUILDER_JS}
  var Q=new URLSearchParams(location.search),H=null,CAT=null,B=null,OPP=null,FORM=false;
  var HS={name:'',opens:null,closes:null};   // the challenge's event: the builder fills in the rest
  function fact(k){var d=el('div'),b=el('b');for(var i=1;i<arguments.length;i++)add(b,arguments[i]);add(d,el('span','k',k),b);$('facts').appendChild(d)}
  function load(){return api('/api/h2h').then(render,function(e){msg('m',e.message)})}
  function balance(){if(!H||!H.credits)return;api('/api/credits').then(function(c){$('facts').innerHTML='';
    if(c.signedIn)fact('Your credits',cr(c.balance||0));var b=$('bal');if(b){b.innerHTML='';add(b,'You have ',cr(c.balance||0),'. Your stake is taken when you send the challenge, theirs when they accept; it comes back if they decline or don\\'t answer.')}},function(){})}
  function render(h){H=h;
    list('incoming',h.incoming,'No challenges for you right now.');list('outgoing',h.outgoing,'Nothing sent and waiting.');
    list('active',h.active,'No 1V1 under way.');list('past',h.past,'None yet.');
    if(!FORM){FORM=true;form();balance()}}
  function list(id,xs,empty){var box=$(id);box.innerHTML='';if(!xs.length){box.appendChild(el('div','empty',empty));return}
    xs.forEach(function(x){box.appendChild(item(x,id))})}
  function other(x){return x.mine==='challenger'?x.opponent:x.challenger}
  function nameOf(sid,x){return sid===x.challenger.steamId?x.challenger.name:x.opponent.name}
  function stake(x){return x.stake?add(el('span'),cr(x.stake),' each'):el('span',null,'a friendly')}
  function item(x,kind){var it=el('div','hh');it.id='h'+x.id;var g=el('div','grow'),o=other(x);
    add(g,el('div','t',x.name));
    var s1=el('div','s');add(s1,kind==='incoming'?'From ':kind==='outgoing'?'To ':'Against ');who(s1,o);add(s1,' · ',stake(x));
    var s2=el('div','s');add(s2,el('b',null,x.rally),' · '+carText(x));
    var s3=el('div','s',stagesText(x));
    var s4=el('div','s','Open '+when(x.opens)+' – '+when(x.closes));
    add(g,s1,s2,s3,s4,ruleChips(x.rules));
    var r=el('div','hr');
    if(kind==='incoming'){add(r,el('span',null,'Answer by '+when(x.answerBy)+(left(x.answerBy)?' ('+left(x.answerBy)+' left)':'')));
      var a=el('div','actions'),ok=el('button','btn','Accept'),no=el('button','btn ghost','Decline');
      ok.onclick=function(){if(!confirm('Accept '+x.name+' against '+o.name+'?'+(x.stake?' Your stake of '+x.stake+' credits is taken now; the winner takes both.':'')))return;
        ok.disabled=no.disabled=true;api('/api/h2h/'+x.id+'/accept',{}).then(function(j){msg('m','Accepted: drive it in the app, under 1V1.',true);load();balance()},
          function(e){ok.disabled=no.disabled=false;msg('m',e.message)})};
      no.onclick=function(){if(!confirm('Decline '+x.name+'?'))return;ok.disabled=no.disabled=true;
        api('/api/h2h/'+x.id+'/decline',{}).then(function(){load()},function(e){ok.disabled=no.disabled=false;msg('m',e.message)})};
      add(a,ok,no);r.appendChild(a)}
    else if(kind==='outgoing'){add(r,el('span',null,'Waiting for '+o.name+' · until '+when(x.answerBy)));
      var cb=el('button','btn ghost small','Cancel');cb.onclick=function(){if(!confirm('Cancel '+x.name+'?'+(x.stake?' Your stake comes back.':'')))return;cb.disabled=true;
        api('/api/h2h/'+x.id+'/cancel',{}).then(function(){load();balance()},function(e){cb.disabled=false;msg('m',e.message)})};r.appendChild(cb)}
    else if(kind==='active'){var on=Date.now()>=x.opens;
      add(r,el('span',null,on?'Closes '+when(x.closes)+(left(x.closes)?' ('+left(x.closes)+' left)':''):'Opens '+when(x.opens)));
      if(x.eventId){var mt=el('a','btn small','The match ›');mt.href='/e/'+x.eventId;r.appendChild(mt)}else add(r,el('span','muted','The match is being set up.'))}
    else{r.appendChild(result(x));if(x.eventId){var lk=el('a','btn ghost small','The match ›');lk.href='/e/'+x.eventId;r.appendChild(lk)}
      // a rematch: the same again (stages, car, rules, stake), open as long, from now
      if(x.status==='settled'){var rb=el('button','btn small','Rematch');rb.onclick=function(){
        if(!confirm('Rematch '+o.name+': the same stages, car and rules'+(x.stake?', '+x.stake+' credits each (yours is taken now)':', a friendly')+'?'))return;rb.disabled=true;
        api('/api/h2h/'+x.id+'/rematch',{}).then(function(){msg('m','Rematch sent to '+o.name+'.',true);load();balance()},function(e){rb.disabled=false;msg('m',e.message)})};r.appendChild(rb)}}
    add(it,g,r);return it}
  function result(x){var o=other(x),me=ME&&ME.steamId;
    if(x.status==='settled'){if(!x.winner)return el('span','res off','No contest ('+(x.note||'')+')');
      var r=el('span','res'+(x.winner===me?' won':''),(x.winner===me?'You won':nameOf(x.winner,x)+' won')+(x.note?' ('+x.note+')':''));
      if(x.stake&&x.winner===me)add(r,' · ',cr(2*x.stake));return r}
    if(x.status==='declined')return el('span','res off',x.mine==='challenger'?o.name+' declined':'You declined');
    if(x.status==='expired')return el('span','res off','Not answered in time');
    if(x.status==='cancelled')return el('span','res off',x.mine==='challenger'?'You cancelled it':o.name+' cancelled it');
    return el('span','res off',x.status)}

  // ---- the challenge: who, the stake, the event (the league event builder, with its window)
  function form(){var f=$('form');f.innerHTML='';
    if(!ME){add(f,el('p','muted','Sign in with Steam to challenge a driver.'));f.appendChild(steamBtn());return}
    var ol=el('label');add(ol,el('span',null,'Who you challenge'));f.appendChild(ol);var ob=el('div');ob.id='opp';f.appendChild(ob);opp();
    if(H.credits){var g=el('div','twocol'),sl=el('label'),si=el('input');add(sl,el('span',null,'Stake each, in credits (0: a friendly; '+H.maxStake+' at most)'));
      si.type='text';si.id='stake';si.inputMode='numeric';si.maxLength=4;si.value='0';sl.appendChild(si);g.appendChild(sl);f.appendChild(g);
      add(f,el('p','note'));f.lastChild.id='bal'}
    else add(f,el('p','note','A friendly: stakes come with credits, which are not on yet.'));
    add(f,el('h3',null,'The event'));var bx=el('div','builder');f.appendChild(bx);add(bx,el('div','empty','Loading…'));
    api('/api/catalog').then(function(c){CAT=c;var now=Date.now();HS.opens=Math.ceil(now/900000)*900000;HS.closes=HS.opens+3*86400000;
      B=eventBuilder(bx,{cat:CAT,state:HS,name:{label:'Name (optional)',placeholder:namePh()},window:true,
        windowNote:'Open for ${days} days at most, from within the next ${days} days. They have ${hours} hours to answer (and at least an hour before it closes).',
        after:function(b){var sb=el('button','btn','Send the challenge');sb.style.marginTop='22px';sb.onclick=send;b.appendChild(sb);add(b,el('div','msg'));b.lastChild.id='hm'}});
      B.draw();if(Q.get('to'))$('new').scrollIntoView()},function(e){bx.innerHTML='';add(bx,el('div','empty',e.message))})}
  function namePh(){return OPP&&ME?ME.name+' vs '+OPP.name:'e.g. Friday duel'}
  function opp(){var box=$('opp');box.innerHTML='';
    if(OPP){var c=el('div','opp');who(c,OPP);var x=el('button','linkbtn','change');x.onclick=function(){OPP=null;opp()};add(c,x);box.appendChild(c)}
    else picker(box,function(p){OPP=p;opp()},'Find a driver by name');
    var fn=$('fn');if(fn)fn.placeholder=namePh()}
  function send(){var b=this;if(!OPP){msg('hm','Pick who you challenge first.');return}
    var st=H.credits?$('stake').value.trim()||'0':'0';
    if(!/^\\d+$/.test(st)){msg('hm','The stake: a whole number of credits, 0 for a friendly.');return}
    if(+st&&!confirm('Challenge '+OPP.name+' with '+st+' credits each? Yours is taken now (it comes back if they decline or don\\'t answer).'))return;
    b.disabled=true;var to=OPP;
    api('/api/h2h',{opponent:to.steamId,stake:+st,event:B.body()}).then(function(){b.disabled=false;OPP=null;opp();msg('hm','Sent: '+to.name+' has '+${hours}+' hours to answer.',true);
      load().then(function(){$('outgoing').scrollIntoView({behavior:'smooth',block:'center'})});balance()},function(e){b.disabled=false;msg('hm',e.message)})}

  var to=Q.get('to');if(to&&/^\\d{17}$/.test(to))OPP={steamId:to,name:Q.get('name')||'driver …'+to.slice(-4)};
  account().then(function(me){
    if(!me){['incoming','outgoing','active','past'].forEach(function(id){$(id).innerHTML=''});$('incoming').appendChild(el('div','empty','Sign in with Steam to see your 1V1s.'));
      $('acts').appendChild(steamBtn());H={credits:false};form();return}
    var nb=el('a','btn','Challenge a driver');nb.href='#new';$('acts').appendChild(nb);load()});
  `, env);
}

// ------------------------------------------------------------------ /cups
export function cupsPage(env) {
  return shell('Cups · ACR Daily', `${CSS}
  <div class="top"><div class="kick">ACR Daily</div><h1>Cups</h1>
  <p class="note">Knockout cups of 1V1 matches anyone can run, for 4 to 128 drivers: an entry fee or free, the pot shared
  as its maker chose. Drivers join before the start; then they are seeded by their <a href="/ranking">driver rating</a>
  into a bracket just big enough for them (byes for the top seeds if it isn't full). Each round's matches open together for as long as its maker set, each driven from the app's <b>CUPS</b>
  view: the lower total goes through; nobody finishing, or a dead heat, the higher seed does.</p>
  <div class="row" style="margin-top:18px" id="acts"></div><div class="msg" id="m"></div></div>
  <h2>Open for entries</h2><div id="open"></div>
  <h2>Under way</h2><div id="running"></div>
  <h2>Finished</h2><div id="finished"></div>
  <h2 id="new">Create a cup</h2><div class="formcard" id="form"></div>`, `${SOCIAL_JS}${BUILDER_JS}
  var C=null,CAT=null,B=null,FORM=false,CS={};   // CS: the matches' event (the builder fills it in)
  function bsize(n){var b=2;while(b<n)b*=2;return b}
  function load(){return api('/api/cups').then(render,function(e){msg('m',e.message)})}
  function render(c){C=c;list('open',c.open,'No cup open for entries right now: create one below.');list('running',c.running,'No cup under way.');
    list('finished',c.finished,'None yet.');if(!FORM){FORM=true;form()}}
  function list(id,xs,empty){var box=$(id);box.innerHTML='';if(!xs.length){box.appendChild(el('div','empty',empty));return}xs.forEach(function(x){box.appendChild(item(x,id))})}
  function item(c,kind){var it=el('div','cupi'+(c.official?' official':'')),a=el('a','grow');a.href='/cup/'+c.id;
    var t=el('div','t',c.name+' ');if(c.official)add(t,officialBadge(),' ');if(C.mine.indexOf(c.id)>=0)t.appendChild(el('span','badge upcoming','you\\'re in'));if(ME&&c.owner.steamId===ME.steamId)add(t,' ',el('span','badge','yours'));
    add(a,t,el('div','s',c.rally+' · '+c.stages.length+(c.stages.length===1?' stage':' stages')+(c.draw?', a new draw each round':'')+' · '+(c.car||c.carClass+' class')+' · rounds of '+roundLength(c.roundHours)+' · by '+c.owner.name));
    var r=el('div','r'),d=el('div');
    if(kind==='open'){add(d,c.entrants+' of '+c.size+' drivers',el('br'),c.fee?add(el('span'),'entry ',cr(c.fee)):'free entry',c.prize?add(el('span'),' · prize ',cr(c.prize)):null,el('br'),'starts '+when(c.starts));r.appendChild(d);
      if(ME&&C.mine.indexOf(c.id)<0&&c.entrants<c.size&&Date.now()<c.starts){var j=el('button','btn small','Join');j.onclick=function(){join(c,j)};r.appendChild(j)}}
    else if(kind==='running'){add(d,roundName(c.round,Math.log2(bsize(c.entrants)))+' under way',el('br'),c.entrants+' drivers'+(c.pot?' · pot ':''),c.pot?cr(c.pot):null)}
    else add(d,c.entrants+' drivers',c.pot?' · pot ':null,c.pot?cr(c.pot):null,el('br'),'started '+when(c.starts));
    if(kind!=='open')r.appendChild(d);
    add(it,a,r);return it}
  function join(c,b){if(!confirm('Join '+c.name+'?'+(c.fee?' The entry fee of '+c.fee+' credits is taken now (back if you leave before the start, or the cup is called off).':'')))return;
    b.disabled=true;api('/api/cups/'+c.id+'/join',{}).then(function(){msg('m','You are in '+c.name+'.',true);load()},function(e){b.disabled=false;msg('m',e.message)})}

  // ---- a new cup: its settings, then what every match races (the league event builder, without a window)
  function radios(name,vals,labels,cur){var d=el('div','radio');vals.forEach(function(v,i){var l=el('label'),inp=el('input');inp.type='radio';inp.name=name;inp.value=String(v);inp.checked=v===cur;
    add(l,inp,el('span',null,labels[i]));d.appendChild(l)});return d}
  function picked(name){var x=document.querySelector('input[name='+name+']:checked');return x?x.value:''}
  function field(p,label,node){var l=el('label');add(l,el('span',null,label),node);p.appendChild(l);return l}
  function form(){var f=$('form');f.innerHTML='';var L=C.limits;
    if(!ME){add(f,el('p','muted','Sign in with Steam to create a cup.'));f.appendChild(steamBtn());return}
    var g=el('div','twocol');f.appendChild(g);
    var nm=el('input');nm.type='text';nm.id='cn';nm.maxLength=60;nm.placeholder='e.g. Wales Gravel Cup';field(g,'Name',nm);
    var sz=el('div');sz.appendChild(radios('csz',L.sizes,L.sizes.map(function(n){return n+' drivers'}),8));field(g,'Size (at most)',sz);
    var ab=el('textarea');ab.id='ca';ab.maxLength=600;ab.placeholder='Who it is for, your Discord...';field(f,'About (optional)',ab);
    var g2=el('div','twocol');f.appendChild(g2);
    var stt=el('input');stt.type='datetime-local';stt.id='cst';stt.value=localInput(Math.ceil(Date.now()/3600000)*3600000+86400000);field(g2,'Starts (your time): entries close, round 1 opens',stt);
    var rh=el('div');rh.appendChild(radios('crh',L.roundHours,L.roundHours.map(function(h){return h+' h'}),24));field(g2,'Each round is open',rh);
    if(C.credits){var g3=el('div','twocol');f.appendChild(g3);
      var fe=el('input');fe.type='text';fe.id='cfee';fe.inputMode='numeric';fe.maxLength=4;fe.value='0';field(g3,'Entry fee, in credits (0: free; '+L.maxFee+' at most)',fe);
      var sp=el('select');sp.id='csp';Object.keys(L.splits).forEach(function(k){opt(sp,k,L.splits[k].label,'all')});field(g3,'The pot goes to',sp)}
    add(f,el('h3',null,'Every match'),el('p','note','What each 1V1 races, in every round: the location, the car, the settings and the stages (one, or a short rally where the total counts). Each round is open for the hours above.'));
    var bx=el('div','builder');f.appendChild(bx);add(bx,el('div','empty','Loading…'));
    api('/api/catalog').then(function(c){CAT=c;B=eventBuilder(bx,{cat:CAT,state:CS,name:false,window:false,after:function(b){
      var sb=el('button','btn','Create the cup');sb.style.marginTop='22px';sb.onclick=create;b.appendChild(sb);add(b,el('div','msg'));b.lastChild.id='cm'}});B.draw()},
      function(e){bx.innerHTML='';add(bx,el('div','empty',e.message))})}
  function create(){var b=this,fee=C.credits?$('cfee').value.trim()||'0':'0';
    if(!/^\\d+$/.test(fee)){msg('cm','The entry fee: a whole number of credits, 0 for free.');return}
    var st=new Date($('cst').value).getTime();if(!st){msg('cm','Set when the cup starts.');return}
    b.disabled=true;
    api('/api/cups',{name:$('cn').value,about:$('ca').value,size:+picked('csz'),fee:+fee,split:C.credits?$('csp').value:'all',event:B.body(),starts:st,roundHours:+picked('crh')})
      .then(function(j){location.href='/cup/'+j.id},function(e){b.disabled=false;msg('cm',e.message)})}
  account().then(function(me){var nb=el('a','btn','Create a cup');nb.href='#new';$('acts').appendChild(nb);if(!me)$('acts').appendChild(steamBtn());load()});
  `, env);
}

// ------------------------------------------------------------------ /cup/:id
export function cupPage(id, env) {
  return shell('Cup · ACR Daily', `${CSS}
  <img class="banner" id="banner" alt="" hidden>
  <div class="top"><div class="kick" id="kick"><a href="/cups">Cups</a></div><h1 id="name"></h1><p class="about" id="about"></p>
    <div class="facts" id="facts"></div>
    <div class="row" style="margin-top:18px" id="acts"></div><div class="msg" id="am"></div></div>
  <h2>Bracket</h2><div id="bracket"></div>
  <h2>Every match</h2><div class="facts" id="spec" style="margin-top:0"></div><div id="rules"></div>
  <div class="tablewrap" style="margin-top:14px"><table class="itin" id="stages"></table></div>
  <h2>Drivers</h2><div class="tablewrap"><table id="entrants"></table></div>`, `${SOCIAL_JS}
  var id=${JSON.stringify(id)},X=null;
  function fact(box,k){var d=el('div'),b=el('b');for(var i=2;i<arguments.length;i++)add(b,arguments[i]);add(d,el('span','k',k),b);$(box).appendChild(d)}
  function load(){return api('/api/cups/'+id).then(render,function(e){$('name').textContent=e.status===404?'No such cup':'Cup';msg('am',e.message)})}
  function render(c){X=c;document.title=c.name+' · ACR Daily';$('name').textContent=c.name;$('about').textContent=c.about||'';showBanner($('banner'),c.banner);
    var open=c.status==='open',n=c.entrants.length,k=$('kick');k.innerHTML='';var ca=el('a',null,'Cups');ca.href='/cups';add(k,ca,' · ');if(c.official)add(k,officialBadge(),' ');
    add(k,(c.rounds?Math.pow(2,c.rounds):c.size)+'-driver knockout ');   // (drawn: the bracket's size, the smallest that holds who joined)
    k.appendChild(c.status==='running'?el('span','badge open',roundName(c.round,c.rounds)):open?el('span','badge open','open for entries'):
      el('span','badge',c.status==='finished'?'finished':'called off'));
    $('facts').innerHTML='';
    var w=c.entrants.filter(function(e){return e.place===1})[0];if(w)fact('facts','Winner',who(el('span'),w));
    fact('facts','Drivers',n+' of '+c.size);
    fact('facts','Entry',c.fee?cr(c.fee):'Free');
    if(c.prize)fact('facts','Prize from ACR Daily',cr(c.prize));
    if(c.pot){if(c.fee)fact('facts','Pot',cr(c.pot));fact('facts','Shared',c.split.length===1?'Winner takes all':c.split.slice(0,2).map(function(s,i){return nth(i+1)+' '+s+'%'})
      .concat(c.split.length>2?['3rd '+c.split[2]+'% each']:[]).join(' · '))}
    fact('facts',open?'Starts':'Started',when(c.starts)+(open&&left(c.starts)?' ('+left(c.starts)+')':''));
    fact('facts','Each round',roundLength(c.roundHours));
    // the rounds close at fixed times: the start plus a round's length each (the next opens once the last is decided)
    var cl=open?c.starts+c.roundHours*3600000:c.status==='running'?Math.max.apply(null,[0].concat(c.matches.filter(function(m){return m.round===c.round&&m.closes}).map(function(m){return m.closes}))):0;
    if(cl)fact('facts',open?'Round 1 closes':roundName(c.round,c.rounds)+' closes',when(cl)+(!open&&left(cl)?' ('+left(cl)+' left)':''));
    if(c.official)fact('facts','Run by',c.owner.name,' ',officialBadge());else fact('facts','Run by',c.owner.name);
    acts(c);bracket(c);spec(c);entrants(c)}
  function acts(c){var a=$('acts');a.innerHTML='';if(c.status!=='open'||Date.now()>=c.starts)return;
    if(!c.me.signedIn){a.appendChild(steamBtn('Sign in with Steam to join'));return}
    if(c.me.entered){add(a,el('span','badge upcoming','you\\'re in'));var lv=el('button','btn ghost small','Leave');
      lv.onclick=function(){if(!confirm('Leave '+c.name+'?'+(c.fee?' Your entry fee of '+c.fee+' credits comes back.':'')))return;lv.disabled=true;
        api('/api/cups/'+id+'/leave',{}).then(load,function(e){lv.disabled=false;msg('am',e.message)})};a.appendChild(lv)}
    else if(c.entrants.length>=c.size)add(a,el('span','muted','The cup is full.'));
    else{var j=add(el('button','btn'),'Join',c.fee?' · ':null,c.fee?cr(c.fee):null);
      j.onclick=function(){if(!confirm('Join '+c.name+'?'+(c.fee?' The entry fee of '+c.fee+' credits is taken now (back if you leave before the start, or the cup is called off).':'')))return;
        j.disabled=true;api('/api/cups/'+id+'/join',{}).then(function(){msg('am','You are in. The draw is made at the start.',true);load()},function(e){j.disabled=false;msg('am',e.message)})};a.appendChild(j)}
    if(c.me.owner){var cx=el('button','btn danger small','Call the cup off');
      cx.onclick=function(){if(!confirm('Call '+c.name+' off? Every entry fee goes back and the drivers are told.'))return;cx.disabled=true;
        api('/api/cups/'+id+'/cancel',{}).then(load,function(e){cx.disabled=false;msg('am',e.message)})};a.appendChild(cx)}}

  // ---- the bracket: a column a round (stacked on a phone), each match its two sides, the winner marked
  function bracket(c){var box=$('bracket');box.innerHTML='';
    if(c.status==='open'){box.appendChild(el('div','empty','The draw is made when the cup starts ('+when(c.starts)+'): the drivers are seeded by their driver rating (equal ratings at random), the top seeds get byes if it isn\\'t full. Then each round\\'s matches open together: round 1 closes '+when(c.starts+c.roundHours*3600000)+', each round after it '+roundLength(c.roundHours)+' later.'));return}
    if(!c.rounds){box.appendChild(el('div','empty','Called off before it started: fewer than two drivers, or by its maker. Every entry fee went back.'));return}
    var br=el('div','bracket'),R=c.rounds;
    for(var r=1;r<=R;r++){var ms=c.matches.filter(function(m){return m.round===r}),col=el('div','rnd'+(c.status==='running'&&r===c.round?' now':''));
      add(col,el('div','rh',ms.length?ms[0].name:roundName(r,R)));var l=el('div','rl');
      for(var s=0;s<Math.pow(2,R-r);s++){var m=ms.filter(function(x){return x.slot===s})[0];l.appendChild(m?match(m):tbd())}
      col.appendChild(l);br.appendChild(col)}
    box.appendChild(br)}
  function side(m,p){var row=el('div','sd');
    if(!p){row.classList.add('bye');add(row,el('span','sn'),el('span','nm','bye'),el('span','tm'));return row}
    var won=m.winner===p.steamId;if(m.winner)row.classList.add(won?'won':'lost');if(ME&&p.steamId===ME.steamId)row.classList.add('me');
    var nm=el('span','nm');flag(nm,p.country);add(nm,p.name);nm.title=p.name;var tm=el('span','tm');
    if(m.a&&m.b){if(p.status==='finished')tm.textContent=ms(p.totalMs);else if(p.status==='dnf'||p.status==='dsq')tm.appendChild(el('span','dnf',p.status.toUpperCase()));
      else if(p.status)tm.appendChild(el('span','run','SS'+(p.done+1)));else tm.textContent=m.winner?'':'–'}
    add(row,el('span','sn',p.seed?String(p.seed):''),nm,tm);return row}
  function match(m){var b=el('div','mt');add(b,side(m,m.a),side(m,m.b));var f=el('div','mf');
    add(f,el('span',null,m.note||(m.winner?'':m.eventId?'under way':'')));
    if(m.eventId){var a=el('a',null,'Match ›');a.href='/e/'+m.eventId;f.appendChild(a)}b.appendChild(f);return b}
  function tbd(){var b=el('div','mt tbd');for(var i=0;i<2;i++){var r=el('div','sd');add(r,el('span','sn'),el('span','nm','to be decided'),el('span','tm'));b.appendChild(r)}
    add(b,el('div','mf'));return b}

  // ---- what every match races
  function spec(c){var s=$('spec');s.innerHTML='';fact('spec','Location',c.rally);fact('spec',c.car?'Car':'Car class',c.car||c.carClass+' (each picks a car of it)');
    fact('spec','Stages',c.stages.length+(c.draw?', a new draw each round':''));var r=$('rules');r.innerHTML='';r.appendChild(ruleChips(c.rules));
    if(c.draw)r.appendChild(el('p','note','Each round, '+c.stages.length+' of '+c.rally+'\\'s stages are drawn at random when it opens: never two on the same road, the ones not driven yet in this cup first'+
      (c.draw.maxKm?', '+c.draw.maxKm+' km at most in all':'')+'. Every match of the round races the same.'));
    var t=$('stages');t.innerHTML='';
    // a cup that draws: each round's draw so far (the slots until the first), else its stages
    var sets=c.draw?(c.roundStages||[]).map(function(x){return{head:x.name,stages:x.stages}}):[{head:null,stages:c.stages}];
    if(c.draw&&!sets.length)sets=[{head:'Drawn when the cup starts',stages:c.stages}];
    sets.forEach(function(set){var h=el('tr');add(h,el('th',null,''),el('th',null,set.head||'Stage'),el('th','r','Start'),el('th',null,'Weather'));t.appendChild(h);
      var days=set.stages.some(function(x){return x.day>1});   // (a rally of more than one day: each day a heading)
      set.stages.forEach(function(x,i){if(days&&(!i||x.day!==set.stages[i-1].day)){var dr=el('tr','day'),td=el('td',null,'Day '+x.day);td.colSpan=4;dr.appendChild(td);t.appendChild(dr)}
        var tr=el('tr');add(tr,el('td','pos','SS'+(i+1)),el('td','drv',x.name||'a stage of '+c.rally+', drawn'),el('td','r',x.time),el('td',null,WX[x.weather]||x.weather));t.appendChild(tr)})})}

  // ---- the drivers: seed once drawn, how far each got
  function entrants(c){var t=$('entrants');t.innerHTML='';var seeded=c.entrants.some(function(e){return e.seed});
    var h=el('tr');add(h,el('th',null,seeded?'Seed':''),el('th',null,'Driver'),el('th','r','Rating'),el('th','r',c.status==='open'?'':'Result'));t.appendChild(h);
    if(!c.entrants.length){var tr=el('tr'),td=el('td','empty','Nobody yet.');td.colSpan=4;tr.appendChild(td);t.appendChild(tr);return}
    var out={};c.matches.forEach(function(m){if(m.winner&&m.a&&m.b){out[m.winner===m.a.steamId?m.b.steamId:m.a.steamId]=m.name}});
    c.entrants.forEach(function(e,i){var tr=el('tr',(e.place===1?'p1':'')+(ME&&e.steamId===ME.steamId?' me':''));
      add(tr,el('td','pos',e.seed?String(e.seed):String(i+1)));var d=el('td','drv');flag(d,e.country);var dl=el('a',null,e.name);dl.href='/d/'+e.steamId;dl.style.textDecoration='none';d.appendChild(dl);tr.appendChild(d);
      tr.appendChild(el('td','r muted',e.rating!=null?String(e.rating):'–'));
      var res=e.place?nth(e.place):out[e.steamId]?'out in the '+out[e.steamId].toLowerCase():c.status==='running'?'still in':'';
      tr.appendChild(el('td','r'+(e.place===1?' tot':' muted'),res));t.appendChild(tr)})}
  account().then(load);
  `, env);
}
