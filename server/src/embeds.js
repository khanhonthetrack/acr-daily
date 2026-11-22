// Embeds: ACR Daily's tables on another site, in an <iframe>, for a championship's organizers who don't write code (the
// public API, src/publicapi.js, for those who do). Each is a small page of its own that reads /api/v1 (so the edge keeps
// its answers) and draws one thing:
//
//   /embed/event/<id>[?code=]            an event's results (each class and division to pick, if it has them)
//   /embed/event/<id>/live[?code=]       its live timing: the map of the stage and who is on it, every few seconds
//   /embed/championship/<id>[?season=]   a championship's standings (drivers, each class and division, teams)
//
// Options on all of them: theme=dark|light, accent=RRGGBB, title=0 (no heading: the organizer's page has its own).
// Unlike every other page they may be framed by any site (frame-ancestors *): they only read, sign no one in and hold
// nothing to click but links, which open ACR Daily in a new tab, so a frame can't be turned against anyone.
// The snippets to copy are on the championship's page (src/leaguepages.js) and the developers' page. In the reader's
// language (WORDS below: ?lang=xx fixes one, else the cookie and the browser's, as the site's pages).

import { DATA, N_, forms, lang, langTag, t } from './i18n.js';

export const EMBED_HEADERS = { 'Content-Type': 'text/html; charset=utf-8', 'X-Content-Type-Options': 'nosniff',
  'Content-Security-Policy': "frame-ancestors *; base-uri 'none'; object-src 'none'; form-action 'none'; connect-src 'self'",
  'Referrer-Policy': 'strict-origin-when-cross-origin', 'Cache-Control': 'public, max-age=300', 'Vary': 'Accept-Language, Cookie' };

// the words they show, in the reader's language (?lang=, the cookie, the browser's: src/i18n.js), as the site's pages
const WORDS = [N_('Loading…'), N_('Overall'), N_('Pos'), N_('Driver'), N_('Car'), N_('Total'), N_('Gap'), N_('Drivers'), N_('Teams'),
  N_('Team'), N_('Points'), N_('Wins'), N_('Stage'), N_('Time'), N_('Progress'), N_('finished'), N_('retired'), N_('No results yet.'),
  N_('No season yet.'), N_('Not available'), N_('open'), N_('closed'), N_('upcoming'), N_('LIVE'), N_('open until {0}'),
  N_('Stage map'), N_('Results from {0}'), N_('Standings from {0}'), N_('Live timing from {0}'), N_('Nobody on a stage right now.'),
  N_('Times are hidden until the event closes.'), N_('The map is hidden until the event closes.'), N_("This private rally's results need its code.")];

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

