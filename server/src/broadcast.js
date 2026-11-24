// Broadcast overlays: TV graphics for a stream (OBS, vMix, Streamlabs: a "browser source" at 1920 x 1080), drawn from the
// public API (src/publicapi.js) like the embeds (src/embeds.js). The user, 24 Nov 2026: "the final goal is for people to
// be able to broadcast events, e-sport events here ... provide some API and guidance for broadcasters ... When there is
// no one on stage, there could be a full table of top 10 with full names, teams, nationality and driving times,
// switching tabs to the daily information, weather etc. MAKE IT FEEL LIKE REAL BROADCAST."
//
//   /broadcast/daily/<1|2>        today's daily
//   /broadcast/tt/<1|2>           this week's time trial stage
//   /broadcast/event/<id>[?code=] an event (a championship's, a cup's, a ranked session's)
//
// What it shows (the same look as WATCH in the game, src: client/acr_daily/ig_watch.py): top left the standings tower
// (the best ten, flags and three letters, then who is on the stage now, how far); top right the LIVE bug; at the bottom
// the driver furthest on (name, flag, team, how far, their time). Nobody on the stage: the studio in the middle, the
// classification (top ten, full names, teams, flags, times, gaps) and the stage (rally, length, surface, car, weather)
// in turn.
// Options: parts=tower,bug,lower,studio (which to draw; all by default), bg=1 (a dark backdrop: to look at it in a
// browser; OBS shows the page see-through), rotate=<seconds> (the studio's pages, 10 by default), accent=RRGGBB,
// lang=xx, code= (a private rally's). The page scales itself to the source's size, its layout always 16:9.

import { N_, langTag, t } from './i18n.js';

export const BROADCAST_HEADERS = { 'Content-Type': 'text/html; charset=utf-8', 'X-Content-Type-Options': 'nosniff',
  'Content-Security-Policy': "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline' https://fonts.googleapis.com; " +
    "font-src https://fonts.gstatic.com; img-src https://flagcdn.com data:; connect-src 'self'; frame-ancestors *; base-uri 'none'; form-action 'none'",
  'Referrer-Policy': 'strict-origin-when-cross-origin', 'Cache-Control': 'public, max-age=300', 'Vary': 'Accept-Language, Cookie' };

const WORDS = [N_("TODAY'S BEST"), N_("THIS WEEK'S BEST"), N_('STAGE BEST'), N_('ON STAGE'), N_('LIVE'), N_('BETWEEN CARS'),
  N_('CLASSIFICATION'), N_('THE STAGE'), N_('RALLY'), N_('LENGTH'), N_('SURFACE'), N_('CAR'), N_('WEATHER'), N_('TIME OF DAY'),
  N_('DRIVERS'), N_('BEST'), N_('POS'), N_('DRIVER'), N_('TEAM'), N_('TIME'), N_('GAP'), N_('DAILY · SS{0}'), N_('TIME TRIAL · TT{0}'),
  N_('{0} drivers on the board'), N_('Nobody on the board yet.'), N_('LIVE COVERAGE'), N_('FINISHED'), N_('RETIRED'),
  N_('The next driver on the stage comes on by themselves.'), N_('Not available')];

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

