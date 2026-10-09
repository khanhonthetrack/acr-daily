// The league pages: /leagues (directory, create, join), /l/:id (a league), /l/:id/new and /e/:id/edit (the event
// builder), /e/:id (an event: itinerary and standings), /join/:code (an invite). Static shells; the data comes from
// the API (src/leagues.js), signed in with the website's Steam sign-in (/login, a session cookie).

import { FAVICON, logoSvg } from './logo.js';
import { BANNER, POINTS_PRESETS, POWER_PRESET } from './leagues.js';

const CSS = `
:root{--bg:#0A0A0B;--panel:#111113;--line:#1F1F23;--line2:#2B2B31;--fg:#F4F4F5;--fg2:#A1A1AA;--fg3:#6B6B74;--acc:#E30613;--bad:#FF453A;--slow:#FF9F0A;--good:#30D158;--steam:#171A21}
*{box-sizing:border-box;margin:0}
html{background:var(--bg)}
body{color:var(--fg);font:15px/1.5 Barlow,system-ui,sans-serif;-webkit-font-smoothing:antialiased}
a{color:inherit}
.wrap{max-width:1200px;margin:0 auto;padding:0 24px 64px}
header{border-bottom:1px solid var(--line)}
header .wrap{display:flex;align-items:center;justify-content:space-between;gap:16px;height:76px;padding-bottom:0}
.brand{display:flex;align-items:center}
.brandmark{display:block;height:60px;width:auto}
.hnav{display:flex;align-items:center;gap:22px}
.back,.hnav a.l{font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;text-transform:uppercase;text-decoration:none;color:var(--fg2)}
.back:hover,.hnav a.l:hover{color:var(--fg)}
#acct{display:flex;align-items:center;gap:10px;font-size:14px;color:var(--fg2)}
#acct img{width:26px;height:26px;border-radius:50%}
#acct form{display:inline}
.linkbtn{background:none;border:0;color:var(--fg3);font:inherit;cursor:pointer;padding:0;text-decoration:underline}
.linkbtn:hover{color:var(--fg)}
.steam{display:inline-flex;align-items:center;gap:8px;background:var(--steam);color:#fff;border:1px solid #2A475E;padding:8px 14px;font:600 13px/1 Barlow,sans-serif;text-decoration:none;white-space:nowrap}
.steam:hover{background:#2A475E}
.top{margin-top:28px;padding-top:20px;border-top:2px solid var(--fg)}
.kick{font:700 15px/1 'Barlow Condensed',sans-serif;letter-spacing:.08em;color:var(--acc);text-transform:uppercase}
.kick a{text-decoration:none}
.kick a:hover{text-decoration:underline}
h1{font:700 clamp(36px,6vw,64px)/.95 'Barlow Condensed',sans-serif;text-transform:uppercase;margin-top:12px;overflow-wrap:anywhere}
h2{font:700 24px/1 'Barlow Condensed',sans-serif;text-transform:uppercase;letter-spacing:.02em;margin:36px 0 14px}
h3{font:600 15px/1.2 'Barlow Condensed',sans-serif;text-transform:uppercase;letter-spacing:.1em;color:var(--fg2);margin:18px 0 8px}
.note{color:var(--fg2);font-size:14px;margin:12px 0 0;max-width:760px}
.about{color:var(--fg);margin-top:14px;max-width:760px;white-space:pre-line}
.muted{color:var(--fg3)}
.k{font:600 11px/1 Barlow,sans-serif;letter-spacing:.12em;text-transform:uppercase;color:var(--fg3)}
.facts{display:flex;flex-wrap:wrap;gap:10px 28px;margin-top:18px}
.facts div{min-width:120px}
.facts b{display:block;font:600 18px/1.2 'Barlow Condensed',sans-serif;margin-top:5px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:14px}
.chip{border:1px solid var(--line2);padding:4px 9px;font:600 12px/1 Barlow,sans-serif;letter-spacing:.06em;text-transform:uppercase;color:var(--fg2)}
.badge{display:inline-block;padding:3px 7px;font:700 11px/1 Barlow,sans-serif;letter-spacing:.1em;text-transform:uppercase;border:1px solid var(--line2);color:var(--fg2);vertical-align:2px}
.badge.open{background:var(--acc);border-color:var(--acc);color:#fff}
.badge.upcoming{border-color:var(--fg2);color:var(--fg)}
.badge.private{border-color:var(--slow);color:var(--slow)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.card{background:var(--panel);border:1px solid var(--line);padding:18px}
.card h3{margin-top:0}
.row{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.item{display:flex;justify-content:space-between;align-items:center;gap:14px;padding:13px 0;border-bottom:1px solid var(--line);text-decoration:none}
.item:hover .t{color:var(--acc)}
.item .t{font:700 20px/1.1 'Barlow Condensed',sans-serif;text-transform:uppercase}
.item .s{color:var(--fg2);font-size:13px;margin-top:4px}
.item .r{text-align:right;color:var(--fg2);font-size:13px;white-space:nowrap}
.empty{color:var(--fg3);padding:16px 0;border-bottom:1px solid var(--line)}
label{display:block;margin:12px 0 0}
label>span{display:block;font:600 11px/1 Barlow,sans-serif;letter-spacing:.12em;text-transform:uppercase;color:var(--fg3);margin-bottom:6px}
input[type=text],input[type=time],input[type=datetime-local],select,textarea{width:100%;background:#0E0E10;border:1px solid var(--line2);color:var(--fg);font:15px/1.3 Barlow,sans-serif;padding:9px 10px;border-radius:0;color-scheme:dark}
textarea{min-height:76px;resize:vertical}
input:focus,select:focus,textarea:focus{outline:none;border-color:var(--fg2)}
.radio{display:flex;gap:6px;flex-wrap:wrap}
.radio label{margin:0}
.radio input{position:absolute;opacity:0}
.radio span{display:block;border:1px solid var(--line2);padding:8px 12px;font:600 13px/1 Barlow,sans-serif;color:var(--fg2);cursor:pointer;margin:0;letter-spacing:.02em;text-transform:none}
.radio input:checked+span{border-color:var(--acc);color:var(--fg);background:#1A0B0C}
.btn{display:inline-block;background:var(--acc);color:#fff;border:1px solid var(--acc);padding:10px 18px;font:700 14px/1 'Barlow Condensed',sans-serif;letter-spacing:.1em;text-transform:uppercase;cursor:pointer;text-decoration:none;white-space:nowrap}
.btn:hover{filter:brightness(1.12)}
.btn.ghost{background:none;color:var(--fg);border-color:var(--line2)}
.btn.ghost:hover{border-color:var(--fg2)}
.btn.small{padding:6px 10px;font-size:12px}
.btn.danger{background:none;color:var(--bad);border-color:#5a1f1c}
.btn:disabled{opacity:.45;cursor:default;filter:none}
.msg{margin-top:10px;font-size:14px;min-height:1px}
.msg.bad{color:var(--bad)}
.msg.good{color:var(--good)}
.code{font:700 26px/1 'Barlow Condensed',sans-serif;letter-spacing:.14em}
.tablewrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-feature-settings:'tnum'}
th{font:600 11px/1 Barlow,sans-serif;letter-spacing:.12em;text-transform:uppercase;color:var(--fg3);padding:8px 10px 10px 0;text-align:left;white-space:nowrap;border-bottom:1px solid var(--line2)}
th.r,td.r{text-align:right}
td{padding:10px 10px 10px 0;border-bottom:1px solid var(--line);white-space:nowrap;vertical-align:middle}
td.pos{width:40px;font:600 18px/1 'Barlow Condensed',sans-serif;color:var(--fg2)}
tr.p1 td.pos{color:var(--acc)}
td.drv{font-weight:500}
td.tot{font:700 19px/1 'Barlow Condensed',sans-serif}
td.t{font:600 15px/1 'Barlow Condensed',sans-serif}
td.t small{display:block;font:500 11px/1.2 Barlow,sans-serif;color:var(--fg3);margin-top:3px}
td.t small.pen{color:var(--slow)}
td.t.w{color:var(--acc)}
.dnf{color:var(--bad);font:600 13px/1 Barlow,sans-serif;letter-spacing:.04em}
.run{color:var(--slow);font:600 13px/1 Barlow,sans-serif}
tr.me td.drv{color:var(--acc)}
.flagimg{width:18px;height:12px;margin-right:8px;vertical-align:-1px;object-fit:cover;box-shadow:0 0 0 1px rgba(255,255,255,.12)}
.itin td{white-space:normal}
.itin tr.day td{font:700 15px/1 'Barlow Condensed',sans-serif;letter-spacing:.1em;text-transform:uppercase;color:var(--fg);padding-top:20px}
.itin tr.sp td{color:var(--fg3);font-size:13px}
.steps{counter-reset:s;margin-top:10px;padding:0;list-style:none}
.steps li{counter-increment:s;padding:6px 0 6px 30px;position:relative;color:var(--fg2)}
.steps li:before{content:counter(s);position:absolute;left:0;top:6px;width:20px;height:20px;border:1px solid var(--line2);text-align:center;font:600 12px/18px Barlow,sans-serif;color:var(--fg)}
.steps b{color:var(--fg);font-weight:600}
.builder .day{border:1px solid var(--line);background:var(--panel);padding:14px 14px 10px;margin-top:12px}
.builder .dayhead{display:flex;justify-content:space-between;align-items:center}
.builder .dayhead b{font:700 18px/1 'Barlow Condensed',sans-serif;text-transform:uppercase;letter-spacing:.06em}
.builder .sprow{color:var(--fg3);font-size:13px;padding:10px 0 6px;border-bottom:1px solid var(--line)}
.builder .st{display:grid;grid-template-columns:44px minmax(160px,2.4fr) 92px minmax(120px,1.3fr) auto auto;gap:8px;align-items:center;padding:8px 0;border-bottom:1px solid var(--line)}
.builder .st .no{font:700 16px/1 'Barlow Condensed',sans-serif;color:var(--fg2)}
.builder .st .sp{font-size:12px;color:var(--fg2);display:flex;align-items:center;gap:5px;margin:0;white-space:nowrap}
.builder .st .tools{display:flex;gap:4px}
.builder .st .tools button{background:none;border:1px solid var(--line2);color:var(--fg2);width:28px;height:28px;cursor:pointer}
.builder .st .tools button:hover{color:var(--fg);border-color:var(--fg2)}
.builder .between{font-size:12px;color:var(--fg3);padding:4px 0 0 52px}
.twocol{display:grid;grid-template-columns:1fr 1fr;gap:0 18px}
.sum{margin-top:14px;color:var(--fg2)}
.danger-zone{margin-top:40px;padding-top:16px;border-top:1px solid var(--line)}
.banner{display:block;width:100%;aspect-ratio:3/1;object-fit:cover;margin-top:24px;background:var(--panel);border:1px solid var(--line)}
.banner[hidden]{display:none}
.banner:not([hidden])+.top{margin-top:0;border-top:0}
.item .thumb{width:108px;aspect-ratio:3/1;object-fit:cover;flex:none;border:1px solid var(--line);background:var(--panel)}
.item .grow{flex:1;min-width:0}
.bannerset{display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap;margin-top:6px}
.bannerset .prev{width:300px;max-width:100%;aspect-ratio:3/1;object-fit:cover;border:1px solid var(--line2);background:#0E0E10}
.bannerset .none{width:300px;max-width:100%;aspect-ratio:3/1;border:1px dashed var(--line2);display:flex;align-items:center;justify-content:center;color:var(--fg3);font-size:13px}
.filebtn{position:relative;overflow:hidden}
.filebtn input{position:absolute;inset:0;opacity:0;cursor:pointer}
.tabs{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:6px}
.tab{background:none;border:1px solid var(--line2);color:var(--fg2);padding:7px 12px;font:600 13px/1 Barlow,sans-serif;cursor:pointer}
.tab:hover{color:var(--fg);border-color:var(--fg2)}
.tab.on{border-color:var(--acc);color:var(--fg);background:#1A0B0C}
td.dropped{color:var(--fg3);text-decoration:line-through}
td small.ps{display:block;font:500 11px/1.2 Barlow,sans-serif;color:var(--good);margin-top:3px}
td.t small.st{color:var(--bad)}
td.t small.st.back{color:var(--good)}
.badge.admin{border-color:var(--fg2);color:var(--fg)}
.badge.owner{background:var(--acc);border-color:var(--acc);color:#fff}
.badge.season{border-color:var(--line2);color:var(--fg2)}
.decision{display:flex;justify-content:space-between;gap:14px;align-items:center;padding:11px 0;border-bottom:1px solid var(--line)}
.decision b{font:700 15px/1 'Barlow Condensed',sans-serif;letter-spacing:.06em;margin-right:8px}
.decision .bad{color:var(--bad)}
.decision .good{color:var(--good)}
.stewform{display:grid;grid-template-columns:minmax(160px,1.4fr) 120px 110px minmax(180px,2fr) auto;gap:8px;align-items:end;margin-top:12px}
.stewform label{margin:0}
.actions{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}
@media (max-width:760px){.stewform{grid-template-columns:1fr 1fr}}
@media (max-width:760px){.wrap{padding:0 16px 48px}.hnav{gap:12px}.hnav a.l{display:none}.twocol{grid-template-columns:1fr}
  .builder .st{grid-template-columns:34px 1fr 108px;}.builder .st .w{grid-column:2/4}.builder .st .sp{grid-column:2/3}.builder .st .tools{grid-column:3/4;justify-content:flex-end}}
`;