/** An embed's page. kind: 'event' | 'live' | 'championship'; id; q: its URLSearchParams; site: the site's address. */
export function embedPage(kind, id, q, site) {
  // (and the rallies' names, as the site says them: src/i18n.js DATA; a plural: its forms and the language's rule)
  const words = Object.fromEntries([...WORDS, ...DATA].map((w) => [w, t(w)]));
  const stagesForms = forms('{0} stage', '{0} stages');
  const theme = q.get('theme') === 'light' ? 'light' : 'dark';
  const accent = /^[0-9a-fA-F]{6}$/.test(q.get('accent') || '') ? '#' + q.get('accent') : '#FF4655';
  const cfg = { kind, id: String(id), code: q.get('code') || '', season: q.get('season') || '', title: q.get('title') !== '0', site };
  return `<!doctype html><html lang="${esc(langTag())}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ACR Daily</title><meta name="robots" content="noindex">
<style>
:root{--bg:#0A0A0B;--panel:#111113;--line:#2A2A30;--fg:#F4F4F5;--fg2:#A1A1AA;--fg3:#85858E;--acc:${esc(accent)};--acct:${esc(accent)};--good:#30D158;--bad:#FF453A}
/* (the light theme's grey on white: 5.9:1, its own variable: the site's --fg3 is for its dark pages) */
:root.light{--bg:#FFFFFF;--panel:#F4F4F5;--line:#E4E4E7;--fg:#18181B;--fg2:#3F3F46;--fg3l:#63636B;--fg3:var(--fg3l)}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.35 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{padding:12px}h1{font-size:17px;margin:0 0 2px;font-weight:700;letter-spacing:.01em}.sub{color:var(--fg2);font-size:12px;margin:0 0 10px}
.bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0 0 8px}
select{background:var(--panel);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:4px 8px;font:inherit;font-size:13px}
.tw{overflow-x:auto;border:1px solid var(--line);border-radius:8px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{padding:6px 8px;text-align:left;white-space:nowrap;border-bottom:1px solid var(--line)}tr:last-child td{border-bottom:0}
th{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--fg3);font-weight:600;background:var(--panel);position:sticky;top:0}
td.n,th.n{text-align:right}td.pos{color:var(--acct);font-weight:700;width:1%}.drv{font-weight:600}.cc{color:var(--fg3);font-size:11px;margin-left:4px}
.tag{color:var(--fg2);font-weight:700;margin-right:4px}.muted{color:var(--fg3)}.dnf{color:var(--bad)}.p1 td{background:color-mix(in srgb,var(--acc) 9%,transparent)}
.foot{margin-top:8px;font-size:11px;color:var(--fg3)}.foot a{color:var(--fg2)}
.empty{padding:18px;text-align:center;color:var(--fg2)}
.map{border:1px solid var(--line);border-radius:8px;background:var(--panel);margin:0 0 8px}.map svg{display:block;width:100%;height:auto}
.route{fill:none;stroke:var(--fg3);stroke-width:3;stroke-linejoin:round;stroke-linecap:round}.car{stroke:var(--bg);stroke-width:2}
.lbl{font:600 11px system-ui,sans-serif;fill:var(--fg);paint-order:stroke;stroke:var(--panel);stroke-width:3px}
.live{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--bad);margin-right:6px;animation:p 1.6s infinite}@keyframes p{50%{opacity:.35}}
@media (max-width:560px){.wide{display:none}}
</style></head><body><div class="wrap" id="root"><div class="empty">${esc(words['Loading…'])}</div></div>
<script>
(function(){
var C=${JSON.stringify(cfg).replace(/</g, '\\u003c')},W=${JSON.stringify(words).replace(/</g, '\\u003c')},LANG=${JSON.stringify(langTag())},CODE=${JSON.stringify(lang())},STAGES=${JSON.stringify(stagesForms).replace(/</g, '\\u003c')};
// a plural's form for n, by the language's rule (src/i18n.js pluralIndex)
function P(f,n){var i=CODE==='ja'||CODE==='zh'||CODE==='hu'?0:CODE==='pl'?(n===1?0:[2,3,4].indexOf(n%10)>=0&&[12,13,14].indexOf(n%100)<0?1:2)
  :CODE==='fr'||CODE==='pt'?(n<=1?0:1):(n===1?0:1);return f[Math.min(i,f.length-1)].split('{0}').join(n)}
function T(w){var v=W[w]||w;for(var i=1;i<arguments.length;i++)v=v.split('{'+(i-1)+'}').join(arguments[i]);return v}
if(${JSON.stringify(theme)}==='light')document.documentElement.className='light';
var root=document.getElementById('root');
function el(t,c,x){var e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e}
function add(p){for(var i=1;i<arguments.length;i++)if(arguments[i]!=null)p.appendChild(arguments[i]);return p}
function ms(v){if(v==null)return '';var t=Math.round(v),m=Math.floor(t/60000),s=((t%60000)/1000).toFixed(3);var h=Math.floor(m/60);
  return h?h+':'+String(m%60).padStart(2,'0')+':'+s.padStart(6,'0'):m+':'+s.padStart(6,'0')}
function api(p){return fetch('/api/v1'+p).then(function(r){return r.json().then(function(j){if(!r.ok)throw new Error(j.error||('error '+r.status));return j})})}
function q(){var a=[];if(C.code)a.push('code='+encodeURIComponent(C.code));if(C.season)a.push('season='+encodeURIComponent(C.season));return a.length?'?'+a.join('&'):''}
function link(href,text){var a=el('a',null,text);a.href=href;a.target='_blank';a.rel='noopener';return a}
// "Results from ACR Daily": the words around the link, in the reader's language
function foot(url,txt){var f=el('div','foot'),w=T(txt||'Results from {0}'),k=w.indexOf('{0}');
  add(f,document.createTextNode(k<0?w+' ':w.slice(0,k)),link(url,'ACR Daily'),k<0?null:document.createTextNode(w.slice(k+3)));return f}
function head(t,s){if(!C.title)return;add(root,el('h1',null,t));if(s)add(root,el('p','sub',s))}
function drv(td,r){var tg=r.team&&(r.team.tag||r.team.name);if(tg)add(td,el('span','tag','['+tg+']'));add(td,el('span','drv',r.name));
  if(r.country)add(td,el('span','cc',String(r.country).toUpperCase()));return td}
function fail(e){root.innerHTML='';add(root,el('div','empty',e.message||T('Not available')))}
var timer=null;function again(f,s){clearTimeout(timer);timer=setTimeout(f,s*1000)}

// ---- an event's results
function results(){api('/events/'+C.id+q()).then(function(e){root.innerHTML='';
  head(e.name,[T(e.rally),e.car||e.carClass,P(STAGES,e.stages.length),e.status==='open'?T('open until {0}',new Date(e.closes).toLocaleString(LANG)):T(e.status)].filter(Boolean).join(' · '));
  if(e.locked){add(root,el('div','empty',T("This private rally's results need its code.")));return}
  var groups=[{name:T('Overall'),results:e.results}].concat(e.groups||[]),cur=0;
  var bar=el('div','bar'),tw=el('div','tw');
  if(groups.length>1){var s=el('select');groups.forEach(function(g,i){var o=el('option',null,g.name);o.value=i;s.appendChild(o)});s.onchange=function(){cur=+s.value;draw()};add(bar,s);add(root,bar)}
  add(root,tw,foot('${esc(site)}/e/'+e.id));
  if(e.hidden&&e.hidden.times)add(root,el('p','sub',T('Times are hidden until the event closes.')));
  function draw(){tw.innerHTML='';var rows=groups[cur].results||[];if(!rows.length){add(tw,el('div','empty',T('No results yet.')));return}
    var t=el('table'),hr=el('tr');['Pos','Driver','Car','Total','Gap'].forEach(function(h,i){add(hr,el('th',i>2?'n':(i===2?'wide':null),T(h)))});
    e.stages.forEach(function(s){add(hr,el('th','n wide','SS'+s.no))});add(t,add(el('thead'),hr));var tb=el('tbody');
    rows.forEach(function(r){var tr=el('tr',r.rank===1?'p1':null);add(tr,el('td','pos',r.rank==null?'–':String(r.rank)));add(tr,drv(el('td'),r));
      add(tr,el('td','wide muted',r.car||''));
      add(tr,el('td','n'+(r.status==='dnf'||r.status==='dsq'?' dnf':''),r.status==='finished'||r.classified?ms(r.totalMs):(r.status||'').toUpperCase()));
      add(tr,el('td','n muted',r.rank>1&&r.gapMs!=null?'+'+ms(r.gapMs):''));
      e.stages.forEach(function(s,k){var x=r.stages[k];add(tr,el('td','n wide muted',x?(x.retired?T('retired'):ms(x.totalMs!=null?x.totalMs:x.timeMs)):''))});add(tb,tr)});
    add(tw,add(t,tb))}
  draw();if(e.status==='open')again(results,60)}).catch(fail)}

// ---- a championship's standings
function standings(){api('/championships/'+C.id+'/standings'+q()).then(function(d){root.innerHTML='';
  var ss=d.seasons||[];if(!ss.length){head(d.championship.name);add(root,el('div','empty',T('No season yet.')),foot(d.championship.url,'Standings from {0}'));return}
  var si=ss.length-1,gi=0;var bar=el('div','bar'),tw=el('div','tw');
  head(d.championship.name);
  if(ss.length>1){var s1=el('select');ss.forEach(function(s,i){var o=el('option',null,s.name);o.value=i;o.selected=i===si;s1.appendChild(o)});s1.onchange=function(){si=+s1.value;gi=0;opts();draw()};add(bar,s1)}
  var s2=el('select');add(bar,s2);add(root,bar,tw,foot(d.championship.url,'Standings from {0}'));
  function lists(){var s=ss[si];return [{name:T('Drivers'),drivers:s.drivers}].concat(s.groups||[]).concat(s.teams&&s.teams.length?[{name:T('Teams'),teams:s.teams}]:[])}
  function opts(){s2.innerHTML='';var l=lists();l.forEach(function(g,i){var o=el('option',null,g.name);o.value=i;s2.appendChild(o)});s2.style.display=l.length>1?'':'none'}
  s2.onchange=function(){gi=+s2.value;draw()};
  function draw(){tw.innerHTML='';var s=ss[si],g=lists()[gi]||lists()[0],t=el('table'),hr=el('tr'),tb=el('tbody');
    if(g.teams){['Pos','Team','Points'].forEach(function(h,i){add(hr,el('th',i===2?'n':null,T(h)))});
      g.teams.forEach(function(x){var tr=el('tr',x.rank===1?'p1':null);add(tr,el('td','pos',String(x.rank==null?'–':x.rank)),el('td','drv',(x.tag?'['+x.tag+'] ':'')+(x.name||'')),el('td','n',String(x.points==null?'':x.points)));add(tb,tr)})}
    else{['Pos','Driver','Points','Wins'].forEach(function(h,i){add(hr,el('th',i>1?'n':null,T(h)))});s.events.forEach(function(e){add(hr,el('th','n wide',e.name))});
      (g.drivers||[]).forEach(function(r){var tr=el('tr',r.rank===1?'p1':null);add(tr,el('td','pos',String(r.rank)),drv(el('td'),r),el('td','n',String(r.points)),el('td','n muted',String(r.wins)));
        s.events.forEach(function(e){var c=r.events[e.id];add(tr,el('td','n wide'+(c&&(c.dnf||c.dsq)?' dnf':' muted'),!c?'':c.dsq?'DSQ':c.dnf?'DNF':c.running?'…':String(c.points)+(c.dropped?'*':'')))});add(tb,tr)})}
    if(!tb.firstChild){add(tw,el('div','empty',T('No results yet.')));return}add(tw,add(t,add(el('thead'),hr),tb))}
  opts();draw();again(standings,120)}).catch(fail)}

// ---- live timing: the stage's map and who is on it
var map=null;
function live(){Promise.all([api('/events/'+C.id+q()),api('/events/'+C.id+'/live'+q())]).then(function(a){var e=a[0],l=a[1];
  if(!map)return api('/events/'+C.id+'/map'+q()).then(function(m){map=m;show(e,l)});show(e,l)}).catch(fail)}
function show(e,l){root.innerHTML='';head(e.name,T(e.rally)+' · '+T('LIVE'));
  var on=l.drivers.filter(function(d){return d.state!=='finished'&&d.state!=='dnf'});
  var stageNo=on.length?on[0].stageNo:(l.drivers[0]&&l.drivers[0].stageNo);
  var st=map&&map.stages?map.stages.filter(function(s){return s.no===stageNo})[0]||map.stages[0]:null;
  if(st&&st.points&&st.points.length>1)add(root,drawMap(st,l.drivers.filter(function(d){return d.stageNo===st.no&&d.x!=null})));
  else if(e.hidden&&e.hidden.stages)add(root,el('p','sub',T('The map is hidden until the event closes.')));
  var tw=el('div','tw');add(root,tw,foot('${esc(site)}/e/'+e.id,'Live timing from {0}'));
  if(!l.drivers.length){add(tw,el('div','empty',T('Nobody on a stage right now.')))}
  else{var t=el('table'),hr=el('tr'),tb=el('tbody');['','Driver','Stage','Progress','Time'].forEach(function(h,i){add(hr,el('th',i>1?'n':null,h?T(h):''))});
    l.drivers.slice().sort(function(a,b){return (b.progress||0)-(a.progress||0)}).forEach(function(d){var tr=el('tr'),dot=el('td');
      if(d.state!=='finished'&&d.state!=='dnf')add(dot,el('span','live'));add(tr,dot,drv(el('td'),d),el('td','n','SS'+(d.stageNo!=null?d.stageNo:'?')),
        el('td','n muted',d.state==='finished'?T('finished'):d.state==='dnf'?T('retired'):d.progress!=null?Math.round(d.progress*100)+'%':''),el('td','n',ms(d.totalMs)));add(tb,tr)});
    add(tw,add(t,add(el('thead'),hr),tb))}
  again(live,l.pollSeconds||5)}
function drawMap(st,cars){var NS='http://www.w3.org/2000/svg',W=640,H=300,pad=22,p=st.points,n=p.length,mx=0,mz=0,i;
  function sv(t,a){var x=document.createElementNS(NS,t);for(var k in a)x.setAttribute(k,a[k]);return x}
  for(i=0;i<n;i++){mx+=p[i][0];mz+=p[i][1]}mx/=n;mz/=n;var sxx=0,szz=0,sxz=0;for(i=0;i<n;i++){var dx=p[i][0]-mx,dz=p[i][1]-mz;sxx+=dx*dx;szz+=dz*dz;sxz+=dx*dz}
  var an=-0.5*Math.atan2(2*sxz,sxx-szz),c=Math.cos(an),s=Math.sin(an),x0=1e9,x1=-1e9,y0=1e9,y1=-1e9;
  function R(q){return[(q[0]-mx)*c-(q[1]-mz)*s,(q[0]-mx)*s+(q[1]-mz)*c]}
  p.forEach(function(q){var r=R(q);x0=Math.min(x0,r[0]);x1=Math.max(x1,r[0]);y0=Math.min(y0,r[1]);y1=Math.max(y1,r[1])});
  var k=Math.min((W-2*pad)/(x1-x0||1),(H-2*pad)/(y1-y0||1)),ox=(W-(x1-x0)*k)/2-x0*k,oy=(H-(y1-y0)*k)/2-y0*k;
  function P(q){var r=R(q);return[r[0]*k+ox,r[1]*k+oy]}
  var svg=sv('svg',{viewBox:'0 0 '+W+' '+H,role:'img','aria-label':T('Stage map')});
  svg.appendChild(sv('polyline',{class:'route',points:p.map(function(q){var r=P(q);return r[0].toFixed(1)+','+r[1].toFixed(1)}).join(' ')}));
  var A=P(p[0]),Z=P(p[n-1]);svg.appendChild(sv('circle',{cx:A[0],cy:A[1],r:4,fill:'var(--good)'}));svg.appendChild(sv('circle',{cx:Z[0],cy:Z[1],r:4,fill:'var(--fg)'}));
  cars.forEach(function(d){var q=P([d.x,d.z]);svg.appendChild(sv('circle',{class:'car',cx:q[0],cy:q[1],r:6,fill:'var(--acc)'}));
    var t=sv('text',{class:'lbl',x:q[0]+9,y:q[1]+4});t.textContent=d.name;svg.appendChild(t)});
  var box=el('div','map');box.appendChild(svg);return box}

({event:results,championship:standings,live:live})[C.kind]();
})();
</script></body></html>`;
}

/** The snippet an organizer copies: an <iframe> of an embed, sized for it. */
export function embedSnippet(site, path, height = 520) {
  return `<iframe src="${site}${path}" width="100%" height="${height}" style="border:0;max-width:100%" loading="lazy" title="ACR Daily"></iframe>`;
}