/** The overlay's page. kind: 'daily' | 'tt' | 'event'; id: the slot or the event's id; q: its URLSearchParams. */
export function broadcastPage(kind, id, q, site) {
  const words = Object.fromEntries(WORDS.map((w) => [w, t(w)]));
  const accent = /^[0-9a-fA-F]{6}$/.test(q.get('accent') || '') ? '#' + q.get('accent') : '#E30613';
  const parts = (q.get('parts') || 'tower,bug,lower,studio').split(',').map((s) => s.trim()).filter(Boolean);
  const rotate = Math.max(4, Math.min(60, +(q.get('rotate') || 10) || 10));
  const cfg = { kind, id: String(id), code: q.get('code') || '', parts, rotate, bg: q.get('bg') === '1', site };
  return `<!doctype html><html lang="${esc(langTag())}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ACR Daily · broadcast</title><meta name="robots" content="noindex">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&display=swap">
<style>
:root{--navy:#0A1428;--navy2:#13213D;--navy3:#1C2D4F;--red:${esc(accent)};--white:#fff;--soft:#C9D1E0;--grey:#5C6A84;--fast:#2BD96B;--slow:#FF453A;--a:.9}
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:transparent}
body.bg{background:radial-gradient(ellipse at 30% 30%,#2c3a2a,#0b0f0a 70%)}
#stage{position:absolute;left:0;top:0;width:1920px;height:1080px;transform-origin:0 0;font-family:"Barlow Condensed",system-ui,sans-serif;color:var(--white);font-variant-numeric:tabular-nums}
.p{background:rgba(10,20,40,var(--a))}.p2{background:rgba(19,33,61,var(--a))}
.tower{position:absolute;left:48px;top:48px;width:330px}
.th{background:var(--red);display:flex;align-items:center;gap:10px;padding:6px 14px;font-weight:700;font-size:24px;white-space:nowrap;overflow:hidden}
.th .nm{overflow:hidden;text-overflow:ellipsis;font-size:21px}.sl{width:4px;height:24px;background:#fff;transform:skewX(-18deg);flex:none}
.sub{font-weight:700;font-size:15px;letter-spacing:.14em;color:var(--soft);text-align:center;padding:7px 8px 5px}
.tr{display:flex;align-items:center;gap:8px;padding:3px 12px 3px 10px;height:34px;transition:background .3s}
.pos{width:30px;height:26px;background:#fff;color:var(--navy);font-weight:700;font-size:18px;display:flex;align-items:center;justify-content:center;flex:none}
.tr .bar{width:4px;height:24px;background:var(--red);transform:skewX(-18deg);flex:none}
.fl{width:27px;height:18px;object-fit:cover;flex:none;border-radius:2px;box-shadow:0 0 0 1px rgba(255,255,255,.15)}.fl0{width:27px;flex:none}
.cd{font-weight:700;font-size:22px;letter-spacing:.04em}.rt{margin-left:auto;font-weight:600;font-size:18px;color:var(--soft)}
.tr.on{background:var(--red)}.tr.on .pos{background:var(--navy);color:#fff}.tr.lv .pos{background:var(--soft)}
.fast{color:var(--fast)}.slow{color:var(--slow)}.rule{height:3px;background:var(--red)}
.bug{position:absolute;right:48px;top:48px;display:flex;gap:0;align-items:stretch}
.live{background:var(--red);display:flex;align-items:center;gap:9px;padding:6px 16px 6px 14px;font-weight:700;font-size:24px;letter-spacing:.12em}
.live i{width:11px;height:11px;border-radius:50%;background:#fff;animation:bl 1.4s infinite}.live.off{background:var(--grey)}.live.off i{animation:none;opacity:.7}
@keyframes bl{50%{opacity:.25}}.what{padding:8px 16px;font-weight:700;font-size:20px;letter-spacing:.1em}
.lower{position:absolute;left:50%;bottom:56px;width:1120px;transform:translateX(-50%);transition:opacity .5s,transform .5s}
.lower.hide{opacity:0;transform:translate(-50%,30px)}
.lt{display:flex;align-items:center;gap:16px;padding:12px 18px}
.lt .sk{width:10px;height:48px;background:var(--red);transform:skewX(-18deg)}.lt .nm{font-size:40px;font-weight:700;letter-spacing:.02em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:560px}
.lt .fl{width:42px;height:28px}.tag{font-weight:700;font-size:20px;padding:2px 9px;letter-spacing:.05em}
.lt .clk{margin-left:auto;background:var(--red);transform:skewX(-8deg);padding:2px 22px;font-size:44px;font-weight:700;min-width:210px;text-align:center}
.prog{padding:0 18px 12px;display:flex;align-items:center;gap:14px}.pb{flex:1;height:6px;background:#3A4F78;position:relative}
.pb b{position:absolute;left:0;top:0;bottom:0;background:var(--red);transition:width 1s linear}
.pb u{position:absolute;top:50%;width:16px;height:16px;margin:-8px 0 0 -8px;border-radius:50%;background:#fff;border:3px solid var(--red);transition:left 1s linear}
.prog span{font-size:20px;font-weight:600;color:var(--soft);min-width:150px;text-align:right}
.studio{position:absolute;left:50%;top:50%;width:1160px;transform:translate(-50%,-50%);transition:opacity .6s}
.studio.hide{opacity:0}
.tabs{display:flex;gap:4px;margin-bottom:6px}.tab{padding:7px 18px;font-weight:700;font-size:18px;letter-spacing:.14em;color:var(--soft);background:rgba(19,33,61,var(--a))}
.tab.on{background:var(--red);color:#fff}.tabs .bc{margin-left:auto;background:var(--grey);color:#fff;display:flex;align-items:center;gap:8px}.tabs .bc i{width:9px;height:9px;border-radius:50%;background:#fff}
.sh{background:var(--red);display:flex;align-items:center;gap:14px;padding:12px 22px;font-weight:700}
.sh .k{font-size:20px;letter-spacing:.12em}.sh .n{font-size:34px;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.sh .r{font-size:20px;letter-spacing:.12em}
.row{display:flex;align-items:center;gap:16px;padding:6px 22px;height:46px;font-size:24px}
.row.hd{height:34px;font-size:15px;font-weight:700;letter-spacing:.14em;color:var(--soft)}
.row .ps{width:40px;height:32px;display:flex;align-items:center;justify-content:center;background:#fff;color:var(--navy);font-weight:700;font-size:22px;flex:none}
.row:nth-child(2) .ps{background:var(--red);color:#fff}
.row .dn{flex:1;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.row .tm{width:120px}.row .cr{width:260px;font-size:19px;color:var(--soft);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.row .ti{width:140px;text-align:right;font-weight:700}.row .gp{width:110px;text-align:right;color:var(--soft)}
.row:nth-child(odd):not(.hd){background:rgba(19,33,61,var(--a))}.row:nth-child(even):not(.hd){background:rgba(10,20,40,var(--a))}
.fact{display:flex;align-items:center;padding:12px 22px;font-size:28px;font-weight:700}.fact:nth-child(odd){background:rgba(19,33,61,var(--a))}.fact:nth-child(even){background:rgba(10,20,40,var(--a))}
.fact b{width:260px;font-size:18px;letter-spacing:.16em;color:var(--soft)}
.foot{display:flex;align-items:center;gap:10px;padding:9px 22px;font-size:19px;color:var(--soft)}.foot i{width:4px;height:18px;background:var(--red)}
.mark{position:absolute;left:48px;bottom:48px;display:flex;align-items:center;gap:12px}.mark i{width:7px;height:44px;background:var(--red);transform:skewX(-18deg)}
.mark b{display:block;font-size:30px;letter-spacing:.06em;line-height:1}.mark span{font-size:14px;letter-spacing:.18em;color:var(--soft);font-weight:700}
.empty{padding:26px;text-align:center;font-size:24px;color:var(--soft)}
</style></head><body${cfg.bg ? ' class="bg"' : ''}><div id="stage"></div>
<script>
(function(){
var C=${JSON.stringify(cfg).replace(/</g, '\\u003c')},W=${JSON.stringify(words).replace(/</g, '\\u003c')};
function T(w){var v=W[w]||w;for(var i=1;i<arguments.length;i++)v=v.split('{'+(i-1)+'}').join(arguments[i]);return v}
var S=document.getElementById('stage');
function fit(){var k=Math.min(innerWidth/1920,innerHeight/1080);S.style.transform='scale('+k+')';S.style.left=((innerWidth-1920*k)/2)+'px';S.style.top=((innerHeight-1080*k)/2)+'px'}
addEventListener('resize',fit);fit();
function el(t,c,x){var e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e}
function add(p){for(var i=1;i<arguments.length;i++)if(arguments[i]!=null)p.appendChild(arguments[i]);return p}
function has(p){return C.parts.indexOf(p)>=0}
function ms(v,d){if(v==null)return '';d=d==null?1:d;var t=Math.max(0,v),m=Math.floor(t/60000),s=(t%60000)/1000;var f=Math.pow(10,d);s=Math.floor(s*f)/f;
  return m+':'+s.toFixed(d).padStart(d?3+d:2,'0')}
function gap(v){return v==null?'':(v>0?'+':'−')+(Math.abs(v)/1000).toFixed(1)}
function flag(c,cls){if(!c){return el('span','fl0')}var i=el('img',cls||'fl');i.src='https://flagcdn.com/w80/'+String(c).toLowerCase()+'.png';i.alt=String(c).toUpperCase();return i}
function code(n,taken){var l=Array.from(String(n||'').toUpperCase().replace(/[^\\p{L}\\p{N}]/gu,'')).join('')||'DRV';l=Array.from(l);l={slice:function(a,b){return this.c.slice(a,b).join('')},c:l};var cs=[l.slice(0,3),l.slice(0,2)+l.slice(-1),l.slice(0,1)+l.slice(2,4)];
  for(var i=0;i<cs.length;i++){var c=(cs[i]+'XXX').slice(0,3);if(!taken[c]){taken[c]=1;return c}}return l.slice(0,3)}
function tagBox(tm){if(!tm||!tm.tag)return null;var b=el('span','tag',String(tm.tag).replace(/\\$[0-9a-fA-F]{3}|\\$[a-zA-Z<>]/g,'').slice(0,6).toUpperCase());
  b.style.background=tm.color?('#'+String(tm.color).replace('#','')):'#3A4F78';return b}
function api(p){return fetch('/api/v1'+p).then(function(r){return r.json().then(function(j){if(!r.ok)throw new Error(j.error||('error '+r.status));return j})})}
var Q=C.code?'?code='+encodeURIComponent(C.code):'';
var D={info:null,board:[],live:[],poll:5,at:0};

// ---- the data: what the stage is, its board, who is on it
function today(){return new Date().toISOString().slice(0,10)}
function load(){
  if(C.kind==='daily')return api('/dailies').then(function(d){var x=(d.dailies||[]).filter(function(s){return String(s.slot)===C.id})[0];if(!x)throw new Error(T('Not available'));
    D.info={label:T('DAILY · SS{0}',C.id),best:T("TODAY'S BEST"),stage:x.stage,rally:x.rally,lengthM:x.lengthM,car:x.car,carClass:x.carClass,weather:x.weather,time:x.time,surface:x.surface};
    D.base='/dailies/'+d.date+'/'+C.id;return api(D.base)}).then(function(r){D.board=r.results||[];D.drivers=r.drivers});
  if(C.kind==='tt')return api('/timetrials').then(function(d){var x=(d.stages||[]).filter(function(s){return String(s.slot)===C.id})[0];if(!x)throw new Error(T('Not available'));
    D.info={label:T('TIME TRIAL · TT{0}',C.id),best:T("THIS WEEK'S BEST"),stage:x.stage,rally:x.rally,car:x.car,carClass:x.carClass,weather:x.weather,time:x.time};
    D.base='/timetrials/'+d.week+'/'+C.id;return api(D.base)}).then(function(r){D.board=r.results||[]});
  return api('/events/'+C.id+Q).then(function(e){var st=(e.stages||[]);
    D.info={label:String(e.name||'').toUpperCase(),best:T('STAGE BEST'),stage:st.length?(st[st.length-1].name||''):'',rally:e.rally,car:e.car,carClass:e.carClass,
      weather:st.length?st[0].weather:null,time:st.length?st[0].time:null,stages:st};
    D.board=(e.results||[]).filter(function(r){return r.totalMs!=null&&(r.status==='finished'||r.classified||r.status==null)});D.base=null});
}
function loadLive(){var p=C.kind==='event'?'/events/'+C.id+'/live'+Q:D.base?D.base+'/live':null;if(!p)return Promise.resolve();
  return api(p).then(function(l){D.live=(l.drivers||[]).filter(function(d){return d.state==='live'||d.state==null});D.poll=l.pollSeconds||5;D.at=Date.now();
    if(C.kind==='event'&&D.live.length&&D.info.stages){var no=D.live[0].stageNo,s=D.info.stages.filter(function(x){return x.no===no})[0];if(s){D.info.stage=s.name||D.info.stage;D.info.no=no}}})}

// ---- the parts
function tower(){var w=el('div','tower');var taken={};
  var lb=C.kind==='daily'?'SS'+C.id:C.kind==='tt'?'TT'+C.id:(D.info.no?'SS'+D.info.no:'');
  add(w,add(el('div','th'),lb?el('span',null,lb):null,lb?el('span','sl'):null,el('span','nm',String(D.info.stage||'').toUpperCase())));
  var b=D.board.filter(function(r){return r.totalMs!=null});
  if(b.length){add(w,el('div','sub p',D.info.best));var lead=b[0].totalMs;
    b.slice(0,10).forEach(function(r,i){add(w,add(el('div','tr p'),el('span','pos',String(i+1)),el('span','bar'),flag(r.country),el('span','cd',code(r.name,taken)),
      el('span','rt',i?gap(r.totalMs-lead):ms(r.totalMs))))})}
  var on=D.live.slice().sort(function(a,b){return (b.progress||0)-(a.progress||0)});
  if(on.length){add(w,el('div','sub p',T('ON STAGE')));var el0=(Date.now()-D.at);
    on.slice(0,6).forEach(function(d,k){add(w,add(el('div','tr lv p'+(k===0?' on':'')),el('span','pos',d.progress!=null?Math.round(d.progress*100)+'%':'–'),el('span','bar'),flag(d.country),
      el('span','cd',code(d.name,taken)),clock(el('span','rt'),d.totalMs)))})}
  add(w,el('div','rule'));return w}
function bug(){var live=D.live.length>0;var b=el('div','bug');
  add(b,add(el('div','live'+(live?'':' off')),el('i'),el('span',null,live?T('LIVE'):T('BETWEEN CARS'))),el('div','what p',D.info.label));return b}
function lower(){var on=D.live.slice().sort(function(a,b){return (b.progress||0)-(a.progress||0)})[0];var w=el('div','lower p'+(on?'':' hide'));if(!on)return w;
  var el0=Date.now()-D.at,pr=Math.max(0,Math.min(1,on.progress||0));
  add(w,add(el('div','lt'),el('span','sk'),tagBox(on.team),el('span','nm',String(on.name||'').toUpperCase()),flag(on.country),clock(el('span','clk'),on.totalMs)));
  var pb=el('div','pb'),fill=el('b'),dot=el('u');fill.style.width=(pr*100)+'%';dot.style.left=(pr*100)+'%';add(pb,fill,dot);
  var km=D.info.lengthM?((pr*D.info.lengthM/1000).toFixed(1)+' / '+(D.info.lengthM/1000).toFixed(1)+' km'):Math.round(pr*100)+'%';
  add(w,add(el('div','prog'),pb,el('span',null,km)));return w}
function studio(){var w=el('div','studio'+(D.live.length?' hide':''));if(D.live.length)return w;
  var b=D.board.filter(function(r){return r.totalMs!=null});var pages=(b.length?['top']:[]).concat(['stage']);
  var pg=pages[Math.floor(Date.now()/1000/C.rotate)%pages.length];
  var tb=add(el('div','tabs'));pages.forEach(function(p){add(tb,el('div','tab'+(p===pg?' on':''),p==='top'?T('CLASSIFICATION'):T('THE STAGE')))});
  add(tb,add(el('div','tab bc'),el('i'),el('span',null,T('BETWEEN CARS'))));add(w,tb);
  add(w,add(el('div','sh'),el('span','k',D.info.label),el('span','sl'),el('span','n',String(D.info.stage||'').toUpperCase()),el('span','r',String(D.info.rally||'').toUpperCase())));
  if(pg==='top'){var lead=b[0].totalMs,cars={};b.slice(0,10).forEach(function(r){if(r.car)cars[r.car]=1});var many=Object.keys(cars).length>1;
    var box=el('div');add(box,add(el('div','row hd p'),el('span','ps',T('POS')),el('span','dn',T('DRIVER')),el('span','tm',T('TEAM')),many?el('span','cr',T('CAR')):null,el('span','ti',T('TIME')),el('span','gp',T('GAP'))));
    box.firstChild.firstChild.style.background='transparent';box.firstChild.firstChild.style.color='var(--soft)';box.firstChild.firstChild.style.fontSize='15px';
    b.slice(0,10).forEach(function(r,i){var tm=el('span','tm');add(tm,tagBox(r.team));
      add(box,add(el('div','row'),el('span','ps',String(i+1)),add(el('span','dn'),flag(r.country),document.createTextNode('  '+String(r.name||''))),tm,
        many?el('span','cr',r.car||''):null,el('span','ti',ms(r.totalMs)),el('span','gp',i?gap(r.totalMs-lead):'')))});
    add(w,box);add(w,add(el('div','foot p'),el('i'),el('span',null,T('{0} drivers on the board',D.drivers||b.length))))}
  else{var f=el('div');[[T('RALLY'),D.info.rally],[T('LENGTH'),D.info.lengthM?(D.info.lengthM/1000).toFixed(2)+' km':''],[T('SURFACE'),D.info.surface],
      [T('CAR'),[D.info.car,D.info.carClass].filter(Boolean).join('  ·  ')],[T('WEATHER'),D.info.weather],[T('TIME OF DAY'),D.info.time],
      [T('DRIVERS'),b.length?String(D.drivers||b.length):''],[T('BEST'),b.length?ms(b[0].totalMs)+'  ·  '+b[0].name:'']].forEach(function(x){
      if(x[1])add(f,add(el('div','fact'),el('b',null,x[0]),el('span',null,String(x[1]).toUpperCase())))});
    add(w,f);add(w,add(el('div','foot p'),el('i'),el('span',null,b.length?T('The next driver on the stage comes on by themselves.'):T('Nobody on the board yet.'))))}
  return w}
function mark(){return add(el('div','mark'),el('i'),add(el('div'),el('b',null,'ACR DAILY'),el('span',null,T('LIVE COVERAGE'))))}
// (a running time: its words set in place ten times a second between the API's answers, nothing drawn again: no flicker)
var clocks=[];function clock(e,v){if(v!=null){e.setAttribute('data-ms',v);e.setAttribute('data-at',D.at)}e.textContent=ms(v);clocks.push(e);return e}
var shownPage=null;
function draw(){if(!D.info)return;clocks=[];S.innerHTML='';if(has('tower')&&(D.live.length||!has('studio')))add(S,tower());if(has('bug'))add(S,bug());if(has('lower'))add(S,lower());if(has('studio'))add(S,studio());add(S,mark());
  shownPage=Math.floor(Date.now()/1000/C.rotate)}
function tick(){var now=Date.now();clocks.forEach(function(e){var v=e.getAttribute('data-ms');if(v!=null)e.textContent=ms(+v+(now-(+e.getAttribute('data-at'))))});
  if(!D.live.length&&shownPage!==Math.floor(now/1000/C.rotate))draw()}
function fail(e){S.innerHTML='';add(S,add(el('div','studio'),el('div','empty p',e.message||T('Not available'))))}
var tl=null;
function tickLive(){loadLive().then(draw).catch(function(){}).then(function(){clearTimeout(tl);tl=setTimeout(tickLive,Math.max(3,D.poll)*1000)})}
function tickAll(){load().then(function(){return loadLive().catch(function(){})}).then(draw).catch(fail).then(function(){setTimeout(tickAll,30000)})}
tickAll();setTimeout(tickLive,5000);setInterval(tick,100);
})();
</script></body></html>`;
}