// helpers every page's script uses: $, el, api (JSON, the session cookie), times, sign-in state in the header
const JS = `
function $(id){return document.getElementById(id)}
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
function add(p){for(var i=1;i<arguments.length;i++){var c=arguments[i];if(c==null)continue;p.appendChild(typeof c==='string'?document.createTextNode(c):c)}return p}
function api(path,body){var o={credentials:'same-origin',cache:'no-store',headers:{}};
  if(body!==undefined){o.method='POST';o.headers['Content-Type']='application/json';o.body=JSON.stringify(body)}
  return fetch(path,o).then(function(r){return r.json().catch(function(){return{}}).then(function(j){if(!r.ok){var e=new Error(j.error||('error '+r.status));e.status=r.status;throw e}return j})})}
function signin(){return '/login?next='+encodeURIComponent(location.pathname+location.search)}
function steamBtn(text){var a=el('a','steam',text||'Sign in with Steam');a.href=signin();return a}
function ms(t){if(t==null)return '';var s=Math.floor(t/1000),m=Math.floor(s/60);return m+':'+String(s%60).padStart(2,'0')+'.'+String(t%1000).padStart(3,'0')}
function gap(t){return t?'+'+(t<60000?(t/1000).toFixed(3):ms(t)):''}
function pen(t){return t?'+'+Math.round(t/1000)+' s':''}
function secs(t){var a=Math.abs(t)/1000;return (t<0?'−':'+')+(a%1?a.toFixed(1):a)+' s'}
function when(t){return new Date(t).toLocaleString(undefined,{weekday:'short',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})}
function left(t){var d=t-Date.now();if(d<=0)return '';var h=Math.floor(d/3600000),m=Math.floor(d%3600000/60000);return h>=48?Math.floor(h/24)+' days':h>=1?h+' h '+m+' min':m+' min'}
function km(m){return (m/1000).toFixed(1)+' km'}
function flag(p,c){if(!c)return;var i=el('img','flagimg');i.src='https://flagcdn.com/w40/'+c+'.png';i.alt=c.toUpperCase();p.appendChild(i)}
function msg(id,text,good){var m=$(id);if(m){m.textContent=text||'';m.className='msg'+(text?(good?' good':' bad'):'')}}
function showBanner(img,url){if(url){img.src=url;img.hidden=false}else{img.removeAttribute('src');img.hidden=true}}
function thumb(url){if(!url)return null;var i=el('img','thumb');i.loading='lazy';i.alt='';i.src=url;return i}
var ME=null;
function account(){return api('/api/me').then(function(me){if(!me.signedIn)throw new Error('signed out');ME=me;var a=$('acct');a.innerHTML='';
    if(me.avatar){var i=el('img');i.src=me.avatar;i.alt='';a.appendChild(i)}
    add(a,el('span',null,me.name));var f=el('form');f.method='post';f.action='/logout?next='+encodeURIComponent(location.pathname);
    add(f,el('button','linkbtn','sign out'));f.firstChild.type='submit';a.appendChild(f);return me})
  .catch(function(){ME=null;var a=$('acct');a.innerHTML='';a.appendChild(steamBtn());return null})}
`;

