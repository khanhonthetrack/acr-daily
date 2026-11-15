// /admin: the site's moderation page. The page itself holds nothing: it asks for the admin key (kept in this browser
// tab's sessionStorage only) and calls the admin API with it (src/index.js adminCall: /api/admin/review, drivers,
// message, runs/<id>/clear|reject, driver, ban, team-delete, league-banner). Everything drivers wrote (names, messages,
// reasons) goes in with textContent, never as HTML, and a strict Content-Security-Policy keeps anything else out: a
// page that holds the admin key must not run anyone's script.

import { FAVICON, logoSvg } from './logo.js';

export const ADMIN_CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline' https://fonts.googleapis.com; " +
  "font-src https://fonts.gstatic.com; img-src 'self' https: data:; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'";

export function adminPage() {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<meta name="referrer" content="no-referrer">
<title>ACR Daily Admin</title>
<link rel="icon" href="${FAVICON}">
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#0A0A0B;--panel:#111113;--line:#1F1F23;--line2:#2B2B31;--fg:#F4F4F5;--fg2:#A1A1AA;--fg3:#6B6B74;--acc:#E30613;--good:#30D158;--warn:#FF9F0A}
*{box-sizing:border-box;margin:0}
html{background:var(--bg)}
body{color:var(--fg);font:15px/1.5 Barlow,system-ui,sans-serif;-webkit-font-smoothing:antialiased}
a{color:inherit}
.wrap{max-width:1200px;margin:0 auto;padding:0 24px}
header{border-bottom:1px solid var(--line)}
header .wrap{display:flex;align-items:center;gap:16px;height:70px}
.brandmark{display:block;height:52px;width:auto}
.title{font:700 22px/1 'Barlow Condensed',sans-serif;letter-spacing:.08em;text-transform:uppercase}
.title b{color:var(--acc)}
.out{margin-left:auto}
nav.tabs{display:flex;gap:4px;flex-wrap:wrap;margin:22px 0 4px;border-bottom:1px solid var(--line2)}
nav.tabs button{background:none;border:0;border-bottom:2px solid transparent;color:var(--fg2);font:600 14px/1 'Barlow Condensed',sans-serif;
  letter-spacing:.12em;text-transform:uppercase;padding:12px 14px;cursor:pointer}
nav.tabs button.on{color:var(--fg);border-bottom-color:var(--acc)}
nav.tabs .n{display:inline-block;min-width:18px;margin-left:6px;padding:2px 5px;background:var(--acc);color:#fff;font:700 11px/1 Barlow,sans-serif;letter-spacing:0}
nav.tabs .n[hidden]{display:none}
h2{font:700 22px/1 'Barlow Condensed',sans-serif;text-transform:uppercase;letter-spacing:.02em;margin:24px 0 6px}
.lead{color:var(--fg2);font-size:14px;margin-bottom:12px;max-width:80ch}
.item{border:1px solid var(--line);background:var(--panel);padding:14px 16px;margin-top:10px}
.item .top{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:baseline}
.item .t{font:600 18px/1.2 'Barlow Condensed',sans-serif}
.item .s{color:var(--fg3);font-size:13px}
.item .body{margin-top:10px;padding:10px 12px;background:#0C0C0E;border-left:3px solid var(--line2);white-space:pre-wrap;overflow-wrap:anywhere}
.item .acts{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.chip{font:600 12px/1 Barlow,sans-serif;padding:4px 7px;border:1px solid var(--line2);color:var(--fg2)}
.chip.flag{border-color:var(--warn);color:var(--warn)}.chip.rep{border-color:var(--acc);color:#FF6B6B}
button.b{font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.1em;text-transform:uppercase;padding:9px 12px;border:1px solid var(--line2);
  background:none;color:var(--fg);cursor:pointer}
button.b:hover{border-color:var(--fg2)}button.b:disabled{opacity:.4;cursor:default}
button.b.go{background:var(--good);border-color:var(--good);color:#06210f}
button.b.bad{border-color:var(--acc);color:#FF6B6B}button.b.bad:hover{background:var(--acc);color:#fff}
input{font:15px Barlow,sans-serif;color:var(--fg);background:#0C0C0E;border:1px solid var(--line2);padding:9px 11px;min-width:0}
input:focus{outline:1px solid var(--fg2)}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.empty{color:var(--fg3);padding:18px 0}
.msg{margin-top:10px;min-height:22px;font-size:14px;color:var(--fg2)}.msg.err{color:#FF6B6B}
.av{width:40px;height:40px;border-radius:50%;object-fit:cover;background:#16161a;flex:none}
.drv{display:flex;gap:12px;align-items:center}
.tag{font:700 15px/1 'Barlow Condensed',sans-serif;letter-spacing:.06em}
.badge{font:700 11px/1 Barlow,sans-serif;letter-spacing:.1em;padding:3px 6px;background:var(--acc);color:#fff}
.key{max-width:460px;margin:60px auto;padding:24px;border:1px solid var(--line2);background:var(--panel)}
.key p{color:var(--fg2);font-size:14px;margin:8px 0 14px}
[hidden]{display:none!important}
@media (max-width:700px){.wrap{padding:0 16px}}
</style>
</head>
<body>
<header><div class="wrap"><a href="/">${logoSvg()}</a><div class="title">ACR Daily <b>Admin</b></div>
  <button class="b out" id="signout" hidden>Forget the key</button></div></header>
<main class="wrap">
  <form class="key" id="keyform" hidden>
    <div class="title">Admin key</div>
    <p>The key from the server's ADMIN_KEY secret. It stays in this tab only (gone when you close it) and goes nowhere but this site's admin API.</p>
    <div class="row"><input type="password" id="key" autocomplete="off" placeholder="Admin key" style="flex:1"><button class="b go" type="submit">Open</button></div>
    <div class="msg err" id="keymsg"></div>
  </form>
  <div id="app" hidden>
    <nav class="tabs" id="tabs"></nav>
    <div class="msg" id="m"></div>
    <section id="p-runs"></section>
    <section id="p-messages" hidden></section>
    <section id="p-drivers" hidden></section>
    <section id="p-teams" hidden></section>
    <section id="p-banned" hidden></section>
    <section id="p-liveries" hidden></section>
  </div>
</main>
<script>
(function(){
var KEY=null,R=null,TAB='runs';
try{KEY=sessionStorage.getItem('acr-admin-key')}catch(e){}
function $(i){return document.getElementById(i)}
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=String(text);return e}
function add(p){for(var i=1;i<arguments.length;i++){var c=arguments[i];if(c==null)continue;p.appendChild(typeof c==='string'?document.createTextNode(c):c)}return p}
function when(t){return t?new Date(t).toLocaleString(undefined,{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}):''}
function ms(t){if(t==null)return '–';var m=Math.floor(t/60000),s=(t%60000)/1000;return m+':'+(s<10?'0':'')+s.toFixed(3)}
function link(text,href){var a=el('a',null,text);a.href=href;a.target='_blank';a.rel='noopener';return a}
function drv(p){return p&&p.steamId?link(p.name||p.steamId,'/d/'+encodeURIComponent(p.steamId)):el('span',null,'(nobody)')}
function say(t,bad){var m=$('m');m.textContent=t||'';m.className='msg'+(bad?' err':'')}
function api(path,body){
  return fetch(path,{method:body?'POST':'GET',headers:Object.assign({'Authorization':'Bearer '+KEY},body?{'Content-Type':'application/json'}:{}),
    body:body?JSON.stringify(body):undefined}).then(function(r){return r.json().catch(function(){return {}}).then(function(j){
      if(r.status===403){forget('That key was refused.');throw new Error('refused')}
      if(!r.ok)throw new Error(j.error||('error '+r.status));return j})})}
function act(btn,path,body,done){btn.disabled=true;say('');return api(path,body).then(function(j){say(done||'Done.');load();return j},
  function(e){btn.disabled=false;say(e.message,true)})}
function button(text,cls,fn){var b=el('button','b'+(cls?' '+cls:''),text);b.type='button';b.onclick=function(){fn(b)};return b}
function forget(why){KEY=null;try{sessionStorage.removeItem('acr-admin-key')}catch(e){}$('app').hidden=true;$('signout').hidden=true;$('keyform').hidden=false;$('keymsg').textContent=why||''}
$('keyform').onsubmit=function(ev){ev.preventDefault();var k=$('key').value.trim();if(k.length<24){$('keymsg').textContent='The key is at least 24 characters.';return}
  KEY=k;$('key').value='';try{sessionStorage.setItem('acr-admin-key',k)}catch(e){}start()};
$('signout').onclick=function(){forget('')};

var TABS=[['runs','Reported runs'],['messages','Reported messages'],['liveries','Liveries'],['drivers','Drivers'],['teams','Teams'],['banned','Banned']],LV=null;
function tabs(){var n=$('tabs');n.innerHTML='';TABS.forEach(function(t){var b=el('button',t[0]===TAB?'on':null,t[1]);b.type='button';
  var c=t[0]==='runs'?R&&R.runs.length:t[0]==='messages'?R&&R.messages.length:t[0]==='liveries'?LV&&LV.pending.length+LV.flagged.length:0;var s=el('span','n',c||'');s.hidden=!c;b.appendChild(s);
  b.onclick=function(){TAB=t[0];show()};n.appendChild(b)})}
function show(){tabs();TABS.forEach(function(t){$('p-'+t[0]).hidden=t[0]!==TAB})}
function start(){$('keyform').hidden=true;$('app').hidden=false;$('signout').hidden=false;drivers();load()}
function load(){return api('/api/admin/review').then(function(r){R=r;runs();messages();teams();banned();show();return loadLiveries()},function(e){if(e.message!=='refused')say(e.message,true)})}
function loadLiveries(){return Promise.all([api('/api/admin/liveries?status=pending'),api('/api/admin/liveries?status=flagged'),api('/api/admin/liveries?status=published')])
  .then(function(x){LV={pending:x[0].liveries,flagged:x[1].liveries,published:x[2].liveries};liveries();show()},function(e){if(e.message!=='refused')say(e.message,true)})}

// ---- runs drivers reported: clear (fine) or reject
function runs(){var p=$('p-runs');p.innerHTML='';add(p,el('h2',null,'Reported runs'),
  el('p','lead','Finished runs of the last 30 days that drivers reported. A report changes nothing by itself. Clear: it is fine (the reports go). Reject: off the timing sheet (its free-daily bonus goes back).'));
  if(!R.runs.length){p.appendChild(el('div','empty','No reported runs.'));return}
  R.runs.forEach(function(r){var it=el('div','item'),top=el('div','top');
    add(top,el('span','t',r.date+' · SS'+r.slot),drv({steamId:r.steamId,name:r.name}),el('span','s',r.track+' · '+r.car),el('span','t',ms(r.totalMs)),link('Run '+r.id+' ›','/run/'+r.id));it.appendChild(top);
    var ch=el('div','chips');r.flags.forEach(function(f){ch.appendChild(el('span','chip flag',typeof f==='string'?f:JSON.stringify(f)))});
    r.reports.forEach(function(x){ch.appendChild(el('span','chip rep','Report'+(x.reason?': '+x.reason:'')+' · '+when(x.at)))});it.appendChild(ch);
    var a=el('div','acts');add(a,button('Clear: it is fine','go',function(b){act(b,'/api/admin/runs/'+r.id+'/clear',{},'Run '+r.id+' cleared.')}),
      button('Reject','bad',function(b){var why=prompt('Why is run '+r.id+' rejected? (the driver sees it)','rejected by admin');if(why==null)return;
        act(b,'/api/admin/runs/'+r.id+'/reject',{reason:why},'Run '+r.id+' rejected.')}));it.appendChild(a);p.appendChild(it)})}

// ---- reported private messages: dismiss the report, delete the message, ban its sender
function messages(){var p=$('p-messages');p.innerHTML='';add(p,el('h2',null,'Reported messages'),el('p','lead','Messages a driver reported. Dismiss: the report goes, the message stays. Delete: the message goes too. Ban: its sender can\\'t drive or post any more (undo under Banned).'));
  if(!R.messages.length){p.appendChild(el('div','empty','No reports.'));return}
  R.messages.forEach(function(m){var it=el('div','item'),top=el('div','top');
    add(top,el('span','s','From'),drv(m.from),m.from.banned?el('span','badge','BANNED'):null,el('span','s','to'),drv(m.to),el('span','s','sent '+when(m.sent)));it.appendChild(top);
    it.appendChild(el('div','body',m.gone?'(the message is gone)':m.body));
    var r=el('div','top');r.style.marginTop='8px';add(r,el('span','s','Reported by'),drv(m.by),el('span','s',when(m.reported)+(m.reason?' · "'+m.reason+'"':'')));it.appendChild(r);
    var a=el('div','acts');add(a,button('Dismiss','',function(b){act(b,'/api/admin/message',{id:m.id,action:'dismiss'},'Report dismissed.')}),
      m.gone?null:button('Delete the message','bad',function(b){if(confirm('Delete this message?'))act(b,'/api/admin/message',{id:m.id,action:'delete'},'Message deleted.')}),
      m.from.steamId&&!m.from.banned?button('Ban '+(m.from.name||'the sender'),'bad',function(b){if(confirm('Ban '+(m.from.name||m.from.steamId)+'?'))act(b,'/api/admin/ban',{steamId:m.from.steamId,banned:true},'Banned.')}):null);
    it.appendChild(a);p.appendChild(it)})}

// ---- drivers: find one, put their name or picture back to Steam's, ban or unban
var LAST='';
function drivers(){var p=$('p-drivers');p.innerHTML='';add(p,el('h2',null,'Drivers'),el('p','lead','Find a driver by their name (as shown, or Steam\\'s) or Steam id. Reset name / picture: back to Steam\\'s (a name reset counts as their weekly change). Make organizer: a Community organizer, who can create championships (anyone can create a rally).'));
  var f=el('form','row'),q=el('input');q.placeholder='Name or Steam id';q.style.flex='1';q.style.maxWidth='420px';var go=el('button','b go','Find');go.type='submit';add(f,q,go);p.appendChild(f);
  var out=el('div');out.id='found';p.appendChild(out);
  f.onsubmit=function(ev){ev.preventDefault();LAST=q.value.trim();find()}}
function find(){var out=$('found');if(!LAST)return;out.innerHTML='';
  api('/api/admin/drivers?q='+encodeURIComponent(LAST)).then(function(r){
    if(!r.drivers.length){out.appendChild(el('div','empty','Nobody found.'));return}
    r.drivers.forEach(function(d){var it=el('div','item'),top=el('div','drv');var img=el('img','av');img.alt='';if(d.avatar)img.src=d.avatar;top.appendChild(img);
      var info=el('div');var l1=el('div','top');if(d.team){var tg=el('span','tag','['+d.team.tag+']');l1.appendChild(tg)}add(l1,drv(d),d.banned?el('span','badge','BANNED'):null,d.organizer?el('span','badge','COMMUNITY ORGANIZER'):null);
      add(info,l1,el('div','s','Steam: '+(d.steamName||'?')+(d.customName?' · own name: '+d.customName:'')+(d.ownAvatar?' · own picture':'')+' · '+d.steamId+(d.team?' · team '+d.team.name:'')));
      top.appendChild(info);it.appendChild(top);
      var a=el('div','acts');
      // a Community organizer makes championships (anyone makes rallies); the rank is the admin's to give
      add(a,button(d.organizer?'Not an organizer':'Make organizer',d.organizer?'':'go',function(b){act(b,'/api/admin/organizer',{steamId:d.steamId,on:!d.organizer},
        d.organizer?'No longer a Community organizer.':'Now a Community organizer.').then(find)}));
      add(a,d.customName?button('Reset name','',function(b){if(confirm('Put '+d.name+'\\'s name back to their Steam name?'))act(b,'/api/admin/driver',{steamId:d.steamId,name:true,avatar:false},'Name reset.').then(find)}):null,
        d.ownAvatar?button('Reset picture','',function(b){if(confirm('Put '+d.name+'\\'s picture back to their Steam picture?'))act(b,'/api/admin/driver',{steamId:d.steamId,name:false,avatar:true},'Picture reset.').then(find)}):null,
        d.banned?button('Unban','go',function(b){act(b,'/api/admin/ban',{steamId:d.steamId,banned:false},'Unbanned.').then(find)})
          :button('Ban','bad',function(b){if(confirm('Ban '+d.name+'? They can\\'t drive, post or join anything.'))act(b,'/api/admin/ban',{steamId:d.steamId,banned:true},'Banned.').then(find)}));
      it.appendChild(a);out.appendChild(it)})},function(e){say(e.message,true)})}

// ---- teams: close one (an offensive name or tag)
function teams(){var p=$('p-teams');p.innerHTML='';add(p,el('h2',null,'Teams'),el('p','lead','All teams, newest first. Close: the team goes, its drivers are teamless (for an offensive name or tag).'));
  if(!R.teams.length){p.appendChild(el('div','empty','No teams yet.'));return}
  R.teams.forEach(function(t){var it=el('div','item'),top=el('div','top');var tg=el('span','tag','['+t.tag+']');tg.style.color=t.color;
    add(top,tg,link(t.name,'/t/'+encodeURIComponent(t.id)),el('span','s',t.members+(t.members===1?' driver':' drivers')+' · captain'),drv(t.captain),el('span','s','since '+when(t.created)));
    it.appendChild(top);var a=el('div','acts');a.appendChild(button('Close the team','bad',function(b){if(confirm('Close '+t.name+' ['+t.tag+']? Its '+t.members+' drivers become teamless.'))act(b,'/api/admin/team-delete',{team:t.id},'Team closed.')}));
    it.appendChild(a);p.appendChild(it)})}

// ---- banned drivers, and a league banner to take down
function banned(){var p=$('p-banned');p.innerHTML='';add(p,el('h2',null,'Banned drivers'));
  if(!R.banned.length)p.appendChild(el('div','empty','Nobody is banned.'));
  R.banned.forEach(function(d){var it=el('div','item'),top=el('div','top');add(top,drv(d),el('span','s','Steam: '+(d.steamName||'?')+' · '+d.steamId));it.appendChild(top);
    var a=el('div','acts');a.appendChild(button('Unban','go',function(b){act(b,'/api/admin/ban',{steamId:d.steamId,banned:false},'Unbanned.')}));it.appendChild(a);p.appendChild(it)});
  add(p,el('h2',null,'A league banner'),el('p','lead','Take down a league\\'s (or a cup\\'s) banner by its id, the 8 characters in /l/<id>; its owner can set another.'));
  var f=el('form','row'),q=el('input');q.placeholder='League id';q.maxLength=8;var go=el('button','b bad','Take it down');go.type='submit';add(f,q,go);p.appendChild(f);
  f.onsubmit=function(ev){ev.preventDefault();var id=q.value.trim();if(!/^[a-z0-9]{8}$/.test(id)){say('A league id is 8 letters or digits.',true);return}
    if(confirm('Take down the banner of '+id+'?'))act(go,'/api/admin/league-banner',{league:id},'Banner taken down.').then(function(){q.value='';go.disabled=false})}}

// ---- liveries drivers sent (src/liveries.js): publish or turn down; a published one's link reported as not working
// (mend it, it is fine, take it off). The preview comes with the key, shown as a data: address (no blob: in the CSP).
function shot(img,path){fetch(path,{headers:{'Authorization':'Bearer '+KEY}}).then(function(r){return r.ok?r.blob():null}).then(function(b){
  if(!b)return;var fr=new FileReader();fr.onload=function(){img.src=fr.result};fr.readAsDataURL(b)},function(){})}
function livery(l,kind){var it=el('div','item'),top=el('div','top');
  add(top,el('span','t',l.title),el('span','s',l.carName+' · by '+l.author+' · sent by'),drv(l.by),el('span','s',when(l.created)),
    l.status!=='pending'?el('span','s',l.votes+' votes · '+l.stars+' stars · '+l.clicks+' downloads'):null);it.appendChild(top);
  var img=el('img');img.alt='';img.style.cssText='display:block;margin-top:10px;max-width:480px;width:100%;aspect-ratio:16/9;object-fit:cover;background:#0C0C0E';
  shot(img,l.shot);it.appendChild(img);
  if(l.description)it.appendChild(el('div','body',l.description));
  var ch=el('div','chips');
  if(l.link){var a=link(l.link,l.link);a.rel='noopener noreferrer nofollow';var c=el('span','chip');c.appendChild(a);ch.appendChild(c);
    ch.appendChild(el('span','chip',l.direct?'the app installs it (the zip itself)':'a page: opens in the browser'))}
  else ch.appendChild(el('span','chip','no link: shown only'));
  if(l.flags)ch.appendChild(el('span','chip rep',l.flags+(l.flags===1?' driver says':' drivers say')+' the link is not working'));
  it.appendChild(ch);
  var p='/api/admin/liveries/'+l.id,acts=el('div','acts');
  if(kind==='pending')add(acts,button('Publish','go',function(b){act(b,p,{action:'publish'},l.title+' published.')}),
    button('Turn down','bad',function(b){var why=prompt('Why is '+l.title+' not published? (the sender sees it)','');if(why==null)return;
      act(b,p,{action:'reject',note:why},l.title+' turned down.')}));
  else add(acts,kind==='flagged'?button('The link is fine','go',function(b){act(b,p,{action:'clear'},'Reports cleared.')}):null,
    button('Mend the link','',function(b){var u=prompt('The new link (https://...)',l.link||'');if(u==null)return;act(b,p,{action:'clear',link:u},'Link changed.')}),
    button('Take it off','bad',function(b){var why=prompt('Why is '+l.title+' taken off? (the sender sees it)','');if(why==null)return;
      act(b,p,{action:'hide',note:why},l.title+' taken off.')}));
  acts.appendChild(button('Delete','bad',function(b){if(confirm('Delete '+l.title+' for good (its votes and downloads too)?'))act(b,p,{action:'delete'},'Deleted.')}));
  it.appendChild(acts);return it}
function liveries(){var p=$('p-liveries');p.innerHTML='';
  add(p,el('h2',null,'Liveries to publish'),el('p','lead','Liveries drivers sent (/liveries). Publish: it shows on the page and in the app, the sender is told. Turn down: the sender sees why. Look at the link before publishing: the app downloads the zip itself where the link gives it.'));
  if(!LV.pending.length)p.appendChild(el('div','empty','Nothing waiting.'));
  LV.pending.forEach(function(l){p.appendChild(livery(l,'pending'))});
  add(p,el('h2',null,'Links reported as not working'));
  if(!LV.flagged.length)p.appendChild(el('div','empty','None.'));
  LV.flagged.forEach(function(l){p.appendChild(livery(l,'flagged'))});
  add(p,el('h2',null,'Published'));
  if(!LV.published.length)p.appendChild(el('div','empty','None yet.'));
  LV.published.forEach(function(l){p.appendChild(livery(l,'published'))})}

if(KEY)start();else forget('');
})();
</script>
</body>
</html>`;
}
