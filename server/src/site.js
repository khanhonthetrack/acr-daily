// The public website. Rally timing-sheet look: black ground, hairlines instead of boxes, condensed type,
// ACR red only for stage numbers, P1, live cars and the active element. Two dailies = SS1 and SS2.
import { downloadUrl, hasDiscord, latestVersion } from './release.js';
import { coinSvg, envelopeSvg, FAVICON, logoSvg } from './logo.js';
import { BONUS_CSS, BONUS_JS } from './bonus.js';
import { STAGE_MAP_CSS, STAGE_MAP_JS } from './stagemap.js';
import { HEADER_FIT, I18N_JS, LANG_CSS, langPicker, langTag, t, tq, tqp, ts } from './i18n.js';

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
<html lang="${langTag()}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ACR Daily</title>
<meta name="description" content="${t("Two special stages a day for Assetto Corsa Rally. One car, one set of conditions, one timing sheet.")}">
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
.m-tt{--m:#BF5AF2}.m-leagues{--m:#5BA8FF}.m-1v1{--m:#FF9F43}.m-cups{--m:#FFD60A}.m-inbox{--m:#4CD6C0}
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
.dl{font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;text-transform:uppercase;text-decoration:none;color:var(--fg);background:var(--acc);padding:9px 14px;white-space:nowrap}
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
/* a daily bought in the shop: who set it */
.setby{margin:-14px 0 18px;font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.14em;text-transform:uppercase;color:#FFD60A}
.setby a{color:inherit;text-decoration:none;border-bottom:1px solid currentColor}.setby a:hover{color:var(--fg)}
.spec{display:grid;grid-template-columns:2.2fr 1fr 1.2fr .8fr;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.spec>div{padding:11px 0 12px;min-width:0}
.spec>div+div{padding-left:16px;border-left:1px solid var(--line)}
.spec .v{font:600 17px/1.2 'Barlow Condensed',sans-serif;margin-top:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

${STAGE_MAP_CSS}
.com{list-style:none;margin:10px 0 0;padding:0 0 0 12px;border-left:2px solid var(--acc);font-size:14px;color:var(--fg2)}
.com li{padding:2px 0;line-height:1.4}.com li.new{color:var(--fg)}.com li.quiet{color:var(--fg3)}
.live .tag{font:700 12px/1 'Barlow Condensed',sans-serif;letter-spacing:.16em;color:var(--fg)}
.live.none .tag{color:var(--fg3)}
.com .when{font:600 11px 'Barlow Condensed',sans-serif;letter-spacing:.08em;color:var(--fg3);margin-right:10px;font-feature-settings:'tnum'}
.live .chip{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;vertical-align:0}
.live .chip.av{width:18px;height:18px;border:2px solid;box-sizing:border-box;vertical-align:-4px;object-fit:cover}
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

/* two rows: logo + Get the app, then the links + the date (a narrower window, or header.two: HEADER_FIT, the one row
   too wide for the window in this language) */
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
@media (min-width:1181px){header:not(.two) .wrap>*{flex-shrink:0}
  header.tight .wrap{gap:14px}header.tight .hof{letter-spacing:.06em}
  header.two .wrap{gap:10px 16px;flex-wrap:wrap;height:auto;padding-top:12px;padding-bottom:12px}
  header.two .wrap::after{content:'';order:3;flex-basis:100%;height:0}
  header.two .brand{order:1}
  header.two .acct{order:2;margin-left:auto}
  header.two .dl,header.two .langpick{order:2}
  header.two .acct:empty+.dl{margin-left:auto}
  header.two .hof{order:4;white-space:nowrap;margin-left:0}
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
${LANG_CSS}
@media (max-width:1180px){.langpick{order:2}}
</style>
</head>
<body>
<header><div class="wrap">
  <a class="brand" href="/">${logoSvg()}<span>ACR Daily</span><b class="beta" title="${t('Beta: expect bugs. Report them on Discord.')}">${t('BETA')}</b></a>
  <a class="hof" href="/guide">${t('How to play')}</a>
  <a class="hof mode m-tt" href="/tt">${t('Time trial')}</a>
  <a class="hof mode m-leagues" href="/leagues">${t('Leagues')}</a>
  <a class="hof mode m-1v1" href="/1v1">1V1</a>
  <a class="hof mode m-cups" href="/cups">${t('Cups')}</a>
  <a class="hof" href="/ranking">${t('Ranking')}</a>
  <a class="hof" href="/teams">${t('Teams')}</a>
  <a class="hof mode m-inbox ib" href="/inbox" title="${t('Inbox')}" aria-label="${t('Inbox')}">${envelopeSvg()}<b class="unread" id="unread" hidden></b></a>
  <span class="hof crhost" id="crhost"></span>
  ${langPicker()}
  <a class="acct" id="acct"></a>
  ${download ? `<a class="dl" href="${download}">${t('Get the app')}</a>` : ''}
</div></header>
${HEADER_FIT}

<main class="wrap">
  <a class="cupstrip" id="cupstrip" hidden></a>
  <a class="cupstrip" id="tcupstrip" hidden></a>
  <div class="dayline"><nav class="datenav"><button id="prev" aria-label="${t('Previous day')}" title="${t('The day before')}">‹</button><h1 id="dayname">${t("Today's stages")}</h1><button id="next" aria-label="${t('Next day')}" title="${t('The day after')}">›</button></nav><div id="ends"></div></div>
  <div class="stages" id="stages"></div>
</main>

<footer><div class="wrap">
  <div><h2>${t('The app')}</h2><p>${t('Runs next to the game and times your run. DRIVE sets up the stage for you.')}</p></div>
  <div><h2>${t('The rules')}</h2><p>${t("Your first run counts, the rest is practice. The game's official time and penalties go on the sheet. Restart or retire and it's a DNF.")}</p></div>
  <div><h2>${t('New stages')}</h2><p>${t('Two every day at 00:00 UTC, each with its own car and weather.')}</p></div>
  <div><h2>${t('Something wrong?')}</h2><p>${t("A time that went missing, a stuck game, a page that breaks: tell us, with a screenshot and the game's log.")}</p><a class="oss foot" href="/report"><span>${t('Report a problem')}</span></a></div>
  ${discord || source ? `<div><h2>${t('Community')}</h2><p>${t('Chat, suggest ideas, report bugs.')}${source ? ' ' + t('The app and this website are open source.') : ''}</p>` +
    (discord ? `<a class="oss foot" href="${discord}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="${DISCORD_MARK}"/></svg><span>${t('ACR Daily on Discord')}</span></a>` : '') +
    (source ? `<a class="oss foot" href="${source}"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="${GITHUB_MARK}"/></svg><span>${t('Code on GitHub')}</span></a>` : '') + '</div>' : ''}
</div>
<div class="wrap legal">
  ${source ? `<span>${t('ACR Daily is open source under the {0}. {1}.', `<a href="${source}/blob/main/LICENSE">${t('MIT licence')}</a>`, `<a href="${source}">${t('Code, issues and pull requests on GitHub')}</a>`)}</span>` : ''}
  ${download ? `<span>${t('App v{0} is built by GitHub from the public code: {1}.', `${latestVersion(env)} (<a href="/changelog">${t("what's new")}</a>)`, `<a href="/guide#verify">${t('check your download')}</a>`)}</span>` : ''}
  ${env.CREDITS_FROM ? `<span>${t('{0}: earn them by driving, stake them on SS2, spend them in the {1}.', `<a href="/credits">${t('Credits')}</a>`, `<a href="/credits#shop">${t('shop')}</a>`)}</span>` : ''}
  <span>${t('A fan project, not affiliated with the makers of Assetto Corsa Rally.')}</span>
</div></footer>

<script>
${I18N_JS()}
(function(){
  var today=new Date().toISOString().slice(0,10),cur=today,ends=0,maps={};
  function $(id){return document.getElementById(id)}
  function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
  var NS='http://www.w3.org/2000/svg';
  function sv(tag,a){var e=document.createElementNS(NS,tag);for(var k in a||{})e.setAttribute(k,a[k]);return e}
  function fmt(ms){if(ms==null)return'–';var m=Math.floor(ms/60000),s=(ms%60000)/1000;return m+':'+(s<10?'0':'')+s.toFixed(3)}
  function shift(d,n){var t=new Date(d+'T00:00:00Z');t.setUTCDate(t.getUTCDate()+n);return t.toISOString().slice(0,10)}
  function dayLabel(d){return new Date(d+'T00:00:00Z').toLocaleDateString(LOC,{weekday:'short',day:'2-digit',month:'short',timeZone:'UTC'})}
  function get(u){return fetch(u,{cache:'no-store'}).then(function(r){return r.json()})}
  function km(m){return m?(m/1000).toFixed(1)+' km':''}
  var COIN=${JSON.stringify(coinSvg())};
  function coined(e,text){e.textContent=text;e.insertAdjacentHTML('beforeend',COIN)}   // an amount of credits: the coin by it
  ${BONUS_JS()}
  // signed in, credits on: the balance by the inbox, and today's bonus claimed here if it still is to be (src/bonus.js)
  // and my picture and name in the header, to my driver page (signed out: sign in)
  fetch('/api/me',{credentials:'same-origin',cache:'no-store'}).then(function(r){return r.ok?r.json():null}).then(function(me){
    var a=$('acct');if(!me)return;
    if(me.signedIn){a.href='/d/'+me.steamId;a.title=${tq('Your driver page')};if(me.avatar){var i=el('img');i.src=me.avatar;i.alt='';a.appendChild(i)}a.appendChild(el('span',null,me.name))}
    else{a.href='/login?next=/';a.className='acct out';a.textContent=${tq('Sign in')}}
    if(me.credits){creditsChip($('crhost'),me.credits);claimBonus($('crhost'),me.credits)}}).catch(function(){});
  // the inbox's unread count by its link (signed in on the website)
  fetch('/api/inbox/unread',{credentials:'same-origin',cache:'no-store'}).then(function(r){return r.ok?r.json():null}).then(function(j){
    if(j&&j.unread){var u=$('unread');u.textContent=j.unread>99?'99+':String(j.unread);u.hidden=false;
      u.parentNode.classList.add('new');u.parentNode.title=F(${tq('Inbox: {0} new')},j.unread)}}).catch(function(){});
  // ACR Daily's own cup, open for entries or under way (src/cups.js): a strip over the stages, to its page
  get('/api/cups/official').then(function(j){var c=j&&j.cups&&j.cups[0];if(!c)return;var s=$('cupstrip'),open=c.status==='open';
    s.href='/cup/'+c.id;s.innerHTML='';s.appendChild(el('span','tag',${tq('OFFICIAL CUP')}));s.appendChild(el('span','cn',c.name));
    var cs=el('span','cs'),said=open?F(${tq('Entries open · {0} of {1} drivers · starts {2}')},c.entrants,c.size,
      new Date(c.starts).toLocaleDateString(LOC,{weekday:'short',day:'numeric',month:'short'})):F(${tq('Under way · {0}')},P(${tqp('{0} driver', '{0} drivers')},c.entrants));
    if(c.prize)coined(cs,said+' · '+F(${tq('prize {0}')},c.prize));else cs.textContent=said;s.appendChild(cs);
    s.appendChild(el('span','go',open?${tq('Join ›')}:${tq('Bracket ›')}));s.hidden=false}).catch(function(){});
  // ACR Daily's own team cup (src/teamcups.js): the same, for teams
  get('/api/tcups/official').then(function(j){var c=j&&j.cups&&j.cups[0];if(!c)return;var s=$('tcupstrip'),open=c.status==='open';
    s.href='/tcup/'+c.id;s.innerHTML='';s.appendChild(el('span','tag',${tq('OFFICIAL TEAM CUP')}));s.appendChild(el('span','cn',c.name));
    s.appendChild(el('span','cs',open?F(${tq('Entries open · {0} of {1} teams · starts {2}')},c.teams,c.size,
      new Date(c.starts).toLocaleDateString(LOC,{weekday:'short',day:'numeric',month:'short'})):F(${tq('Under way · {0}')},P(${tqp('{0} team', '{0} teams')},c.teams))));
    s.appendChild(el('span','go',open?${tq('Sign up your team ›')}:${tq('Bracket ›')}));s.hidden=false}).catch(function(){});

${STAGE_MAP_JS()}

  function flag(parent,code){if(!code)return;var i=el('img','flagimg');i.src='https://flagcdn.com/w40/'+code+'.png';i.alt=code.toUpperCase();i.title=code.toUpperCase();i.width=18;i.height=12;parent.appendChild(i)}
  function sheet(x,b){
    var st=b.stats||{};x.stats.innerHTML='';
    [[st.drivers||0,${tq('drivers')}],[st.dnfs||0,${tq('DNF')}]].forEach(function(p,i){
      if(i)x.stats.appendChild(document.createTextNode('  ·  '));var s=el('b',null,String(p[0]));x.stats.appendChild(s);x.stats.appendChild(document.createTextNode(' '+p[1]))});
    var tb=x.tb;tb.innerHTML='';
    if(!b.entries||!b.entries.length){var tr=el('tr');var td=el('td','empty',${tq('No times yet.')});td.colSpan=5;tr.appendChild(td);tb.appendChild(tr);return}
    b.entries.forEach(function(e){
      var dnf=e.status==='dnf';var tr=el('tr',e.rank===1?'p1':(dnf?'dnf':''));tr.appendChild(el('td','pos',dnf?'–':String(e.rank)));
      var d=el('td','drv');flag(d,e.country);tagEl(d,e.look);var a=el('a',null,e.name);a.href='/d/'+e.steamId;a.title=${tq('Driver page')};d.appendChild(a);
      paint(a,e.look);if(e.look&&e.look.badge)d.appendChild(el('span','lookbadge',e.look.badge));   // (the shop)
      tr.appendChild(d);
      var t=el('td','t r');if(dnf){t.textContent=${tq('DNF')};t.title=e.reason||''}else{var ta=el('a',null,fmt(e.totalMs));ta.href='/run/'+e.runId;ta.title=${tq('Open the run')};t.appendChild(ta)}tr.appendChild(t);
      tr.appendChild(el('td','gap r',dnf||e.rank===1?'':'+'+(e.gapMs/1000).toFixed(3)));
      var pen=dnf?0:Math.round((e.totalMs-e.clockMs)/1000);   // the penalty: total - stage clock
      tr.appendChild(el('td','pen r',pen>0?'+'+pen:''));tb.appendChild(tr);
    });
  }


  function stageBlock(ch){
    var s=el('section','stage');
    var plate=el('div','plate');plate.appendChild(el('span','ss','SS'+ch.slot));
    plate.appendChild(el('span','where',[TD(ch.rally),TD(ch.surface),km(ch.lengthM)].filter(Boolean).join('  ·  ')));s.appendChild(plate);
    if(ch.wager){var wg=el('a','wager');coined(wg,F(${tq('Wager daily · stake {0}')},ch.wager.stake));wg.href='/credits';wg.title=${tq('Costs a stake to enter')};plate.appendChild(wg);
      get('/api/credits/wager?date='+ch.date+'&slot='+ch.slot).then(function(w){if(w&&w.entrants)coined(wg,F(${tq('Wager · {0} in · pot {1}')},w.entrants,w.pot+w.stake))})}
    var nm=el('h2','name');var na=el('a',null,ch.menuName||ch.stageName||ch.track);na.href='/stage/'+ch.date+'/'+ch.slot;na.title=${tq('Stage statistics')};nm.appendChild(na);s.appendChild(nm);
    // a daily bought in the shop: who set it
    if(ch.setBy){var sb=el('div','setby');var sa=el('a',null,ch.setBy.name);sa.href='/d/'+ch.setBy.steamId;add(sb,FN(${tq('Set by {0}')},sa));s.appendChild(sb)}
    var spec=el('div','spec');
    [[${tq('Car')},ch.car],[${tq('Class')},ch.carClass||'–'],[${tq('Weather')},TD(ch.weatherLabel)||'–'],[${tq('Start')},(ch.timeLabel||'').replace(/^.*\\((.*)\\)$/,'$1')||'–']].forEach(function(p){
      var d=el('div');d.appendChild(el('div','k',p[0]));d.appendChild(el('div','v',p[1]));spec.appendChild(d)});
    s.appendChild(spec);
    var mapBox=el('div','map');s.appendChild(mapBox);
    var sh=el('div','sheet');var hd=el('div','sheethead');var hl=el('div','k',${tq('Timing')}+'  ·  ');var st=el('a','statlink',${tq('Stats ›')});st.href='/stage/'+ch.date+'/'+ch.slot;hl.appendChild(st);hd.appendChild(hl);var stats=el('div','stats');hd.appendChild(stats);sh.appendChild(hd);
    var t=el('table');t.innerHTML='<thead><tr><th>${ts('Pos')}</th><th>${ts('Driver')}</th><th class="r">${ts('Time')}</th><th class="r gaph">${ts('Gap')}</th><th class="r">${ts('Pen')}</th></tr></thead>';
    var tb=el('tbody');t.appendChild(tb);sh.appendChild(t);s.appendChild(sh);
    return {node:s,map:mapBox,stats:stats,tb:tb};
  }
  function add(p){for(var i=1;i<arguments.length;i++){var c=arguments[i];if(c==null)continue;if(Array.isArray(c)){add.apply(null,[p].concat(c));continue}p.appendChild(typeof c==='string'?document.createTextNode(c):c)}return p}

  function load(){
    $('next').disabled=cur>=today;
    $('dayname').textContent=cur===today?${tq("Today's stages")}:F(${tq('Stages of {0}')},dayLabel(cur));
    get('/api/challenges?date='+cur).then(function(r){
      var box=$('stages');box.innerHTML='';maps={};PB={};
      if(r.error||!r.challenges||!r.challenges.length){box.appendChild(el('p','empty',${tq('No stages for this day.')}));return}
      var tm=r.challenges[0].timing;   // how often the server wants the live map asked (wrangler.toml)
      // (with someone on stage, checked twice an app's update: the cars then run one update and one check late)
      if(tm){LIVE_BUSY=Math.min(tm.livePollS,Math.ceil(tm.liveSendS/2));LIVE_IDLE=tm.liveIdleS;
        LIVE_DELAY=(tm.liveSendS+LIVE_BUSY+1)*1000;LIVE_GAP=3*tm.liveSendS*1000}
      r.challenges.forEach(function(ch){
        ends=ch.endsAt;var x=stageBlock(ch);box.appendChild(x.node);x.m=drawMap(x.map,ch.route,EARTH[ch.track],EARTH[ch.track]?(window.innerWidth<=700?74:92):0);x.slot=ch.slot;maps[ch.slot]=x;
        satButton(x.map,ch,cur===today);
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
    $('ends').innerHTML=F(${tq('Stages close in {0}')},'<b class="num">'+h+':'+(m<10?'0':'')+m+':'+(s<10?'0':'')+s+'</b>');
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
