// The website's header, the same on every page: the home page (src/site.js), every page of the shell
// (src/leaguepages.js shell()), the guide (src/guidepage.js) and a daily's statistics (src/statspage.js).
//
// The logo, then the parts of the game as the app names them (client tabsui.py NAV): DAILIES, TIME TRIAL, COMPETITIONS
// and COMMUNITY, the last two drop-downs: COMPETITIONS holds Rallies, 1V1 and Cups (the app's COMPETITIONS tab),
// COMMUNITY holds Ranking, Teams, Liveries and Discord. Each is grey; the part this page is in is underlined in its
// colour (the game's modes' colours, as in the app), each item of a drop-down has its colour as a bar. On the right:
// how to play (in words while signed out, a ? signed in), the inbox and the credits (signed in), the language and
// SIGN IN (signed out) or the driver's menu (their picture: driver page, credits and shop, language, sign out), then
// Get the app. A narrow window, or a row too wide for it (HEADER_FIT, src/i18n.js): one shorter row, the parts in a
// menu under ☰. With the page's CSS: HEADER_CSS; LANG_CSS (src/i18n.js) for the language.
//
// The page's script tells it who is signed in (headerMe(me): /api/me's answer, null signed out), or siteHeader(env,
// { me: true }) fetches /api/me itself (a page with no sign-in of its own). Globals for the pages: headerMe(me),
// unread(n) (the inbox's count) and navOn(key) (the part a page is in, when the address alone can't tell: an event's
// page is a 1V1's or a cup's).
import { coinSvg, envelopeSvg, logoSvg } from './logo.js';
import { downloadUrl, hasDiscord } from './release.js';
import { HEADER_FIT, langPicker, t, tq } from './i18n.js';

const esc = (x) => String(x).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const CARET = '<svg class="hcaret" viewBox="0 0 10 6" aria-hidden="true"><path d="M1 1l4 4 4-4"/></svg>';
const EXT = '<svg class="hext" viewBox="0 0 12 12" aria-hidden="true"><path d="M4 2h6v6M10 2 3 9"/></svg>';
const HELP = '<svg class="hic" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9.5"/><path d="M9.3 9.2a2.8 2.8 0 0 1 5.4 1c0 1.9-2.7 2.5-2.7 4"/><path d="M12 17.3h.01"/></svg>';
const BURGER = '<svg class="hic" viewBox="0 0 24 24" aria-hidden="true"><path d="M3.5 6.5h17M3.5 12h17M3.5 17.5h17"/></svg>';

// the parts' colours: the game's modes (client tabsui.py TABS, NAV_COLOUR); COMMUNITY's green; Ranking red, Teams turquoise
const C = { daily: '#F4F4F5', tt: '#BF5AF2', leagues: '#5BA8FF', '1v1': '#FF9F43', cups: '#FFD60A', comm: '#30D158',
  liveries: '#30D158', ranking: '#FF453A', teams: '#40E0D0', discord: '#8C9EFF' };

