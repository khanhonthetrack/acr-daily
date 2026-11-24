// /ranked: RANKED on the website, as the app's RANKED page in the game shows it (the user, 24 Nov 2026: "In Ranked the
// view should be like in the game. The next 4 events, how many signed up, logos of the championship"): the next four
// sessions as cards (the series' tile, its hour, rally, class, how many registered, a countdown), the four series, and
// the last sessions' winners. From /api/liverallies (src/liverallies.js), as the app reads it; registering stays in the
// app (the car is picked there, from the player's game).

import { N_, t, tq } from './i18n.js';
import { shell } from './leaguepages.js';

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
</style>`;

export function rankedPage(env) {
  return shell(`${esc(t('Ranked'))} · ACR Daily`, `${CSS}
  <div class="rk">
  <div class="top"><div class="kick">${esc(t('Competitions'))}</div><h1>${esc(t('Ranked'))}</h1>
  <p class="note rkhow">${esc(t('Official rallies every hour, the four series in turn: three stages, one car at a time, 20 s to start on your turn. Register in the ACR DAILY app in the 30 minutes before the hour; your rating moves with every result.'))}</p></div>
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
  function draw(j){var names={},about={},cls={};(j.series||[]).forEach(function(s){names[s.key]=s.name;about[s.key]=s.about;cls[s.key]=s.carClass});
    var now=Date.now(),list=(j.sessions||[]).filter(function(s){return s.phase!=='over'&&s.closes>now}).sort(function(a,b){return a.starts-b.starts}).slice(0,4);
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
    (j.series||[]).forEach(function(s){add(ss,add(el('div','s'),img('/series/'+s.key+'-logo.webp'),el('b',null,s.name),el('small',null,[s.carClass,s.about].filter(Boolean).join(' · '))))});
    var r=document.getElementById('rkr');r.innerHTML='';
    (j.recent||[]).slice(0,12).forEach(function(x){var tr=el('tr'),w=x.winner;
      var a=el('a',null,W.res+' ›');a.href='/e/'+x.eventId;
      add(tr,add(el('td'),img('/series/'+x.series+'-logo.webp','lg')),
        el('td','t',new Date(x.starts).toLocaleString([],{weekday:'short',hour:'2-digit',minute:'2-digit'})+' · '+(x.rally||'')),
        el('td','w',w?w.name:''),el('td','t',w?ms(w.totalMs):''),el('td','t',T(W.drivers,x.drivers||0)),add(el('td'),a));add(r,tr)});
    tick()}
  function tick(){var now=Date.now();cds.forEach(function(p){var s=p[1];p[0].textContent=s.phase==='running'?T(W.closes,span(s.closes-now)):T(W.starts,span(s.starts-now))})}
  function load(){fetch('/api/liverallies',{credentials:'same-origin',cache:'no-store'}).then(function(r){return r.ok?r.json():null}).then(function(j){if(j)draw(j)},function(){})}
  load();setInterval(tick,1000);setInterval(load,60000);
  navOn('ranked');`, env);
}
