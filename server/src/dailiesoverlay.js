// ACR DAILY: Dailies, the stream overlay for broadcasting the dailies (the user, 25 Nov 2026: "a stream overlay ... for
// twitch (16:9) where ACR is streamed, 21:9 resolution, 3440x1440; the remaining should be some rankings, or the AI
// commentary text; ACR Daily logo appearing. This stream overlay only focuses on broadcasting dailies").
//
//   /broadcast/dailies     a 1920 x 1080 browser source: the game on top, its 21:9 picture scaled to 1920 x 804 (the
//                          page leaves that see-through), and under it a band: the logo, both dailies' boards and the
//                          commentary
//
// The band: left the logo, the day and the time to the next dailies; then SS1's and SS2's boards (the best six, then
// the next six and so on in turn, as on TV; the drivers on that stage now at the foot, their time running); right
// the commentary: who is on a stage now (with feed=1, the car WATCH follows), then the lines, newest on top. The lines
// come from what the page sees change (a driver away, halfway, a finish with its place and gap, a new fastest time, a
// driver out) and, when nothing happens for a while, the facts of the day (who leads and by how much, the closest
// gaps, the conditions, how long is left), in the plain voice of the website's old live ticker.
// Options: bg=1 (a stand-in picture where the game goes, to look at it in a browser), accent=RRGGBB, lang=xx, feed=1
// (served by the ACR DAILY app on the streamer's PC, client broadcastfeed.py: its /feed.json is the car WATCH follows),
// rows=4..8 (a board's rows, 6 by default), page=<seconds> (a board's page, 8 by default), ai=0 (no Claude lines:
// src/commentary.js writes the lines on what happens when the server has a Claude key; without one, the rules above).

import { N_, langTag, t } from './i18n.js';
import { BROADCAST_HEADERS } from './broadcast.js';

export { BROADCAST_HEADERS };

const WORDS = [N_('DAILIES'), N_('NEW DAILIES IN'), N_('ON STAGE'), N_('ON CAM'), N_('BETWEEN CARS'), N_('COMMENTARY'),
  N_('{0} drivers'), N_('Nobody on the board yet.'), N_('P{0}–{1} of {2}'), N_('Not available'), N_('LIVE'),
  N_('The next car on a stage comes on by itself.'),
  // the commentary's lines
  N_('SS{0} today: {1}, {2}, {3} km in the {4}.'), N_('SS{0} conditions: {1}, {2}.'),
  N_('{0} leads SS{1} on {2}, {3} s up on {4}.'), N_('{0} leads SS{1} on {2}.'), N_('{0} is away on SS{1}.'),
  N_('{0} is halfway through SS{1}, {2} on the clock.'), N_('{0} goes fastest on SS{1}: {2}, {3} s clear of {4}.'),
  N_('{0} sets the first time on SS{1}: {2}.'), N_('{0} finishes SS{1} in {2}: P{3}, {4} s off {5}.'),
  N_('One reset on the run.'), N_('{0} resets on the run.'), N_('{0} improves on SS{1} to {2}, now P{3}.'), N_('{0} is out of SS{1}.'),
  N_('{0} drivers have a time on SS{1}.'), N_('{0} drivers have a time on SS{1}, {2} out.'),
  N_('{0} s between {1} (P{2}) and {3} (P{4}) on SS{5}.'), N_('{0} left to drive today\'s dailies.'),
  N_('Nobody has a time on SS{0} yet.')];

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

