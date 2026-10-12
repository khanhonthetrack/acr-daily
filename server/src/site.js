// The public website. Rally timing-sheet look: black ground, hairlines instead of boxes, condensed type,
// ACR red only for stage numbers, P1, live cars and the active element. Two dailies = SS1 and SS2.
import { downloadUrl, hasDiscord, latestVersion } from './release.js';
import { coinSvg, envelopeSvg, FAVICON, logoSvg } from './logo.js';
import { BONUS_CSS, BONUS_JS } from './bonus.js';
import { TM_JS } from './tmtext.js';
import { EARTH_JS } from './earth.js';
import { GLIDE_JS } from './glide.js';

// the Discord logo mark (Simple Icons, CC0); Discord is a trademark of Discord Inc.
// the GitHub mark (Octicons, MIT); GitHub is a trademark of GitHub, Inc.
const GITHUB_MARK = 'M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z';
const DISCORD_MARK = 'M20.317 4.3698a19.7913 19.7913 0 00-4.8851-1.5152.0741.0741 0 00-.0785.0371c-.211.3753-.4447.8648-.6083 1.2495-1.8447-.2762-3.68-.2762-5.4868 0-.1636-.3933-.4058-.8742-.6177-1.2495a.077.077 0 00-.0785-.037 19.7363 19.7363 0 00-4.8852 1.515.0699.0699 0 00-.0321.0277C.5334 9.0458-.319 13.5799.0992 18.0578a.0824.0824 0 00.0312.0561c2.0528 1.5076 4.0413 2.4228 5.9929 3.0294a.0777.0777 0 00.0842-.0276c.4616-.6304.8731-1.2952 1.226-1.9942a.076.076 0 00-.0416-.1057c-.6528-.2476-1.2743-.5495-1.8722-.8923a.077.077 0 01-.0076-.1277c.1258-.0943.2517-.1923.3718-.2914a.0743.0743 0 01.0776-.0105c3.9278 1.7933 8.18 1.7933 12.0614 0a.0739.0739 0 01.0785.0095c.1202.099.246.1981.3728.2924a.077.077 0 01-.0066.1276 12.2986 12.2986 0 01-1.873.8914.0766.0766 0 00-.0407.1067c.3604.698.7719 1.3628 1.225 1.9932a.076.076 0 00.0842.0286c1.961-.6067 3.9495-1.5219 6.0023-3.0294a.077.077 0 00.0313-.0552c.5004-5.177-.8382-9.6739-3.5485-13.6604a.061.061 0 00-.0312-.0286zM8.02 15.3312c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9555-2.4189 2.157-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.9555 2.4189-2.1569 2.4189zm7.9748 0c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9554-2.4189 2.1569-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.946 2.4189-2.1568 2.4189Z';