/** The header's HTML (with HEADER_FIT and its script after it). opts.me: fetch /api/me here (the page doesn't). */
export function siteHeader(env = {}, opts = {}) {
  const download = downloadUrl(env);
  const item = (k, href, name, about, colour, ext) => `<a href="${href}" data-k="${k}" style="--m:${colour}"` +
    (ext ? ' target="_blank" rel="noopener"' : '') + `><i></i><span><b>${name}${ext ? EXT : ''}</b><small>${about}</small></span></a>`;
  const group = (k, name, colour, items) => `<div class="grp" data-g="${k}" style="--m:${colour}"><button class="l" type="button" ` +
    `aria-expanded="false" aria-haspopup="true">${name}${CARET}</button><div class="dd">${items.join('')}</div></div>`;
  return `<header class="site"><div class="wrap">
<a class="brand" href="/" aria-label="ACR Daily">${logoSvg()}<b class="beta" title="${t('ACR Daily is in beta: things may change and bugs are expected. Report them at acrdaily.com/report.')}">${t('BETA')}</b></a>
<nav class="hnav" id="hnav" aria-label="ACR Daily">
<a class="l" href="/" data-k="daily" style="--m:${C.daily}">${t('Dailies')}</a>
<a class="l" href="/tt" data-k="tt" style="--m:${C.tt}">${t('Time trial')}</a>
${group('comp', t('Competitions'), C.leagues, [
    item('leagues', '/rallies', t('Rallies'), t('Rallies anyone made, and championships'), C.leagues),
    item('1v1', '/1v1', '1V1', t('Challenge a driver, stake credits'), C['1v1']),
    item('cups', '/cups', t('Cups'), t('Knockouts of 1V1s'), C.cups),
    // the next ranked sessions and how many are registered (the user, 22 Nov 2026): filled in when the drop-down is
    // first opened (rankedSoon: /api/liverallies), not on every page view
    '<div class="rk" id="hrk" hidden></div>'])}
${group('comm', t('Community'), C.comm, [
    item('ranking', '/ranking', t('Ranking'), t('Driver rating and world rank'), C.ranking),
    item('teams', '/teams', t('Teams'), t('Teams and their drivers'), C.teams),
    item('liveries', '/liveries', t('Liveries'), t('Painted by the drivers, ready for your car'), C.liveries),
    hasDiscord(env) ? item('discord', '/discord', 'Discord', t('Chat, ideas and live timing'), C.discord, true) : ''])}
</nav>
<div class="hside">
<a class="hi help" href="/guide" data-k="guide" title="${t('How to play')}" aria-label="${t('How to play')}">${HELP}<span class="tx">${t('How to play')}</span></a>
<a class="hi ib" id="nav-inbox" href="/inbox" data-k="inbox" title="${t('Inbox')}" aria-label="${t('Inbox')}" hidden>${envelopeSvg()}<b class="unread" id="unread" hidden></b></a>
<span id="crhost"></span>
<span class="acct" id="acct">${langPicker()}</span>
${download ? `<a class="dl" href="${esc(download)}">${t('Get the app')}</a>` : ''}
<button class="hburger" type="button" aria-label="${t('Menu')}" aria-expanded="false" aria-controls="hnav">${BURGER}</button>
</div></div></header>
${HEADER_FIT}
${BMC_WIDGET}
<script>${HEADER_JS()}${opts.me ? `
fetch('/api/me',{credentials:'same-origin',cache:'no-store'}).then(function(r){return r.ok?r.json():null}).then(headerMe,function(){headerMe(null)});` : ''}</script>`;
}

// Buy Me a Coffee's own floating button, bottom right of every page with the header (the user, 23 Nov 2026)
const BMC_WIDGET = '<script data-name="BMC-Widget" data-cfasync="false" src="https://cdnjs.buymeacoffee.com/1.0.0/widget.prod.min.js" ' +
  'data-id="acrdaily" data-description="Support me on Buy me a coffee!" data-message="" data-color="#FF813F" ' +
  'data-position="Right" data-x_margin="18" data-y_margin="18"></script>';

