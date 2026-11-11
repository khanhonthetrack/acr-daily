// /guide - how to take part: install, sign in, set up, drive; then the two dailies, the rules, credits, the time trial, 1V1s, cups,
// leagues, the rating, the driver page, the shop and the inbox, the badges and a short FAQ. The numbers come from the
// code that applies them (credits.js, h2h.js, cups.js, rating.js, drivers.js), so the page can't drift from the rules.

// the Steam logo mark (Simple Icons); Steam is a trademark of Valve Corporation
const STEAM = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M11.979 0C5.678 0 .511 4.86.022 11.037l6.432 2.658c.545-.371 1.203-.59 1.912-.59.063 0 .125.004.188.006l2.861-4.142V8.91c0-2.495 2.028-4.524 4.524-4.524 2.494 0 4.524 2.031 4.524 4.527s-2.03 4.525-4.524 4.525h-.105l-4.076 2.911c0 .052.004.105.004.159 0 1.875-1.515 3.396-3.39 3.396-1.635 0-3.016-1.173-3.331-2.727L.436 15.27C1.862 20.307 6.486 24 11.979 24c6.627 0 11.999-5.373 11.999-12S18.605 0 11.979 0zM7.54 18.21l-1.473-.61c.262.543.714.999 1.314 1.25 1.297.539 2.793-.076 3.332-1.375.263-.63.264-1.319.005-1.949s-.75-1.121-1.377-1.383c-.624-.26-1.29-.249-1.878-.03l1.523.63c.956.4 1.409 1.5 1.009 2.455-.397.957-1.497 1.41-2.454 1.012H7.54zm11.415-9.303c0-1.662-1.353-3.015-3.015-3.015-1.665 0-3.015 1.353-3.015 3.015 0 1.665 1.35 3.015 3.015 3.015 1.663 0 3.015-1.35 3.015-3.015zm-5.273-.005c0-1.252 1.013-2.266 2.265-2.266 1.249 0 2.266 1.014 2.266 2.266 0 1.251-1.017 2.265-2.266 2.265-1.253 0-2.265-1.014-2.265-2.265z"/></svg>';

import { downloadUrl, latestVersion, releasePage } from './release.js';
import { coinSvg, envelopeSvg, FAVICON, logoSvg } from './logo.js';
import { CREDITS, WAGER } from './credits.js';
import { H2H } from './h2h.js';
import { CUP } from './cups.js';
import { RATING } from './rating.js';
import { TT } from './timetrial.js';
import { LANG_CSS, langPicker, langTag, t, tq } from './i18n.js';

