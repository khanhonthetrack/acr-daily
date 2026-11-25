// Broadcast overlays: TV graphics for a stream (OBS, vMix, Streamlabs: a "browser source" at 1920 x 1080), drawn from the
// public API (src/publicapi.js) like the embeds (src/embeds.js). The user, 24 Nov 2026: "the final goal is for people to
// be able to broadcast events, e-sport events here ... provide some API and guidance for broadcasters ... When there is
// no one on stage, there could be a full table of top 10 with full names, teams, nationality and driving times,
// switching tabs to the daily information, weather etc. MAKE IT FEEL LIKE REAL BROADCAST."
//
//   /broadcast/daily/<1|2>                 today's daily
//   /broadcast/tt/<1|2>                    this week's time trial stage
//   /broadcast/event/<id>[?code=]          an event (a championship's, a cup's, a ranked session's)
//   /broadcast/championship/<id>           a championship: its event open now (else the last one, else the next)
//   /broadcast/ranked/<series>[/<starts>]  a ranked session: a series' under way (else its next), a special event's
//                                          (/broadcast/ranked/skoda), or one session (its hour in ms)
//
// What it shows (the same look as WATCH in the game, src: client/acr_daily/ig_watch.py): top left the standings tower
// (the best ten, flags and three letters, then who is on the stage now, how far); top right the LIVE bug; at the bottom
// the driver furthest on (name, flag, team, how far, their time). Nobody on the stage: the studio in the middle, its
// pages in turn. An event's and a ranked session's pages (the user, 25 Nov 2026: "the participants list for ranked, the
// full queue list (if too long, it should slowly scroll after some time like on TV), current standings ... similar
// overlays for any leagues (participants, current standings of championships or standings after this SS)"):
//   entry     the entry list (a ranked session's registered drivers / start list, with ratings and cars)
//   queue     a ranked stage's queue: on the stage, on turn, waiting (when), on their break, done
//   stage     the stage's times (the stage under way, else the last one driven)
//   overall   the standings after that stage
//   champ     the championship's table for the event's season
//   rally     the itinerary (a ranked session before its start: the country, how many stages, the car, the countdown)
// Long lists scroll slowly, as on TV: held, then a row at a time to the end, held, the next page. While cars are on a
// stage a side panel under the LIVE bug has the stage's queue (UP NEXT) and the standings in turn.
// Options: parts=tower,bug,lower,studio,side (which to draw; all by default), pages=entry,queue,... (the studio's, in
// that order), studio=always (the studio's pages even while cars are on the stage: a scene of its own), bg=1 (a dark
// backdrop: to look at it in a browser; OBS shows the page see-through), rotate=<seconds> (each page at least, 10 by
// default), accent=RRGGBB, lang=xx, code= (a private rally's). The page scales itself to the source's size, its layout
// always 16:9.
// feed=1: the page as the ACR DAILY app serves it on the streamer's PC while WATCH runs (http://127.0.0.1:8833/, client
// broadcastfeed.py): its /feed.json, ten times a second, is the car WATCH follows (the lower third) and its dash: the gauge as
// in the game (revs round the dial, the speed, the gear on its plate, brake and throttle bars beside it; the user, 25
// Nov 2026: "did you forget to also include the gauge?"); the page follows WATCH to another stage by itself.

import { N_, langTag, t } from './i18n.js';

export const BROADCAST_HEADERS = { 'Content-Type': 'text/html; charset=utf-8', 'X-Content-Type-Options': 'nosniff',
  'Content-Security-Policy': "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline' https://fonts.googleapis.com; " +
    "font-src https://fonts.gstatic.com; img-src 'self' https://flagcdn.com data:; connect-src 'self'; frame-ancestors *; base-uri 'none'; form-action 'none'",
  'Referrer-Policy': 'strict-origin-when-cross-origin', 'Cache-Control': 'public, max-age=300', 'Vary': 'Accept-Language, Cookie' };

const WORDS = [N_("TODAY'S BEST"), N_("THIS WEEK'S BEST"), N_('STAGE BEST'), N_('ON STAGE'), N_('LIVE'), N_('BETWEEN CARS'),
  N_('CLASSIFICATION'), N_('THE STAGE'), N_('RALLY'), N_('LENGTH'), N_('SURFACE'), N_('CAR'), N_('WEATHER'), N_('TIME OF DAY'),
  N_('DRIVERS'), N_('BEST'), N_('POS'), N_('DRIVER'), N_('TEAM'), N_('TIME'), N_('GAP'), N_('DAILY · SS{0}'), N_('TIME TRIAL · TT{0}'),
  N_('{0} drivers on the board'), N_('Nobody on the board yet.'), N_('LIVE COVERAGE'), N_('FINISHED'), N_('RETIRED'),
  N_('The next driver on the stage comes on by themselves.'), N_('Not available'),
  N_('ENTRY LIST'), N_('START QUEUE'), N_('SS{0} QUEUE'), N_('SS{0} RESULTS'), N_('STANDINGS AFTER SS{0}'), N_('STANDINGS'),
  N_('CHAMPIONSHIP'), N_('THE RALLY'), N_('UP NEXT'), N_('RATING'), N_('NO.'), N_('STATE'), N_('POINTS'), N_('WINS'),
  N_('ON THE STAGE'), N_('ON TURN'), N_('WAITING'), N_('BREAK'), N_('DONE'), N_('OUT'), N_('STARTS IN'), N_('STAGES'),
  N_('{0} stages, drawn at the start'), N_('SS'), N_('KM'), N_('{0} drivers'), N_('Nobody registered yet.'),
  N_('No stage driven yet.'), N_('SPECIAL EVENT'), N_('PRIZE'), N_('{0} credits for every finisher'), N_('ENTRY'),
  N_('Free'), N_('RANKED'), N_('Nothing on now.'), N_('Results final'), N_('The stages are kept hidden until the event closes.'), N_('BRAKE'), N_('THROTTLE'), N_('GEAR')];

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

/** The overlay's page. kind: 'daily' | 'tt' | 'event' | 'championship' | 'ranked'; id: the slot, the event's id, the
 *  championship's, or a ranked session's '<series>[/<starts>]'; q: its URLSearchParams. */