// the header's script: the drop-downs, ☰, the part this page is in, who is signed in
const HEADER_JS = () => `
var COIN_H=${JSON.stringify(coinSvg())};
function navOn(k){var h=document.querySelector('header.site');if(!h)return;
  [].forEach.call(h.querySelectorAll('.on'),function(e){e.classList.remove('on');e.removeAttribute('aria-current')});
  var a=k&&h.querySelector('[data-k="'+k+'"]');if(!a)return;a.classList.add('on');a.setAttribute('aria-current','page');
  var g=a.closest('.grp');if(g){var b=g.querySelector('.l');b.classList.add('on');b.style.setProperty('--m',a.style.getPropertyValue('--m'))}}
function unread(n){var u=document.getElementById('unread');if(!u)return;u.textContent=n>99?'99+':String(n||0);u.hidden=!n;
  u.parentNode.classList.toggle('new',!!n);u.parentNode.title=n?${tq('Inbox: {0} new')}.replace('{0}',n):${tq('Inbox')}}
var headerMe=(function(){var h=document.querySelector('header.site'),LP=h&&h.querySelector('.langpick');
  function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
  function initials(n){var w=String(n||'').replace(/_/g,' ').split(/\\s+/).filter(Boolean);return (w.length>1?w[0][0]+w[1][0]:(w[0]||'?').slice(0,2)).toUpperCase()}
  function pic(me,cls){var a=el('span','av'+(cls?' '+cls:''));if(me.avatar){var i=el('img');i.src=me.avatar;i.alt='';a.appendChild(i)}else a.textContent=initials(me.name);return a}
  function close(keep){[].forEach.call(h.querySelectorAll('.grp.open'),function(g){if(g===keep)return;g.classList.remove('open');
    var b=g.querySelector('[aria-expanded]');if(b)b.setAttribute('aria-expanded','false')})}
  // the mouse gone from a drop-down (a mouse's, not ☰'s): shut, unless its language list is open (focus on the select)
  function hoverOff(g){g.addEventListener('focusin',function(e){if(e.target.tagName==='SELECT')g.classList.add('open')});
    g.addEventListener('mouseleave',function(){var f=document.activeElement;if(!matchMedia('(hover:hover)').matches||h.classList.contains('two')&&!g.classList.contains('me')||
      f&&f.tagName==='SELECT'&&g.contains(f))return;g.classList.remove('open');var b=g.querySelector('[aria-expanded]');if(b)b.setAttribute('aria-expanded','false')})}
  function menu(on){h.classList.toggle('open',on);var b=h.querySelector('.hburger');if(b)b.setAttribute('aria-expanded',on?'true':'false')}
  if(h){
    h.addEventListener('click',function(e){var b=e.target.closest('.grp>button');
      if(b){var g=b.parentNode,on=!g.classList.contains('open');close(g);g.classList.toggle('open',on);b.setAttribute('aria-expanded',on?'true':'false');return}
      if(e.target.closest('.hburger')){close();menu(!h.classList.contains('open'))}});
    document.addEventListener('click',function(e){if(!h.contains(e.target)){close();menu(false)}});
    document.addEventListener('keydown',function(e){if(e.key!=='Escape')return;var g=h.querySelector('.grp.open');close();menu(false);
      if(g){var b=g.querySelector('button');if(b)b.focus()}});
    h.addEventListener('focusout',function(e){if(e.relatedTarget&&!h.contains(e.relatedTarget)){close();menu(false)}});
    [].forEach.call(h.querySelectorAll('.grp'),hoverOff);
    // COMPETITIONS: the next 4 ranked sessions, their series, rally and drivers registered (once, as it is first opened)
    var rk=document.getElementById('hrk'),rkDone=false;
    function rankedSoon(){if(rkDone||!rk)return;rkDone=true;
      fetch('/api/liverallies',{cache:'no-store'}).then(function(r){return r.ok?r.json():null}).then(function(j){
        if(!j||!j.on||!j.sessions)return;var names={};(j.series||[]).forEach(function(s){names[s.key]=s.name});
        var now=Date.now(),list=j.sessions.filter(function(s){return s.phase!=='over'&&s.closes>now}).sort(function(a,b){return a.starts-b.starts}).slice(0,4);
        if(!list.length)return;rk.appendChild(el('div','rkh',${tq('Ranked · next sessions')}));
        list.forEach(function(s){var a=el('a');a.href='/guide#ranked';a.style.setProperty('--m','#FF453A');a.appendChild(el('i'));
          var w=el('span'),at=new Date(s.starts).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});
          w.appendChild(el('b',null,at+' · '+(names[s.series]||s.series)));
          var st=s.phase==='signup'?${tq('registration open')}:s.phase==='running'?${tq('under way')}:'';
          w.appendChild(el('small',null,[s.rally,${tq('{0} registered')}.replace('{0}',s.signups||0),st].filter(Boolean).join(' · ')));
          a.appendChild(w);rk.appendChild(a)});rk.hidden=false},function(){})}
    var cg=h.querySelector('.grp[data-g="comp"]');
    if(cg){cg.addEventListener('mouseenter',rankedSoon);cg.addEventListener('click',rankedSoon)}
    var hb=h.querySelector('.hburger');if(hb)hb.addEventListener('click',rankedSoon);
    // the part this page is in, from its address (a page can say otherwise: navOn)
    var p=location.pathname;
    navOn(p==='/'||/^\\/stage\\//.test(p)?'daily':/^\\/tt$/.test(p)?'tt':/^\\/(leagues|rallies|l\\/|e\\/|join\\/)/.test(p)?'leagues':
      /^\\/1v1/.test(p)?'1v1':/^\\/cups?(\\/|$)/.test(p)?'cups':/^\\/liveries/.test(p)?'liveries':/^\\/(ranking|d\\/)/.test(p)?'ranking':
      /^\\/(teams|t\\/)/.test(p)?'teams':/^\\/inbox/.test(p)?'inbox':/^\\/guide/.test(p)?'guide':'')}
  // me: /api/me's answer (signed out: null or {signedIn: false})
  return function(me){var a=document.getElementById('acct');if(!h||!a)return;var inn=!!(me&&me.signedIn);
    h.classList.toggle('in',inn);a.innerHTML='';
    var ib=document.getElementById('nav-inbox'),cr=document.getElementById('crhost');if(ib)ib.hidden=!inn;if(cr)cr.innerHTML='';
    if(!inn){if(LP)a.appendChild(LP);var s=el('a','signin',${tq('Sign in')});
      s.href='/login?next='+encodeURIComponent(location.pathname+location.search);a.appendChild(s);return}
    if(me.credits&&cr){var c=el('a','crchip',String(me.credits.balance));c.id='crchip';c.href='/credits';c.title=${tq('Your credits')};
      c.insertAdjacentHTML('beforeend',COIN_H);cr.appendChild(c)}
    var g=el('div','grp me'),b=el('button','hav');b.type='button';b.setAttribute('aria-haspopup','true');b.setAttribute('aria-expanded','false');
    b.setAttribute('aria-label',${tq('Account')});b.title=me.name||'';b.appendChild(pic(me));b.insertAdjacentHTML('beforeend',${JSON.stringify(CARET)});
    var d=el('div','dd right'),who=el('a','who');who.href='/d/'+encodeURIComponent(me.steamId);who.appendChild(pic(me,'big'));
    var w=el('span');w.appendChild(el('b',null,me.name||''));w.appendChild(el('small',null,${tq('Your driver page')}));who.appendChild(w);d.appendChild(who);
    if(me.credits){var cs=el('a');cs.href='/credits';cs.appendChild(el('b',null,${tq('Credits and shop')}));d.appendChild(cs)}
    if(LP){var lr=el('div','lrow');lr.appendChild(el('b',null,${tq('Language')}));lr.appendChild(LP);d.appendChild(lr)}
    var f=el('form');f.method='post';f.action='/logout?next='+encodeURIComponent(location.pathname);var o=el('button','out',${tq('sign out')});o.type='submit';
    f.appendChild(o);d.appendChild(f);g.appendChild(b);g.appendChild(d);a.appendChild(g);
    hoverOff(g);
    fetch('/api/inbox/unread',{credentials:'same-origin',cache:'no-store'}).then(function(r){return r.ok?r.json():null}).then(function(j){if(j)unread(j.unread)},function(){})}})();
`;