export function guidePage(env) {
  const download = downloadUrl(env);
  const release = releasePage(env);
  const repo = (env.SOURCE_URL || '').replace(/^https:\/\/github\.com\//, '');
  const coin = coinSvg();
  // an amount of credits with the coin: "1,000" (by hand: a Worker's first Intl call costs ~14 ms of CPU)
  const cr = (n) => `<b>${String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}</b>${coin}`;
  return `<!doctype html>
<html lang="${langTag()}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${t('ACR Daily guide')}</title>
<meta name="description" content="${t('How to take part in ACR Daily.')}">
<link rel="icon" href="${FAVICON}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#0A0A0B;--line:#1F1F23;--line2:#2B2B31;--fg:#F4F4F5;--fg2:#A1A1AA;--fg3:#6B6B74;--acc:#E30613;--bad:#FF453A;--good:#30D158;--steam:#171A21}
*{box-sizing:border-box;margin:0}
html{background:var(--bg)}
body{color:var(--fg);font:16px/1.6 Barlow,system-ui,sans-serif;-webkit-font-smoothing:antialiased}
a{color:inherit}
.wrap{max-width:880px;margin:0 auto;padding:0 24px}
header{border-bottom:1px solid var(--line)}
header .wrap{display:flex;align-items:center;justify-content:space-between;height:76px;max-width:1200px}
.brand{display:flex;align-items:center;gap:10px;font:700 20px/1 'Barlow Condensed',sans-serif;letter-spacing:.06em;text-decoration:none}
.brandmark{display:block;height:60px;width:auto}
.back{font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;text-transform:uppercase;text-decoration:none;color:var(--fg2)}
.back:hover{color:var(--fg)}
.top{margin-top:28px;padding-top:20px;border-top:2px solid var(--fg)}
.kick{font:700 15px/1 'Barlow Condensed',sans-serif;letter-spacing:.08em;color:var(--acc)}
h1{font:700 clamp(40px,6vw,72px)/.95 'Barlow Condensed',sans-serif;text-transform:uppercase;margin-top:12px}
.lead{color:var(--fg2);margin:14px 0 8px;max-width:60ch}
h2{font:700 28px/1 'Barlow Condensed',sans-serif;text-transform:uppercase;letter-spacing:.02em;margin:56px 0 6px}
.k{font:600 11px/1 Barlow,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:var(--fg3)}
ol.steps{list-style:none;padding:0;margin-top:22px;counter-reset:s}
ol.steps>li{display:grid;grid-template-columns:56px 1fr;gap:0 8px;padding:20px 0;border-top:1px solid var(--line);counter-increment:s}
ol.steps>li::before{content:counter(s,decimal-leading-zero);font:700 26px/1 'Barlow Condensed',sans-serif;color:var(--acc)}
.steps h3{font:700 20px/1.1 'Barlow Condensed',sans-serif;text-transform:uppercase;letter-spacing:.02em;margin-bottom:6px}
.steps p,.steps li li{color:var(--fg2)}
.steps p+p{margin-top:8px}
b,strong{color:var(--fg);font-weight:600}
.path{font:600 15px/1.5 'Barlow Condensed',sans-serif;letter-spacing:.04em;color:var(--fg)}
.path i{font-style:normal;color:var(--fg3);margin:0 6px}
.btn{display:inline-flex;align-items:center;gap:8px;margin-top:10px;font:600 14px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;text-transform:uppercase;text-decoration:none;padding:10px 14px}
.btn.dl{background:var(--acc);color:var(--fg)}.btn.dl:hover{background:var(--fg);color:var(--bg)}
.btn.steam{background:var(--steam);color:#fff;cursor:default}
.btn svg{width:18px;height:18px;fill:currentColor}
table{width:100%;border-collapse:collapse;margin-top:14px}
td{padding:11px 0;border-top:1px solid var(--line);vertical-align:top}
td:first-child{width:150px;padding-right:16px;white-space:nowrap}
td+td{color:var(--fg2)}
.badge{font:700 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em}
.live{color:var(--acc)}.ready{color:var(--good)}.muted{color:var(--fg2)}
.small{font-size:13px;color:var(--fg3);margin-top:10px}
code{font:13px/1.5 Consolas,ui-monospace,monospace;color:var(--fg);background:#141417;padding:1px 6px;word-break:break-all}
.faq dt{font-weight:600;margin-top:18px}
.faq dd{color:var(--fg2);margin:4px 0 0}
footer{margin-top:64px;border-top:1px solid var(--line);padding:20px 0 48px;color:var(--fg3);font-size:13px}
/* the contents, and each part of the game in its own colour (as in the headers and the app's tabs) */
.toc{display:flex;flex-wrap:wrap;gap:8px 18px;margin-top:22px;padding:14px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.toc a{font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;text-transform:uppercase;text-decoration:none;color:var(--fg2)}
.toc a:hover{color:var(--fg)}.toc a.mode{color:var(--m)}
h2 .tag{display:inline-block;margin-right:10px;padding:3px 7px 2px;font:700 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;color:#0A0A0B;background:var(--m,var(--fg));vertical-align:6px}
.m-tt{--m:#BF5AF2}.m-leagues{--m:#5BA8FF}.m-1v1{--m:#FF9F43}.m-cups{--m:#FFD60A}.m-inbox{--m:#4CD6C0}
.part{margin-top:14px;color:var(--fg2)}
.part p+p{margin-top:8px}
.coin{display:inline-block;width:1em;height:1em;vertical-align:-.15em;margin-left:.15em}
td .coin{width:.95em;height:.95em}
.env{display:inline-block;width:1.2em;height:1.2em;vertical-align:-.25em;color:#4CD6C0}
.note{margin-top:12px;padding:10px 14px;border-left:3px solid var(--acc);background:#111113;color:var(--fg2);font-size:15px}
@media (max-width:640px){.wrap{padding:0 16px}ol.steps>li{grid-template-columns:40px 1fr}td:first-child{width:110px;white-space:normal}}
.beta{display:inline-block;margin-left:8px;padding:2px 6px;border:1px solid #E30613;border-radius:3px;color:#E30613;font:700 12px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;vertical-align:middle;text-decoration:none}
${LANG_CSS}
header .back{margin-left:auto}header .langpick{margin-left:22px}
</style>
</head>
<body>
<header><div class="wrap"><a class="brand" href="/">${logoSvg()}<b class="beta" title="${t('ACR Daily is in beta: things may change and bugs are expected. Report them at acrdaily.com/report.')}">${t('BETA')}</b></a><a class="back" href="/">${t("‹ Today's stages")}</a>${langPicker()}</div></header>
<main class="wrap">
  <div class="top">
    <div class="kick">${t('GUIDE')}</div>
    <h1>${t('How to take part')}</h1>
    <p class="lead">${t('Two new stages every day. Same car and conditions for everyone, one timing sheet. You need Assetto Corsa Rally on Steam and a Windows PC. Setup takes about five minutes.')}</p>
  </div>
  <nav class="toc" aria-label="${t('Contents')}">
    <a href="#start">${t('Set up')}</a><a href="#dailies">${t('The dailies')}</a><a href="#rules">${t('Rules')}</a><a href="#credits">${t('Credits')}</a>
    <a class="mode m-tt" href="#tt">${t('Time trial')}</a><a class="mode m-1v1" href="#1v1">1V1</a><a class="mode m-cups" href="#cups">${t('Cups')}</a><a class="mode m-leagues" href="#leagues">${t('Leagues')}</a>
    <a href="#rating">${t('Rating')}</a><a href="#driver">${t('Your page')}</a><a href="#shop">${t('Shop')}</a><a class="mode m-inbox" href="#inbox">${t('Inbox')}</a>
    <a href="#app">${t('The app')}</a><a href="#faq">${t('FAQ')}</a>
  </nav>

  <ol class="steps" id="start">
    <li><div>
      <h3>${t('Get the app')}</h3>
      <p>${t('Download <b>ACR-Daily.exe</b> and run it. No install needed.')}</p>
      <p>${t('Windows may say <b>“Windows protected your PC”</b> the first time. Click <b>More info › Run anyway</b>.')}</p>
      ${download ? `<a class="btn dl" href="${download}">${t('Download the app')}</a>` : ''}
      ${release ? `<p class="small">${t('v{0}, built by GitHub from the public code. {1}.', latestVersion(env), `<a href="#verify">${t('Check it')}</a>`)}</p>` : ''}
    </div></li>
    <li><div>
      <h3>${t('Sign in with Steam')}</h3>
      <p>${t("Click the Steam button at the bottom of the app and sign in on Steam's page. We never see your password.")}</p>
      <span class="btn steam">${STEAM} ${t('Sign in with Steam')}</span>
    </div></li>
    <li><div>
      <h3>${t('Set the game to Borderless')}</h3>
      <p>${t("Graphics settings › <b>Display mode</b> › <b>Borderless</b>. The app's timer can't show over exclusive fullscreen.")}</p>
    </div></li>
    <li><div>
      <h3>${t('Click DRIVE')}</h3>
      <p>${t('The app sets up the stage, car and conditions in your game and starts it. Your old setup is backed up (<b>Restore save</b>).')}</p>
      <p>${t('Then in the game:')}</p>
      <p class="path">${t('any key')} <i>›</i> Racing <i>›</i> Rally <i>›</i> Rally Weekend <i>›</i> Start Rally <i>›</i> ${t('J (automatic tyres)')} <i>›</i> Confirm and start rally <i>›</i> Start Stage</p>
      <p>${t("The app shows {0} when you're on the right stage in the right car.", `<span class="badge ready">${t('READY')}</span>`)}</p>
    </div></li>
    <li><div>
      <h3>${t('Place the timer')}</h3>
      <p>${t("Click <b>Move overlays</b>, drag the timer over the game's own, then <b>Lock overlays</b>. You only do this once.")}</p>
    </div></li>
    <li><div>
      <h3>${t('Drive')}</h3>
      <p>${t('Timing starts with the stage clock ({0}). You see your gap at each split, and your time goes on the sheet when you finish.', `<span class="badge live">${t('LIVE')}</span>`)}</p>
    </div></li>
  </ol>

  <h2 id="dailies">${t('The dailies')}</h2>
  <table>
    <tr><td><b>${t('SS1 · free')}</b></td><td>${t('Finish your first run and get {0}.', cr(CREDITS.finish))}</td></tr>
    <tr><td><b>${t('SS2 · wager')}</b></td><td>${t('Costs {0} to enter. DRIVE asks for the stake first. The house puts in {0} too. After the day, the faster half get {1} back, the rest lose their stake, and anything left goes to the winner. If nobody finishes, everyone gets their stake back.', cr(WAGER.stake), cr(2 * WAGER.stake))}</td></tr>
  </table>

  <h2 id="rules">${t('Rules')}</h2>
  <table>
    <tr><td><b>${t('First run counts')}</b></td><td>${t('Later runs are practice.')}</td></tr>
    <tr><td><b>${t('Your time')}</b></td><td>${t("The game's official time plus its penalties (Light).")}</td></tr>
    <tr><td><b>${t('Damage')}</b></td><td>${t('Light damage and wear, no failures, manual respawn on.')}</td></tr>
    <tr><td><b>${t('DNF')}</b></td><td>${t('Restart, retire, quit or stop for 30 seconds. A run never finished is a DNF after an hour.')}</td></tr>
    <tr><td><b>${t('Shortcuts')}</b></td><td>${t('You must pass 90 % of the route checkpoints.')}</td></tr>
    <tr><td><b>${t('Car and stage')}</b></td><td>${t("Only the daily's count.")}</td></tr>
    <tr><td><b>${t('New stages')}</b></td><td>${t('Every day at 00:00 UTC.')}</td></tr>
  </table>

  <h2 id="credits">${t('Credits')} ${coin}</h2>
  <table>
    <tr><td><b>${t('Welcome')}</b></td><td>${t('{0} on your first day.', cr(CREDITS.welcome))}</td></tr>
    <tr><td><b>${t('Daily bonus')}</b></td><td>${t('{0} each day you open the app or the website.', cr(CREDITS.daily))}</td></tr>
    <tr><td><b>${t('Finish SS1')}</b></td><td>${cr(CREDITS.finish)}.</td></tr>
    <tr><td><b>${t('Spend them on')}</b></td><td>${t("The SS2 stake, the {0}'s TT2 entry, 1V1 stakes, cup entry fees and {1}.", `<a href="#tt">${t('time trial')}</a>`, `<a href="#shop">${t('the shop')}</a>`)}</td></tr>
  </table>
  <p class="note">${t("You can't buy credits, sell them or give them away.")}</p>

  <h2 id="tt"><span class="tag m-tt">${t('TIME TRIAL')}</span>${t('Hotlap all week')}</h2>
  <div class="part">
    <p>${t("Two stages a week, new every Monday at 00:00 UTC, each with its own car and conditions. Pick one in the app's <b>TIME TRIAL</b> tab and drive it as often as you like until the week ends: only your best time goes on the {0}. After a run, go on from the game's results screen (it saves its time), then Rally Weekend › Start Rally again for another go.", `<a href="/tt">${t('sheet')}</a>`)}</p>
    ${env.CREDITS_FROM ? `<p>${t("TT{0} is free: no entry fee, no prizes. The other stage's entry is {1}, before your first run on it. When the week is over the top half of its drivers with a time win: their fee back plus a share of everyone else's fees, more for each place higher up. No time set: your fee comes back.", TT.freeSlot, cr(TT.fee))}</p>` : ''}
  </div>

  <h2 id="1v1"><span class="tag m-1v1">1V1</span>${t('Challenge a driver')}</h2>
  <div class="part">
    <p>${t("Challenge any driver from their {0}, the {1} or the app's <b>1V1</b> tab. You choose the stages, car, conditions, how long it's open (up to {2} days) and a stake (0 to {3} each).", `<a href="#driver">${t('page')}</a>`, `<a href="/1v1">${t('1V1 page')}</a>`, H2H.windowDays, cr(H2H.maxStake))}</p>
    <p>${t('They have {0} hours to accept. Lower total wins both stakes; a tie or no finisher returns them. It\'s paid as soon as you have both driven. <b>Rematch</b> sends the same challenge again.', H2H.answerMs / 3600000)}</p>
  </div>

  <h2 id="cups"><span class="tag m-cups">${t('CUPS')}</span>${t('Knockout cups')}</h2>
  <div class="part">
    <p>${t("Knockouts of 1V1s for up to {0} drivers. Join on the {1} or in the app before it starts. Seeds go by {2}; if the cup isn't full, the top seeds get byes.", CUP.sizes[CUP.sizes.length - 1], `<a href="/cups">${t('cups page')}</a>`, `<a href="#rating">${t('rating')}</a>`)}</p>
    <p>${t('Drive your match before the round closes. Lower total goes through; if nobody finishes, the higher seed does. Your inbox reminds you a day before.')}</p>
    <p>${t('Anyone can run a cup and decide how the pot is shared: a % for each place, down the bracket. <b>Official</b> cups are ours: prize credits on top, sometimes new stages each round, and posts on {0}.', '<a href="/discord">Discord</a>')}</p>
  </div>

  <h2 id="leagues"><span class="tag m-leagues">${t('LEAGUES')}</span>${t('Leagues')}</h2>
  <div class="part">
    <p>${t('Clubs that run their own multi-stage rallies and championships. Anyone can start one, public or invite-only. Free, no credits.')}</p>
    <p>${t('An event can have several car classes, and a league can have divisions such as PRO and AM. Each class and division gets its own standings and championship.')}</p>
  </div>

  <h2 id="rating">${t('Rating')}</h2>
  <div class="part">
    <p>${t('Everyone starts at {0}. Dailies and cup matches count. Beating higher-rated drivers gains more; a DNF counts as last. It never resets. Dailies are rated after the day ends. See the {1}.', `<b>${RATING.start}</b>`, `<a href="/ranking">${t('world ranking')}</a>`)}</p>
  </div>

  <h2 id="driver">${t('Your page and teams')}</h2>
  <div class="part">
    <p>${t("Every driver has a page ({0}) with their rating, results, stats and achievements. On yours you can set a name (one change a week), a picture, your flag and a team. A team's coloured tag shows next to its drivers' names ({1}).", `<a href="/me">${t('yours')}</a>`, `<a href="/teams">${t('teams')}</a>`)}</p>
  </div>

  <h2 id="shop">${t('Shop')}</h2>
  <div class="part">
    <p>${t("Spend credits on a name colour, a badge or a frame for your picture. Looks only, they don't change your times ({0}).", `<a href="/credits#shop">${t('shop')}</a>`)}</p>
  </div>

  <h2 id="inbox"><span class="tag m-inbox">${t('INBOX')}</span>${t('Inbox')} ${envelopeSvg()}</h2>
  <div class="part">
    <p>${t('Challenges, cup matches, results and messages from other drivers. You can block or report anyone.')}</p>
  </div>

  <h2 id="app">${t('The app')}</h2>
  <table>
    <tr><td><span class="badge muted">${t('STANDBY')}</span></td><td>${t('Waiting for the game, stage or car.')}</td></tr>
    <tr><td><span class="badge ready">${t('READY')}</span></td><td>${t('Right stage and car. Timing starts with the stage clock.')}</td></tr>
    <tr><td><span class="badge live">${t('LIVE')}</span></td><td>${t('On the stage.')}</td></tr>
    <tr><td><span class="badge">${t('FINISHED')}</span></td><td>${t("Your time is sent once you leave the game's results screen.")}</td></tr>
    <tr><td><span class="badge live">${t('DNF')}</span> / <span class="badge live">${t('INVALID')}</span></td><td>${t('Restarted or quit / missed part of the route.')}</td></tr>
  </table>
  <p class="lead">${t('Optional overlays: a stage strip with you, the leaders and anyone else on the stage, and your gap to P1.')}</p>

  ${release ? `<h2 id="verify">${t('Is the download the open-source code?')}</h2>
  <p class="lead">${t('Yes. GitHub builds it from the public {0} and signs a {1}. You can check it:', `<a href="${env.SOURCE_URL}">${t('code')}</a>`, `<a href="https://docs.github.com/en/actions/security-for-github-actions/using-artifact-attestations">${t('build attestation')}</a>`)}</p>
  <table>
    <tr><td><b>${t('Version')}</b></td><td>v${latestVersion(env)} · <a href="${release}">${t('release and build log')}</a></td></tr>
    <tr><td><b>SHA-256</b></td><td><code id="sha">${t('loading…')}</code></td></tr>
    <tr><td><b>${t('Quick check')}</b></td><td>${t('{0} should print the same.', '<code>certutil -hashfile ACR-Daily.exe SHA256</code>')}</td></tr>
    <tr><td><b>${t('Full check')}</b></td><td><code>gh attestation verify ACR-Daily.exe --repo ${repo}</code> (<a href="https://cli.github.com">GitHub CLI</a>)</td></tr>
  </table>` : ''}

  <h2 id="faq">${t('FAQ')}</h2>
  <dl class="faq">
    <dt>${t('Can I buy credits?')}</dt>
    <dd>${t('No. You earn them by driving.')}</dd>
    <dt>${t('Why is DRIVE locked on SS2?')}</dt>
    <dd>${t('It needs a {0} credit stake. Short? Finish SS1 ({1}) and come back tomorrow ({2}).', WAGER.stake, CREDITS.finish, CREDITS.daily)}</dd>
    <dt>${t('Where are my 1V1 and cup matches?')}</dt>
    <dd>${t("In the app's <b>1V1</b> and <b>CUPS</b> tabs.")}</dd>
    <dt>${t('How do I update?')}</dt>
    <dd>${t('Click the red <b>UPDATE</b> bar in the app.')}</dd>
    <dt>${t("The timer doesn't show over the game.")}</dt>
    <dd>${t('Set the game to Borderless and tick “Show timer” in the app.')}</dd>
    <dt>${t('Can I drive without signing in?')}</dt>
    <dd>${t('Yes. Your run is sent when you sign in, if the stage is still open.')}</dd>
    <dt>${t('Does the app change my game?')}</dt>
    <dd>${t('Only the stage setup in your save, when you click DRIVE, with a backup. A rally you had in progress is set aside and <b>PUT BACK</b> returns it. <b>AUTO</b> (off by default) clicks through the menus for you and stops when you touch the keyboard or mouse.')}</dd>
    <dt>${t('Can I see how a run was driven?')}</dt>
    <dd>${t('Click a time on the timing sheet.')}</dd>
    <dt>${t('Something went wrong. Where do I tell you?')}</dt>
    <dd>${t("{0}: say what happened and attach a screenshot, the game's log and its save (the page says where they are). You see there, and in your inbox, how far your report has got.", `<a href="/report">${t('Report a problem')}</a>`)}</dd>
  </dl>
</main>
<script>
fetch('/api/version').then(function(r){return r.json()}).then(function(v){
  var el=document.getElementById('sha'); if(el) el.textContent=v.sha256||${tq('not published yet')};
}).catch(function(){var el=document.getElementById('sha'); if(el) el.textContent=${tq('could not load')};});
</script>
<footer><div class="wrap">${t('ACR Daily is a free, open-source fan project, not affiliated with the makers of Assetto Corsa Rally or with Valve. Steam and the Steam logo are trademarks of Valve Corporation.')}</div></footer>
</body>
</html>`;
}