export function broadcastPage(kind, id, q, site) {
  const words = Object.fromEntries(WORDS.map((w) => [w, t(w)]));
  const accent = /^[0-9a-fA-F]{6}$/.test(q.get('accent') || '') ? '#' + q.get('accent') : '#E30613';
  const parts = (q.get('parts') || 'tower,bug,lower,studio,side').split(',').map((s) => s.trim()).filter(Boolean);
  const pages = (q.get('pages') || '').split(',').map((s) => s.trim()).filter((s) => /^[a-z]+$/.test(s));
  const rotate = Math.max(4, Math.min(60, +(q.get('rotate') || 10) || 10));
  const cfg = { kind, id: String(id), code: q.get('code') || '', parts, pages, rotate, bg: q.get('bg') === '1', site,
    always: q.get('studio') === 'always', feed: q.get('feed') === '1' };
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
.tr.lv .pos{width:44px;font-size:16px}.tr .sn{font-size:15px;font-weight:700;color:var(--soft);margin-left:6px}.tr.on .sn{color:#fff}
.tr.on{background:var(--red)}.tr.on .pos,.tr.lv.on .pos{background:var(--navy);color:#fff}.tr.lv .pos{background:var(--soft)}
.fast{color:var(--fast)}.slow{color:var(--slow)}.rule{height:3px;background:var(--red)}
.bug{position:absolute;right:48px;top:48px;display:flex;gap:0;align-items:stretch}
.live{background:var(--red);display:flex;align-items:center;gap:9px;padding:6px 16px 6px 14px;font-weight:700;font-size:24px;letter-spacing:.12em}
.live i{width:11px;height:11px;border-radius:50%;background:#fff;animation:bl 1.4s infinite}.live.off{background:var(--grey)}.live.off i{animation:none;opacity:.7}
@keyframes bl{50%{opacity:.25}}.what{padding:8px 16px;font-weight:700;font-size:20px;letter-spacing:.1em;max-width:620px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.side{position:absolute;right:48px;top:112px;width:440px}
.side .sh{padding:8px 16px}.side .sh .k{font-size:17px}.side .row{height:38px;font-size:20px;padding:4px 14px;gap:10px}
.side .row .ps{width:32px;height:26px;font-size:17px}.side .row .ti{width:110px;font-size:19px}.side .row .st{width:120px;font-size:16px}
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
.tabs{display:flex;gap:4px;margin-bottom:6px;flex-wrap:nowrap;overflow:hidden}.tab{padding:7px 18px;font-weight:700;font-size:18px;letter-spacing:.14em;color:var(--soft);background:rgba(19,33,61,var(--a));white-space:nowrap}
.tab.on{background:var(--red);color:#fff}.tabs .bc{margin-left:auto;background:var(--grey);color:#fff;display:flex;align-items:center;gap:8px}.tabs .bc i{width:9px;height:9px;border-radius:50%;background:#fff}
.tabs .bc.lv{background:var(--red)}
.sh{background:var(--red);display:flex;align-items:center;gap:14px;padding:12px 22px;font-weight:700}
.sh .k{font-size:20px;letter-spacing:.12em;white-space:nowrap}.sh .n{font-size:34px;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.sh .r{font-size:20px;letter-spacing:.12em;white-space:nowrap}
.row{display:flex;align-items:center;gap:16px;padding:6px 22px;height:46px;font-size:24px;font-weight:500}
.row.hd{height:34px;font-size:15px;font-weight:700;letter-spacing:.14em;color:var(--soft)}
.row .ps{width:40px;height:32px;display:flex;align-items:center;justify-content:center;background:#fff;color:var(--navy);font-weight:700;font-size:22px;flex:none}
.row.hd .ps{background:transparent;color:var(--soft);font-size:15px}
.row.first .ps{background:var(--red);color:#fff}
.row .dn{flex:1;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:flex;align-items:center;gap:12px}.row .tm{width:120px}.row .cr{width:260px;font-size:19px;color:var(--soft);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.row .ti{width:140px;text-align:right;font-weight:700}.row .gp{width:110px;text-align:right;color:var(--soft)}.row .ss{width:118px;text-align:right;font-size:20px;color:var(--soft)}
.row .st{width:200px;text-align:right;font-weight:700;font-size:20px;letter-spacing:.06em}.row .rg{width:100px;text-align:right;color:var(--soft)}
.row .st.on{color:var(--fast)}.row .st.turn{color:#FFD60A}.row .st.out{color:var(--slow)}.row .st.done{color:var(--soft)}
.zebra>.row:nth-child(odd){background:rgba(19,33,61,var(--a))}.zebra>.row:nth-child(even){background:rgba(10,20,40,var(--a))}
.sc{overflow:hidden;position:relative}.sci{will-change:transform}
.fact{display:flex;align-items:center;padding:12px 22px;font-size:28px;font-weight:700}.facts>.fact:nth-child(odd){background:rgba(19,33,61,var(--a))}.facts>.fact:nth-child(even){background:rgba(10,20,40,var(--a))}
.fact b{width:260px;font-size:18px;letter-spacing:.16em;color:var(--soft)}
.big{font-size:64px;font-weight:700;letter-spacing:.04em}
.foot{display:flex;align-items:center;gap:10px;padding:9px 22px;font-size:19px;color:var(--soft)}.foot i{width:4px;height:18px;background:var(--red)}
.mark{position:absolute;left:48px;bottom:48px;display:flex;align-items:center;gap:12px}.mark i{width:7px;height:44px;background:var(--red);transform:skewX(-18deg)}
.mark b{display:block;font-size:30px;letter-spacing:.06em;line-height:1}.mark span{font-size:14px;letter-spacing:.18em;color:var(--soft);font-weight:700}
.mark img{height:64px;width:auto;margin-right:6px}
.empty{padding:26px;text-align:center;font-size:24px;color:var(--soft)}
.lower.wd{left:400px;width:840px;transform:none}.lower.wd.hide{transform:translateY(30px)}.lower.wd .lt .nm{max-width:360px}
.gauge{position:absolute;right:40px;bottom:30px;display:flex;align-items:flex-start;gap:8px;transition:opacity .4s}.gauge.off{opacity:0}
.ped{margin-top:170px;display:flex;flex-direction:column;gap:5px}.ped .bars{display:flex;gap:3px}.ped .bars i{width:9px;height:20px;transform:skewX(-14deg)}
.ped b{font-size:11px;letter-spacing:.14em;color:var(--soft)}.ped.br{align-items:flex-end}.ped.br i{background:#3A1A22}.ped.br i.on{background:#FF3B47}
.ped.thr i{background:#1F3318}.ped.thr i.on{background:#9BE22B}
.dial{width:300px;height:300px;position:relative}.dial svg{position:absolute;left:0;top:0}
.dial .kmh{position:absolute;left:50px;top:74px;width:200px;text-align:center;font-size:66px;font-weight:700;line-height:90px}
.dial .ku{position:absolute;left:116px;top:165px;width:68px;text-align:center;font-size:14px;font-weight:700}
.dial .gp{position:absolute;left:106px;top:188px;width:88px;height:86px;border-radius:8px;background:rgba(28,45,79,.96);border:2px solid #3A4F78;text-align:center}
.dial .gp b{display:block;font-size:10px;letter-spacing:.16em;color:var(--soft);margin-top:4px}.dial .gp span{display:block;font-size:44px;font-weight:700;line-height:58px}
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
function ms(v,d){if(v==null)return '';d=d==null?1:d;var t=Math.max(0,v),h=Math.floor(t/3600000),m=Math.floor(t%3600000/60000),s=(t%60000)/1000;var f=Math.pow(10,d);s=Math.floor(s*f)/f;
  return (h?h+':'+String(m).padStart(2,'0'):m)+':'+s.toFixed(d).padStart(d?3+d:2,'0')}
function gap(v){return v==null?'':(v>0?'+':'−')+(Math.abs(v)/1000).toFixed(1)}
function span(v){v=Math.max(0,v);var s=Math.floor(v/1000),d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60),x=s%60;
  return (d?d+'d ':'')+(d||h?h+':'+String(m).padStart(2,'0'):String(m))+':'+String(x).padStart(2,'0')}
function hm(t){return new Date(t).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}
function flag(c,cls){if(!c){return el('span','fl0')}var i=el('img',cls||'fl');i.src='https://flagcdn.com/w80/'+String(c).toLowerCase()+'.png';i.alt=String(c).toUpperCase();return i}
function code(n,taken){var l=Array.from(String(n||'').toUpperCase().replace(/[^\\p{L}\\p{N}]/gu,'')).join('')||'DRV';l=Array.from(l);l={slice:function(a,b){return this.c.slice(a,b).join('')},c:l};var cs=[l.slice(0,3),l.slice(0,2)+l.slice(-1),l.slice(0,1)+l.slice(2,4)];
  for(var i=0;i<cs.length;i++){var c=(cs[i]+'XXX').slice(0,3);if(!taken[c]){taken[c]=1;return c}}return l.slice(0,3)}
function tagOf(x){var tm=x&&(x.team||(x.look&&x.look.tag?{tag:x.look.tag.text,color:x.look.tag.color}:null));return tm&&tm.tag?tm:null}
function tagBox(tm){if(!tm||!tm.tag)return null;var b=el('span','tag',String(tm.tag).replace(/\\$[0-9a-fA-F]{3}|\\$[a-zA-Z<>]/g,'').slice(0,6).toUpperCase());
  b.style.background=tm.color?('#'+String(tm.color).replace('#','')):'#3A4F78';return b}
function get(u){return fetch(u,{cache:'no-store'}).then(function(r){return r.json().then(function(j){if(!r.ok)throw new Error(j.error||('error '+r.status));return j})})}
function api(p){return get('/api/v1'+p)}
var Q=C.code?'?code='+encodeURIComponent(C.code):'';
// D: what is shown. info (the stage's / event's facts), board (the tower's: the stage's best), live (on the stage now),
// and an event's / a ranked session's: ev {id, name, stages}, rows (its classification: each with stages[k].totalMs),
// entry (the entry list), queues (a ranked session's: one a stage), champ (the season's table), phase, starts
var D={info:null,board:[],live:[],poll:5,at:0,ev:null,rows:[],entry:null,queues:null,champ:null,phase:null,starts:null,special:null};
var MULTI=C.kind==='event'||C.kind==='championship'||C.kind==='ranked';

// ---- the data
function loadDaily(){
  if(C.kind==='daily')return api('/dailies').then(function(d){var x=(d.dailies||[]).filter(function(s){return String(s.slot)===C.id})[0];if(!x)throw new Error(T('Not available'));
    D.info={label:T('DAILY · SS{0}',C.id),best:T("TODAY'S BEST"),stage:x.stage,rally:x.rally,lengthM:x.lengthM,car:x.car,carClass:x.carClass,weather:x.weather,time:x.time,surface:x.surface};
    D.base='/dailies/'+d.date+'/'+C.id;return api(D.base)}).then(function(r){D.board=r.results||[];D.drivers=r.drivers});
  return api('/timetrials').then(function(d){var x=(d.stages||[]).filter(function(s){return String(s.slot)===C.id})[0];if(!x)throw new Error(T('Not available'));
    D.info={label:T('TIME TRIAL · TT{0}',C.id),best:T("THIS WEEK'S BEST"),stage:x.stage,rally:x.rally,car:x.car,carClass:x.carClass,weather:x.weather,time:x.time};
    D.base='/timetrials/'+d.week+'/'+C.id;return api(D.base)}).then(function(r){D.board=r.results||[]});
}
function loadEvent(id){
  return api('/events/'+id+Q).then(function(e){
    D.ev={id:e.id,name:e.name,stages:e.stages||[]};D.rows=e.results||[];D.phase=e.status;D.hidden=e.hidden&&e.hidden.stages?e.hidden:null;
    D.info={label:String(e.name||'').toUpperCase(),best:T('STAGE BEST'),rally:e.rally,car:e.car,carClass:e.carClass||(e.carClasses||[]).join(' · '),surface:e.surface};
    // (a championship's: its members as the entry list, its season's table)
    var h=e.holder||{};if(h.kind==='championship'&&h.id){return api('/championships/'+h.id).then(function(l){D.champName=l.name;
        if(!D.entry||C.kind!=='ranked')D.entry=(l.members||[]).filter(function(m){return m.role!=='pending'}).map(function(m){return {name:m.name,country:m.country,team:m.team}});
        return e.season?api('/championships/'+h.id+'/standings?season='+e.season.id).then(function(s){var t=(s.seasons||[])[0];D.champ=t?{name:t.name,rows:t.drivers||[]}:null}):null})
      .catch(function(){})}
    if(!D.entry||!D.entry.length)D.entry=D.rows.map(function(r){return {name:r.name,country:r.country,team:r.team,car:r.car}});
  })}
function loadChampionship(){
  return api('/championships/'+C.id).then(function(l){var ev=l.events||[],now=Date.now();
    var pick=ev.filter(function(e){return e.status==='open'||e.status==='running'})[0]||ev.filter(function(e){return e.closes<=now}).sort(function(a,b){return b.closes-a.closes})[0]||
      ev.sort(function(a,b){return a.opens-b.opens})[0];if(!pick)throw new Error(T('Nothing on now.'));return loadEvent(pick.id)})}
function loadRanked(){
  var p=C.id.split('/'),key=p[0];
  var which=p[1]?Promise.resolve(+p[1]):get('/api/liverallies').then(function(o){
    var sp=(o.specials||[]).filter(function(s){return s.key===key})[0];if(sp)return sp.starts;
    var ss=(o.sessions||[]).filter(function(s){return s.series===key});
    var x=ss.filter(function(s){return s.phase==='running'})[0]||ss.filter(function(s){return s.phase==='signup'||s.phase==='upcoming'}).sort(function(a,b){return a.starts-b.starts})[0];
    if(!x){var r=(o.recent||[]).filter(function(s){return s.series===key})[0];if(r)return r.starts}
    if(!x)throw new Error(T('Nothing on now.'));return x.starts});
  return which.then(function(starts){return get('/api/liverallies/'+key+'/'+starts)}).then(function(v){
    var s=v.series||{};D.starts=v.starts;D.phase=v.resultsOut?'over':v.phase;D.special=v.special?{prize:(v.prize&&v.prize.each)||s.prize||0,stages:s.stages}:null;
    D.series=s;D.info={label:String(s.name||'').toUpperCase()+(v.special?'':' · '+hm(v.starts)),best:T('STAGE BEST'),rally:v.rally,
      car:(s.cars||[]).length===1?s.cars[0].name:null,carClass:s.carClass,stagesN:(v.live&&v.live.stages)||3};
    if(v.event){var e=v.event;D.ev={id:v.eventId,name:e.name,stages:(e.stages||[]).map(function(x){return {no:x.no,name:x.name,lengthM:x.lengthM,weather:x.weatherLabel||x.weather,time:x.time,rally:x.rally}})};
      D.rows=(v.standings||[]).map(function(r){return {rank:r.rank,name:r.name,country:r.country,team:r.team,car:r.car,status:r.status,totalMs:r.totalMs,
        stages:(r.stages||[]).map(function(x){return x?{totalMs:x.totalMs}:null})}});
      D.queues=v.queues||[];D.entry=(D.queues[0]||[]).map(function(x){return {name:x.name,country:x.country,team:x.team,car:x.car}})}
    else{D.ev=null;D.rows=[];D.queues=null;D.entry=v.entrants||[]}
  })}
function load(){return C.kind==='daily'||C.kind==='tt'?loadDaily():C.kind==='event'?loadEvent(C.id):C.kind==='championship'?loadChampionship():loadRanked()}
function loadLive(){var p=MULTI?(D.ev?'/events/'+D.ev.id+'/live'+Q:null):D.base?D.base+'/live':null;if(!p)return Promise.resolve();
  return api(p).then(function(l){D.live=(l.drivers||[]).filter(function(d){return d.state==='live'||d.state==null});D.poll=l.pollSeconds||5;D.at=Date.now()})}

// ---- the stage in focus (an event's): the one the furthest car is on, else the last one driven
function lead(){return D.live.slice().sort(function(a,b){return ((b.stageNo||0)-(a.stageNo||0))||((b.progress||0)-(a.progress||0))})[0]}
function focusNo(){if(!MULTI||!D.ev)return null;var on=lead();
  if(on&&on.stageNo)return on.stageNo;var n=0;D.rows.forEach(function(r){(r.stages||[]).forEach(function(s,k){if(s&&s.totalMs!=null)n=Math.max(n,k+1)})});return n||null}
function stageOf(no){return D.ev&&no?(D.ev.stages||[]).filter(function(s){return s.no===no})[0]||D.ev.stages[no-1]:null}
function stageBoard(no){return D.rows.filter(function(r){var s=(r.stages||[])[no-1];return s&&s.totalMs!=null}).map(function(r){return {name:r.name,country:r.country,team:r.team,car:r.car,totalMs:r.stages[no-1].totalMs}})
  .sort(function(a,b){return a.totalMs-b.totalMs})}
function overallAfter(no){return D.rows.filter(function(r){for(var k=0;k<no;k++){var s=(r.stages||[])[k];if(!s||s.totalMs==null)return false}return r.status!=='dnf'&&r.status!=='dsq'})
  .map(function(r){var t=0,ss=[];for(var k=0;k<no;k++){t+=r.stages[k].totalMs;ss.push(r.stages[k].totalMs)}return {name:r.name,country:r.country,team:r.team,car:r.car,totalMs:t,ss:ss}})
  .sort(function(a,b){return a.totalMs-b.totalMs})}
function queueNo(){if(!D.queues)return null;var f=focusNo();var busy=D.queues.map(function(q,k){return q.some(function(x){return x.state==='turn'||x.state==='waiting'||x.state==='break'})?k:-1}).filter(function(k){return k>=0});
  return busy.length?busy[0]+1:f||1}
var STATE={driving:['ON THE STAGE','on'],turn:['ON TURN','turn'],waiting:['WAITING',''],'break':['BREAK',''],done:['DONE','done'],dnf:['OUT','out'],dns:['OUT','out'],retired:['OUT','out']};
function stateOf(x){var s=STATE[x.state]||[String(x.state||'').toUpperCase(),''];var w=T(s[0]);
  if(x.state==='done'&&x.timeMs!=null)w=ms(x.timeMs);else if(x.state==='waiting'&&x.estAt)w=T('WAITING')+' · '+hm(x.estAt);else if(x.state==='break'&&x.readyAt)w=T('BREAK')+' · '+hm(x.readyAt);
  return [w,s[1]]}

// ---- the parts
function tower(){var w=el('div','tower');var taken={};var no=focusNo(),st=stageOf(no);
  var lb=C.kind==='daily'?'SS'+C.id:C.kind==='tt'?'TT'+C.id:(no?'SS'+no:'');
  add(w,add(el('div','th'),lb?el('span',null,lb):null,lb?el('span','sl'):null,el('span','nm',String((st&&st.name)||D.info.stage||'').toUpperCase())));
  var b=(MULTI?(no?stageBoard(no):[]):D.board).filter(function(r){return r.totalMs!=null});
  if(b.length){add(w,el('div','sub p',D.info.best));var lead=b[0].totalMs;
    b.slice(0,10).forEach(function(r,i){add(w,add(el('div','tr p'),el('span','pos',String(i+1)),el('span','bar'),flag(r.country),el('span','cd',code(r.name,taken)),
      el('span','rt',i?gap(r.totalMs-lead):ms(r.totalMs))))})}
  var on=D.live.slice().sort(function(a,b){return ((b.stageNo||0)-(a.stageNo||0))||((b.progress||0)-(a.progress||0))});
  if(on.length){add(w,el('div','sub p',T('ON STAGE')));
    on.slice(0,6).forEach(function(d,k){add(w,add(el('div','tr lv p'+(k===0?' on':'')),el('span','pos',d.progress!=null?Math.round(d.progress*100)+'%':'–'),el('span','bar'),flag(d.country),
      el('span','cd',code(d.name,taken)),MULTI&&d.stageNo&&d.stageNo!==no?el('span','sn','SS'+d.stageNo):null,clock(el('span','rt'),d.totalMs)))})}
  add(w,el('div','rule'));return w}
function bug(){var live=D.live.length>0;var b=el('div','bug');
  add(b,add(el('div','live'+(live?'':' off')),el('i'),el('span',null,live?T('LIVE'):T('BETWEEN CARS'))),el('div','what p',D.info.label));return b}
function lower(){var fd=C.feed&&F.d&&F.d.on&&F.d.driver;var on=fd||lead();var w=el('div','lower p'+(on?'':' hide'));if(!on)return w;
  if(C.feed)w.classList.add('wd');
  var pr=Math.max(0,Math.min(1,on.progress||0)),st=MULTI?stageOf(on.stageNo):null,len=st?st.lengthM:D.info.lengthM;
  add(w,add(el('div','lt'),el('span','sk'),tagBox(tagOf(on)),el('span','nm',String(on.name||'').toUpperCase()),flag(on.country),clock(el('span','clk'),on.totalMs)));
  var pb=el('div','pb'),fill=el('b'),dot=el('u');fill.style.width=(pr*100)+'%';dot.style.left=(pr*100)+'%';add(pb,fill,dot);
  var km=len?((pr*len/1000).toFixed(1)+' / '+(len/1000).toFixed(1)+' km'):Math.round(pr*100)+'%';
  add(w,add(el('div','prog'),pb,el('span',null,(st?'SS'+on.stageNo+'  ·  ':'')+km)));return w}

// a list that scrolls when it is longer than vis rows: held, a row at a time to its end, held (tick moves it)
var ROW_S=1.5,HOLD_S=4;
function scroller(rows,vis,h){var box=el('div','sc zebra'),inner=el('div','sci zebra');rows.forEach(function(r){add(inner,r)});
  if(rows.length<=vis){rows.forEach(function(r){add(box,r)});return box}
  box.style.height=(vis*h)+'px';inner.setAttribute('data-n',rows.length-vis);inner.setAttribute('data-h',h);add(box,inner);return box}
function scrollTime(n,vis){return n>vis?HOLD_S*2+(n-vis)*ROW_S:0}
function headRow(cells){var r=el('div','row hd p');cells.forEach(function(c){if(c)add(r,el('span',c[1],c[0]))});return r}
function who(x,taken){var d=el('span','dn');add(d,flag(x.country),el('span',null,String(x.name||'')),tagBox(tagOf(x)));return d}

// the studio's pages: [{key, tab, title, n (rows: for its time), node()}]
var VIS=12,RH=46;
function pagesOf(){var out=[],no=focusNo();
  if(!MULTI){var b=D.board.filter(function(r){return r.totalMs!=null});if(b.length)out.push({key:'top',tab:T('CLASSIFICATION')});out.push({key:'stage',tab:T('THE STAGE')});return out}
  var qn=queueNo(),q=D.queues&&qn?D.queues[qn-1]||[]:[];
  if(D.entry&&(D.entry.length||C.kind==='ranked'))out.push({key:'entry',tab:T('ENTRY LIST'),n:D.entry.length});
  if(D.queues&&q.length&&D.phase!=='over')out.push({key:'queue',tab:qn>1?T('SS{0} QUEUE',qn):T('START QUEUE'),n:q.length,no:qn});
  if(no){out.push({key:'stage',tab:T('SS{0} RESULTS',no),n:stageBoard(no).length,no:no});
    if(no>1)out.push({key:'overall',tab:T('STANDINGS AFTER SS{0}',no),n:overallAfter(no).length,no:no})}
  if(D.champ&&D.champ.rows.length)out.push({key:'champ',tab:T('CHAMPIONSHIP'),n:D.champ.rows.length});
  out.push({key:'rally',tab:T('THE RALLY')});
  if(C.pages.length)out=C.pages.map(function(k){return out.filter(function(p){return p.key===k})[0]}).filter(Boolean);
  return out.length?out:[{key:'rally',tab:T('THE RALLY')}]}
var PG={list:[],i:0,at:0};
function pageDur(p){return Math.max(C.rotate,scrollTime(p.n||0,VIS)+2)*1000}
function curPage(now){var list=pagesOf();var keyNow=PG.list[PG.i]&&PG.list[PG.i].key;PG.list=list;
  var i=list.map(function(p){return p.key}).indexOf(keyNow);if(i<0){PG.i=0;PG.at=now}else PG.i=i;
  if(now-PG.at>=pageDur(list[PG.i])){PG.i=(PG.i+1)%list.length;PG.at=now}return list[PG.i]}

function studioHead(label,name,right){return add(el('div','sh'),el('span','k',label),el('span','sl'),el('span','n',String(name||'').toUpperCase()),right?el('span','r',String(right).toUpperCase()):null)}
function studio(live){var now=Date.now();var w=el('div','studio');var pg=curPage(now);
  var tb=add(el('div','tabs'));PG.list.forEach(function(p){add(tb,el('div','tab'+(p===pg?' on':''),p.tab))});
  add(tb,add(el('div','tab bc'+(live?' lv':'')),el('i'),el('span',null,live?T('LIVE'):T('BETWEEN CARS'))));add(w,tb);
  if(!MULTI)return dailyStudio(w,pg);
  var body=el('div'),foot=null,title=D.info.label,no=pg.no;
  if(pg.key==='entry'){add(w,studioHead(title,T('ENTRY LIST'),T('{0} drivers',D.entry.length)));
    var cars={};D.entry.forEach(function(e){if(e.car)cars[e.car]=1});var many=Object.keys(cars).length>1;var rated=D.entry.some(function(e){return e.rating!=null});
    add(body,headRow([[T('NO.'),'ps'],[T('DRIVER'),'dn'],many?[T('CAR'),'cr']:null,rated?[T('RATING'),'rg']:null]));
    if(!D.entry.length)add(body,el('div','empty p',T('Nobody registered yet.')));
    add(body,scroller(D.entry.map(function(e,i){return add(el('div','row'),el('span','ps',String(i+1)),who(e),many?el('span','cr',e.car||''):null,
      rated?el('span','rg',e.rating!=null?String(e.rating):'–'):null)}),VIS,RH))}
  else if(pg.key==='queue'){var q=D.queues[no-1]||[],st=stageOf(no);add(w,studioHead(title,no>1?T('SS{0} QUEUE',no):T('START QUEUE'),st?'SS'+no+' · '+st.name:''));
    var qc={};q.forEach(function(x){if(x.car)qc[x.car]=1});var qm=Object.keys(qc).length>1;
    add(body,headRow([[T('POS'),'ps'],[T('DRIVER'),'dn'],qm?[T('CAR'),'cr']:null,[T('STATE'),'st']]));
    add(body,scroller(q.map(function(x,i){var s=stateOf(x);return add(el('div','row'+(x.state==='turn'?' first':'')),el('span','ps',String(i+1)),who(x),qm?el('span','cr',x.car||''):null,el('span','st '+s[1],s[0]))}),VIS,RH))}
  else if(pg.key==='stage'||pg.key==='overall'){var st2=stageOf(no),list=pg.key==='stage'?stageBoard(no):overallAfter(no);
    add(w,studioHead(title,pg.key==='stage'?T('SS{0} RESULTS',no):T('STANDINGS AFTER SS{0}',no),st2?st2.name:''));
    var cars2={};list.forEach(function(r){if(r.car)cars2[r.car]=1});var many2=Object.keys(cars2).length>1;var lead=list.length?list[0].totalMs:0;
    var ssCols=pg.key==='overall'&&no<=5;
    add(body,headRow([[T('POS'),'ps'],[T('DRIVER'),'dn'],many2?[T('CAR'),'cr']:null].concat(ssCols?Array.from({length:no},function(_,k){return ['SS'+(k+1),'ss']}):[]).concat([[T('TIME'),'ti'],[T('GAP'),'gp']])));
    if(!list.length)add(body,el('div','empty p',T('No stage driven yet.')));
    add(body,scroller(list.map(function(r,i){var row=add(el('div','row'+(i===0?' first':'')),el('span','ps',String(i+1)),who(r),many2?el('span','cr',r.car||''):null);
      if(ssCols)r.ss.forEach(function(v){add(row,el('span','ss',ms(v)))});return add(row,el('span','ti',ms(r.totalMs)),el('span','gp',i?gap(r.totalMs-lead):''))}),VIS,RH))}
  else if(pg.key==='champ'){add(w,studioHead(title,T('CHAMPIONSHIP'),(D.champName||'')+(D.champ.name?' · '+D.champ.name:'')));
    add(body,headRow([[T('POS'),'ps'],[T('DRIVER'),'dn'],[T('WINS'),'rg'],[T('POINTS'),'ti']]));
    add(body,scroller(D.champ.rows.map(function(r,i){return add(el('div','row'+(i===0?' first':'')),el('span','ps',String(r.rank||i+1)),who(r),el('span','rg',String(r.wins||0)),el('span','ti',String(r.points||0)))}),VIS,RH))}
  else{add(w,studioHead(title,T('THE RALLY'),D.info.rally||''));var f=el('div','facts');
    if(D.ev&&D.ev.stages.length){add(f,headRow([[T('SS'),'ps'],[T('THE STAGE'),'dn'],[T('KM'),'gp'],[T('WEATHER'),'cr'],[T('TIME OF DAY'),'gp']]));
      D.ev.stages.forEach(function(s,k){add(f,add(el('div','row'),el('span','ps',String(s.no||k+1)),el('span','dn',s.name||'?'),el('span','gp',s.lengthM?(s.lengthM/1000).toFixed(1):''),
        el('span','cr',s.weather||''),el('span','gp',s.time||'')))})}
    else{if(D.starts&&Date.now()<D.starts)add(f,add(el('div','fact'),el('b',null,T('STARTS IN')),clockDown(el('span','big'),D.starts)));
      [[T('RALLY'),D.info.rally],[T('STAGES'),D.info.stagesN?T('{0} stages, drawn at the start',D.info.stagesN):''],[T('CAR'),D.info.car||D.info.carClass],
       [T('ENTRY'),D.special?T('Free'):''],[T('PRIZE'),D.special&&D.special.prize?T('{0} credits for every finisher',D.special.prize):'']].forEach(function(x){
        if(x[1])add(f,add(el('div','fact'),el('b',null,x[0]),el('span',null,String(x[1]).toUpperCase())))})}
    add(body,f)}
  add(w,body);add(w,el('div','rule'));
  add(w,add(el('div','foot p'),el('i'),el('span',null,D.phase==='over'||D.phase==='closed'?T('Results final'):D.hidden&&pg.key==='rally'?T('The stages are kept hidden until the event closes.'):live?T('LIVE'):T('The next driver on the stage comes on by themselves.'))));
  return w}
function dailyStudio(w,pg){var b=D.board.filter(function(r){return r.totalMs!=null});
  add(w,studioHead(D.info.label,D.info.stage,D.info.rally));
  if(pg.key==='top'){var lead=b[0].totalMs,cars={};b.slice(0,10).forEach(function(r){if(r.car)cars[r.car]=1});var many=Object.keys(cars).length>1;
    var box=el('div','zebra');add(box,headRow([[T('POS'),'ps'],[T('DRIVER'),'dn'],[T('TEAM'),'tm'],many?[T('CAR'),'cr']:null,[T('TIME'),'ti'],[T('GAP'),'gp']]));
    b.slice(0,10).forEach(function(r,i){var tm=el('span','tm');add(tm,tagBox(tagOf(r)));var dn=el('span','dn');add(dn,flag(r.country),el('span',null,String(r.name||'')));
      add(box,add(el('div','row'+(i===0?' first':'')),el('span','ps',String(i+1)),dn,tm,many?el('span','cr',r.car||''):null,el('span','ti',ms(r.totalMs)),el('span','gp',i?gap(r.totalMs-lead):'')))});
    add(w,box);add(w,add(el('div','foot p'),el('i'),el('span',null,T('{0} drivers on the board',D.drivers||b.length))))}
  else{var f=el('div','facts');[[T('RALLY'),D.info.rally],[T('LENGTH'),D.info.lengthM?(D.info.lengthM/1000).toFixed(2)+' km':''],[T('SURFACE'),D.info.surface],
      [T('CAR'),[D.info.car,D.info.carClass].filter(Boolean).join('  ·  ')],[T('WEATHER'),D.info.weather],[T('TIME OF DAY'),D.info.time],
      [T('DRIVERS'),b.length?String(D.drivers||b.length):''],[T('BEST'),b.length?ms(b[0].totalMs)+'  ·  '+b[0].name:'']].forEach(function(x){
      if(x[1])add(f,add(el('div','fact'),el('b',null,x[0]),el('span',null,String(x[1]).toUpperCase())))});
    add(w,f);add(w,add(el('div','foot p'),el('i'),el('span',null,b.length?T('The next driver on the stage comes on by themselves.'):T('Nobody on the board yet.'))))}
  return w}
// while cars are on the stage: UP NEXT (a ranked stage's queue) and the standings, in turn, under the LIVE bug
var SD={i:0,at:0};
function side(){if(!MULTI||!D.ev)return null;var now=Date.now(),opts=[],qn=queueNo(),no=focusNo();
  if(D.queues&&qn){var q=(D.queues[qn-1]||[]).filter(function(x){return x.state==='turn'||x.state==='waiting'||x.state==='break'});if(q.length)opts.push({k:'next',rows:q,no:qn})}
  if(no){var o=no>1?overallAfter(no):stageBoard(no);if(o.length)opts.push({k:'stand',rows:o,no:no})}
  if(!opts.length)return null;var dur=function(o){return Math.max(C.rotate,scrollTime(o.rows.length,8)+2)*1000};
  if(SD.i>=opts.length)SD.i=0;if(!SD.at)SD.at=now;if(now-SD.at>=dur(opts[SD.i])){SD.i=(SD.i+1)%opts.length;SD.at=now}var o=opts[SD.i];
  var w=el('div','side');add(w,add(el('div','sh'),el('span','k',o.k==='next'?T('UP NEXT')+' · SS'+o.no:(o.no>1?T('STANDINGS AFTER SS{0}',o.no):T('SS{0} RESULTS',o.no)))));
  var lead=o.rows[0].totalMs;
  add(w,scroller(o.rows.map(function(x,i){var r=add(el('div','row'),el('span','ps',String(i+1)),who(x));
    if(o.k==='next'){var s=stateOf(x);add(r,el('span','st '+s[1],x.state==='waiting'&&x.estAt?hm(x.estAt):s[0]))}else add(r,el('span','ti',i?gap(x.totalMs-lead):ms(x.totalMs)));return r}),8,38));
  add(w,el('div','rule'));return w}
// ---- the gauge (feed=1): built once, its parts set in place ten times a second
var F={d:null,at:0,g:null};var REV_N=28,PED_N=12;
function gaugeEl(){var g=el('div','gauge off'),NS='http://www.w3.org/2000/svg';
  function bars(cls,label){var p=el('div','ped '+cls),b=el('div','bars');for(var i=0;i<PED_N;i++)add(b,el('i'));add(p,b,el('b',null,label));return p}
  var br=bars('br',T('BRAKE')),th=bars('thr',T('THROTTLE')),dial=el('div','dial');
  var svg=document.createElementNS(NS,'svg');svg.setAttribute('width','300');svg.setAttribute('height','300');
  function a(n){var c=document.createElementNS(NS,n);return c}var c=150,R=146;
  var disc=a('circle');disc.setAttribute('cx',c);disc.setAttribute('cy',c);disc.setAttribute('r',R);disc.setAttribute('fill','rgba(14,24,44,.91)');disc.setAttribute('stroke','rgba(150,175,215,.8)');disc.setAttribute('stroke-width','2');svg.appendChild(disc);
  var inner=a('circle');inner.setAttribute('cx',c);inner.setAttribute('cy',c);inner.setAttribute('r',R-30);inner.setAttribute('fill','none');inner.setAttribute('stroke','rgba(120,150,200,.28)');svg.appendChild(inner);
  [[c-R*.8,c-34],[c+34,c+R*.8]].forEach(function(x){var l=a('line');l.setAttribute('x1',x[0]);l.setAttribute('x2',x[1]);l.setAttribute('y1',176);l.setAttribute('y2',176);l.setAttribute('stroke','rgba(225,232,245,.9)');l.setAttribute('stroke-width','2');svg.appendChild(l)});
  var segs=[];for(var i=0;i<REV_N;i++){var ang=(-16+(98+16)*(i+.5)/REV_N)*Math.PI/180,h=(114/REV_N*.32)*Math.PI/180,ri=R-31,ro=R-6;
    var pts=[[ri,-h],[ro,-h],[ro,h],[ri,h]].map(function(p){return (c+p[0]*Math.cos(ang+p[1])).toFixed(1)+','+(c-p[0]*Math.sin(ang+p[1])).toFixed(1)}).join(' ');
    var s=a('polygon');s.setAttribute('points',pts);svg.appendChild(s);segs.push([s,i>=REV_N-4])}
  add(dial,svg,el('div','kmh','–'),el('div','ku','Km/h'),add(el('div','gp'),el('b',null,T('GEAR')),el('span',null,'–')));
  add(g,br,dial,th);F.g={el:g,segs:segs,kmh:dial.querySelector('.kmh'),gear:dial.querySelector('.gp span'),br:br.querySelectorAll('i'),th:th.querySelectorAll('i')};return g}
function gaugeSet(){var G=F.g;if(!G)return;var d=F.d&&F.d.dash,on=!!(F.d&&F.d.on&&d);G.el.className='gauge'+(on?'':' off');if(!on)return;
  var n=Math.round(REV_N*Math.max(0,Math.min(1,d.rpm_frac||0)));G.segs.forEach(function(s,i){s[0].setAttribute('fill',i<n?(s[1]?'#FF3C46':'#B0EE28'):(s[1]?'rgba(60,30,36,.6)':'rgba(40,60,40,.5)'))});
  G.kmh.textContent=d.kmh!=null?String(Math.round(d.kmh)):'–';var g=d.gear;G.gear.textContent=g==null?'–':g===0?'R':g===1?'N':String(g-1);
  function lit(nodes,v,rev){var k=Math.round(PED_N*Math.max(0,Math.min(1,v||0)));for(var i=0;i<nodes.length;i++){var p=rev?nodes.length-1-i:i;nodes[i].className=p<k?'on':''}}
  lit(G.br,d.brake,true);lit(G.th,d.gas,false)}
function feedLoad(){fetch('/feed.json',{cache:'no-store'}).then(function(r){return r.json()}).then(function(j){F.d=j;F.at=Date.now();
    if(j&&j.page&&j.page!==location.pathname){location.replace(j.page+'?feed=1');return}gaugeSet();
    var dv=j&&j.on&&j.driver,lw=S.querySelector('.lower');if(!dv||!lw||lw.classList.contains('hide')){if(dv&&!lw)draw();return}
    var ck=lw.querySelector('.clk');if(ck&&dv.totalMs!=null){ck.setAttribute('data-ms',dv.totalMs);ck.setAttribute('data-at',Date.now())}
    var nm=lw.querySelector('.nm');if(nm&&nm.textContent!==String(dv.name||'').toUpperCase())draw();
    var p=Math.max(0,Math.min(1,dv.progress||0)),b=lw.querySelector('.pb b'),u=lw.querySelector('.pb u');if(b){b.style.width=(p*100)+'%';u.style.left=(p*100)+'%'}}).catch(function(){F.d=null;gaugeSet()})}
function mark(){var m=el('div','mark');if(C.kind==='ranked'){var i=el('img');i.src='/series/'+C.id.split('/')[0]+'-logo.webp';i.onerror=function(){i.remove()};add(m,i)}
  return add(m,el('i'),add(el('div'),el('b',null,'ACR DAILY'),el('span',null,T('LIVE COVERAGE'))))}
// (a running time: its words set in place ten times a second between the API's answers, nothing drawn again: no flicker)
var clocks=[],downs=[];function clock(e,v){if(v!=null){e.setAttribute('data-ms',v);e.setAttribute('data-at',D.at)}e.textContent=ms(v);clocks.push(e);return e}
function clockDown(e,to){e.textContent=span(to-Date.now());downs.push([e,to]);return e}
var shown=null;
function draw(){if(!D.info)return;clocks=[];downs=[];S.innerHTML='';var live=D.live.length>0||!!(C.feed&&F.d&&F.d.on&&F.d.driver),stud=has('studio')&&(!live||C.always);
  if(has('tower')&&(live||!has('studio'))&&!(C.always&&has('studio')))add(S,tower());if(has('bug'))add(S,bug());
  if(live&&has('side')&&!stud)add(S,side());if(has('lower')&&!stud)add(S,lower());if(stud)add(S,studio(live));add(S,mark());if(C.feed){add(S,F.g?F.g.el:gaugeEl());gaugeSet()}
  shown=(PG.list[PG.i]||{}).key+':'+PG.i+':'+SD.i;scrollTick()}
function scrollTick(){var now=Date.now();document.querySelectorAll('.sci[data-n]').forEach(function(e){var n=+e.getAttribute('data-n'),h=+e.getAttribute('data-h');
  var since=(now-(e.closest('.side')?SD.at:PG.at))/1000,k=Math.max(0,Math.min(n,(since-HOLD_S)/ROW_S));e.style.transform='translateY('+(-k*h)+'px)'})}
function tick(){var now=Date.now();clocks.forEach(function(e){var v=e.getAttribute('data-ms');if(v!=null)e.textContent=ms(+v+(now-(+e.getAttribute('data-at'))))});
  downs.forEach(function(x){x[0].textContent=span(x[1]-now)});scrollTick();
  // (the studio's page or the side panel's due to change: drawn again)
  var live=D.live.length>0;if(has('studio')&&(!live||C.always)){var p=PG.list[PG.i];if(p&&now-PG.at>=pageDur(p))draw()}
  else if(live&&MULTI&&has('side')&&now-SD.at>=C.rotate*1000)draw()}
function fail(e){S.innerHTML='';add(S,add(el('div','studio'),el('div','empty p',e.message||T('Not available'))))}
var tl=null;
function tickLive(){loadLive().then(draw).catch(function(){}).then(function(){clearTimeout(tl);tl=setTimeout(tickLive,Math.max(3,D.poll)*1000)})}
// (an event's or a ranked session's standings and queues change as it goes: asked again every 15 s; a daily's every 30)
function tickAll(){load().then(function(){return loadLive().catch(function(){})}).then(draw).catch(fail).then(function(){setTimeout(tickAll,MULTI?15000:30000)})}
tickAll();setTimeout(tickLive,5000);setInterval(tick,100);
if(C.feed)setInterval(feedLoad,100);
})();
</script></body></html>`;
}