// brand/acr-daily-logo-white.svg (the mark and the letters A, C, R), drawn in the band as it is
const LOGO = '<svg class="logo" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 163.6 200" aria-hidden="true"><path fill="#F4F4F5" fill-rule="evenodd" d="M110.5 2.6L121.4 29.5C122.1 31.3 121.3 33.3 119.5 34C117.7 34.7 115.7 33.9 115 32.1L104.1 5.2C103.4 3.4 104.3 1.4 106 0.7C107.8 0 109.8 0.9 110.5 2.6ZM101.9 18L108.6 34.7C109.3 36.4 108.5 38.4 106.7 39.2C104.9 39.9 102.9 39 102.2 37.3L95.5 20.6C94.8 18.9 95.6 16.8 97.4 16.1C99.1 15.4 101.2 16.3 101.9 18ZM92.7 32.2L95.8 39.8C96.5 41.6 95.7 43.6 93.9 44.3C92.1 45 90.1 44.2 89.4 42.4L86.3 34.7C85.6 33 86.4 31 88.2 30.3C90 29.5 92 30.4 92.7 32.2ZM74.2 65.7L78.3 75.9C86.7 74.8 94.7 79.6 97.9 87.4C101 95.2 98.6 104.2 91.8 109.2L108.3 150.1C116.7 149.1 124.7 153.8 127.9 161.6C131 169.4 128.6 178.4 121.8 183.5L125.9 193.7L138.7 188.5C151 183.6 159.1 169.9 161.3 150.6C163.6 131.3 159.7 107.8 150.7 85.4L137.8 53.4C135.2 47.1 127.9 44 121.6 46.5L79.3 63.6C76.1 64.9 74.2 65.7 74.2 65.7ZM110.1 66.1L141.2 143.1C144.6 136.2 146.2 127.6 145.9 118.3C145.7 109 143.6 99.1 139.8 89.8L130 65.5C128.6 62 124.5 60.3 121 61.7ZM86 107.8C78.6 110.8 70.2 107.2 67.2 99.8C64.2 92.4 67.8 83.9 75.2 80.9C82.6 77.9 91 81.5 94 88.9C97 96.4 93.5 104.8 86 107.8ZM116 182C108.6 185 100.2 181.5 97.2 174C94.2 166.6 97.7 158.2 105.2 155.2C112.6 152.2 121 155.8 124 163.2C127 170.6 123.5 179 116 182Z"/><path fill="#F4F4F5" d="M21.5 86.4L21.3 81C21.4 80.9 21.4 80.8 21.3 80.7C21.2 80.7 21.1 80.6 21 80.6L14.8 80.6C14.6 80.6 14.4 80.7 14.3 81L13 86.4C12.8 87 12.4 87.4 11.8 87.4L1 87.4C0.3 87.4 0 87 0.2 86.2L15.8 38.6C16 38 16.4 37.7 17.1 37.7L29.7 37.7C30.3 37.7 30.7 38 30.7 38.6L34.6 86.2L34.6 86.4C34.6 87 34.3 87.4 33.6 87.4L22.4 87.4C21.7 87.4 21.4 87 21.5 86.4ZM17.4 70.4L20.8 70.4C20.9 70.4 21 70.3 21.1 70L20.8 56.9C20.8 56.7 20.8 56.6 20.7 56.7C20.6 56.7 20.5 56.8 20.5 56.9L17.2 70C17.1 70.3 17.2 70.4 17.4 70.4ZM24.4 132.1C24.4 131.6 24.4 130.8 24.5 129.7L27.1 109C27.6 104.4 29.5 100.7 32.5 98C35.6 95.3 39.4 94 44 94C48.1 94 51.3 95.1 53.8 97.4C56.2 99.6 57.4 102.7 57.4 106.6C57.4 107 57.3 107.8 57.2 109L57.2 109.3C57.1 109.7 57 109.9 56.8 110.1C56.6 110.4 56.3 110.5 56 110.5L45.1 110.8C44.4 110.8 44.1 110.5 44.2 109.8L44.4 108C44.5 107.2 44.4 106.6 44 106.1C43.7 105.7 43.2 105.4 42.6 105.4C41.9 105.4 41.4 105.7 40.9 106.1C40.5 106.6 40.2 107.2 40.1 108L37.4 130.8C37.3 131.6 37.4 132.2 37.7 132.7C38 133.2 38.5 133.4 39.1 133.4C39.8 133.4 40.3 133.2 40.8 132.7C41.2 132.3 41.5 131.6 41.6 130.8L41.8 128.9C41.9 128.6 42 128.3 42.2 128.2C42.4 128 42.7 127.9 43 127.9L53.8 128.3C54.2 128.3 54.4 128.4 54.6 128.6C54.7 128.8 54.8 129.1 54.7 129.4L54.7 129.7C54.1 134.3 52.3 138 49.2 140.7C46.1 143.4 42.3 144.8 37.7 144.8C33.6 144.8 30.3 143.7 27.9 141.4C25.6 139.1 24.4 136 24.4 132.1ZM63 199.1L61 181.2C61 181 60.9 180.9 60.7 180.9C60.6 180.9 60.5 181 60.5 181.3L58.3 198.9C58.2 199.3 58.1 199.5 57.9 199.7C57.7 199.9 57.4 200 57.1 200L46.2 200C45.9 200 45.7 199.9 45.5 199.7C45.4 199.5 45.3 199.3 45.3 198.9L51.2 151.4C51.2 151 51.3 150.8 51.6 150.6C51.8 150.4 52 150.3 52.3 150.3L67.8 150.3C71.6 150.3 74.6 151.5 76.8 153.9C79 156.3 80.1 159.5 80.1 163.5C80.1 164.6 80.1 165.5 80 166.1C79.7 168.7 78.9 171.1 77.8 173.1C76.6 175.2 75.2 176.9 73.4 178.1C73.1 178.3 73.1 178.4 73.2 178.6L76.2 198.8L76.2 199.1C76.2 199.4 76.1 199.6 75.9 199.8C75.8 199.9 75.5 200 75.2 200L64 200C63.4 200 63.1 199.7 63 199.1ZM63.2 161.7C62.9 161.7 62.8 161.9 62.8 162.1L61.7 170.4C61.7 170.6 61.9 170.8 62.1 170.8L63 170.8C64.2 170.8 65.1 170.3 65.9 169.3C66.7 168.3 67.1 166.9 67.1 165.1C67.1 164.1 66.8 163.2 66.3 162.6C65.8 162 65.1 161.7 64.2 161.7Z"/></svg>';

