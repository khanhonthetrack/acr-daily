// The public website. Rally timing-sheet look: black ground, hairlines instead of boxes, condensed type,
// ACR red only for stage numbers, P1, live cars and the active element. Two dailies = SS1 and SS2.
import { siteDownloadUrl, hasDiscord, latestVersion } from './release.js';
import { COMMUNITIES, communityImage } from './communities.js';
import { coinSvg, FAVICON } from './logo.js';
import { BONUS_CSS, BONUS_JS } from './bonus.js';
import { STAGE_MAP_CSS, STAGE_MAP_JS } from './stagemap.js';
import { I18N_JS, LANG_CSS, langTag, t, tq, tqp, ts } from './i18n.js';
import { HEADER_CSS, siteHeader } from './header.js';
import { metaTags } from './pagemeta.js';
import { PAGER_CSS, PAGER_JS } from './pager.js';

// the Discord logo mark (Simple Icons, CC0); Discord is a trademark of Discord Inc.
// the GitHub mark (Octicons, MIT); GitHub is a trademark of GitHub, Inc.
const GITHUB_MARK = 'M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z';
const DISCORD_MARK = 'M20.317 4.3698a19.7913 19.7913 0 00-4.8851-1.5152.0741.0741 0 00-.0785.0371c-.211.3753-.4447.8648-.6083 1.2495-1.8447-.2762-3.68-.2762-5.4868 0-.1636-.3933-.4058-.8742-.6177-1.2495a.077.077 0 00-.0785-.037 19.7363 19.7363 0 00-4.8852 1.515.0699.0699 0 00-.0321.0277C.5334 9.0458-.319 13.5799.0992 18.0578a.0824.0824 0 00.0312.0561c2.0528 1.5076 4.0413 2.4228 5.9929 3.0294a.0777.0777 0 00.0842-.0276c.4616-.6304.8731-1.2952 1.226-1.9942a.076.076 0 00-.0416-.1057c-.6528-.2476-1.2743-.5495-1.8722-.8923a.077.077 0 01-.0076-.1277c.1258-.0943.2517-.1923.3718-.2914a.0743.0743 0 01.0776-.0105c3.9278 1.7933 8.18 1.7933 12.0614 0a.0739.0739 0 01.0785.0095c.1202.099.246.1981.3728.2924a.077.077 0 01-.0066.1276 12.2986 12.2986 0 01-1.873.8914.0766.0766 0 00-.0407.1067c.3604.698.7719 1.3628 1.225 1.9932a.076.076 0 00.0842.0286c1.961-.6067 3.9495-1.5219 6.0023-3.0294a.077.077 0 00.0313-.0552c.5004-5.177-.8382-9.6739-3.5485-13.6604a.061.061 0 00-.0312-.0286zM8.02 15.3312c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9555-2.4189 2.157-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.9555 2.4189-2.1569 2.4189zm7.9748 0c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9554-2.4189 2.1569-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.946 2.4189-2.1568 2.4189Z';


/** The community spotlight under the dailies: each community's picture (to its Discord), name, a line and links. */
function spotlight() {
  if (!COMMUNITIES.length) return '';
  const esc = (x) => String(x).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  return `<section class="spot"><h2>${t('Community spotlight')}</h2><div class="spots">` + COMMUNITIES.map((c) =>
    `<article class="comm"><a class="pic" href="${esc(c.discord)}" target="_blank" rel="noopener" title="${esc(t('{0} on Discord', c.name))}">` +
    `<img src="${communityImage(c.key)}" width="${c.w}" height="${c.h}" alt="${esc(c.name)}" loading="lazy"></a>` +
    `<h3>${esc(c.name)}</h3><p>${esc(t(c.about))}</p><div class="links">` +
    `<a href="${esc(c.discord)}" target="_blank" rel="noopener"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="${DISCORD_MARK}"/></svg>${t('Join on Discord')}</a>` +
    (c.league ? `<a href="/l/${esc(c.league)}">${t('Their championship on ACR Daily')}</a>` : '') + '</div></article>').join('') + '</div></section>';
}