export function shell(title, body, script) {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${title}</title>
<link rel="icon" href="${FAVICON}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">
<style>${CSS}</style>
</head>
<body>
<header><div class="wrap"><a class="brand" href="/">${logoSvg()}</a>
<nav class="hnav"><a class="l" href="/">Today's stages</a><a class="l" href="/leagues">Leagues</a><span id="acct"></span></nav></div></header>
<main class="wrap">${body}</main>
<script>
${JS}
(function(){
${script}
})();
</script>
</body>
</html>`;
}

// ------------------------------------------------------------------ /leagues
export function leaguesPage() {
  return shell('Leagues · ACR Daily', `
  <div class="top"><div class="kick">ACR Daily</div><h1>Leagues</h1>
  <p class="note">Your own rallies with friends or your community: several stages over one or more days, service parks
  between them, the damage carried from stage to stage. Each driver gets one go before the event closes, and the game's
  own stage times and penalties count. Events add up to a championship.</p></div>
  <h2>Your leagues</h2><div id="mine"></div>
  <div class="grid" style="margin-top:22px">
    <div class="card"><h3>Create a league</h3><div id="create"></div></div>
    <div class="card"><h3>Join with an invite code</h3>
      <label><span>Invite code</span><input type="text" id="code" placeholder="ABCD-EFGH" maxlength="12" autocomplete="off"></label>
      <div class="row" style="margin-top:12px"><button class="btn" id="joinb">Join</button></div><div class="msg" id="joinmsg"></div></div>
  </div>
  <h2>Public leagues</h2><div id="pub"></div>`, `
  function list(box,ls,emptyText){box.innerHTML='';if(!ls.length){box.appendChild(el('div','empty',emptyText));return}
    ls.forEach(function(l){var a=el('a','item');a.href='/l/'+l.id;add(a,thumb(l.banner));var d=el('div','grow');var t=el('div','t',l.name+' ');
      if(!l.public)t.appendChild(el('span','badge private','private'));
      add(d,t,el('div','s',(l.about||'').slice(0,140)));
      var r=el('div','r',l.members+(l.members===1?' driver':' drivers')+' · '+l.events+(l.events===1?' event':' events'));
      if(l.openEvents)add(r,el('br'),el('span','badge open',l.openEvents+' open'));
      else if(l.nextOpens)add(r,el('br'),'next: '+when(l.nextOpens));
      add(a,d,r);box.appendChild(a)})}
  function load(){api('/api/leagues').then(function(j){list($('pub'),j.public,'No public leagues yet. Create the first one.');
    if(ME)list($('mine'),j.mine,'You are not in a league yet: create one, or join one below.')})}
  account().then(function(me){
    var c=$('create');c.innerHTML='';
    if(!me){$('mine').innerHTML='';add($('mine'),el('div','empty','Sign in with Steam to see your leagues, create one or join one. '),steamBtn());
      add(c,el('p','muted','Sign in with Steam first.'));c.appendChild(steamBtn());$('joinb').onclick=function(){location.href=signin()};load();return}
    c.innerHTML='<label><span>Name</span><input type="text" id="ln" maxlength="60" placeholder="e.g. Friday Night Rally Club"></label>'+
      '<label><span>About (optional)</span><textarea id="la" maxlength="600" placeholder="Who it is for, how often you run events, your Discord..."></textarea></label>'+
      '<p class="note">A banner picture can be added from the league\\'s page once it is made.</p>'+
      '<label><span>Who can join</span></label><div class="radio"><label><input type="radio" name="lp" value="1" checked><span>Public: listed here, anyone can join</span></label>'+
      '<label><input type="radio" name="lp" value="0"><span>Private: only with your invite link</span></label></div>'+
      '<div class="row" style="margin-top:14px"><button class="btn" id="lc">Create league</button></div><div class="msg" id="lcmsg"></div>';
    $('lc').onclick=function(){var b=this;b.disabled=true;
      api('/api/leagues',{name:$('ln').value,about:$('la').value,public:document.querySelector('input[name=lp]:checked').value==='1'})
        .then(function(j){location.href='/l/'+j.id},function(e){b.disabled=false;msg('lcmsg',e.message)})};
    $('joinb').onclick=function(){var b=this;b.disabled=true;
      api('/api/leagues/join',{code:$('code').value}).then(function(j){location.href='/l/'+j.id},function(e){b.disabled=false;msg('joinmsg',e.message)})};
    load()});
  `);
}

// ------------------------------------------------------------------ /join/:code
export function joinPage(code) {
  return shell('Join a league · ACR Daily', `
  <img class="banner" id="banner" alt="" hidden>
  <div class="top"><div class="kick">Invitation</div><h1 id="name">League</h1><p class="about" id="about"></p>
  <div class="facts" id="facts"></div><div class="row" style="margin-top:22px" id="act"></div><div class="msg" id="m"></div></div>`, `
  var code=${JSON.stringify(code)};
  account().then(function(me){
    api('/api/leagues/code?code='+encodeURIComponent(code)).then(function(l){
      $('name').textContent=l.name;$('about').textContent=l.about||'';document.title=l.name+' · ACR Daily';showBanner($('banner'),l.banner);
      $('facts').innerHTML='';var f=el('div');add(f,el('span','k','Drivers'),el('b',null,String(l.members)));$('facts').appendChild(f);
      var a=$('act');
      if(l.member){var g=el('a','btn','Open the league');g.href='/l/'+l.id;a.appendChild(g);msg('m','You are in this league already.',true);return}
      if(!me){a.appendChild(steamBtn('Sign in with Steam to join'));return}
      var b=el('button','btn','Join '+l.name);b.onclick=function(){b.disabled=true;
        api('/api/leagues/join',{code:code}).then(function(){location.href='/l/'+l.id},function(e){b.disabled=false;msg('m',e.message)})};
      a.appendChild(b)},
    function(e){$('name').textContent='Invite link not valid';msg('m',e.message)})});
  `);
}

// ------------------------------------------------------------------ /l/:id
export function leaguePage(id) {
  return shell('League · ACR Daily', `
  <img class="banner" id="banner" alt="" hidden>
  <div class="top"><div class="kick" id="kick">League</div><h1 id="name"></h1><p class="about" id="about"></p>
    <div class="row" style="margin-top:18px" id="acts"></div><div class="msg" id="am"></div></div>
  <div id="ownerbox"></div>
  <h2>Events</h2><div id="evs"></div>
  <h2>Championship</h2><div id="seasons"></div>
  <h2>Drivers</h2><div id="members"></div><div class="msg" id="mm"></div><div id="bans"></div>`, `
  var id=${JSON.stringify(id)},q=new URLSearchParams(location.search),L=null,SEL=null;
  var PRESETS=${JSON.stringify(POINTS_PRESETS)},POWER=${JSON.stringify(POWER_PRESET)};
  function load(){return api('/api/leagues/'+id+(q.get('code')?'?code='+encodeURIComponent(q.get('code')):'')).then(render,function(e){
    $('name').textContent=e.status===404?'No such league':'League';msg('am',e.status===404?'This league does not exist, or it is private: open it with its invite link.':e.message)})}
  function evById(eid){return L.events.filter(function(e){return e.id===eid})[0]}
  function seasonById(sid){return L.seasons.filter(function(s){return s.id===sid})[0]}
  function render(l){L=l;document.title=l.name+' · ACR Daily';$('name').textContent=l.name;$('about').textContent=l.about||'';showBanner($('banner'),l.banner);
    $('kick').textContent=(l.public?'Public':'Private')+' league · '+l.members.length+(l.members.length===1?' driver':' drivers')+(l.owner.name?' · run by '+l.owner.name:'');
    var a=$('acts');a.innerHTML='';
    if(!l.me.signedIn)a.appendChild(steamBtn('Sign in with Steam to join'));
    else if(!l.me.member){var j=el('button','btn','Join this league');j.onclick=function(){j.disabled=true;
      api('/api/leagues/'+id+'/join',{code:q.get('code')||''}).then(load,function(e){j.disabled=false;msg('am',e.message)})};a.appendChild(j)}
    else if(!l.me.owner){var lv=el('button','btn ghost small','Leave');lv.onclick=function(){if(!confirm('Leave '+l.name+'?'))return;
      api('/api/leagues/'+id+'/leave',{}).then(function(){location.href='/leagues'},function(e){msg('am',e.message)})};a.appendChild(lv)}
    if(l.me.staff){var ne=el('a','btn','New event');ne.href='/l/'+id+'/new';a.appendChild(ne)}
    if(l.me.role==='admin')add(a,el('span','badge admin','you are an admin'));
    manage(l);events(l);seasons(l);members(l)}

  // ---- invite (the owner and admins; anyone on a public league), settings, banner, Discord (the owner)
  function manage(l){var box=$('ownerbox');box.innerHTML='';if(!l.me.staff&&!(l.public&&l.code))return;
    var c=el('div','card');c.style.marginTop='26px';box.appendChild(c);
    add(c,el('h3',null,'Invite drivers'));var link=location.origin+'/join/'+l.code;
    var r=el('div','row');add(r,el('span','code',l.code));var cp=el('button','btn ghost small','Copy invite link');
    cp.onclick=function(){navigator.clipboard.writeText(link).then(function(){msg('om','Copied: '+link,true)})};r.appendChild(cp);c.appendChild(r);
    add(c,el('p','note',l.public?'Anyone can join from this page; the link or code takes friends straight here.':'Private: drivers join only with this link or code.'));
    if(!l.me.staff)return;
    var nc=el('button','btn ghost small','New code (the old link stops working)');nc.style.marginTop='10px';
    nc.onclick=function(){if(!confirm('Make a new invite code? The old link and code stop working.'))return;api('/api/leagues/'+id+'/code',{}).then(load)};c.appendChild(nc);
    add(c,el('div','msg'));c.lastChild.id='om';
    if(!l.me.owner)return;
    add(c,el('h3',null,'League settings'));
    var f=el('div','twocol');f.innerHTML='<label><span>Name</span><input type="text" id="en" maxlength="60"></label>'+
      '<label><span>Who can join</span><select id="ep"><option value="1">Public: listed, anyone can join</option><option value="0">Private: invite link only</option></select></label>';
    c.appendChild(f);add(c,el('label'));c.lastChild.innerHTML='<span>About</span><textarea id="ea" maxlength="600"></textarea>';
    $('en').value=l.name;$('ea').value=l.about||'';$('ep').value=l.public?'1':'0';
    var sv=el('button','btn small','Save');sv.style.marginTop='12px';sv.onclick=function(){api('/api/leagues/'+id+'/edit',{name:$('en').value,about:$('ea').value,public:$('ep').value==='1'})
      .then(function(){msg('sm','Saved.',true);load()},function(e){msg('sm',e.message)})};c.appendChild(sv);add(c,el('div','msg'));c.lastChild.id='sm';
    bannerBox(c,l);discordBox(c,l);
    var dz=el('div','danger-zone');add(dz,el('h3',null,'Delete the league'),el('p','note','Deletes its events, seasons and results for good.'));
    var del=el('button','btn danger small','Delete league');del.style.marginTop='10px';del.onclick=function(){var t=prompt('Type the league name to delete it: '+l.name);if(t==null)return;
      api('/api/leagues/'+id+'/delete',{confirm:t}).then(function(){location.href='/leagues'},function(e){msg('dm',e.message)})};
    dz.appendChild(del);add(dz,el('div','msg'));dz.lastChild.id='dm';c.appendChild(dz)}
  // the banner: any wide picture, cut to 3:1 from its middle and made a 1200 x 400 JPEG here (src/leagues.js BANNER)
  function makeBanner(file){return new Promise(function(ok,no){
    if(!/^image\\/(png|jpeg|webp)$/.test(file.type))return no(new Error('a PNG, JPEG or WebP picture, please'));
    var u=URL.createObjectURL(file),img=new Image();
    img.onerror=function(){URL.revokeObjectURL(u);no(new Error('this picture could not be read'))};
    img.onload=function(){URL.revokeObjectURL(u);var iw=img.naturalWidth,ih=img.naturalHeight,W=1200,H=400,s=Math.max(W/iw,H/ih);
      if(s>2)return no(new Error('the picture is '+iw+' x '+ih+': it needs to be at least 600 x 200'));
      var cv=document.createElement('canvas');cv.width=W;cv.height=H;var g=cv.getContext('2d');
      g.fillStyle='#0A0A0B';g.fillRect(0,0,W,H);g.imageSmoothingQuality='high';g.drawImage(img,(W-iw*s)/2,(H-ih*s)/2,iw*s,ih*s);
      var qs=[0.86,0.78,0.7,0.6,0.5];(function next(k){cv.toBlob(function(b){
        if(!b)return no(new Error('the browser could not make the banner'));
        if(b.size<=${BANNER.maxBytes})return ok(b);
        if(k===qs.length-1)return no(new Error('the picture stays too big: try a simpler one'));
        next(k+1)},'image/jpeg',qs[k])})(0)};
    img.src=u})}
  function bannerBox(c,l){add(c,el('h3',null,'Banner'));
    var wrap=el('div','bannerset'),pv;
    if(l.banner){pv=el('img','prev');pv.alt='';pv.src=l.banner}else pv=el('div','none','No banner yet');
    var side=el('div'),pick=el('span','btn ghost small filebtn',l.banner?'Change picture':'Choose a picture');
    var fi=el('input');fi.type='file';fi.accept='image/png,image/jpeg,image/webp';pick.appendChild(fi);side.appendChild(pick);
    if(l.banner){var rm=el('button','btn ghost small','Remove');rm.style.marginLeft='6px';rm.onclick=function(){if(!confirm('Remove the banner?'))return;
      api('/api/leagues/'+id+'/banner',{remove:true}).then(load,function(e){msg('bm',e.message)})};side.appendChild(rm)}
    add(side,el('p','note','Any wide picture: it is cut to 3:1 from its middle and made 1200 × 400 here, then shown across the top of the league page and in the list of leagues. Your own or free to use, nothing offensive: an admin can take it down.'));
    add(wrap,pv,side);c.appendChild(wrap);add(c,el('div','msg'));c.lastChild.id='bm';
    fi.onchange=function(){var f=fi.files&&fi.files[0];if(!f)return;msg('bm','Making the banner...',true);
      makeBanner(f).then(function(b){msg('bm','Uploading ('+Math.round(b.size/1000)+' KB)...',true);
        return fetch('/api/leagues/'+id+'/banner',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'image/jpeg'},body:b})
          .then(function(r){return r.json().catch(function(){return{}}).then(function(j){if(!r.ok)throw new Error(j.error||('error '+r.status));return j})})})
      .then(function(){msg('bm','');load()},function(e){fi.value='';msg('bm',e.message)})}}
  function discordBox(c,l){add(c,el('h3',null,'Discord'));
    add(c,el('p','note','Posts in one of your Discord channels when an event opens, when it has 24 hours left, and its results. In Discord: the channel\\'s settings › Integrations › Webhooks › New Webhook › Copy Webhook URL, then paste it here. Keep that address private: anyone with it can post in the channel.'));
    var r=el('div','row');
    if(l.discord&&l.discord.set){add(r,el('span','muted','Connected (webhook …'+l.discord.hint+')'));
      var tb=el('button','btn ghost small','Send a test message');tb.onclick=function(){tb.disabled=true;
        api('/api/leagues/'+id+'/discord',{test:true}).then(function(){tb.disabled=false;msg('dcm','Sent: have a look in the channel.',true)},function(e){tb.disabled=false;msg('dcm',e.message)})};
      var dc=el('button','btn ghost small','Disconnect');dc.onclick=function(){if(!confirm('Stop posting in that Discord channel?'))return;
        api('/api/leagues/'+id+'/discord',{remove:true}).then(load,function(e){msg('dcm',e.message)})};
      add(r,tb,dc)}
    else{var inp=el('input');inp.type='text';inp.placeholder='https://discord.com/api/webhooks/…';inp.style.flex='1';inp.style.minWidth='240px';inp.style.width='auto';
      var cb=el('button','btn small','Connect');cb.onclick=function(){cb.disabled=true;
        api('/api/leagues/'+id+'/discord',{webhook:inp.value}).then(load,function(e){cb.disabled=false;msg('dcm',e.message)})};add(r,inp,cb)}
    c.appendChild(r);add(c,el('div','msg'));c.lastChild.id='dcm'}

  // ---- events
  function evItem(e){var a=el('a','item');a.href='/e/'+e.id;var d=el('div');
    var t=el('div','t',e.name+' ');t.appendChild(el('span','badge '+e.status,e.status==='open'?'open':e.status==='upcoming'?'upcoming':'finished'));
    var s=e.seasonId&&seasonById(e.seasonId);
    add(d,t,el('div','s',(s?s.name:'One-off')+' · '+e.rally+' · '+e.stages+(e.stages===1?' stage':' stages')+' · '+e.days+(e.days===1?' day':' days')+' · '+km(e.lengthM)+' · '+(e.car||e.carClass+' class')));
    var r=el('div','r');
    if(e.status==='open')add(r,'closes '+when(e.closes),el('br'),e.entries+' started · '+e.finished+' finished');
    else if(e.status==='upcoming')add(r,'opens '+when(e.opens));
    else add(r,e.winner?'won by '+e.winner:'no finishers',el('br'),e.finished+' of '+e.entries+' finished');
    add(a,d,r);return a}
  function events(l){var box=$('evs');box.innerHTML='';
    var groups=[['open','Open now'],['upcoming','Coming up'],['closed','Finished']],any=false;
    groups.forEach(function(g){var es=l.events.filter(function(e){return e.status===g[0]});if(g[0]==='closed')es.reverse();if(!es.length)return;any=true;
      box.appendChild(el('h3',null,g[1]));es.forEach(function(e){box.appendChild(evItem(e))})});
    if(!any)box.appendChild(el('div','empty',l.me.staff?'No events yet: make the first one with NEW EVENT.':'No events yet.'))}

  // ---- seasons: one tab each, the one under way first shown
  function seasons(l){var box=$('seasons');box.innerHTML='';var ss=l.seasons;var nb=null;
    if(l.me.staff){nb=el('button','btn ghost small','+ New season');nb.onclick=function(){seasonForm(null)}}
    if(!ss.length){add(box,el('div','empty','No season yet.'+(l.me.staff?' Make one, then put events in it (the event builder has a Season field), or let the first event make one.':'')));
      if(nb){nb.style.marginTop='10px';box.appendChild(nb)}add(box,el('div'));box.lastChild.id='sform';return}
    if(SEL==null||!seasonById(SEL)){var run=ss.filter(function(s){return s.events.some(function(eid){var e=evById(eid);return e&&e.status!=='upcoming'})});
      SEL=(run.length?run[run.length-1]:ss[ss.length-1]).id}
    var tabs=el('div','tabs');ss.forEach(function(s){var t=el('button','tab'+(s.id===SEL?' on':''),s.name);t.onclick=function(){SEL=s.id;seasons(l)};tabs.appendChild(t)});
    if(nb)tabs.appendChild(nb);box.appendChild(tabs);
    var s=seasonById(SEL);var head=el('div','row');head.style.justifyContent='space-between';add(head,el('p','note',s.about+' Events still open count as they stand; ties go to more wins, then more events finished.'));
    if(l.me.staff){var eb=el('button','btn ghost small','Edit season');eb.onclick=function(){seasonForm(s)};head.appendChild(eb)}
    box.appendChild(head);add(box,el('div'));box.lastChild.id='sform';
    var evs=s.events.map(evById).filter(function(e){return e&&e.status!=='upcoming'});
    var tw=el('div','tablewrap'),t=el('table');tw.appendChild(t);box.appendChild(tw);
    var h=el('tr');add(h,el('th',null,'Pos'),el('th',null,'Driver'));evs.forEach(function(e,i){var th=el('th','r');var a=el('a',null,'R'+(i+1));a.href='/e/'+e.id;a.title=e.name;th.appendChild(a);h.appendChild(th)});
    add(h,el('th','r','Wins'),el('th','r','Points'));t.appendChild(h);
    if(!s.standings.length){var tr=el('tr'),td=el('td','empty',s.events.length?'No results yet.':'No events in this season yet.');td.colSpan=4+evs.length;tr.appendChild(td);t.appendChild(tr)}
    s.standings.forEach(function(p){var tr=el('tr',p.rank===1?'p1':'');add(tr,el('td','pos',String(p.rank)));var d=el('td','drv');flag(d,p.country);add(d,p.name);tr.appendChild(d);
      evs.forEach(function(e){var c=p.cells[e.id],td=el('td','r'+(c&&c.dropped?' dropped':''));
        if(!c||c.absent)td.textContent='·';else if(c.pos){td.textContent=c.pts;if(c.power)td.appendChild(el('small','ps','PS +'+c.power))}
        else if(c.dsq)td.appendChild(el('span','dnf','DSQ'));else if(c.dnf)td.appendChild(el('span','dnf','DNF'));else td.appendChild(el('span','run','…'));
        td.title=e.name+(c&&c.pos?': P'+c.pos+(c.power?', Power Stage +'+c.power:''):'')+(c&&c.dropped?' (dropped)':'');tr.appendChild(td)});
      add(tr,el('td','r',String(p.wins)),el('td','r tot',String(p.points)));t.appendChild(tr)})}
  function seasonForm(s){var box=$('sform');box.innerHTML='';var f=el('div','card');f.style.margin='14px 0';box.appendChild(f);
    add(f,el('h3',null,s?'Edit '+s.name:'New season'));
    var g=el('div','twocol');g.innerHTML='<label><span>Name</span><input type="text" id="sn" maxlength="60" placeholder="e.g. 2026 Autumn"></label>'+
      '<label><span>Points</span><select id="sp"></select></label>'+
      '<label class="cust"><span>Points from P1 down</span><input type="text" id="st" placeholder="25, 18, 15, 12, 10, 8, 6, 4, 2, 1"></label>'+
      '<label class="cust"><span>Then, for every other finisher</span><input type="text" id="sf" placeholder="0"></label>'+
      '<label><span>Power Stage bonus (each event\\'s last stage)</span><select id="sw"><option value="">None</option><option value="wrc">'+POWER.join('-')+' (as in the WRC)</option><option value="custom">Your own…</option></select></label>'+
      '<label class="custw"><span>Bonus from P1 down</span><input type="text" id="swt" placeholder="5, 4, 3, 2, 1"></label>'+
      '<label><span>Worst rounds dropped (each driver)</span><select id="sd"></select></label>';
    f.appendChild(g);
    Object.keys(PRESETS).forEach(function(k){var o=el('option',null,PRESETS[k].label);o.value=k;$('sp').appendChild(o)});var oc=el('option',null,'Your own…');oc.value='custom';$('sp').appendChild(oc);
    for(var i=0;i<=5;i++){var od=el('option',null,i?String(i):'None: every round counts');od.value=String(i);$('sd').appendChild(od)}
    var pts=s?s.points:PRESETS.wrc,pw=s?s.power:[];
    var pk=Object.keys(PRESETS).filter(function(k){return PRESETS[k].table.join()===pts.table.join()&&PRESETS[k].finisher===pts.finisher})[0];
    $('sn').value=s?s.name:'Season '+(L.seasons.length+1);$('sp').value=pk||'custom';$('st').value=pts.table.join(', ');$('sf').value=String(pts.finisher||0);
    $('sw').value=!pw.length?'':pw.join()===POWER.join()?'wrc':'custom';$('swt').value=pw.join(', ');$('sd').value=String(s?s.drop:0);
    function vis(){[].forEach.call(f.querySelectorAll('.cust'),function(x){x.style.display=$('sp').value==='custom'?'':'none'});
      [].forEach.call(f.querySelectorAll('.custw'),function(x){x.style.display=$('sw').value==='custom'?'':'none'})}
    $('sp').onchange=function(){var p=PRESETS[this.value];if(p){$('st').value=p.table.join(', ');$('sf').value=String(p.finisher)}vis()};$('sw').onchange=vis;vis();
    var r=el('div','row');r.style.marginTop='14px';
    var sv=el('button','btn small',s?'Save season':'Make season');sv.onclick=function(){sv.disabled=true;
      var w=$('sw').value,body={name:$('sn').value,points:{table:$('st').value,finisher:$('sf').value},power:w==='wrc'?POWER:w==='custom'?$('swt').value:[],drop:+$('sd').value};
      api(s?'/api/seasons/'+s.id+'/edit':'/api/leagues/'+id+'/seasons',body).then(function(j){if(!s)SEL=j.id;load()},function(e){sv.disabled=false;msg('sfm',e.message)})};
    var cn=el('button','btn ghost small','Cancel');cn.onclick=function(){box.innerHTML=''};add(r,sv,cn);
    if(s){var dl=el('button','btn danger small','Delete season');dl.onclick=function(){if(!confirm('Delete '+s.name+'? Its events stay, as one-offs, with their results.'))return;
      api('/api/seasons/'+s.id+'/delete',{}).then(function(){SEL=null;load()},function(e){msg('sfm',e.message)})};r.appendChild(dl)}
    f.appendChild(r);add(f,el('div','msg'));f.lastChild.id='sfm';f.scrollIntoView({behavior:'smooth',block:'nearest'})}

  // ---- drivers: roles (the owner), remove and ban (the owner and admins)
  function members(l){var box=$('members');box.innerHTML='';msg('mm','');
    l.members.forEach(function(m){var it=el('div','item');var d=el('div');var t=el('div','t');t.style.fontSize='17px';
      flag(t,m.country);add(t,m.name+' ');if(m.role!=='member')t.appendChild(el('span','badge '+m.role,m.role));
      add(d,t,el('div','s','joined '+new Date(m.joined).toLocaleDateString()));it.appendChild(d);
      var act=el('div','actions'),me=ME&&ME.steamId===m.steamId;
      if(l.me.owner&&m.role!=='owner'){var rb=el('button','btn ghost small',m.role==='admin'?'Make member':'Make admin');
        rb.title=m.role==='admin'?'No longer an admin':'Admins make events and seasons, remove and ban members, and steward results';
        rb.onclick=function(){api('/api/leagues/'+id+'/role',{steamId:m.steamId,role:m.role==='admin'?'member':'admin'}).then(load,function(e){msg('mm',e.message)})};act.appendChild(rb)}
      if(!me&&(l.me.owner&&m.role!=='owner'||l.me.role==='admin'&&m.role==='member')){
        var rm=el('button','btn ghost small','Remove');rm.onclick=function(){if(!confirm('Remove '+m.name+' from the league? Their results stay; an event they are driving ends for them (DNF). They can join again.'))return;
          api('/api/leagues/'+id+'/remove',{steamId:m.steamId}).then(load,function(e){msg('mm',e.message)})};
        var bn=el('button','btn danger small','Ban');bn.onclick=function(){var why=prompt('Ban '+m.name+': removed, and they can\\'t join again. Why? (they see it if they try to join)','');if(why==null)return;
          api('/api/leagues/'+id+'/remove',{steamId:m.steamId,ban:true,reason:why}).then(load,function(e){msg('mm',e.message)})};
        add(act,rm,bn)}
      it.appendChild(act);box.appendChild(it)});
    var bx=$('bans');bx.innerHTML='';if(!l.bans||!l.bans.length)return;
    add(bx,el('h3',null,'Banned'));l.bans.forEach(function(b){var it=el('div','item');var d=el('div');
      add(d,el('div','t',b.name),el('div','s',(b.reason?b.reason+' · ':'')+'since '+new Date(b.at).toLocaleDateString()));it.appendChild(d);
      var ub=el('button','btn ghost small','Unban');ub.onclick=function(){api('/api/leagues/'+id+'/unban',{steamId:b.steamId}).then(load,function(e){msg('mm',e.message)})};
      it.appendChild(ub);bx.appendChild(it)})}
  account().then(load);
  `);
}

// ------------------------------------------------------------------ /e/:id
export function eventPage(id) {
  return shell('Event · ACR Daily', `
  <img class="banner" id="banner" alt="" hidden>
  <div class="top"><div class="kick" id="kick">Event</div><h1 id="name"></h1>
    <div class="facts" id="facts"></div><div class="chips" id="rules"></div>
    <div class="row" style="margin-top:18px" id="acts"></div><div class="msg" id="am"></div></div>
  <div class="grid" style="margin-top:26px"><div class="card"><h3>How to drive it</h3><ol class="steps" id="how"></ol></div>
    <div class="card"><h3>The rules</h3><ol class="steps" id="rulestext"></ol></div></div>
  <h2>Standings</h2><div class="tablewrap"><table id="st"></table></div>
  <div id="stewards"></div>
  <h2>Itinerary</h2><div class="tablewrap"><table class="itin" id="itin"></table></div>`, `
  var id=${JSON.stringify(id)},E=null;
  var LEVEL={off:'off',light:'light',severe:'severe',realistic:'realistic'};
  function load(){return api('/api/events/'+id).then(render,function(e){$('name').textContent=e.status===404?'No such event':'Event';msg('am',e.message)})}
  function fact(k,v){var d=el('div');add(d,el('span','k',k),el('b',null,v));$('facts').appendChild(d)}
  function render(e){E=e;document.title=e.name+' · ACR Daily';$('name').textContent=e.name;showBanner($('banner'),e.league.banner);
    var k=$('kick');k.innerHTML='';var la=el('a',null,e.league.name);la.href='/l/'+e.league.id;add(k,la,' · '+(e.season?e.season.name:'one-off')+' · '+e.rally+' ');
    k.appendChild(el('span','badge '+e.status,e.status==='open'?'open':e.status==='upcoming'?'upcoming':'finished'));
    $('facts').innerHTML='';
    fact(e.car?'Car':'Car class',e.car||e.carClass+' (pick one)');
    fact('Stages',e.stages.length+' · '+e.days+(e.days===1?' day':' days')+' · '+km(e.lengthM));
    fact(e.status==='upcoming'?'Opens':'Opened',when(e.opens));
    fact(e.status==='closed'?'Closed':'Closes',when(e.closes)+(e.status==='open'?' ('+left(e.closes)+' left)':''));
    var r=$('rules');r.innerHTML='';var R=e.rules;
    [R.damage?'Damage '+LEVEL[R.damageIntensity]:'No damage','Wear '+LEVEL[R.wear],'Failures '+LEVEL[R.failures],R.respawn?'Respawn on':'No respawn','Penalties '+R.penalty,'Time stands still'].forEach(function(x){r.appendChild(el('span','chip',x))});
    if(e.season&&e.season.power&&e.season.power.length)r.appendChild(el('span','chip','Power Stage: SS'+e.stages.length));
    var a=$('acts');a.innerHTML='';
    if(e.me.staff){var ed=el('a','btn ghost small','Edit event');ed.href='/e/'+id+'/edit';
      var cp=el('a','btn ghost small','Copy as the next round');cp.href='/l/'+e.league.id+'/new?from='+id;cp.title='A new event like this one, opening when this one closes';
      var dl=el('button','btn danger small','Delete event');dl.onclick=function(){if(!confirm('Delete '+e.name+' and its results?'))return;
        api('/api/events/'+id+'/delete',{}).then(function(){location.href='/l/'+e.league.id},function(x){msg('am',x.message)})};add(a,ed,cp,dl)}
    if(!e.me.signedIn)a.appendChild(steamBtn());
    else if(!e.me.member){var jl=el('a','btn','Join '+e.league.name+' to take part');jl.href='/l/'+e.league.id;a.appendChild(jl)}
    var how=$('how');how.innerHTML='';
    ['Get <b>ACR Daily</b> (from the home page) and sign in with Steam in it, as for the dailies.',
     'In the app, open <b>LEAGUES</b>: the event shows there while it is open'+(e.car?'.':', with the cars of its class to pick from.'),
     'Press <b>DRIVE</b>: the app closes the game if needed and sets the whole rally up in it (stages, days, service parks, weather, car, settings).',
     'In the game: <b>Racing › Rally › Rally Weekend › Start Rally</b>, tyres, then drive. The app stays open and sends each stage as you finish it.',
     'Stop after any stage and come back later: the game keeps the rally (Rally Weekend › Resume), the app picks up where you are.'].forEach(function(x){var li=el('li');li.innerHTML=x;how.appendChild(li)});
    var rt=$('rulestext');rt.innerHTML='';
    ['One go: your first start is the one that counts.','The stages in order, each once; the game\\'s own stage time + its penalties count.',
     'Retire, restart a stage, start a stage a second time, or drive one without the app running: DNF.','Repair in the service parks; the damage carries over between them.',
     'Finish every stage before the event closes, or it is a DNF.','The league\\'s stewards (its owner and admins) can add time penalties or disqualify, always with a reason shown below.'
    ].concat(e.season?['Season: '+e.season.name+'. '+e.season.about]:[]).forEach(function(x){rt.appendChild(el('li',null,x))});
    standings(e);stewards(e);itin(e)}
  function standings(e){var t=$('st');t.innerHTML='';var n=e.stages.length;
    var h=el('tr');add(h,el('th',null,'Pos'),el('th',null,'Driver'));if(!e.car)h.appendChild(el('th',null,'Car'));
    e.stages.forEach(function(s){var th=el('th','r','SS'+s.no);th.title=s.name;h.appendChild(th)});add(h,el('th','r','Total'),el('th','r','Gap'));t.appendChild(h);
    if(!e.standings.length){var tr=el('tr'),td=el('td','empty',e.status==='upcoming'?'The event has not opened yet.':'Nobody has started yet.');td.colSpan=5+n;tr.appendChild(td);t.appendChild(tr);return}
    var meId=e.me.entry&&e.me.entry.steamId;
    e.standings.forEach(function(r){var tr=el('tr',(r.rank===1?'p1':'')+(r.steamId===meId?' me':''));
      tr.appendChild(el('td','pos',r.rank?String(r.rank):''));var d=el('td','drv');flag(d,r.country);add(d,r.name);tr.appendChild(d);
      if(!e.car)tr.appendChild(el('td','muted',r.car));
      r.stages.forEach(function(s){var td=el('td','r t'+(s&&s.pos===1?' w':''));
        if(s){add(td,ms(s.totalMs));var bits=[];if(s.penaltyMs)bits.push(pen(s.penaltyMs));if(s.pos)bits.push('P'+s.pos);
          if(bits.length)td.appendChild(el('small',s.penaltyMs?'pen':null,bits.join(' · ')));
          if(s.stewardMs)td.appendChild(el('small','st'+(s.stewardMs<0?' back':''),secs(s.stewardMs)+' stewards'));
          td.title='stage time '+ms(s.timeMs)+(s.penaltyMs?' + '+pen(s.penaltyMs)+' game penalty':'')+(s.stewardMs?' '+secs(s.stewardMs)+' from the stewards':'')+
            (s.pos?' · P'+s.pos+' on the stage, P'+s.cumPos+' overall after it':'')}tr.appendChild(td)});
      var tot=el('td','r tot');var gp=el('td','r muted');
      if(r.status==='finished'){tot.textContent=ms(r.totalMs);gp.textContent=gap(r.gapMs)}
      else if(r.status==='dsq'){tot.appendChild(el('span','dnf','DSQ'));gp.textContent=r.reason||''}
      else if(r.status==='dnf'){tot.appendChild(el('span','dnf','DNF'));gp.textContent=r.reason||''}
      else{tot.appendChild(el('span','run','SS'+(r.done+1)+' next'));gp.textContent=r.done?ms(r.totalMs)+' so far':''}
      if(r.stewardMs&&r.status!=='dsq')tot.appendChild(el('small',null,' incl. '+secs(r.stewardMs)+' stewards'));
      add(tr,tot,gp);t.appendChild(tr)})}
  // the stewards' decisions, for everyone; the owner and admins add and take them back
  function stewards(e){var box=$('stewards');box.innerHTML='';var D=e.decisions||[];if(!D.length&&!e.me.staff)return;
    add(box,el('h2',null,'Stewards'));
    if(!D.length)add(box,el('div','empty','No decisions.'));
    D.forEach(function(x){var it=el('div','decision');var d=el('div');
      var tag=x.kind==='dsq'?el('b','bad','DSQ'):el('b',x.ms<0?'good':'bad',secs(x.ms)+(x.stage?' on SS'+x.stage:' on the total'));
      add(d,tag,x.driver+': '+x.reason);add(d,el('div','muted','by '+x.by+(x.at?' · '+when(x.at):'')));it.appendChild(d);
      if(e.me.staff){var rb=el('button','btn ghost small',x.kind==='dsq'?'Reinstate':'Take back');rb.onclick=function(){
        (x.kind==='dsq'?api('/api/events/'+id+'/dsq',{steamId:x.steamId,remove:true}):api('/api/events/'+id+'/penalty',{remove:x.id})).then(load,function(er){msg('swm',er.message)})};it.appendChild(rb)}
      box.appendChild(it)});
    if(!e.me.staff)return;
    if(!e.standings.length){add(box,el('p','note','Penalties can be given once drivers have started.'));return}
    var f=el('div','stewform');
    f.innerHTML='<label><span>Driver</span><select id="pd"></select></label><label><span>On</span><select id="ps"></select></label>'+
      '<label><span>Seconds</span><input type="text" id="pt" placeholder="10 or -5"></label><label><span>Reason (everyone sees it)</span><input type="text" id="pr" maxlength="200" placeholder="e.g. cut at the hairpin after split 2"></label>';
    var bt=el('div','row');var ab=el('button','btn small','Add penalty');var qb=el('button','btn danger small','Disqualify');add(bt,ab,qb);f.appendChild(bt);box.appendChild(f);
    add(box,el('div','msg'));box.lastChild.id='swm';
    e.standings.forEach(function(r){var o=el('option',null,r.name+(r.status==='dsq'?' (DSQ)':''));o.value=r.steamId;$('pd').appendChild(o)});
    var o0=el('option',null,'The total');o0.value='';$('ps').appendChild(o0);
    e.stages.forEach(function(s){var o=el('option',null,'SS'+s.no+' · '+s.name);o.value=String(s.no);$('ps').appendChild(o)});
    ab.onclick=function(){api('/api/events/'+id+'/penalty',{steamId:$('pd').value,stage:$('ps').value,seconds:$('pt').value.replace(',','.'),reason:$('pr').value})
      .then(load,function(er){msg('swm',er.message)})};
    qb.onclick=function(){var nm=$('pd').options[$('pd').selectedIndex].text;if(!confirm('Disqualify '+nm+' from '+e.name+'? The reason is shown to everyone.'))return;
      api('/api/events/'+id+'/dsq',{steamId:$('pd').value,reason:$('pr').value}).then(load,function(er){msg('swm',er.message)})}}
  function itin(e){var t=$('itin');t.innerHTML='';var h=el('tr');add(h,el('th',null,''),el('th',null,'Stage'),el('th','r','Length'),el('th','r','Start'),el('th',null,'Weather'));t.appendChild(h);
    var day=0;e.stages.forEach(function(s){if(s.day!==day){day=s.day;var tr=el('tr','day'),td=el('td',null,'Day '+day);td.colSpan=5;tr.appendChild(td);t.appendChild(tr)}
      if(s.service){var sp=el('tr','sp'),td2=el('td',null,'Service park');td2.colSpan=5;sp.appendChild(td2);t.appendChild(sp)}
      var tr2=el('tr');add(tr2,el('td','pos','SS'+s.no),el('td','drv',s.name+(e.season&&e.season.power&&e.season.power.length&&s.no===e.stages.length?' (Power Stage)':'')),
        el('td','r',km(s.lengthM)),el('td','r',s.time),el('td',null,s.weatherLabel));t.appendChild(tr2)})}
  account().then(load);
  `);
}

// ------------------------------------------------------------------ /l/:id/new, /e/:id/edit: the event builder
export function eventEditPage({ leagueId = null, eventId = null }) {
  return shell(`${eventId ? 'Edit' : 'New'} event · ACR Daily`, `
  <div class="top"><div class="kick" id="kick">New event</div><h1 id="h">${eventId ? 'Edit event' : 'New event'}</h1>
  <p class="note">A Rally Weekend in the game, so it follows its rules: one location, each day opens with a service park,
  more service parks between stages if you want, and the stages of a day in time order. Drivers each get one go
  between the opening and the closing time.</p></div>
  <div class="builder" id="b"><div class="empty">Loading…</div></div>`, `
  var leagueId=${JSON.stringify(leagueId)},eventId=${JSON.stringify(eventId)},CAT=null,EV=null,LG=null,limited=false;
  var FROM=new URLSearchParams(location.search).get('from');
  var S={name:'',rally:'Wales',carMode:'car',car:'',carClass:'',rules:null,opens:null,closes:null,days:[[]],seasonId:''};
  function pad(n){return String(n).padStart(2,'0')}
  function localInput(t){var d=new Date(t);return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())+'T'+pad(d.getHours())+':'+pad(d.getMinutes())}
  function nextName(n){var m=/^(.*?)(\\d+)(\\D*)$/.exec(n);return m?m[1]+(+m[2]+1)+m[3]:n+' 2'}   // "Round 2" -> "Round 3"
  function rally(){return CAT.rallies.filter(function(r){return r.name===S.rally})[0]}
  function stageOf(track){return rally().stages.filter(function(s){return s.track===track})[0]}
  function opt(sel,v,t,cur){var o=el('option',null,t);o.value=v;if(v===cur)o.selected=true;sel.appendChild(o)}
  function newStage(day){var st=rally().stages,used=S.days.reduce(function(a,d){return a.concat(d)},[]).map(function(x){return x.track});
    var free=st.filter(function(s){return used.indexOf(s.track)<0})[0]||st[0];var last=day.length?day[day.length-1].time:'08:00';
    var h=Math.min(22,parseInt(last,10)+(day.length?2:0));return{track:free?free.track:'',time:pad(h)+':'+last.slice(3),weather:'Clear',service:false}}
  function fromEvent(x){S.rally=x.rally;S.carMode=x.car?'car':'class';S.car=x.car||'';S.carClass=x.carClass||'';S.rules=x.rules;
    S.days=[];x.stages.forEach(function(s){while(S.days.length<s.day)S.days.push([]);S.days[s.day-1].push({track:s.track,time:s.time,weather:s.weather,service:s.service})})}
  function start(){Promise.all([api('/api/catalog'),eventId?api('/api/events/'+eventId):null,FROM&&!eventId?api('/api/events/'+FROM):null]).then(function(r){
      CAT=r[0];EV=r[1];var src=r[2];leagueId=EV?EV.league.id:leagueId;
      return api('/api/leagues/'+leagueId).then(function(lg){LG=lg;
        if(!lg.me.staff){fail('Only the league\\'s owner and admins can '+(EV?'edit its events.':'make events.'));return}
        if(EV){$('kick').textContent=lg.name+' · edit';limited=EV.standings.length>0;
          S.name=EV.name;S.opens=EV.opens;S.closes=EV.closes;S.seasonId=EV.seasonId==null?'':String(EV.seasonId);fromEvent(EV)}
        else{$('kick').textContent=lg.name+' · new event';S.rules=Object.assign({},CAT.rules.defaults);
          var ss=lg.seasons;S.seasonId=ss.length?String(ss[ss.length-1].id):'new';
          if(src){fromEvent(src);S.name=nextName(src.name);var len=src.closes-src.opens;S.opens=Math.max(src.closes,Math.ceil(Date.now()/3600000)*3600000);S.closes=S.opens+len;
            S.seasonId=src.seasonId==null?'':String(src.seasonId);$('h').textContent='Next round'}
          else{var now=Date.now();S.opens=Math.ceil(now/3600000)*3600000;S.closes=S.opens+7*86400000;
            S.car=CAT.cars[0].name;S.carClass=CAT.classes[0].cls;S.days=[[newStage([])]];S.days[0][0].service=true}}
        draw()})}).catch(function(e){fail(e.status===401?'Sign in with Steam first.':e.message)})}
  function fail(t){var b=$('b');b.innerHTML='';add(b,el('div','empty',t));if(!ME)b.appendChild(steamBtn())}
  function draw(){var b=$('b');b.innerHTML='';
    var top=el('div','twocol');top.innerHTML='<label><span>Event name</span><input type="text" id="fn" maxlength="60" placeholder="e.g. Round 3: Rally Wales"></label>'+
      '<label><span>Location</span><select id="fr"></select></label>';b.appendChild(top);
    $('fn').value=S.name;$('fn').oninput=function(){S.name=this.value};
    CAT.rallies.forEach(function(r){opt($('fr'),r.name,r.name+(r.surface?' ('+r.surface.toLowerCase()+')':''),S.rally)});
    $('fr').onchange=function(){if(S.days.some(function(d){return d.length})&&!confirm('Changing the location clears the stages. Go on?')){this.value=S.rally;return}
      S.rally=this.value;S.days=[[newStage([])]];S.days[0][0].service=true;draw()};
    if(limited){$('fr').disabled=true}
    var sl=el('label');sl.innerHTML='<span>Season (its championship)</span>';var ss=el('select');
    LG.seasons.forEach(function(s){opt(ss,String(s.id),s.name,S.seasonId)});
    opt(ss,'new',LG.seasons.length?'A new season (WRC points; set it on the league page)':'Season 1 (made now, WRC points; set it on the league page)',S.seasonId);
    opt(ss,'','One-off: no championship',S.seasonId);ss.onchange=function(){S.seasonId=this.value};sl.appendChild(ss);b.appendChild(sl);
    var w=el('div','twocol');w.innerHTML='<label><span>Opens (your time)</span><input type="datetime-local" id="fo"></label><label><span>Closes (your time)</span><input type="datetime-local" id="fc"></label>';b.appendChild(w);
    $('fo').value=localInput(S.opens);$('fc').value=localInput(S.closes);
    $('fo').onchange=function(){S.opens=new Date(this.value).getTime()};$('fc').onchange=function(){S.closes=new Date(this.value).getTime()};
    if(limited){$('fo').disabled=true;add(b,el('p','note','Drivers have started this event: only its name, its season and a later closing time can change.'))}
    if(!limited){
      var cm=el('label');cm.innerHTML='<span>Car</span>';b.appendChild(cm);
      var rd=el('div','radio');rd.innerHTML='<label><input type="radio" name="cm" value="car"><span>One car for everyone</span></label><label><input type="radio" name="cm" value="class"><span>A class: each driver picks a car of it</span></label>';b.appendChild(rd);
      [].forEach.call(document.querySelectorAll('input[name=cm]'),function(x){x.checked=x.value===S.carMode;x.onchange=function(){S.carMode=this.value;draw()}});
      var cs=el('select');cs.style.marginTop='8px';b.appendChild(cs);
      if(S.carMode==='car'){CAT.cars.forEach(function(c){opt(cs,c.name,c.name+' · '+c.cls,S.car)});cs.onchange=function(){S.car=this.value}}
      else{CAT.classes.forEach(function(k){var n=CAT.cars.filter(function(c){return c.cls===k.cls}).map(function(c){return c.name});opt(cs,k.cls,k.cls+' ('+k.group+'): '+n.join(', '),S.carClass)});cs.onchange=function(){S.carClass=this.value}}
      rules(b);days(b)}
    var sv=el('button','btn',eventId?'Save changes':'Create event');sv.style.marginTop='22px';sv.onclick=save;b.appendChild(sv);add(b,el('div','msg'));b.lastChild.id='fm';summary()}
  function sel(label,key,values,names){var l=el('label');add(l,el('span',null,label));var s=el('select');values.forEach(function(v,i){opt(s,v,names?names[i]:v,String(S.rules[key]))});
    s.onchange=function(){S.rules[key]=this.value==='true'?true:this.value==='false'?false:this.value;draw()};l.appendChild(s);return l}
  function rules(b){add(b,el('h3',null,'Settings'));var g=el('div','twocol');
    g.appendChild(sel('Damage','damage',['true','false'],['On (repair it in the service parks)','Off']));
    if(S.rules.damage)g.appendChild(sel('Damage intensity','damageIntensity',['light','severe','realistic']));
    g.appendChild(sel('Wear','wear',CAT.rules.levels));g.appendChild(sel('Mechanical failures','failures',CAT.rules.levels));
    g.appendChild(sel('Manual respawn','respawn',['true','false'],['On','Off (stuck = retire)']));
    g.appendChild(sel('Penalties (cuts, respawns, jump starts...)','penalty',CAT.rules.penalty));b.appendChild(g)}
  function days(b){add(b,el('h3',null,'Itinerary'));var no=0;
    S.days.forEach(function(d,di){var box=el('div','day');var hd=el('div','dayhead');add(hd,el('b',null,'Day '+(di+1)));
      if(S.days.length>1){var x=el('button','btn ghost small','Remove day');x.onclick=function(){S.days.splice(di,1);draw()};hd.appendChild(x)}
      box.appendChild(hd);box.appendChild(el('div','sprow','Service park (the day starts here)'));
      d.forEach(function(s,si){no++;if(si>0&&s.service)box.appendChild(el('div','sprow','Service park'));
        var r=el('div','st');add(r,el('span','no','SS'+no));
        var ss=el('select');rally().stages.forEach(function(x){opt(ss,x.track,x.name+' · '+km(x.lengthM),s.track)});ss.onchange=function(){s.track=this.value;summary()};r.appendChild(ss);
        var ti=el('input');ti.type='time';ti.value=s.time;ti.onchange=function(){s.time=this.value};r.appendChild(ti);
        var ws=el('select','w');CAT.weathers.forEach(function(w){opt(ws,w.id,w.label,s.weather)});ws.onchange=function(){s.weather=this.value};r.appendChild(ws);
        var spl=el('label','sp');if(si>0){var cb=el('input');cb.type='checkbox';cb.checked=!!s.service;cb.onchange=function(){s.service=this.checked;draw()};add(spl,cb,'service park before')}r.appendChild(spl);
        var tools=el('span','tools');
        var up=el('button',null,'↑');up.title='Move up';up.disabled=si===0;up.onclick=function(){d.splice(si-1,0,d.splice(si,1)[0]);fixSp(d);draw()};
        var dn=el('button',null,'↓');dn.title='Move down';dn.disabled=si===d.length-1;dn.onclick=function(){d.splice(si+1,0,d.splice(si,1)[0]);fixSp(d);draw()};
        var rm=el('button',null,'✕');rm.title='Remove';rm.onclick=function(){d.splice(si,1);if(!d.length&&S.days.length>1)S.days.splice(di,1);else if(!d.length)d.push(newStage(d));fixSp(d);draw()};
        add(tools,up,dn,rm);r.appendChild(tools);box.appendChild(r)});
      var as=el('button','btn ghost small','+ Add stage');as.style.marginTop='10px';as.onclick=function(){d.push(newStage(d));draw()};box.appendChild(as);b.appendChild(box)});
    var ad=el('button','btn ghost small','+ Add day');ad.style.marginTop='12px';ad.onclick=function(){var nd=[newStage([])];nd[0].service=true;S.days.push(nd);draw()};
    if(S.days.length>=CAT.limits.days)ad.disabled=true;b.appendChild(ad);add(b,el('div','sum'));b.lastChild.id='sum'}
  function fixSp(d){if(d.length)d[0].service=true}
  function flat(){var out=[];S.days.forEach(function(d,di){d.forEach(function(s,si){out.push({track:s.track,day:di+1,service:si===0?true:!!s.service,weather:s.weather,time:s.time})})});return out}
  function summary(){var s=$('sum');if(!s||limited)return;var st=flat(),m=0;st.forEach(function(x){var g=stageOf(x.track);if(g)m+=g.lengthM});
    s.textContent=st.length+(st.length===1?' stage':' stages')+' · '+S.days.length+(S.days.length===1?' day':' days')+' · '+km(m)+' of stages (limits: '+CAT.limits.stages+' stages, '+CAT.limits.days+' days)'}
  function save(){var b=this;b.disabled=true;var season=S.seasonId===''?null:S.seasonId;
    var body={name:S.name,rally:S.rally,rules:S.rules,stages:flat(),opens:S.opens,closes:S.closes,seasonId:season};
    if(S.carMode==='car')body.car=S.car;else body.carClass=S.carClass;
    if(limited)body={name:S.name,closes:S.closes,seasonId:season};
    api(eventId?'/api/events/'+eventId+'/edit':'/api/leagues/'+leagueId+'/events',body).then(function(j){
      location.href='/e/'+(eventId||j.id)},function(e){b.disabled=false;msg('fm',e.message)})}
  account().then(function(me){if(!me){fail('Sign in with Steam first.');return}start()});
  `);
}