/** The overlay's page; q: its URLSearchParams. */
export function dailiesOverlayPage(q, site) {
  const words = Object.fromEntries(WORDS.map((w) => [w, t(w)]));
  const accent = /^[0-9a-fA-F]{6}$/.test(q.get('accent') || '') ? '#' + q.get('accent') : '#E30613';
  const cfg = { bg: q.get('bg') === '1', feed: q.get('feed') === '1', site, lang: langTag(), ai: q.get('ai') !== '0',
    lq: /^[a-z]{2}$/.test(q.get('lang') || '') ? q.get('lang') : '',
    rows: Math.max(4, Math.min(8, +(q.get('rows') || 6) || 6)), page: Math.max(4, Math.min(60, +(q.get('page') || 8) || 8)) };
  return `<!doctype html><html lang="${esc(langTag())}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ACR DAILY: Dailies</title><meta name="robots" content="noindex">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700;800&display=swap">
<style>
:root{--navy:#0A1428;--navy2:#13213D;--navy3:#1C2D4F;--line:#2A3B60;--red:${esc(accent)};--white:#fff;--soft:#C9D1E0;--dim:#8391AB;--grey:#5C6A84;--fast:#2BD96B;--slow:#FF453A}
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:transparent}
#stage{position:absolute;left:0;top:0;width:1920px;height:1080px;transform-origin:0 0;font-family:"Barlow Condensed",system-ui,sans-serif;color:var(--white);font-variant-numeric:tabular-nums}
/* the game: 3440 x 1440 (21:9) at 1920 x 804, left see-through */
.game{position:absolute;left:0;top:0;width:1920px;height:804px}
.bg .game{background:linear-gradient(180deg,#5d7590 0%,#a9b9c6 38%,#d9e0e4 47%,#6f7766 49%,#3d4434 70%,#22261d 100%)}
.bg .game:after{content:"GAME  ·  3440 × 1440  →  1920 × 804";position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);font-size:30px;letter-spacing:.2em;color:rgba(255,255,255,.55);font-weight:700}
/* the band */
.band{position:absolute;left:0;top:804px;width:1920px;height:276px;background:linear-gradient(180deg,#101D38 0%,#0A1428 60%,#08101F 100%);overflow:hidden}
.band:before{content:"";position:absolute;left:0;top:0;right:0;height:4px;background:var(--red)}
.band:after{content:"";position:absolute;left:0;top:4px;right:0;height:1px;background:rgba(255,255,255,.18)}
.stripes{position:absolute;right:-40px;top:4px;bottom:0;width:420px;background:repeating-linear-gradient(-62deg,rgba(255,255,255,.025) 0 14px,transparent 14px 28px);pointer-events:none}
/* the brand */
.brand{position:absolute;left:28px;top:24px;width:300px;height:228px}
.brand .logo{position:absolute;left:0;top:0;height:132px;width:auto}
.brand .wm{position:absolute;left:122px;top:2px}
.brand .wm b{display:block;font-size:48px;font-weight:800;letter-spacing:.03em;line-height:.92}
.brand .wm .dl{display:inline-block;margin-top:9px;background:var(--red);padding:1px 14px 0 12px;font-size:28px;font-weight:700;letter-spacing:.16em;transform:skewX(-10deg)}
.brand .wm .dl span{display:inline-block;transform:skewX(10deg)}
.brand .day{position:absolute;left:0;top:146px;font-size:18px;font-weight:700;letter-spacing:.16em;color:var(--soft);white-space:nowrap}
.brand .cd{position:absolute;left:0;bottom:0;width:300px;display:flex;align-items:center;background:var(--navy2);border-left:4px solid var(--red)}
.brand .cd span{padding:8px 12px;font-size:16px;font-weight:700;letter-spacing:.14em;color:var(--soft);flex:1}
.brand .cd b{padding:4px 14px;font-size:30px;font-weight:700}
.com .tt .url{margin-left:auto;font-weight:600;letter-spacing:.1em;color:var(--dim);text-transform:lowercase}
/* a board */
.board{position:absolute;top:24px;width:500px;height:228px}
.board .hd{display:flex;align-items:center;height:40px;background:var(--navy3)}
.board .ss{background:var(--red);height:40px;padding:0 12px;display:flex;align-items:center;font-size:26px;font-weight:800;letter-spacing:.04em}
.board .nm{padding:0 12px;font-size:25px;font-weight:700;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.board .ry{padding:0 12px;font-size:16px;font-weight:700;letter-spacing:.14em;color:var(--soft);white-space:nowrap}
.board .mt{display:flex;align-items:center;gap:10px;height:26px;padding:0 12px;font-size:15px;font-weight:600;letter-spacing:.06em;color:var(--dim);white-space:nowrap;overflow:hidden;border-bottom:1px solid var(--line)}
.board .mt .pg{margin-left:auto;color:var(--soft);letter-spacing:.1em}
.rows{position:relative;transition:opacity .35s}.rows.out{opacity:0}
.r{display:flex;align-items:center;gap:9px;height:27px;padding:0 12px 0 8px;font-size:20px;font-weight:600}
.r:nth-child(odd){background:rgba(19,33,61,.6)}
.r .ps{width:30px;height:22px;display:flex;align-items:center;justify-content:center;background:#fff;color:var(--navy);font-weight:800;font-size:16px;flex:none}
.r.p1 .ps{background:var(--red);color:#fff}
.r .fl{width:24px;height:16px;object-fit:cover;flex:none;border-radius:2px;box-shadow:0 0 0 1px rgba(255,255,255,.15)}.r .fl0{width:24px;flex:none}
.r .dn{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:700}
.tag{font-weight:700;font-size:14px;padding:1px 6px;letter-spacing:.05em;flex:none}
.r .tm{width:96px;text-align:right;font-weight:700}.r .gp{color:var(--soft);font-weight:600}
.r.lv{background:rgba(227,6,19,.22)!important;box-shadow:inset 4px 0 0 var(--red)}
.r.lv .ps{background:var(--red);color:#fff;width:44px;font-size:14px}
.r.lv .tm{color:#fff}
.r.fresh{animation:fresh 1.2s ease-out 4}
@keyframes fresh{0%{background:rgba(43,217,107,.45)}100%{background:transparent}}
.r.out .dn,.r.out .tm{color:var(--dim)}
.empty{height:162px;display:flex;align-items:center;justify-content:center;font-size:20px;color:var(--dim)}
/* the commentary */
.com{position:absolute;left:1394px;top:24px;width:498px;height:228px;display:flex;flex-direction:column}
.com .on{display:flex;align-items:center;gap:10px;height:40px;background:var(--navy3);position:relative;flex:none}
.com .on .lb{height:40px;display:flex;align-items:center;gap:8px;padding:0 12px;background:var(--grey);font-size:18px;font-weight:700;letter-spacing:.12em;flex:none}
.com .on.lv .lb{background:var(--red)}
.com .on .lb i{width:9px;height:9px;border-radius:50%;background:#fff}.com .on.lv .lb i{animation:bl 1.4s infinite}
@keyframes bl{50%{opacity:.25}}
.com .on .who{flex:1;display:flex;align-items:center;gap:8px;font-size:22px;font-weight:700;white-space:nowrap;overflow:hidden}
.com .on .who .x{overflow:hidden;text-overflow:ellipsis}
.com .on .who .sn{font-size:15px;color:var(--soft);letter-spacing:.1em}
.com .on .ck{padding:0 12px;font-size:24px;font-weight:700}
.com .on .fl{width:26px;height:17px;object-fit:cover;border-radius:2px;flex:none}
.com .on .idle{font-size:16px;color:var(--soft);font-weight:600;letter-spacing:.04em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.com .on .pb{position:absolute;left:0;right:0;bottom:0;height:3px;background:rgba(255,255,255,.12)}.com .on .pb b{display:block;height:3px;background:#fff;transition:width 1s linear}
.com .tt{display:flex;align-items:center;gap:8px;height:26px;font-size:15px;font-weight:700;letter-spacing:.16em;color:var(--soft);border-bottom:1px solid var(--line);flex:none}
.com .tt i{width:4px;height:14px;background:var(--red);transform:skewX(-18deg)}
.com .tt .eq{display:flex;gap:2px;align-items:flex-end;height:12px;margin-left:4px}.com .tt .eq u{width:3px;background:var(--red);animation:eq 1s infinite ease-in-out}
.com .tt .eq u:nth-child(2){animation-delay:.2s}.com .tt .eq u:nth-child(3){animation-delay:.4s}
@keyframes eq{0%,100%{height:3px}50%{height:12px}}
.lines{flex:1;overflow:hidden;position:relative;padding-top:4px}
.ln{display:flex;gap:10px;padding:5px 4px 5px 0;font-size:19px;font-weight:500;line-height:1.18;color:var(--white)}
.ln .at{flex:none;width:44px;font-size:15px;font-weight:700;color:var(--dim);padding-top:2px;letter-spacing:.04em}
.ln.n1{opacity:.82}.ln.n2{opacity:.64}.ln.n3{opacity:.46}.ln.n4{opacity:.3}.ln.n5{opacity:.18}
.ln.new{animation:ln .6s ease-out}
@keyframes ln{0%{opacity:0;transform:translateY(-10px)}100%{opacity:1;transform:none}}
.ln .hi{color:#fff;font-weight:700}
.lines:after{content:"";position:absolute;left:0;right:0;bottom:0;height:26px;background:linear-gradient(180deg,transparent,#08101F)}
</style></head><body${cfg.bg ? ' class="bg"' : ''}><div id="stage">
<div class="game"></div>
<div class="band"><div class="stripes"></div>
  <div class="brand">${LOGO}<div class="wm"><b>ACR DAILY</b><div class="dl"><span>${esc(words.DAILIES)}</span></div></div>
    <div class="day" id="day"></div>
    <div class="cd"><span>${esc(words['NEW DAILIES IN'])}</span><b id="cd">–</b></div></div>
  <div class="board" id="b1" style="left:352px"></div>
  <div class="board" id="b2" style="left:870px"></div>
  <div class="com"><div class="on" id="on"></div>
    <div class="tt"><i></i><span>${esc(words.COMMENTARY)}</span><span class="eq"><u></u><u></u><u></u></span><span class="url">${esc(String(site || '').replace(/^https?:\/\//, ''))}</span></div>
    <div class="lines" id="lines"></div></div>
</div></div>
<script>
(function(){
var C=${JSON.stringify(cfg).replace(/</g, '\\u003c')},W=${JSON.stringify(words).replace(/</g, '\\u003c')};
function T(w){var v=W[w]||w;for(var i=1;i<arguments.length;i++)v=v.split('{'+(i-1)+'}').join(arguments[i]);return v}
var S=document.getElementById('stage');
function fit(){var k=Math.min(innerWidth/1920,innerHeight/1080);S.style.transform='scale('+k+')';S.style.left=((innerWidth-1920*k)/2)+'px';S.style.top=((innerHeight-1080*k)/2)+'px'}
addEventListener('resize',fit);fit();
function $(id){return document.getElementById(id)}
function el(t,c,x){var e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e}
function add(p){for(var i=1;i<arguments.length;i++)if(arguments[i]!=null)p.appendChild(arguments[i]);return p}
function ms(v,d){if(v==null)return '';d=d==null?3:d;var t=Math.max(0,v),m=Math.floor(t/60000),s=(t%60000)/1000,f=Math.pow(10,d);s=Math.floor(s*f)/f;return m+':'+s.toFixed(d).padStart(d?3+d:2,'0')}
function secs(v){return (Math.abs(v)/1000).toFixed(3)}
function span(v){v=Math.max(0,v);var s=Math.floor(v/1000),h=Math.floor(s/3600),m=Math.floor(s%3600/60),x=s%60;return h+':'+String(m).padStart(2,'0')+':'+String(x).padStart(2,'0')}
function hoursLeft(v){var m=Math.max(0,Math.round(v/60000)),h=Math.floor(m/60);return (h?h+' h ':'')+(m%60)+' min'}
function hm(t){return new Date(t).toLocaleTimeString(C.lang,{hour:'2-digit',minute:'2-digit',hour12:false})}
function words(s){return String(s||'').replace(/([a-z])([A-Z])/g,'$1 $2').replace(/_/g,' ')}
function low(s){s=words(s);return s.charAt(0)+s.slice(1).toLowerCase()}
function flag(c,cls){if(!c)return el('span','fl0');var i=el('img',cls||'fl');i.src='https://flagcdn.com/w80/'+String(c).toLowerCase()+'.png';i.alt=String(c).toUpperCase();return i}
function tagBox(tm){if(!tm||!tm.tag)return null;var b=el('span','tag',String(tm.tag).replace(/\\$[0-9a-fA-F]{3}|\\$[a-zA-Z<>]/g,'').slice(0,6).toUpperCase());
  b.style.background=tm.color?('#'+String(tm.color).replace('#','')):'#3A4F78';return b}
function api(p){return fetch('/api/v1'+p,{cache:'no-store'}).then(function(r){return r.json().then(function(j){if(!r.ok)throw new Error(j.error||('error '+r.status));return j})})}

// ---- what is known: the day, each daily's facts, board and who is on it now
var D={date:null,endsAt:null,slots:{}},LV={at:0},F=null;
function slot(n){return D.slots[n]||(D.slots[n]={n:n,info:null,rows:[],drivers:0,live:[],seen:null,half:{},fresh:{}})}
var BOOT=true;

// ---- the commentary: lines from what changes, the day's facts when it is quiet
var L=[],lastLine=0,fillI=0;
function say(text,hi){if(!text)return;L.unshift({at:Date.now(),text:text,hi:hi||[]});if(L.length>30)L.length=30;lastLine=Date.now();drawLines(true)}
function drawLines(fresh){var box=$('lines');box.innerHTML='';L.slice(0,6).forEach(function(x,i){var ln=el('div','ln'+(i?' n'+i:'')+(fresh&&i===0?' new':''));
  var tx=el('span');var s=x.text,parts=[s];x.hi.forEach(function(h){if(!h)return;parts=parts.reduce(function(o,p){if(typeof p!=='string')return o.concat([p]);var k=p.indexOf(h);
    if(k<0)return o.concat([p]);return o.concat([p.slice(0,k),{h:h},p.slice(k+h.length)])},[])});
  parts.forEach(function(p){if(typeof p==='string'){if(p)tx.appendChild(document.createTextNode(p))}else add(tx,el('span','hi',p.h))});
  add(box,add(ln,el('span','at',hm(x.at)),tx))})}
function finished(rows){return rows.filter(function(r){return r.status==='finished'&&r.totalMs!=null}).sort(function(a,b){return a.totalMs-b.totalMs})}
function opener(s){var i=s.info;if(!i)return null;return T('SS{0} today: {1}, {2}, {3} km in the {4}.',s.n,i.stage,i.rally,i.lengthM?(i.lengthM/1000).toFixed(1):'?',i.car)}
function leads(s){var f=finished(s.rows);if(!f.length)return [T('Nobody has a time on SS{0} yet.',s.n),[]];
  return f.length>1?[T('{0} leads SS{1} on {2}, {3} s up on {4}.',f[0].name,s.n,ms(f[0].totalMs),secs(f[1].totalMs-f[0].totalMs),f[1].name),[f[0].name]]:
    [T('{0} leads SS{1} on {2}.',f[0].name,s.n,ms(f[0].totalMs)),[f[0].name]]}
function closest(s){var f=finished(s.rows).slice(0,10);if(f.length<3)return null;var best=null;
  for(var i=1;i<f.length;i++){var g=f[i].totalMs-f[i-1].totalMs;if(!best||g<best.g)best={g:g,a:f[i-1],b:f[i],i:i}}
  return [T('{0} s between {1} (P{2}) and {3} (P{4}) on SS{5}.',secs(best.g),best.a.name,best.i,best.b.name,best.i+1,s.n),[best.a.name,best.b.name]]}
function count(s){var f=finished(s.rows).length,o=s.rows.filter(function(r){return r.status==='dnf'||r.status==='dsq'}).length;if(!f)return null;
  return [o?T('{0} drivers have a time on SS{1}, {2} out.',f,s.n,o):T('{0} drivers have a time on SS{1}.',f,s.n),[]]}
function conds(s){var i=s.info;if(!i||!i.weather)return null;return [T('SS{0} conditions: {1}, {2}.',s.n,low(i.weather),low(i.time||'')),[]]}
function fillers(){var out=[];[1,2].forEach(function(n){var s=D.slots[n];if(!s||!s.info)return;out.push(leads(s),closest(s))});
  [1,2].forEach(function(n){var s=D.slots[n];if(s&&s.info)out.push(count(s),conds(s),[opener(s),[]])});
  if(D.endsAt)out.push([T('{0} left to drive today\\'s dailies.',hoursLeft(D.endsAt-Date.now())),[]]);return out.filter(function(x){return x&&x[0]})}
// Claude's lines (src/commentary.js; ai=0: off): while the server has them on, they say what happens, in place of the
// lines above; the day's facts still fill the quiet. The server not answering three times: back to the lines above.
var AI={on:false,id:null,fails:0};
function ev(text,hi){if(!AI.on)say(text,hi)}
function claude(){fetch('/api/broadcast/dailies/commentary'+(C.lq?'?lang='+C.lq:''),{cache:'no-store'}).then(function(r){if(!r.ok)throw new Error(r.status);return r.json()})
  .then(function(j){AI.fails=0;AI.on=!!(j&&j.on);if(AI.on&&j.id&&j.line&&j.id!==AI.id){AI.id=j.id;say(j.line,j.names||[])}})
  .catch(function(){if(++AI.fails>=3)AI.on=false}).then(function(){setTimeout(claude,10000)})}
function filler(){var f=fillers();if(!f.length)return;var x=f[fillI%f.length];fillI++;if(L[0]&&L[0].text===x[0]&&f.length>1){x=f[fillI%f.length];fillI++}say(x[0],x[1])}

// what changed on a board since the last look: finishes (a new fastest time, the first one), better times, drivers out
function boardNews(s,rows){if(!s.seen){s.seen={};rows.forEach(function(r){s.seen[r.steamId]={status:r.status,totalMs:r.totalMs}});return}
  var before=finished(s.rows),lead=before[0],after=finished(rows),lines=[];
  rows.forEach(function(r){var o=s.seen[r.steamId];var rank=after.indexOf(r)+1;
    if(r.status==='finished'&&r.totalMs!=null&&(!o||o.status!=='finished')){s.fresh[r.steamId]=Date.now();
      if(!before.length&&rank===1)lines.push([T('{0} sets the first time on SS{1}: {2}.',r.name,s.n,ms(r.totalMs)),[r.name]]);
      else if(rank===1&&lead)lines.push([T('{0} goes fastest on SS{1}: {2}, {3} s clear of {4}.',r.name,s.n,ms(r.totalMs),secs(lead.totalMs-r.totalMs),lead.name),[r.name]]);
      else{var x=T('{0} finishes SS{1} in {2}: P{3}, {4} s off {5}.',r.name,s.n,ms(r.totalMs),rank,secs(r.totalMs-after[0].totalMs),after[0].name);
        if(r.resets)x+=' '+(r.resets===1?T('One reset on the run.'):T('{0} resets on the run.',r.resets));lines.push([x,[r.name]])}}
    else if(o&&o.status==='finished'&&r.status==='finished'&&r.totalMs<o.totalMs){s.fresh[r.steamId]=Date.now();
      lines.push([T('{0} improves on SS{1} to {2}, now P{3}.',r.name,s.n,ms(r.totalMs),rank),[r.name]])}
    else if((r.status==='dnf'||r.status==='dsq')&&(!o||(o.status!=='dnf'&&o.status!=='dsq')))lines.push([T('{0} is out of SS{1}.',r.name,s.n),[r.name]]);
    s.seen[r.steamId]={status:r.status,totalMs:r.totalMs}});
  lines.forEach(function(x){ev(x[0],x[1])})}
function liveNews(s,live){var was={};s.live.forEach(function(d){was[d.steamId]=d});
  live.forEach(function(d){var o=was[d.steamId];if(!BOOT&&!o)ev(T('{0} is away on SS{1}.',d.name,s.n),[d.name]);
    if(o&&!s.half[d.steamId]&&(o.progress||0)<.5&&(d.progress||0)>=.5){s.half[d.steamId]=1;ev(T('{0} is halfway through SS{1}, {2} on the clock.',d.name,s.n,ms(d.totalMs,1)),[d.name])}})}

// ---- the data
function loadDay(){return api('/dailies').then(function(d){
  if(D.date&&d.date!==D.date){D.slots={};L=[];BOOT=true}D.date=d.date;
  (d.dailies||[]).forEach(function(x){slot(x.slot).info=x;D.endsAt=x.endsAt});
  return Promise.all((d.dailies||[]).map(function(x){return api('/dailies/'+d.date+'/'+x.slot).then(function(b){var s=slot(x.slot);var rows=b.results||[];
    boardNews(s,rows);s.rows=rows;s.drivers=b.drivers||rows.length})}))})}
function loadLive(){if(!D.date)return Promise.resolve();return Promise.all([1,2].filter(function(n){return D.slots[n]}).map(function(n){
  return api('/dailies/'+D.date+'/'+n+'/live').then(function(l){var s=slot(n);var live=(l.drivers||[]).filter(function(d){return d.state==='live'||d.state==null});
    liveNews(s,live);live.forEach(function(d){d.at=Date.now()});s.live=live;LV.poll=l.pollSeconds||5}).catch(function(){})}))}

// ---- the boards: the best rows, then the next ones in turn; who is on that stage now at the foot
var PG={i:0,at:Date.now()};
function board(n){var s=D.slots[n],b=$('b'+n);b.innerHTML='';if(!s||!s.info){add(b,el('div','empty',T('Not available')));return}
  var i=s.info,ss=el('span','ss','SS'+n);
  add(b,add(el('div','hd'),ss,el('span','nm',String(i.stage||'').toUpperCase()),el('span','ry',String(i.rally||'').toUpperCase())));
  var f=finished(s.rows),out=s.rows.filter(function(r){return r.status==='dnf'||r.status==='dsq'});
  var live=s.live.slice().sort(function(a,b){return (b.progress||0)-(a.progress||0)}).slice(0,2);
  var per=C.rows-live.length,pages=Math.max(1,Math.min(4,Math.ceil(f.length/per))),p=PG.i%pages,from=p*per,to=Math.min(f.length,from+per);
  var mt=add(el('div','mt'),el('span',null,[i.car,i.carClass,low(i.weather),low(i.time)].filter(Boolean).join('  ·  ')));
  if(f.length)add(mt,el('span','pg',f.length>per?T('P{0}–{1} of {2}',from+1,to,f.length):T('{0} drivers',s.drivers||f.length)));add(b,mt);
  var rs=el('div','rows');if(!f.length&&!live.length)add(rs,el('div','empty',T('Nobody on the board yet.')));
  var lead=f.length?f[0].totalMs:0,now=Date.now();
  f.slice(from,to).forEach(function(r,k){var rank=from+k+1;var row=el('div','r'+(rank===1?' p1':'')+(s.fresh[r.steamId]&&now-s.fresh[r.steamId]<6000?' fresh':''));
    add(rs,add(row,el('span','ps',String(rank)),flag(r.country),el('span','dn',r.name),tagBox(r.team),el('span','tm'+(rank>1?' gp':''),rank>1?'+'+secs(r.totalMs-lead):ms(r.totalMs))))});
  live.forEach(function(d){var row=el('div','r lv');var tm=el('span','tm',ms(d.totalMs,1));tm.setAttribute('data-ms',d.totalMs||0);tm.setAttribute('data-at',d.at||now);clocks.push(tm);
    add(rs,add(row,el('span','ps',Math.round((d.progress||0)*100)+'%'),flag(d.country),el('span','dn',d.name),tagBox(d.team),tm))});
  if(pages>1)PG.multi=true;add(b,rs)}
// the commentary's head: who is on a stage now (the car WATCH follows, with feed=1), else between cars
function onStage(){var o=$('on');o.innerHTML='';var d=null,n=null;
  if(C.feed&&F&&F.on&&F.driver){d=F.driver;n=F.slot||null;d.at=F.at}
  else{[1,2].forEach(function(k){var s=D.slots[k];if(!s)return;s.live.forEach(function(x){if(!d||(x.progress||0)>(d.progress||0)){d=x;n=k}})})}
  o.className='on'+(d?' lv':'');
  if(!d){add(o,add(el('span','lb'),el('i'),el('span',null,T('BETWEEN CARS'))),el('span','idle',T('The next car on a stage comes on by itself.')));return}
  var who=add(el('span','who'),flag(d.country),el('span','x',String(d.name||'').toUpperCase()),tagBox(d.team),n?el('span','sn','SS'+n):null);
  var ck=el('span','ck',ms(d.totalMs,1));if(d.totalMs!=null){ck.setAttribute('data-ms',d.totalMs);ck.setAttribute('data-at',d.at||Date.now());clocks.push(ck)}
  var pb=add(el('div','pb'),el('b'));pb.firstChild.style.width=Math.round(Math.max(0,Math.min(1,d.progress||0))*100)+'%';
  add(o,add(el('span','lb'),el('i'),el('span',null,C.feed&&F&&F.on?T('ON CAM'):T('ON STAGE'))),who,ck,pb)}
var clocks=[];
function draw(){clocks=[];PG.multi=false;board(1);board(2);onStage();
  if(D.date){var dt=new Date(D.date+'T12:00:00Z');$('day').textContent=dt.toLocaleDateString(C.lang,{weekday:'long',day:'numeric',month:'long',timeZone:'UTC'}).toUpperCase()}}
function tick(){var now=Date.now();clocks.forEach(function(e){var v=e.getAttribute('data-ms');if(v!=null)e.textContent=ms(+v+(now-(+e.getAttribute('data-at'))),1)});
  if(D.endsAt)$('cd').textContent=span(D.endsAt-now);
  if(now-PG.at>=C.page*1000&&PG.multi){PG.i++;PG.at=now;var rs=document.querySelectorAll('.rows');rs.forEach(function(r){r.classList.add('out')});setTimeout(draw,350)}
  if(!BOOT&&now-lastLine>40000)filler()}
function boot(){if(!BOOT)return;BOOT=false;var f=[];[1,2].forEach(function(n){var s=D.slots[n];if(s&&s.info){f.push([opener(s),[]]);f.push(leads(s))}});
  f.reverse().forEach(function(x){if(x&&x[0])L.unshift({at:Date.now(),text:x[0],hi:x[1]})});lastLine=Date.now();drawLines(false)}
function fail(e){var b=$('b1');b.innerHTML='';add(b,el('div','empty',e&&e.message||T('Not available')))}
function all(){loadDay().then(loadLive).then(function(){boot();draw()}).catch(fail).then(function(){setTimeout(all,30000)})}
function live(){loadLive().then(draw).catch(function(){}).then(function(){setTimeout(live,Math.max(3,LV.poll||5)*1000)})}
function feed(){fetch('/feed.json',{cache:'no-store'}).then(function(r){return r.json()}).then(function(j){var was=F&&F.on;F=j||null;if(F){F.at=Date.now();
  var m=F.page&&String(F.page).match(/\\/broadcast\\/daily\\/(\\d)/);F.slot=m?+m[1]:null}if(!!(F&&F.on)!==!!was)onStage();
  else if(F&&F.on){var ck=document.querySelector('.com .ck');if(ck&&F.driver&&F.driver.totalMs!=null){ck.setAttribute('data-ms',F.driver.totalMs);ck.setAttribute('data-at',F.at)}
    var pb=document.querySelector('.com .pb b');if(pb&&F.driver)pb.style.width=Math.round(Math.max(0,Math.min(1,F.driver.progress||0))*100)+'%'}}).catch(function(){F=null})}
all();setTimeout(live,5000);setInterval(tick,100);if(C.feed)setInterval(feed,250);if(C.ai)setTimeout(claude,3000);
})();
</script></body></html>`;
}