export function sitePage(env) {
  const download = siteDownloadUrl(env);
  const source = env.SOURCE_URL || '';
  // through /discord, which picks the current invite (the server widget's, naming nobody, when it is on)
  const discord = hasDiscord(env) ? '/discord' : '';
  return `<!doctype html>
<html lang="${langTag()}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ACR Daily · ${t('Your daily competitive portal')}</title>
${metaTags({ title: 'ACR Daily · ' + t('Your daily competitive portal'), url: '/', site: env.SITE_URL || '',
    description: t('Your daily competitive portal for Assetto Corsa Rally: dailies, time trials, ranked rallies, championships and cups.') })}
<link rel="icon" href="${FAVICON}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#0A0A0B;--line:#1F1F23;--line2:#2B2B31;--fg:#F4F4F5;--fg2:#A1A1AA;--fg3:#85858E;--acc:#E30613;--acct:#FF4655;--bad:#FF453A;--slow:#FF9F0A;--good:#30D158}
${PAGER_CSS}
*{box-sizing:border-box;margin:0}
html{background:var(--bg)}
body{color:var(--fg);font:15px/1.5 Barlow,system-ui,sans-serif;-webkit-font-smoothing:antialiased}
a{color:inherit}
.c{font-family:'Barlow Condensed',sans-serif}
.num{font-family:'Barlow Condensed',sans-serif;font-variant-numeric:tabular-nums;font-feature-settings:'tnum'}
.k{font:600 11px/1 Barlow,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:var(--fg3)}
.wrap{max-width:1200px;margin:0 auto;padding:0 24px}

/* the day's line: the day between its arrows (earlier days, back to today), when its stages close */
.dayline{display:flex;justify-content:space-between;align-items:center;padding:22px 0 8px;gap:8px 16px;flex-wrap:wrap}
.dayline h1{font:600 14px/1 'Barlow Condensed',sans-serif;letter-spacing:.16em;text-transform:uppercase;color:var(--fg);min-width:150px;text-align:center}
.datenav{display:flex;align-items:center;gap:2px;margin-left:-13px}
.datenav button{background:none;border:0;color:var(--fg2);font:500 22px/1 Barlow,sans-serif;width:44px;height:44px;cursor:pointer}
.datenav button:hover:not(:disabled){color:var(--acct,#FF4655)}
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
.cupstrip .go{margin-left:auto;font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;text-transform:uppercase;color:var(--acct,#FF4655)}
.cupstrip.sp{border-left-color:#78FAAE;padding:0 14px 0 0;overflow:hidden}.cupstrip.sp .tag{background:#78FAAE;color:#04140E}.cupstrip.sp .go{color:#78FAAE}
.cupstrip.sp img{display:block;height:76px;width:auto;aspect-ratio:480/270;object-fit:cover}
.cupstrip.tw{border-left-color:#9146FF;margin-top:10px}.cupstrip.tw .tag{background:#9146FF;color:#fff;display:inline-flex;align-items:center;gap:6px}
.cupstrip.tw .tag i{width:7px;height:7px;border-radius:50%;background:#fff;animation:twb 1.4s infinite}.cupstrip.tw .go{color:#BF94FF}
@keyframes twb{50%{opacity:.25}}


/* stages */
.stages{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 48px}
/* the community spotlight, under the dailies (src/communities.js) */
.spot{margin-top:8px}
.spot h2{font:600 14px/1 'Barlow Condensed',sans-serif;letter-spacing:.16em;text-transform:uppercase;color:var(--fg);padding:22px 0 18px}
.spots{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 48px}
.comm{padding:20px 0 40px;border-top:2px solid var(--fg)}
.comm .pic{display:block;aspect-ratio:3/2;overflow:hidden;background:#05070d;border:1px solid var(--line)}
.comm .pic img{display:block;width:100%;height:100%;object-fit:cover;transition:transform .25s ease,filter .25s ease}
.comm .pic:hover img{transform:scale(1.02);filter:brightness(1.12)}
.comm h3{font:600 26px/1.1 'Barlow Condensed',sans-serif;letter-spacing:.02em;margin:16px 0 6px}
.comm p{color:var(--fg2);font-size:14px;margin-bottom:12px}
.comm .links{display:flex;flex-wrap:wrap;gap:8px 20px}
.comm .links a{display:inline-flex;align-items:center;gap:8px;font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;text-transform:uppercase;text-decoration:none;color:var(--fg)}
.comm .links a:hover{color:var(--acct,#FF4655)}
.comm .links svg{width:16px;height:16px;fill:currentColor}
.stage{padding:20px 0 40px;border-top:2px solid var(--fg)}
.plate{display:flex;align-items:baseline;gap:14px}
.ss{font:700 15px/1 'Barlow Condensed',sans-serif;letter-spacing:.08em;color:var(--acct,#FF4655)}
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
tr.p1 td.pos{color:var(--acct,#FF4655)}
tr.me td{background:rgba(227,6,19,.12)}tr.me td:first-child{box-shadow:inset 3px 0 0 var(--acc);padding-left:10px}   /* my row, signed in */
.mepos{color:var(--acct,#FF4655);font-weight:600;text-decoration:none;cursor:pointer}.mepos:hover{text-decoration:underline}
td.drv{font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:0;width:100%}
td.drv a{text-decoration:none}
.flagimg{width:18px;height:12px;margin-right:8px;vertical-align:-1px;object-fit:cover;box-shadow:0 0 0 1px rgba(255,255,255,.12)}
.live .flagimg{margin:0 5px 0 0}
tr.dnf td{color:var(--fg3)}tr.dnf td.t{font-weight:500;color:var(--bad)}
td.drv a:hover{text-decoration:underline}
td.drv .cmt{white-space:normal;font:italic 400 12.5px/1.35 Barlow,sans-serif;color:var(--fg2);margin-top:3px;max-width:520px;overflow-wrap:anywhere}   /* a driver's comment on the run (src/comments.js) */
td.drv .cmt .only{font-style:normal;color:var(--fg3)}   /* my own, before the day is over: only I see it */
td.t{font:600 18px/1 'Barlow Condensed',sans-serif;font-feature-settings:'tnum';padding-left:16px;white-space:nowrap}
td.t a{text-decoration:none}
td.t a:hover{color:var(--acct,#FF4655)}
td.gap{font:500 15px/1 'Barlow Condensed',sans-serif;font-feature-settings:'tnum';color:var(--fg2);padding-left:16px;white-space:nowrap;width:84px}
td.pen{font:500 15px/1 'Barlow Condensed',sans-serif;color:var(--slow);padding-left:16px;width:48px}
.name a{text-decoration:none}.name a:hover{color:var(--acct,#FF4655)}
.statlink{color:var(--fg2);text-decoration:none}.statlink:hover{color:var(--acct,#FF4655)}
.lookbadge{margin-left:6px;font-size:14px;vertical-align:-1px}
.teamtag{font:700 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.06em;margin-right:6px}
.empty{padding:22px 0;color:var(--fg3);border-bottom:1px solid var(--line)}

.plate .wager{margin-left:auto;font:600 12px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;text-transform:uppercase;color:var(--acct,#FF4655);text-decoration:none;border:1px solid var(--acc);padding:4px 8px}
.plate .wager:hover{background:var(--acc);color:#fff}
.plate .wager .coin{display:inline-block;width:1.1em;height:1.1em;margin-left:.3em;vertical-align:-.25em}
/* footer */
footer{border-top:1px solid var(--line);margin-top:24px}
footer .wrap{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:32px;padding:32px 24px 56px}
.oss.foot{margin-top:12px;color:var(--fg)}
footer h2{font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.14em;text-transform:uppercase;margin-bottom:10px}
footer p{color:var(--fg2);font-size:14px;max-width:34ch}
.oss{display:flex;align-items:center;gap:7px;font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;text-transform:uppercase;text-decoration:none;color:var(--fg2)}
.oss:hover{color:var(--acct,#FF4655)}
.oss svg{width:15px;height:15px;fill:currentColor}
.legal{border-top:1px solid var(--line);padding:16px 0 40px;font-size:12px;color:var(--fg3);display:flex;gap:6px 16px;flex-wrap:wrap}
.legal a{color:var(--fg2)}.legal a:hover{color:var(--acct,#FF4655)}

/* the dailies' two tabs: the official ones, and CODRIVER DAILY (src/copilot.js) */
.dtabs{display:flex;gap:4px;margin:0 0 18px;border-bottom:1px solid var(--line)}
.dtabs[hidden],#stages[hidden],#cpday[hidden],.datenav button[hidden]{display:none!important}   /* (.stages is a grid: its own display beat [hidden]) */
.dtabs button{background:none;border:0;border-bottom:2px solid transparent;color:var(--fg2);cursor:pointer;margin-bottom:-1px;
  font:700 14px/1 'Barlow Condensed',sans-serif;letter-spacing:.14em;text-transform:uppercase;padding:12px 14px}
.dtabs button:hover{color:var(--fg)}
.dtabs button.on{color:var(--fg);border-bottom-color:var(--acc)}
.cphide{display:flex;gap:18px;align-items:center;padding:18px 0;border-bottom:1px solid var(--line)}
.cphide .q{flex:0 0 auto;width:76px;height:76px;display:grid;place-items:center;background:#FF9F0A;color:#0b0b0d;
  font:800 52px/1 'Barlow Condensed',sans-serif}
.cphide b{display:block;font:700 22px/1.15 'Barlow Condensed',sans-serif;letter-spacing:.04em;text-transform:uppercase}
.cphide p{margin:6px 0 0;color:var(--fg2);max-width:60ch}
.cptab td.drv{width:38%}.cptab td.drv.co{color:var(--fg2)}
@media (max-width:860px){
  .stages,.spots{grid-template-columns:1fr}
  .spec{grid-template-columns:1fr 1fr}
  .spec>div:nth-child(3){padding-left:0;border-left:0}
  .spec>div:nth-child(n+3){border-top:1px solid var(--line)}
  footer .wrap{grid-template-columns:1fr;gap:20px}
  td.gap,th.gaph{display:none}
  .wrap{padding:0 16px}
}
${BONUS_CSS}
${LANG_CSS}
${HEADER_CSS}
</style>
</head>
<body>
${siteHeader(env)}

<main class="wrap">
  <a class="cupstrip" id="cupstrip" hidden></a>
<a class="cupstrip tw" id="twstrip" hidden target="_blank" rel="noopener"></a>
  <a class="cupstrip" id="tcupstrip" hidden></a>
  <div class="dayline"><nav class="datenav"><button id="prev" aria-label="${t('Previous day')}" title="${t('The day before')}">‹</button><h1 id="dayname">${t("Today's stages")}</h1><button id="next" aria-label="${t('Next day')}" title="${t('The day after')}">›</button></nav><div id="ends"></div></div>
  <nav class="dtabs" id="dtabs" hidden><button id="tab-official" class="on">${t('Official')}</button><button id="tab-codriver">${t('Codriver')}</button></nav>
  <div class="stages" id="stages"></div>
  <div id="cpday" hidden></div>
  ${spotlight()}
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
${PAGER_JS()}
(function(){
  var today=new Date().toISOString().slice(0,10),cur=today,ends=0,maps={};
  function $(id){return document.getElementById(id)}
  function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
  var NS='http://www.w3.org/2000/svg';
  function sv(tag,a){var e=document.createElementNS(NS,tag);for(var k in a||{})e.setAttribute(k,a[k]);return e}
  function fmt(ms){if(ms==null)return'–';var m=Math.floor(ms/60000),s=(ms%60000)/1000;return m+':'+(s<10?'0':'')+s.toFixed(3)}
  function shift(d,n){var t=new Date(d+'T00:00:00Z');t.setUTCDate(t.getUTCDate()+n);return t.toISOString().slice(0,10)}
  function dayLabel(d){return FDATE(d+'T00:00:00Z',{utc:true,wd:true})}
  function get(u){return fetch(u,{cache:'no-store'}).then(function(r){return r.json()})}
  function km(m){return m?(m/1000).toFixed(1)+' km':''}
  var COIN=${JSON.stringify(coinSvg())};
  function coined(e,text){e.textContent=text;e.insertAdjacentHTML('beforeend',COIN)}   // an amount of credits: the coin by it
  ${BONUS_JS()}
  // who is signed in: the header's account, the inbox's count and the credits (src/header.js headerMe), and today's bonus
  // claimed here if it still is to be (src/bonus.js)
  var MEP=fetch('/api/me',{credentials:'same-origin',cache:'no-store'}).then(function(r){return r.ok?r.json():null}).catch(function(){return null});
  MEP.then(function(me){headerMe(me);if(me&&me.signedIn&&me.credits)claimBonus($('crhost'),me.credits)}).catch(function(){});
  // ACR Daily live on Twitch (src/twitch.js): a thin strip of its own while the channel streams, to it (asked again every minute)
  function tw(){get('/api/twitch').then(function(t){var s=$('twstrip');if(!t||!t.live||String(t.url||'').indexOf('https://www.twitch.tv/')!==0){s.hidden=true;return}
    s.href=t.url;s.innerHTML='';var g=el('span','tag');g.appendChild(el('i'));g.appendChild(document.createTextNode(${tq('LIVE ON TWITCH')}));s.appendChild(g);
    s.appendChild(el('span','cn',${tq('ACR Daily is live')}));var bits=[t.title,t.viewers!=null?P(${tqp('{0} watching','{0} watching')},t.viewers):''].filter(Boolean);
    if(bits.length)s.appendChild(el('span','cs',bits.join(' · ')));s.appendChild(el('span','go',${tq('Watch ›')}));s.hidden=false}).catch(function(){})}
  tw();setInterval(tw,60000);
  // a special event (src/liverallies.js SPECIALS: the Skoda Saturday Challenge) in the official cup's place while it is listed (the user,
  // 25 Nov 2026: "Put the announcement of this special event in the place of mini challenge"); else ACR Daily's own cup, open for
  // entries or under way (src/cups.js): a strip over the stages, to its page. Not once it is over (the user, 28 Nov 2026: "remove
  // the special event bar for skoda on main website, it already finished"; its results stay in RANKED)
  var SPP=get('/api/liverallies').then(function(j){var x=((j&&j.specials)||[]).filter(function(y){return y.phase!=='over'})[0];if(!x)return false;var s=$('cupstrip');s.className='cupstrip sp';
    s.href='/ranked/'+x.key;s.innerHTML='';var im=el('img');im.src='/series/'+x.key+'.webp';im.alt='';s.appendChild(im);
    s.appendChild(el('span','tag',${tq('SPECIAL EVENT')}));s.appendChild(el('span','cn',x.name));
    var d=new Date(x.starts),when=d.toLocaleDateString(LOC,{weekday:'short',day:'numeric',month:'short'})+' '+d.toLocaleTimeString(LOC,{hour:'2-digit',minute:'2-digit'});
    var cs=el('span','cs');coined(cs,F(${tq('{0} · {1} stages of {2} · free entry · {3} registered · every finisher gets {4}')},when,x.stages,x.rally,x.signups||0,x.prize));s.appendChild(cs);
    s.appendChild(el('span','go',x.phase==='signup'?${tq('Register ›')}:${tq('Watch it live ›')}));s.hidden=false;return true}).catch(function(){return false});
  SPP.then(function(sp){if(sp)return;get('/api/cups/official').then(function(j){var c=j&&j.cups&&j.cups[0];if(!c)return;var s=$('cupstrip'),open=c.status==='open';
    s.href='/cup/'+c.id;s.innerHTML='';s.appendChild(el('span','tag',${tq('OFFICIAL CUP')}));s.appendChild(el('span','cn',c.name));
    var cs=el('span','cs'),said=open?F(${tq('Entries open · {0} of {1} drivers · starts {2}')},c.entrants,c.size,
      FDATE(c.starts,{wd:true})):F(${tq('Under way · {0}')},P(${tqp('{0} driver', '{0} drivers')},c.entrants));
    if(c.prize)coined(cs,said+' · '+F(${tq('prize {0}')},c.prize));else cs.textContent=said;s.appendChild(cs);
    s.appendChild(el('span','go',open?${tq('Join ›')}:${tq('Bracket ›')}));s.hidden=false}).catch(function(){})});
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
    var tb=x.tb;tb.innerHTML='';var cells={},mine={};
    if(!b.entries||!b.entries.length){var tr=el('tr');var td=el('td','empty',${tq('No times yet.')});td.colSpan=5;tr.appendChild(td);tb.appendChild(tr);return}
    b.entries.forEach(function(e){
      var dnf=e.status==='dnf';var tr=el('tr',e.rank===1?'p1':(dnf?'dnf':''));tr.appendChild(el('td','pos',dnf?'–':String(e.rank)));
      var d=el('td','drv');cells[e.steamId]=d;mine[e.steamId]=e;flag(d,e.country);tagEl(d,e.look);var a=el('a',null,e.name);a.href='/d/'+e.steamId;a.title=${tq('Driver page')};d.appendChild(a);
      paint(a,e.look);if(e.look&&e.look.badge)d.appendChild(el('span','lookbadge',e.look.badge));   // (the shop)
      if(e.comment){var cm=el('div','cmt','“'+e.comment+'”');cm.title=${tq('Their comment on the run')};d.appendChild(cm)}   // (src/comments.js)
      tr.appendChild(d);
      var t=el('td','t r');if(dnf){t.textContent=${tq('DNF')};t.title=e.reason||''}else{var ta=el('a',null,fmt(e.totalMs));ta.href='/run/'+e.runId;ta.title=${tq('Open the run')};t.appendChild(ta);}tr.appendChild(t);
      tr.appendChild(el('td','gap r',dnf||e.rank===1?'':'+'+(e.gapMs/1000).toFixed(3)));
      var pen=dnf?0:Math.round((e.totalMs-e.clockMs)/1000);   // the penalty: total - stage clock
      tr.appendChild(el('td','pen r',pen>0?'+'+pen:''));tb.appendChild(tr);
    });
    paginate(tb,'ss'+b.date+'/'+b.slot,tb.parentNode);   // (30 a page: src/pager.js)
    // signed in and on it: my row lit, and "You: P12" by the counts takes the page to it (a long sheet)
    MEP.then(function(me){var c=me&&me.signedIn&&cells[me.steamId];if(!c||!c.isConnected)return;var tr=c.parentNode,e=mine[me.steamId];
      tr.classList.add('me');var lk=el('a','mepos',F(${tq('You: {0}')},e.status==='dnf'?${tq('DNF')}:'P'+e.rank));lk.href='#ss'+b.slot;
      lk.onclick=function(ev){ev.preventDefault();var still=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;
        if(tb.pageTo)tb.pageTo(tr);tr.scrollIntoView({behavior:still?'auto':'smooth',block:'center'})};
      x.stats.appendChild(document.createTextNode('  ·  '));x.stats.appendChild(lk)});
    // the comments are everyone's once the day is over (src/commentboard.js); until then a driver sees their own
    if(b.commentsAt&&Date.now()<b.commentsAt)MEP.then(function(me){var c=me&&me.signedIn&&cells[me.steamId];if(!c)return;
      var on=b.date+'/'+b.slot;get('/api/comments/mine?on='+encodeURIComponent(on)).then(function(j){var t=j&&j.comments&&j.comments[on];
        if(!t||!c.isConnected)return;var cm=el('div','cmt','“'+t+'”');cm.appendChild(el('span','only',' · '+${tq('only you see it until the day is over')}));c.appendChild(cm)})});
  }


  function stageBlock(ch){
    var s=el('section','stage');s.id='ss'+ch.slot;   // (/#ss2: the app's "Timing sheet ›" on daily 2's card)
    if(location.hash==='#ss'+ch.slot)setTimeout(function(){s.scrollIntoView()},300);
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
    if(typeof tab==='undefined'||tab==='official')$('dayname').textContent=cur===today?${tq("Today's stages")}:F(${tq('Stages of {0}')},dayLabel(cur));
    get('/api/challenges?date='+cur).then(function(r){
      var box=$('stages');box.innerHTML='';var keep=maps.cp;maps={};if(keep)maps.cp=keep;PB={};
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
      Object.keys(maps).forEach(function(slot){if(slot==='cp')return;drawLive(maps[slot],{drivers:all.filter(function(x){return String(x.slot)===slot})},d.now)})},
      function(){}).then(function(){liveBusy=false})}
  // the timing sheets every minute while the tab is shown (a hidden one asks nothing: it catches up when shown again)
  var stale=false;
  function refresh(){if(cur!==today)return;if(document.hidden){stale=true;return}stale=false;
    Object.keys(maps).forEach(function(slot){if(slot==='cp')return;var x=maps[slot];get('/api/leaderboard?date='+cur+'&slot='+slot).then(function(b){sheet(x,b)})})}
  document.addEventListener('visibilitychange',function(){if(!document.hidden){if(stale)refresh();pollLive(true)}});
  function tick(){
    if(cur!==today||!ends){$('ends').textContent='';return}
    var l=Math.max(0,ends-Date.now()),h=Math.floor(l/3600000),m=Math.floor(l%3600000/60000),s=Math.floor(l%60000/1000);
    $('ends').innerHTML=F(${tq('Stages close in {0}')},'<b class="num">'+h+':'+(m<10?'0':'')+m+':'+(s<10?'0':'')+s+'</b>');
    if(l===0){today=new Date().toISOString().slice(0,10);cur=today;load()}
  }
  // ---- CODRIVER (src/copilot.js: the daily for two): today's crews' standings to everyone; the stage, its map and the crews on it
  // only to someone who has driven it (as driver or co-driver): it stays hidden until then (the user, 26 Nov 2026)
  var tab='official',cpOn=false,cpShown=false,cpLive=0;
  // (the day's heading: the day before / after go through the CODRIVER days too, as the official ones: the user, 26 Nov
  // 2026 "we should be able to see the history, like yesterday, just like normal daily")
  function dayHead(){$('dayname').textContent=tab==='official'?(cur===today?${tq("Today's stages")}:F(${tq('Stages of {0}')},dayLabel(cur))):
    (cur===today?${tq("Today's CODRIVER DAILY")}:${tq('CODRIVER')}+' · '+dayLabel(cur))}
  function setTab(t){tab=t;$('tab-official').className=t==='official'?'on':'';$('tab-codriver').className=t==='codriver'?'on':'';
    $('stages').hidden=t!=='official';$('cpday').hidden=t!=='codriver';dayHead();
    try{history.replaceState(null,'',t==='codriver'?'#codriver':location.pathname)}catch(e){}
    if(t==='codriver')cpLoad()}
  $('tab-official').onclick=function(){setTab('official')};
  $('tab-codriver').onclick=function(){setTab('codriver')};
  get('/api/copilot').then(function(d){if(!d||!d.on)return;cpOn=true;$('dtabs').hidden=false;if(location.hash==='#codriver')setTab('codriver')}).catch(function(){});
  function cpLoad(){
    var day=cur;   // (the day on screen: today's, or one before it)
    Promise.all([get('/api/copilot?date='+day),get('/api/copilot/board?date='+day)]).then(function(a){
      if(day!==cur)return;   // (another day asked for meanwhile)
      var d=a[0]||{},b=a[1]||{},box=$('cpday');box.innerHTML='';delete maps.cp;cpShown=false;
      if(d.on===false||d.error){box.appendChild(el('p','empty',${tq('No stages for this day.')}));return}
      var s=el('section','stage');var plate=el('div','plate');plate.appendChild(el('span','ss',${tq('CODRIVER')}));
      var st=d.revealed&&d.stage?d.stage:(b.stage||null);
      if(st)plate.appendChild(el('span','where',[TD(st.rally),km(st.lengthM)].filter(Boolean).join('  ·  ')));
      s.appendChild(plate);
      if(st){
        s.appendChild(el('h2','name',st.menuName||st.stageName||st.track));
        var spec=el('div','spec');
        [[${tq('Car')},st.car||'–'],[${tq('Weather')},TD(st.weatherLabel)||'–'],[${tq('Start')},(st.timeLabel||'').replace(/^.*\\((.*)\\)$/,'$1')||'–'],[${tq('Mode')},${tq('Hardcore')}]].forEach(function(p){
          var x=el('div');x.appendChild(el('div','k',p[0]));x.appendChild(el('div','v',p[1]));spec.appendChild(x)});
        s.appendChild(spec);
        var mb=el('div','map');s.appendChild(mb);
        get('/api/route?track='+encodeURIComponent(st.track)).then(function(r){if(!r||!r.route||!mb.isConnected)return;
          // (on satellite imagery as the official stages: the corner kept clear for its button)
          var g=EARTH[st.track];maps.cp={m:drawMap(mb,r.route,g,g?(window.innerWidth<=700?74:92):0),slot:'cp'};
          satButton(mb,{track:st.track,route:r.route},false);
          cpShown=day===today;cpPoll(true)}).catch(function(){});
      }else{
        var h=el('div','cphide');h.appendChild(el('div','q','?'));var w=el('div');
        w.appendChild(el('b',null,${tq('Hidden until you drive it')}));
        w.appendChild(el('p',null,${tq('Drive it once, as the driver or the co-driver, to see the stage, its map and the crews on it. Until then: the standings.')}));
        h.appendChild(w);s.appendChild(h);
      }
      var sh=el('div','sheet');var hd=el('div','sheethead');hd.appendChild(el('div','k',${tq('Standings')}));
      var stats=el('div','stats');stats.textContent=P(${tqp('{0} crew','{0} crews')},(b.entries||[]).length);hd.appendChild(stats);sh.appendChild(hd);
      var t=el('table','cptab');t.innerHTML='<thead><tr><th>${ts('Pos')}</th><th>${ts('Driver')}</th><th>${ts('Co-driver')}</th><th class="r">${ts('Time')}</th><th class="r gaph">${ts('Gap')}</th></tr></thead>';
      var tb=el('tbody');t.appendChild(tb);sh.appendChild(t);s.appendChild(sh);box.appendChild(s);
      if(!b.entries||!b.entries.length){var tr=el('tr');var td=el('td','empty',${tq('No crew has driven it yet.')});td.colSpan=5;tr.appendChild(td);tb.appendChild(tr);return}
      MEP.then(function(me){var mid=me&&me.signedIn?me.steamId:null;
        b.entries.forEach(function(e){var dnf=e.status!=='finished';var tr=el('tr',e.rank===1?'p1':(dnf?'dnf':''));
          if(mid&&((e.driver||{}).steamId===mid||(e.codriver||{}).steamId===mid))tr.classList.add('me');
          tr.appendChild(el('td','pos',dnf?'–':String(e.rank)));
          [[e.driver,'drv'],[e.codriver,'drv co']].forEach(function(p){var c=el('td',p[1]),who=p[0]||{};flag(c,who.country);tagEl(c,who.look);
            var a=el('a',null,who.name||'?');a.href='/d/'+who.steamId;c.appendChild(a);tr.appendChild(c)});
          var tt=el('td','t r',dnf?${tq('DNF')}:fmt(e.totalMs));if(dnf)tt.title=e.reason||'';tr.appendChild(tt);
          tr.appendChild(el('td','gap r',dnf||e.rank===1||e.gapMs==null?'':'+'+(e.gapMs/1000).toFixed(3)));tb.appendChild(tr)});
        paginate(tb,'cp'+(b.date||''),tb.parentNode)});
    }).catch(function(){})}
  // the crews on the stage: every few seconds while the tab is shown (only to those who may see it: the server says)
  function cpPoll(force){if(tab!=='codriver'||!cpShown||document.hidden)return;if(force!==true&&cpLive++%3)return;
    get('/api/copilot/live').then(function(d){if(d&&d.drivers&&maps.cp)drawLive(maps.cp,{drivers:d.drivers},d.now)}).catch(function(){})}
  setInterval(cpPoll,1000);
  setInterval(function(){if(tab==='codriver'&&cur===today&&!document.hidden)cpLoad()},60000);
  $('prev').onclick=function(){cur=shift(cur,-1);load();if(tab==='codriver'){dayHead();cpLoad()}};
  $('next').onclick=function(){if(cur<today){cur=shift(cur,1);load();if(tab==='codriver'){dayHead();cpLoad()}}};
  load();tick();setInterval(tick,1000);setInterval(pollLive,1000);setInterval(refresh,60000);
})();
</script>
</body>
</html>`;
}