export function sitePage(env) {
  const download = downloadUrl(env);
  const source = env.SOURCE_URL || '';
  // through /discord, which picks the current invite (the server widget's, naming nobody, when it is on)
  const discord = hasDiscord(env) ? '/discord' : '';
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ACR Daily</title>
<meta name="description" content="Two special stages a day for Assetto Corsa Rally. One car, one set of conditions, one timing sheet.">
<link rel="icon" href="${FAVICON}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#0A0A0B;--line:#1F1F23;--line2:#2B2B31;--fg:#F4F4F5;--fg2:#A1A1AA;--fg3:#6B6B74;--acc:#E30613;--bad:#FF453A;--slow:#FF9F0A;--good:#30D158}
*{box-sizing:border-box;margin:0}
html{background:var(--bg)}
body{color:var(--fg);font:15px/1.5 Barlow,system-ui,sans-serif;-webkit-font-smoothing:antialiased}
a{color:inherit}
.c{font-family:'Barlow Condensed',sans-serif}
.num{font-family:'Barlow Condensed',sans-serif;font-variant-numeric:tabular-nums;font-feature-settings:'tnum'}
.k{font:600 11px/1 Barlow,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:var(--fg3)}
.wrap{max-width:1200px;margin:0 auto;padding:0 24px}

/* top bar */
header{border-bottom:1px solid var(--line)}
header .wrap{display:flex;align-items:center;gap:24px;height:76px}
.brand{display:flex;align-items:center;gap:10px;font:700 20px/1 'Barlow Condensed',sans-serif;letter-spacing:.06em;text-decoration:none}
.brandmark{display:block;height:60px;width:auto}
.brand span{color:var(--fg);margin-left:4px}
.beta{display:inline-block;margin-left:8px;padding:2px 6px;border:1px solid #E30613;border-radius:3px;color:#E30613;font:700 12px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;vertical-align:middle;text-decoration:none}
.hof+.hof{margin-left:0}
.hof{margin-left:auto;font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;text-transform:uppercase;text-decoration:none;color:var(--fg2)}.hof:hover{color:var(--acc)}
/* the game's modes, each in its own colour (as in the app's tabs and the other pages' header) */
.hof.mode{color:var(--m)}.hof.mode:hover{color:var(--fg)}
.m-leagues{--m:#5BA8FF}.m-1v1{--m:#FF9F43}.m-cups{--m:#FFD60A}.m-inbox{--m:#4CD6C0}
/* the inbox: a letter, filled with the count by it when something is unread */
.ib{position:relative;display:inline-flex;align-items:center}
.ib .env{display:block;width:24px;height:24px}
.ib .unread{position:absolute;top:-8px;left:15px;margin:0;min-width:16px;padding:2px 3px;font-size:10px;border-radius:8px}
.ib.new .env .body{fill:currentColor}.ib.new .env .flap{stroke:var(--bg)}
.hof{white-space:nowrap}
.unread{display:inline-block;min-width:17px;margin-left:6px;padding:2px 4px;background:var(--acc);color:#fff;font:700 11px/1 Barlow,sans-serif;letter-spacing:0;text-align:center;vertical-align:1px}
.unread[hidden]{display:none}
/* signed in: my picture and name, to my driver page; signed out: sign in */
.acct{display:inline-flex;align-items:center;gap:9px;text-decoration:none;color:var(--fg);font:600 14px/1 'Barlow Condensed',sans-serif;letter-spacing:.06em;white-space:nowrap}
.acct img{width:28px;height:28px;border-radius:50%;object-fit:cover}
.acct:hover{color:var(--acc)}
.acct:empty{display:none}
.acct.out{font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:var(--fg2)}
.dl{font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;text-transform:uppercase;text-decoration:none;color:var(--fg);background:var(--acc);padding:9px 14px}
.dl:hover{background:var(--fg);color:var(--bg)}

/* the day's line: the day between its arrows (earlier days, back to today), when its stages close */
.dayline{display:flex;justify-content:space-between;align-items:center;padding:22px 0 8px;gap:8px 16px;flex-wrap:wrap}
.dayline h1{font:600 14px/1 'Barlow Condensed',sans-serif;letter-spacing:.16em;text-transform:uppercase;color:var(--fg);min-width:150px;text-align:center}
.datenav{display:flex;align-items:center;gap:2px;margin-left:-8px}
.datenav button{background:none;border:0;color:var(--fg2);font:500 22px/1 Barlow,sans-serif;width:34px;height:34px;cursor:pointer}
.datenav button:hover:not(:disabled){color:var(--acc)}
.datenav button:disabled{color:var(--line2);cursor:default}
#ends{font-size:13px;color:var(--fg3)}
#ends b{color:var(--fg);font-weight:600}

/* ACR Daily's own cup, open or under way: a strip over the stages */
.cupstrip{display:flex;align-items:center;gap:8px 16px;flex-wrap:wrap;margin-top:22px;padding:12px 14px;border:1px solid var(--line2);border-left:3px solid var(--acc);background:#111113;text-decoration:none}
.cupstrip[hidden]{display:none}
.cupstrip:hover{border-color:var(--fg2);border-left-color:var(--acc)}
.cupstrip .tag{font:700 12px/1 'Barlow Condensed',sans-serif;letter-spacing:.14em;color:#fff;background:var(--acc);padding:4px 7px}
.cupstrip .cn{font:700 20px/1.1 'Barlow Condensed',sans-serif;text-transform:uppercase;letter-spacing:.02em}
.cupstrip .cs{color:var(--fg2);font-size:13px}
.cupstrip .coin{display:inline-block;width:1.1em;height:1.1em;margin-left:.3em;vertical-align:-.2em}
.cupstrip .go{margin-left:auto;font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;text-transform:uppercase;color:var(--acc)}


/* stages */
.stages{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 48px}
.stage{padding:20px 0 40px;border-top:2px solid var(--fg)}
.plate{display:flex;align-items:baseline;gap:14px}
.ss{font:700 15px/1 'Barlow Condensed',sans-serif;letter-spacing:.08em;color:var(--acc)}
.where{font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.14em;text-transform:uppercase;color:var(--fg2)}
.name{font:700 clamp(40px,5vw,60px)/.95 'Barlow Condensed',sans-serif;text-transform:uppercase;letter-spacing:.01em;margin:12px 0 22px}
.spec{display:grid;grid-template-columns:2.2fr 1fr 1.2fr .8fr;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.spec>div{padding:11px 0 12px;min-width:0}
.spec>div+div{padding-left:16px;border-left:1px solid var(--line)}
.spec .v{font:600 17px/1.2 'Barlow Condensed',sans-serif;margin-top:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

/* map */
.map{position:relative;aspect-ratio:16/9;margin:18px 0 10px}
.map svg{position:absolute;inset:0;width:100%;height:100%;overflow:visible}
.map .route{fill:none;stroke:#55555E;stroke-width:2.5;stroke-linejoin:round;stroke-linecap:round}
.map .done{fill:none;stroke:var(--fg);stroke-width:1.5;stroke-linejoin:round;stroke-linecap:round}
/* the stage's real place: a satellite thumbnail in the map's corner, the way to the live satellite view */
.satbtn{position:absolute;right:0;bottom:0;z-index:2;width:92px;height:92px;border-radius:6px;overflow:hidden;
  border:1px solid var(--line2);background:#16161a;text-decoration:none;box-shadow:0 2px 10px #0009;transition:border-color .15s}
.satbtn img,.satbtn svg{position:absolute;inset:0;width:100%;height:100%}
.satbtn img{object-fit:cover;filter:saturate(.9) brightness(.9)}
.satbtn svg polyline{fill:none;stroke:var(--acc);stroke-width:2.2;stroke-linejoin:round;stroke-linecap:round;vector-effect:non-scaling-stroke}
.satbtn span{position:absolute;left:0;right:0;bottom:0;padding:14px 0 5px;text-align:center;font:700 10px/1 'Barlow Condensed',sans-serif;
  letter-spacing:.16em;color:#fff;background:linear-gradient(transparent,#000c)}
.satbtn:hover,.satbtn:focus-visible{border-color:var(--acc)}
.satbtn:hover span{color:var(--acc)}
@media (max-width:700px){.satbtn{width:74px;height:74px}}
.com{list-style:none;margin:10px 0 0;padding:0 0 0 12px;border-left:2px solid var(--acc);font-size:14px;color:var(--fg2)}
.com li{padding:2px 0;line-height:1.4}.com li.new{color:var(--fg)}.com li.quiet{color:var(--fg3)}
.live .tag{font:700 12px/1 'Barlow Condensed',sans-serif;letter-spacing:.16em;color:var(--fg)}
.live.none .tag{color:var(--fg3)}
.com .when{font:600 11px 'Barlow Condensed',sans-serif;letter-spacing:.08em;color:var(--fg3);margin-right:10px;font-feature-settings:'tnum'}
.live .chip{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;vertical-align:0}
.live .chip.av{width:18px;height:18px;border:2px solid;box-sizing:border-box;vertical-align:-4px;object-fit:cover}
.dot text{font:600 12px 'Barlow Condensed',sans-serif;letter-spacing:.04em;fill:var(--fg);paint-order:stroke;stroke:var(--bg);stroke-width:4px}
.mark{font:600 10px 'Barlow Condensed',sans-serif;letter-spacing:.14em;fill:var(--fg3)}
.live{display:flex;align-items:center;gap:10px;flex-wrap:wrap;min-height:22px;font-size:13px;color:var(--fg2)}
.live .pulse{width:7px;height:7px;border-radius:50%;background:var(--acc);box-shadow:0 0 0 0 rgba(227,6,19,.6);animation:p 1.6s infinite}
.live.none .pulse{background:var(--line2);animation:none}
@keyframes p{70%{box-shadow:0 0 0 7px rgba(227,6,19,0)}100%{box-shadow:0 0 0 0 rgba(227,6,19,0)}}
.live .who{color:var(--fg)}
.live .sep{color:var(--line2)}

/* timing sheet */
.sheet{margin-top:22px}
.sheethead{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px}
.stats{font-size:13px;color:var(--fg3)}
.stats b{color:var(--fg2);font-weight:500}
table{width:100%;border-collapse:collapse}
th{font:600 11px/1 Barlow,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:var(--fg3);text-align:left;padding:10px 0;border-bottom:1px solid var(--line2)}
td{padding:11px 0;border-bottom:1px solid var(--line);vertical-align:baseline}
th.r,td.r{text-align:right}
th.r{padding-left:16px}
th:first-child,td.pos{width:44px;min-width:44px;padding-right:14px;white-space:nowrap}
td.pos{width:44px;font:600 17px/1 'Barlow Condensed',sans-serif;color:var(--fg2)}
tr.p1 td.pos{color:var(--acc)}
td.drv{font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:0;width:100%}
td.drv a{text-decoration:none}
.flagimg{width:18px;height:12px;margin-right:8px;vertical-align:-1px;object-fit:cover;box-shadow:0 0 0 1px rgba(255,255,255,.12)}
.live .flagimg{margin:0 5px 0 0}
tr.dnf td{color:var(--fg3)}tr.dnf td.t{font-weight:500;color:var(--bad)}
td.drv a:hover{text-decoration:underline}
td.t{font:600 18px/1 'Barlow Condensed',sans-serif;font-feature-settings:'tnum';padding-left:16px;white-space:nowrap}
td.t a{text-decoration:none}
td.t a:hover{color:var(--acc)}
td.gap{font:500 15px/1 'Barlow Condensed',sans-serif;font-feature-settings:'tnum';color:var(--fg2);padding-left:16px;white-space:nowrap;width:84px}
td.pen{font:500 15px/1 'Barlow Condensed',sans-serif;color:var(--slow);padding-left:16px;width:48px}
.name a{text-decoration:none}.name a:hover{color:var(--acc)}
.statlink{color:var(--fg2);text-decoration:none}.statlink:hover{color:var(--acc)}
.lookbadge{margin-left:6px;font-size:14px;vertical-align:-1px}
.teamtag{font:700 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.06em;margin-right:6px}
.flagged{margin-left:8px;font:600 10px/1 Barlow,sans-serif;letter-spacing:.12em;color:var(--acc);vertical-align:middle}
.empty{padding:22px 0;color:var(--fg3);border-bottom:1px solid var(--line)}

.plate .wager{margin-left:auto;font:600 12px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;text-transform:uppercase;color:var(--acc);text-decoration:none;border:1px solid var(--acc);padding:4px 8px}
.plate .wager:hover{background:var(--acc);color:#fff}
.plate .wager .coin{display:inline-block;width:1.1em;height:1.1em;margin-left:.3em;vertical-align:-.25em}
/* footer */
footer{border-top:1px solid var(--line);margin-top:24px}
footer .wrap{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:32px;padding:32px 24px 56px}
.oss.foot{margin-top:12px;color:var(--fg)}
footer h2{font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.14em;text-transform:uppercase;margin-bottom:10px}
footer p{color:var(--fg2);font-size:14px;max-width:34ch}
.oss{display:flex;align-items:center;gap:7px;font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;text-transform:uppercase;text-decoration:none;color:var(--fg2)}
.oss:hover{color:var(--acc)}
.oss svg{width:15px;height:15px;fill:currentColor}
.legal{border-top:1px solid var(--line);padding:16px 0 40px;font-size:12px;color:var(--fg3);display:flex;gap:6px 16px;flex-wrap:wrap}
.legal a{color:var(--fg2)}.legal a:hover{color:var(--acc)}

/* two rows: logo + Get the app, then the links + the date */
@media (max-width:1180px){
  header .wrap{gap:10px 16px;flex-wrap:wrap;height:auto;padding-top:12px;padding-bottom:12px}
  header .wrap::after{content:'';order:3;flex-basis:100%;height:0}
  .brand{order:1}
  .acct{order:2;margin-left:auto}
  .dl{order:2}
  .acct:empty+.dl{margin-left:auto}
  .hof{order:4;white-space:nowrap}
  .hof{margin-left:0}
}
@media (max-width:860px){
  .stages{grid-template-columns:1fr}
  .spec{grid-template-columns:1fr 1fr}
  .spec>div:nth-child(3){padding-left:0;border-left:0}
  .spec>div:nth-child(n+3){border-top:1px solid var(--line)}
  footer .wrap{grid-template-columns:1fr;gap:20px}
  .brandmark{height:52px}
  .brand span{display:none}
  td.gap,th.gaph{display:none}
  .wrap{padding:0 16px}
}
@media (max-width:420px){header .wrap{gap:10px 14px}}
.crhost:empty{display:none}
${BONUS_CSS}
</style>
</head>
<body>
<header><div class="wrap">
  <a class="brand" href="/">${logoSvg()}<span>ACR Daily</span><b class="beta" title="Beta: expect bugs. Report them on Discord.">BETA</b></a>
  <a class="hof" href="/guide">How to play</a>
  <a class="hof mode m-leagues" href="/leagues">Leagues</a>
  <a class="hof mode m-1v1" href="/1v1">1V1</a>
  <a class="hof mode m-cups" href="/cups">Cups</a>
  <a class="hof" href="/ranking">Ranking</a>
  <a class="hof" href="/teams">Teams</a>
  <a class="hof mode m-inbox ib" href="/inbox" title="Inbox" aria-label="Inbox">${envelopeSvg()}<b class="unread" id="unread" hidden></b></a>
  <span class="hof crhost" id="crhost"></span>
  <a class="acct" id="acct"></a>
  ${download ? `<a class="dl" href="${download}">Get the app</a>` : ''}
</div></header>

<main class="wrap">
  <a class="cupstrip" id="cupstrip" hidden></a>
  <div class="dayline"><nav class="datenav"><button id="prev" aria-label="Previous day" title="The day before">‹</button><h1 id="dayname">Today's stages</h1><button id="next" aria-label="Next day" title="The day after">›</button></nav><div id="ends"></div></div>
  <div class="stages" id="stages"></div>
</main>

<footer><div class="wrap">
  <div><h2>The app</h2><p>Runs next to the game and times your run. DRIVE sets up the stage for you.</p></div>
  <div><h2>The rules</h2><p>Your first run counts, the rest is practice. The game's official time and penalties go on the sheet. Restart or retire and it's a DNF.</p></div>
  <div><h2>New stages</h2><p>Two every day at 00:00 UTC, each with its own car and weather.</p></div>
  ${discord || source ? `<div><h2>Community</h2><p>Chat, suggest ideas, report bugs.${source ? ' The app and this website are open source.' : ''}</p>` +
    (discord ? `<a class="oss foot" href="${discord}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="${DISCORD_MARK}"/></svg><span>ACR Daily on Discord</span></a>` : '') +
    (source ? `<a class="oss foot" href="${source}"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="${GITHUB_MARK}"/></svg><span>Code on GitHub</span></a>` : '') + '</div>' : ''}
</div>
<div class="wrap legal">
  ${source ? `<span>ACR Daily is open source under the <a href="${source}/blob/main/LICENSE">MIT licence</a>. <a href="${source}">Code, issues and pull requests on GitHub</a>.</span>` : ''}
  ${download ? `<span>App v${latestVersion(env)} is built by GitHub from the public code: <a href="/guide#verify">check your download</a>.</span>` : ''}
  ${env.CREDITS_FROM ? '<span><a href="/credits">Credits</a>: earn them by driving, stake them on SS2, spend them in the <a href="/credits#shop">shop</a>.</span>' : ''}
  <span>A fan project, not affiliated with the makers of Assetto Corsa Rally.</span>
</div></footer>

<script>
(function(){
  var today=new Date().toISOString().slice(0,10),cur=today,ends=0,maps={};
  function $(id){return document.getElementById(id)}
  function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
  var NS='http://www.w3.org/2000/svg';
  function sv(tag,a){var e=document.createElementNS(NS,tag);for(var k in a||{})e.setAttribute(k,a[k]);return e}
  function fmt(ms){if(ms==null)return'–';var m=Math.floor(ms/60000),s=(ms%60000)/1000;return m+':'+(s<10?'0':'')+s.toFixed(3)}
  function shift(d,n){var t=new Date(d+'T00:00:00Z');t.setUTCDate(t.getUTCDate()+n);return t.toISOString().slice(0,10)}
  function dayLabel(d){return new Date(d+'T00:00:00Z').toLocaleDateString('en-GB',{weekday:'short',day:'2-digit',month:'short',timeZone:'UTC'})}
  function get(u){return fetch(u,{cache:'no-store'}).then(function(r){return r.json()})}
  function km(m){return m?(m/1000).toFixed(1)+' km':''}
  var COIN=${JSON.stringify(coinSvg())};
  function coined(e,text){e.textContent=text;e.insertAdjacentHTML('beforeend',COIN)}   // an amount of credits: the coin by it
  ${BONUS_JS}
  // signed in, credits on: the balance by the inbox, and today's bonus claimed here if it still is to be (src/bonus.js)
  // and my picture and name in the header, to my driver page (signed out: sign in)
  fetch('/api/me',{credentials:'same-origin',cache:'no-store'}).then(function(r){return r.ok?r.json():null}).then(function(me){
    var a=$('acct');if(!me)return;
    if(me.signedIn){a.href='/d/'+me.steamId;a.title='Your driver page';if(me.avatar){var i=el('img');i.src=me.avatar;i.alt='';a.appendChild(i)}a.appendChild(el('span',null,me.name))}
    else{a.href='/login?next=/';a.className='acct out';a.textContent='Sign in'}
    if(me.credits){creditsChip($('crhost'),me.credits);claimBonus($('crhost'),me.credits)}}).catch(function(){});
  // the inbox's unread count by its link (signed in on the website)
  fetch('/api/inbox/unread',{credentials:'same-origin',cache:'no-store'}).then(function(r){return r.ok?r.json():null}).then(function(j){
    if(j&&j.unread){var u=$('unread');u.textContent=j.unread>99?'99+':String(j.unread);u.hidden=false;
      u.parentNode.classList.add('new');u.parentNode.title='Inbox: '+j.unread+' new'}}).catch(function(){});
  // ACR Daily's own cup, open for entries or under way (src/cups.js): a strip over the stages, to its page
  get('/api/cups/official').then(function(j){var c=j&&j.cups&&j.cups[0];if(!c)return;var s=$('cupstrip'),open=c.status==='open';
    s.href='/cup/'+c.id;s.innerHTML='';s.appendChild(el('span','tag','OFFICIAL CUP'));s.appendChild(el('span','cn',c.name));
    var cs=el('span','cs'),said=open?'Entries open · '+c.entrants+' of '+c.size+' drivers · starts '+
      new Date(c.starts).toLocaleDateString('en-GB',{weekday:'short',day:'numeric',month:'short'}):'Under way · '+c.entrants+' drivers';
    if(c.prize)coined(cs,said+' · prize '+c.prize);else cs.textContent=said;s.appendChild(cs);
    s.appendChild(el('span','go',open?'Join ›':'Bracket ›'));s.hidden=false}).catch(function(){});

  // ---- stage map: route rotated to fill the frame; a projector for the live dots
  function drawMap(box,raw,g,corner){   // corner: px kept clear at the bottom right (the satellite button)
    box.innerHTML='';
    if(!raw||raw.length<2)return null;
    // a stage lined up with the real roads (g, geofits.js) is drawn as it is on Earth: the game's coordinates are a
    // mirror image of it. North up when that still fills the box well, else turned to fill it (never mirrored).
    var T=earthScreen(g);
    var pts=raw.map(T);
    var W=640,H=360,pad=28,mx=0,mz=0,i;for(i=0;i<pts.length;i++){mx+=pts[i][0];mz+=pts[i][1]}mx/=pts.length;mz/=pts.length;
    var sxx=0,szz=0,sxz=0;for(i=0;i<pts.length;i++){var dx=pts[i][0]-mx,dz=pts[i][1]-mz;sxx+=dx*dx;szz+=dz*dz;sxz+=dx*dz}
    function fitFor(a){var c=Math.cos(a),s=Math.sin(a),x0=1e9,x1=-1e9,y0=1e9,y1=-1e9;
      pts.forEach(function(p){var x=(p[0]-mx)*c-(p[1]-mz)*s,y=(p[0]-mx)*s+(p[1]-mz)*c;x0=Math.min(x0,x);x1=Math.max(x1,x);y0=Math.min(y0,y);y1=Math.max(y1,y)});
      return {a:a,c:c,s:s,x0:x0,x1:x1,y0:y0,y1:y1,k:Math.min((W-2*pad)/(x1-x0||1),(H-2*pad)/(y1-y0||1))}}
    var f=fitFor(-0.5*Math.atan2(2*sxz,sxx-szz));
    if(g){var up=fitFor(0);if(up.k>=0.75*f.k)f=up}
    var c=f.c,s=f.s,k,ox,oy;
    function place(Wa){k=Math.min((Wa-2*pad)/(f.x1-f.x0||1),(H-2*pad)/(f.y1-f.y0||1));ox=(Wa-(f.x1-f.x0)*k)/2-f.x0*k;oy=(H-(f.y1-f.y0)*k)/2-f.y0*k}
    function Pt(p){var x=(p[0]-mx)*c-(p[1]-mz)*s,y=(p[0]-mx)*s+(p[1]-mz)*c;return[x*k+ox,y*k+oy]}
    place(W);
    if(corner&&box.clientWidth){   // the route would run under the button: draw it in the width left of it
      var r=(corner+8)*W/box.clientWidth;
      if(pts.some(function(p){var q=Pt(p);return q[0]>W-r&&q[1]>H-r}))place(W-r);
    }
    function P(p){return Pt(T(p))}   // game (x, z): the live cars
    var line=pts.map(function(p){var q=Pt(p);return q[0].toFixed(1)+','+q[1].toFixed(1)}).join(' ');
    var svg=sv('svg',{viewBox:'0 0 '+W+' '+H,role:'img','aria-label':'Stage map'});
    svg.appendChild(sv('polyline',{points:line,class:'route'}));
    var A=Pt(pts[0]),Z=Pt(pts[pts.length-1]);
    // start: a short bar across the road; finish: a small chequer
    svg.appendChild(sv('circle',{cx:A[0],cy:A[1],r:4,fill:'#F4F4F5'}));
    var ts=sv('text',{x:A[0]+9,y:A[1]+4,class:'mark'});ts.textContent='START';svg.appendChild(ts);
    var fin=sv('g',{transform:'translate('+(Z[0]-6)+','+(Z[1]-6)+')'});
    fin.appendChild(sv('rect',{width:12,height:12,fill:'#F4F4F5'}));fin.appendChild(sv('rect',{width:6,height:6,fill:'#0A0A0B'}));fin.appendChild(sv('rect',{x:6,y:6,width:6,height:6,fill:'#0A0A0B'}));
    svg.appendChild(fin);
    var tf=sv('text',{x:Z[0]+10,y:Z[1]+4,class:'mark'});tf.textContent='FINISH';svg.appendChild(tf);
    var dots=sv('g');svg.appendChild(dots);box.appendChild(svg);
    return {P:P,dots:dots,nodes:{},trk:routeTrack(raw)};
  }

  // ---- live cars: each driver has their own colour (same as in the app), a flag and a name; they move along the road,
  // a few seconds late (src/glide.js). Finished = white ring, retired = red ring.
  var PAL=['#5BA8FF','#FF7AB6','#4CD6C0','#FF9F43','#B48CFF','#7BE07B','#FFD60A','#3DD5F3','#F2A0FF','#C8E06B'];
  // a different colour for everyone on stage (by Steam id, next free one on a clash); a colour bought in the shop
  // (chosen: {steamId: colour}) comes first
  function colours(ids,chosen){chosen=chosen||{};var out={},used={};
    ids.forEach(function(id){if(chosen[id]){out[id]=chosen[id];var c=PAL.indexOf(chosen[id]);if(c>=0)used[c]=1}});
    ids.slice().sort().forEach(function(id){if(out[id])return;var k=Number(String(id).slice(-6))%PAL.length;
      for(var n=0;n<PAL.length&&used[k];n++)k=(k+1)%PAL.length;used[k]=1;out[id]=PAL[k]});return out}
  // a look from the shop: a name in its colour (or gradient)
  function paint(e,l){if(!l)return;if(l.grad){e.style.backgroundImage='linear-gradient(90deg,'+l.grad.join(',')+')';
    e.style.webkitBackgroundClip='text';e.style.backgroundClip='text';e.style.color='transparent'}else if(l.color)e.style.color=l.color}
  // a team's tag in its colour before the name (src/drivers.js)
  ${TM_JS}
  function tagEl(p,l){if(!l||!l.tag)return;tmInto(p,l.tag.fmt,l.tag.text,l.tag.color,'teamtag')}
  ${GLIDE_JS}
  // a driver's label on the map: their team's tag in its colours ([TAG] as tspans), then their badge and name
  function dotLabel(tx,d,colour){while(tx.firstChild)tx.removeChild(tx.firstChild);tx.style.fill=colour;var t=d.look&&d.look.tag;
    if(t){tx.appendChild(document.createTextNode('['));(t.fmt?tmSpans(t.fmt):[{t:t.text}]).forEach(function(x){var s=sv('tspan',x.b?{'font-weight':'800'}:{});
        s.textContent=x.u?x.t.toUpperCase():x.t;s.style.fill=x.c||t.color;tx.appendChild(s)});tx.appendChild(document.createTextNode('] '))}
    tx.appendChild(document.createTextNode((d.look&&d.look.badge?d.look.badge+' ':'')+d.name))}
  var RING={live:'#0A0A0B',finished:'#F4F4F5',dnf:'#FF453A'};
  // each map's playback (by slot); one frame loop moves every car. LIVE_DELAY: how late the cars run (an update of the
  // app's and a check of ours always ahead of them); LIVE_GAP: updates further apart are not driven between
  var PB={},LIVE_DELAY=9000,LIVE_GAP=15000,raf=0;
  function drawLive(x,data,srvNow){
    var chosen={};data.drivers.forEach(function(d){if(d.look&&d.look.color)chosen[d.steamId]=d.look.color});
    var m=x.m,col=colours(data.drivers.map(function(d){return d.steamId}),chosen);
    if(!m)return;
    var pb=PB[x.slot]||(PB[x.slot]=livePlayback(LIVE_DELAY,LIVE_GAP));
    pb.feed(data.drivers,srvNow||Date.now(),Date.now());
    data.drivers.forEach(function(d){
      var g=m.nodes[d.steamId];
      if(!g){g=sv('g',{class:'dot'});
        // the Steam avatar in a circle, ringed in the driver's colour (a plain coloured dot without an avatar)
        var R=d.avatar?11:6;g.appendChild(sv('circle',{r:R+2,'stroke-width':1.5}));
        if(d.avatar){var cid='av'+d.steamId+'s'+x.slot;var cp=sv('clipPath',{id:cid});cp.appendChild(sv('circle',{r:R}));g.appendChild(cp);
          var av=sv('image',{x:-R,y:-R,width:2*R,height:2*R,'clip-path':'url(#'+cid+')',preserveAspectRatio:'xMidYMid slice'});av.setAttribute('href',d.avatar);g.appendChild(av)}
        if(d.country){var im=sv('image',{x:R+6,y:-6,width:18,height:12,preserveAspectRatio:'xMidYMid slice'});im.setAttribute('href','https://flagcdn.com/w40/'+d.country+'.png');g.appendChild(im)}
        g.appendChild(sv('text',{x:d.country?R+28:R+6,y:4}));m.dots.appendChild(g);m.nodes[d.steamId]=g}
      g.col=col[d.steamId];g.fr=d.look&&d.look.frame;g.st=null;   // (its ring: the next frame)
      dotLabel(g.lastChild,d,col[d.steamId]);
    });
    if(!raf)raf=requestAnimationFrame(frame);
  }
  // ring: driver colour on stage (or their frame from the shop), white once finished, red when retired
  function ring(g,state){if(g.st===state)return;g.st=state;var fr=g.fr,live=state==='live';
    g.firstChild.setAttribute('fill',g.col);g.firstChild.setAttribute('stroke',live?(fr?fr.color:g.col):RING[state]||RING.live);
    g.firstChild.setAttribute('stroke-width',live&&fr?fr.width:1.5);g.firstChild.setAttribute('stroke-dasharray',live&&fr&&fr.dash?'3 2':'')}
  // every frame while there are cars: each where its playback has it (a car whose updates are all shown and that is
  // off the server's list goes)
  function frame(){var now=Date.now(),any=false;raf=0;
    Object.keys(maps).forEach(function(slot){var m=maps[slot].m,pb=PB[slot];if(!m||!pb)return;
      Object.keys(m.nodes).forEach(function(id){var g=m.nodes[id],st=pb.at(id,now);
        if(!st){g.remove();delete m.nodes[id];return}
        any=true;ring(g,st.state);var q=m.P(m.trk.at(st.p));
        g.setAttribute('transform','translate('+q[0].toFixed(2)+','+q[1].toFixed(2)+')')})});
    if(any)raf=requestAnimationFrame(frame)}

  function flag(parent,code){if(!code)return;var i=el('img','flagimg');i.src='https://flagcdn.com/w40/'+code+'.png';i.alt=code.toUpperCase();i.title=code.toUpperCase();i.width=18;i.height=12;parent.appendChild(i)}
  function sheet(x,b){
    var st=b.stats||{};x.stats.innerHTML='';
    [[st.drivers||0,'drivers'],[st.dnfs||0,'DNF']].forEach(function(p,i){
      if(i)x.stats.appendChild(document.createTextNode('  ·  '));var s=el('b',null,String(p[0]));x.stats.appendChild(s);x.stats.appendChild(document.createTextNode(' '+p[1]))});
    var tb=x.tb;tb.innerHTML='';
    if(!b.entries||!b.entries.length){var tr=el('tr');var td=el('td','empty','No times yet.');td.colSpan=5;tr.appendChild(td);tb.appendChild(tr);return}
    b.entries.forEach(function(e){
      var dnf=e.status==='dnf';var tr=el('tr',e.rank===1?'p1':(dnf?'dnf':''));tr.appendChild(el('td','pos',dnf?'–':String(e.rank)));
      var d=el('td','drv');flag(d,e.country);tagEl(d,e.look);var a=el('a',null,e.name);a.href='/d/'+e.steamId;a.title='Driver page';d.appendChild(a);
      paint(a,e.look);if(e.look&&e.look.badge)d.appendChild(el('span','lookbadge',e.look.badge));   // (the shop)
      if(e.review)d.appendChild(el('span','flagged','UNDER REVIEW'));tr.appendChild(d);
      var t=el('td','t r');if(dnf){t.textContent='DNF';t.title=e.reason||''}else{var ta=el('a',null,fmt(e.totalMs));ta.href='/run/'+e.runId;ta.title='Open the run';t.appendChild(ta)}tr.appendChild(t);
      tr.appendChild(el('td','gap r',dnf||e.rank===1?'':'+'+(e.gapMs/1000).toFixed(3)));
      var pen=dnf?0:Math.round((e.totalMs-e.clockMs)/1000);   // the penalty: total - stage clock
      tr.appendChild(el('td','pen r',pen>0?'+'+pen:''));tb.appendChild(tr);
    });
  }

  // ---- the real place: satellite thumbnail of the stage (Esri World Imagery) with the route on it, linking the
  // satellite view (today: live drivers on it). Only for stages lined up with the real roads (geofits.js).
  ${EARTH_JS}
  function mercY(lat){return Math.log(Math.tan(Math.PI/4+lat*Math.PI/360))}
  function satButton(box,ch){
    var g=EARTH[ch.track],r=ch.route;if(!g||!r||r.length<2)return;
    var step=Math.max(1,Math.floor(r.length/120)),pts=[];
    for(var i=0;i<r.length;i+=step)pts.push(earthLL(g,r[i]));pts.push(earthLL(g,r[r.length-1]));
    var la0=1e9,la1=-1e9,lo0=1e9,lo1=-1e9;pts.forEach(function(p){la0=Math.min(la0,p[0]);la1=Math.max(la1,p[0]);lo0=Math.min(lo0,p[1]);lo1=Math.max(lo1,p[1])});
    // a square around the route (in metres), with a margin
    var cl=(la0+la1)/2,mx=Math.cos(cl*Math.PI/180),h=(la1-la0)*111132.954,w=(lo1-lo0)*111319.49*mx,half=Math.max(h,w)*0.6+150;
    var dla=half/111132.954,dlo=half/(111319.49*mx),clo=(lo0+lo1)/2;
    la0=cl-dla;la1=cl+dla;lo0=clo-dlo;lo1=clo+dlo;
    var a=el('a','satbtn');a.title='The stage on satellite imagery'+(cur===today?', with the drivers on it live':'');
    a.href=cur===today?'/lab/map?ss='+ch.slot:'/lab/map?stage='+encodeURIComponent(ch.track);
    var img=el('img');img.alt='';img.loading='lazy';
    img.src='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?bbox='+[lo0,la0,lo1,la1].map(function(v){return v.toFixed(5)}).join(',')+
      '&bboxSR=4326&imageSR=3857&size=184,184&format=jpg&f=image';
    a.appendChild(img);
    var y0=mercY(la0),y1=mercY(la1),svg=sv('svg',{viewBox:'0 0 100 100',preserveAspectRatio:'none'});
    svg.appendChild(sv('polyline',{points:pts.map(function(p){return ((p[1]-lo0)/(lo1-lo0)*100).toFixed(1)+','+((y1-mercY(p[0]))/(y1-y0)*100).toFixed(1)}).join(' ')}));
    a.appendChild(svg);a.appendChild(el('span',null,'SATELLITE'));box.appendChild(a);
  }

  function stageBlock(ch){
    var s=el('section','stage');
    var plate=el('div','plate');plate.appendChild(el('span','ss','SS'+ch.slot));
    plate.appendChild(el('span','where',[ch.rally,ch.surface,km(ch.lengthM)].filter(Boolean).join('  ·  ')));s.appendChild(plate);
    if(ch.wager){var wg=el('a','wager');coined(wg,'Wager daily · stake '+ch.wager.stake);wg.href='/credits';wg.title='Costs a stake to enter';plate.appendChild(wg);
      get('/api/credits/wager?date='+ch.date+'&slot='+ch.slot).then(function(w){if(w&&w.entrants)coined(wg,'Wager · '+w.entrants+' in · pot '+(w.pot+w.stake))})}
    var nm=el('h2','name');var na=el('a',null,ch.menuName||ch.stageName||ch.track);na.href='/stage/'+ch.date+'/'+ch.slot;na.title='Stage statistics';nm.appendChild(na);s.appendChild(nm);
    var spec=el('div','spec');
    [['Car',ch.car],['Class',ch.carClass||'–'],['Weather',ch.weatherLabel||'–'],['Start',(ch.timeLabel||'').replace(/^.*\\((.*)\\)$/,'$1')||'–']].forEach(function(p){
      var d=el('div');d.appendChild(el('div','k',p[0]));d.appendChild(el('div','v',p[1]));spec.appendChild(d)});
    s.appendChild(spec);
    var mapBox=el('div','map');s.appendChild(mapBox);
    var sh=el('div','sheet');var hd=el('div','sheethead');var hl=el('div','k','Timing  ·  ');var st=el('a','statlink','Stats ›');st.href='/stage/'+ch.date+'/'+ch.slot;hl.appendChild(st);hd.appendChild(hl);var stats=el('div','stats');hd.appendChild(stats);sh.appendChild(hd);
    var t=el('table');t.innerHTML='<thead><tr><th>Pos</th><th>Driver</th><th class="r">Time</th><th class="r gaph">Gap</th><th class="r">Pen</th></tr></thead>';
    var tb=el('tbody');t.appendChild(tb);sh.appendChild(t);s.appendChild(sh);
    return {node:s,map:mapBox,stats:stats,tb:tb};
  }

  function load(){
    $('next').disabled=cur>=today;
    $('dayname').textContent=cur===today?"Today's stages":'Stages of '+dayLabel(cur);
    get('/api/challenges?date='+cur).then(function(r){
      var box=$('stages');box.innerHTML='';maps={};PB={};
      if(r.error||!r.challenges||!r.challenges.length){box.appendChild(el('p','empty','No stages for this day.'));return}
      var tm=r.challenges[0].timing;   // how often the server wants the live map asked (wrangler.toml)
      // (with someone on stage, checked twice an app's update: the cars then run one update and one check late)
      if(tm){LIVE_BUSY=Math.min(tm.livePollS,Math.ceil(tm.liveSendS/2));LIVE_IDLE=tm.liveIdleS;
        LIVE_DELAY=(tm.liveSendS+LIVE_BUSY+1)*1000;LIVE_GAP=3*tm.liveSendS*1000}
      r.challenges.forEach(function(ch){
        ends=ch.endsAt;var x=stageBlock(ch);box.appendChild(x.node);x.m=drawMap(x.map,ch.route,EARTH[ch.track],EARTH[ch.track]?(window.innerWidth<=700?74:92):0);x.slot=ch.slot;maps[ch.slot]=x;
        satButton(x.map,ch);
        get('/api/leaderboard?date='+cur+'&slot='+ch.slot).then(function(b){sheet(x,b)});
      });
      pollLive(true);
    });
  }
  // live map: both dailies in one request, every LIVE_BUSY s while someone is on stage, every LIVE_IDLE s otherwise
  // (the server's timing), nothing while the tab is hidden; the cars played back between the apps' updates (drawLive)
  var liveN=0,anyLive=false,liveBusy=false,LIVE_BUSY=3,LIVE_IDLE=15;
  function pollLive(force){if(cur!==today||document.hidden||liveBusy)return;if(force!==true&&liveN++%(anyLive?LIVE_BUSY:LIVE_IDLE))return;
    liveBusy=true;
    get('/api/live?date='+cur+'&slot=all').then(function(d){if(!d||!d.drivers)return;   // (an error: the cars drive on)
      var all=d.drivers;anyLive=all.length>0;
      Object.keys(maps).forEach(function(slot){drawLive(maps[slot],{drivers:all.filter(function(x){return String(x.slot)===slot})},d.now)})},
      function(){}).then(function(){liveBusy=false})}
  // the timing sheets every minute while the tab is shown (a hidden one asks nothing: it catches up when shown again)
  var stale=false;
  function refresh(){if(cur!==today)return;if(document.hidden){stale=true;return}stale=false;
    Object.keys(maps).forEach(function(slot){var x=maps[slot];get('/api/leaderboard?date='+cur+'&slot='+slot).then(function(b){sheet(x,b)})})}
  document.addEventListener('visibilitychange',function(){if(!document.hidden){if(stale)refresh();pollLive(true)}});
  function tick(){
    if(cur!==today||!ends){$('ends').textContent='';return}
    var l=Math.max(0,ends-Date.now()),h=Math.floor(l/3600000),m=Math.floor(l%3600000/60000),s=Math.floor(l%60000/1000);
    $('ends').innerHTML='Stages close in <b class="num">'+h+':'+(m<10?'0':'')+m+':'+(s<10?'0':'')+s+'</b>';
    if(l===0){today=new Date().toISOString().slice(0,10);cur=today;load()}
  }
  $('prev').onclick=function(){cur=shift(cur,-1);load()};
  $('next').onclick=function(){if(cur<today){cur=shift(cur,1);load()}};
  load();tick();setInterval(tick,1000);setInterval(pollLive,1000);setInterval(refresh,60000);
})();
</script>
</body>
</html>`;
}