/** The header's look (scoped to header.site: the pages keep their own .brand, .dl, .unread...). */
export const HEADER_CSS = `
header.site{position:relative;z-index:40;border-bottom:1px solid var(--line,#1F1F23);background:var(--bg,#0A0A0B)}
header.site [hidden]{display:none!important}
header.site .wrap{display:flex;align-items:center;gap:20px;height:76px;padding-top:0;padding-bottom:0}
header.site:not(.two) .wrap>*,header.site:not(.two) .hnav>*,header.site:not(.two) .hside>*{flex-shrink:0}
header.site .brand{display:flex;align-items:center;text-decoration:none}
header.site .brandmark{display:block;height:60px;width:auto}
header.site .beta{margin-left:10px;padding:2px 6px;border:1px solid #E30613;border-radius:3px;color:#FF4655;font:700 12px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em}
.hnav{display:flex;align-self:stretch;gap:2px;margin-left:10px}
.hnav .l{display:flex;align-items:center;gap:7px;padding:0 12px;margin:0;background:none;border:0;border-top:3px solid transparent;border-bottom:3px solid transparent;
  color:var(--fg2,#A1A1AA);font:600 14px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;text-transform:uppercase;text-decoration:none;white-space:nowrap;cursor:pointer}
.hnav .l:hover,.hnav .grp.open>.l{color:var(--fg,#F4F4F5)}
.hnav .l.on{color:var(--fg,#F4F4F5);border-bottom-color:var(--m)}
header.site .hcaret{width:9px;height:6px;fill:none;stroke:currentColor;stroke-width:1.6;opacity:.7;transition:transform .15s}
header.site .grp.open>button .hcaret{transform:rotate(180deg)}
header.site .grp{position:relative;display:flex;align-self:stretch}
header.site .dd{display:none;position:absolute;top:100%;left:0;z-index:50;min-width:290px;padding:6px;background:#111113;border:1px solid var(--line2,#2B2B31);box-shadow:0 18px 40px rgba(0,0,0,.6)}
header.site .grp.open>.dd{display:block}
@media (hover:hover){header.site .grp:hover>.dd{display:block}}
header.site .dd a{display:flex;gap:12px;align-items:flex-start;padding:10px 12px;text-decoration:none;color:var(--fg,#F4F4F5)}
header.site .dd a:hover,header.site .dd a.on{background:#1A1A1E}
header.site .dd i{flex:none;width:3px;align-self:stretch;background:var(--m)}
header.site .dd b{display:flex;align-items:center;gap:6px;font:600 15px/1.1 'Barlow Condensed',sans-serif;letter-spacing:.1em;text-transform:uppercase;white-space:nowrap}
header.site .dd small{display:block;margin-top:3px;color:var(--fg2,#A1A1AA);font:13px/1.35 Barlow,sans-serif}
header.site .hext{width:10px;height:10px;fill:none;stroke:var(--fg3,#85858E);stroke-width:1.6}
.hside{display:flex;align-items:center;align-self:stretch;gap:18px;margin-left:auto}
.hside .acct{display:flex;align-items:center;align-self:stretch;gap:18px}
header.site .hi{position:relative;display:inline-flex;align-items:center;gap:8px;color:var(--fg2,#A1A1AA);text-decoration:none}
header.site .hi:hover,header.site .hi.on{color:var(--fg,#F4F4F5)}
header.site .hic{display:block;width:22px;height:22px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
header.site .help .tx{display:none;font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;text-transform:uppercase;white-space:nowrap}
header.site:not(.in):not(.two) .help .tx{display:inline}header.site:not(.in):not(.two) .help .hic{display:none}
header.site .ib .env{display:block;width:24px;height:24px;color:inherit;vertical-align:0}
header.site .ib.new{color:#4CD6C0}header.site .ib.new .env .body{fill:currentColor}header.site .ib.new .env .flap{stroke:var(--bg,#0A0A0B)}
header.site .ib .unread{position:absolute;top:-8px;left:15px;margin:0;min-width:16px;padding:2px 3px;border-radius:8px;background:var(--acc,#E30613);color:#fff;font:700 10px/1 Barlow,sans-serif;text-align:center}
header.site .crchip{display:inline-flex;align-items:center;font:600 15px/1 'Barlow Condensed',sans-serif;letter-spacing:.02em;color:#FFD60A;text-decoration:none;white-space:nowrap}
header.site .crchip:hover{color:#FFE45C}header.site .crchip .coin{width:15px;height:15px;margin-left:4px}
#crhost:empty{display:none}
header.site .signin{display:inline-flex;align-items:center;justify-content:center;min-height:44px;min-width:44px;padding:0 4px;font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;text-transform:uppercase;color:var(--fg2,#A1A1AA);text-decoration:none;white-space:nowrap}
header.site .signin:hover{color:var(--fg,#F4F4F5)}
header.site .hav{display:inline-flex;align-items:center;gap:6px;padding:0;background:none;border:0;color:var(--fg2,#A1A1AA);cursor:pointer}
header.site .hav:hover,header.site .grp.open>.hav{color:var(--fg,#F4F4F5)}
header.site .av{display:inline-grid;place-items:center;flex:none;width:30px;height:30px;border-radius:50%;overflow:hidden;background:var(--acc,#E30613);color:#fff;font:700 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.04em}
header.site .av img{display:block;width:100%;height:100%;object-fit:cover}
header.site .av.big{width:38px;height:38px;font-size:15px}
header.site .dd.right{left:auto;right:0;min-width:240px}
header.site .dd .rk{margin-top:4px;padding-top:4px;border-top:1px solid var(--line,#1F1F23)}
header.site .dd .rkh{padding:8px 12px 2px;color:var(--fg2,#A1A1AA);font:600 12px/1 'Barlow Condensed',sans-serif;letter-spacing:.14em;text-transform:uppercase}
header.site .dd .who{align-items:center;padding:10px 12px 12px;margin-bottom:4px;border-bottom:1px solid var(--line,#1F1F23)}
header.site .dd .who b{font:600 16px/1.15 Barlow,sans-serif;letter-spacing:0;text-transform:none;white-space:normal;overflow-wrap:anywhere}
header.site .dd .lrow{position:relative;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 12px}
header.site .dd .lrow:hover{background:#1A1A1E}header.site .dd .lrow .langpick{position:static;color:var(--fg2,#A1A1AA)}
header.site .dd form{margin:0}
header.site .dd .out{display:block;width:100%;padding:10px 12px;background:none;border:0;text-align:left;color:var(--fg2,#A1A1AA);font:600 15px/1.1 'Barlow Condensed',sans-serif;letter-spacing:.1em;text-transform:uppercase;cursor:pointer}
header.site .dd .out:hover{background:#1A1A1E;color:var(--fg,#F4F4F5)}
header.site .dl{font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;text-transform:uppercase;text-decoration:none;color:var(--fg,#F4F4F5);background:var(--acc,#E30613);padding:10px 15px;white-space:nowrap}
header.site .dl:hover{background:var(--fg,#F4F4F5);color:var(--bg,#0A0A0B)}
header.site .hburger{display:none;align-items:center;justify-content:center;min-width:44px;min-height:44px;padding:4px;margin-right:-10px;background:none;border:0;color:var(--fg2,#A1A1AA);cursor:pointer}
header.site .hburger:hover,header.site.open .hburger{color:var(--fg,#F4F4F5)}
/* the row closer together (HEADER_FIT: it didn't fit the window) */
header.site.tight .wrap,header.site.tight .hside,header.site.tight .hside .acct{gap:14px}header.site.tight .hnav .l{padding:0 9px;letter-spacing:.07em}
/* a narrow window (HEADER_FIT): one shorter row, the parts in a menu under ☰ */
header.site.two .wrap{height:64px;gap:14px}
header.site.two .brandmark{height:46px}
header.site.two .hside,header.site.two .hside .acct{gap:16px}
header.site.two .hburger{display:inline-flex}
header.site.two .hnav{display:none;position:absolute;top:100%;left:0;right:0;flex-direction:column;margin:0;padding:8px 0 14px;max-height:calc(100vh - 64px);overflow:auto;
  background:#111113;border-bottom:1px solid var(--line2,#2B2B31);box-shadow:0 24px 48px rgba(0,0,0,.6)}
header.site.two.open .hnav{display:flex}
header.site.two .hnav>a.l{position:relative;margin:0 20px;padding:13px 14px 13px 17px;border:0;font-size:17px;color:var(--fg,#F4F4F5)}
header.site.two .hnav>a.l::before{content:'';position:absolute;left:0;top:12px;bottom:12px;width:3px;background:var(--m)}
header.site.two .hnav>a.l.on{background:#1A1A1E}
header.site.two .hnav .grp{display:block}
header.site.two .hnav .grp>.l{pointer-events:none;width:100%;margin-top:8px;padding:16px 20px 6px;border:0;border-top:1px solid var(--line,#1F1F23);color:var(--fg3,#85858E);font:700 11px/1 Barlow,sans-serif;letter-spacing:.16em}
header.site.two .hnav .grp>.l .hcaret{display:none}
header.site.two .hnav .dd{display:block;position:static;min-width:0;padding:0;background:none;border:0;box-shadow:none}
header.site.two .hnav .dd a{margin:0 20px;padding:10px 14px 10px 0;gap:14px}
header.site.two .hnav .dd a.on{background:#1A1A1E}
header.site.two .hnav .dd b{font-size:16px}
header.site.two .hnav .dd small{display:none}
@media (max-width:700px){header.site .dl{display:none}}
/* a finger's room on a touch screen: 44 px at least (WCAG's target size; SIGN IN was 44 x 13, ☰ 30: a UI review, Nov 2026) */
@media (pointer:coarse){header.site .hi,header.site .hav,header.site .crchip{min-height:44px;min-width:44px;justify-content:center}
  header.site .dd a,header.site .dd .out,header.site .dd .lrow{min-height:44px}}
@media (max-width:420px){header.site .beta{display:none}header.site.two .hside,header.site.two .hside .acct{gap:14px}}
`;
