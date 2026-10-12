// /guide - how to take part: install, sign in, set up, drive; then the two dailies, the rules, credits, 1V1s, cups,
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

export function guidePage(env) {
  const download = downloadUrl(env);
  const release = releasePage(env);
  const repo = (env.SOURCE_URL || '').replace(/^https:\/\/github\.com\//, '');
  const coin = coinSvg();
  // an amount of credits with the coin: "1,000" (by hand: a Worker's first Intl call costs ~14 ms of CPU)
  const cr = (n) => `<b>${String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}</b>${coin}`;
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ACR Daily Guide</title>
<meta name="description" content="How to take part in ACR Daily.">
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
.m-leagues{--m:#5BA8FF}.m-1v1{--m:#FF9F43}.m-cups{--m:#FFD60A}.m-inbox{--m:#4CD6C0}
.part{margin-top:14px;color:var(--fg2)}
.part p+p{margin-top:8px}
.coin{display:inline-block;width:1em;height:1em;vertical-align:-.15em;margin-left:.15em}
td .coin{width:.95em;height:.95em}
.env{display:inline-block;width:1.2em;height:1.2em;vertical-align:-.25em;color:#4CD6C0}
.note{margin-top:12px;padding:10px 14px;border-left:3px solid var(--acc);background:#111113;color:var(--fg2);font-size:15px}
@media (max-width:640px){.wrap{padding:0 16px}ol.steps>li{grid-template-columns:40px 1fr}td:first-child{width:110px;white-space:normal}}
.beta{display:inline-block;margin-left:8px;padding:2px 6px;border:1px solid #E30613;border-radius:3px;color:#E30613;font:700 12px/1 'Barlow Condensed',sans-serif;letter-spacing:.12em;vertical-align:middle;text-decoration:none}
</style>
</head>
<body>
<header><div class="wrap"><a class="brand" href="/">${logoSvg()}<b class="beta" title="ACR Daily is in beta: things may change and bugs are expected. Report them on Discord.">BETA</b></a><a class="back" href="/">‹ Today's stages</a></div></header>
<main class="wrap">
  <div class="top">
    <div class="kick">GUIDE</div>
    <h1>How to take part</h1>
    <p class="lead">Two new stages every day. Same car and conditions for everyone, one timing sheet.
    You need Assetto Corsa Rally on Steam and a Windows PC. Setup takes about five minutes.</p>
  </div>
  <nav class="toc" aria-label="Contents">
    <a href="#start">Set up</a><a href="#dailies">The dailies</a><a href="#rules">Rules</a><a href="#credits">Credits</a>
    <a class="mode m-1v1" href="#1v1">1V1</a><a class="mode m-cups" href="#cups">Cups</a><a class="mode m-leagues" href="#leagues">Leagues</a>
    <a href="#rating">Rating</a><a href="#driver">Your page</a><a href="#shop">Shop</a><a class="mode m-inbox" href="#inbox">Inbox</a>
    <a href="#app">The app</a><a href="#faq">FAQ</a>
  </nav>

  <ol class="steps" id="start">
    <li><div>
      <h3>Get the app</h3>
      <p>Download <b>ACR-Daily.exe</b> and run it. No install needed.</p>
      <p>Windows may say <b>“Windows protected your PC”</b> the first time. Click <b>More info › Run anyway</b>.</p>
      ${download ? `<a class="btn dl" href="${download}">Download the app</a>` : ''}
      ${release ? `<p class="small">v${latestVersion(env)}, built by GitHub from the public code. <a href="#verify">Check it</a>.</p>` : ''}
    </div></li>
    <li><div>
      <h3>Sign in with Steam</h3>
      <p>Click the Steam button at the bottom of the app and sign in on Steam's page. We never see your password.</p>
      <span class="btn steam">${STEAM} Sign in with Steam</span>
    </div></li>
    <li><div>
      <h3>Set the game to Borderless</h3>
      <p>Graphics settings › <b>Display mode</b> › <b>Borderless</b>. The app's timer can't show over exclusive fullscreen.</p>
    </div></li>
    <li><div>
      <h3>Click DRIVE</h3>
      <p>The app sets up the stage, car and conditions in your game and starts it. Your old setup is backed up (<b>Restore save</b>).</p>
      <p>Then in the game:</p>
      <p class="path">any key <i>›</i> Racing <i>›</i> Rally <i>›</i> Rally Weekend <i>›</i> Start Rally <i>›</i> J (automatic tyres) <i>›</i> Confirm and start rally <i>›</i> Start Stage</p>
      <p>The app shows <span class="badge ready">READY</span> when you're on the right stage in the right car.</p>
    </div></li>
    <li><div>
      <h3>Place the timer</h3>
      <p>Click <b>Move overlays</b>, drag the timer over the game's own, then <b>Lock overlays</b>. You only do this once.</p>
    </div></li>
    <li><div>
      <h3>Drive</h3>
      <p>Timing starts with the stage clock (<span class="badge live">LIVE</span>). You see your gap at each split, and your time goes on the sheet when you finish.</p>
    </div></li>
  </ol>

  <h2 id="dailies">The dailies</h2>
  <table>
    <tr><td><b>SS1 · free</b></td><td>Finish your first run and get ${cr(CREDITS.finish)}.</td></tr>
    <tr><td><b>SS2 · wager</b></td><td>Costs ${cr(WAGER.stake)} to enter. DRIVE asks for the stake first. The house puts in ${cr(WAGER.stake)} too.
      After the day, the faster half get ${cr(2 * WAGER.stake)} back, the rest lose their stake, and anything left goes to the winner.
      If nobody finishes, everyone gets their stake back.</td></tr>
  </table>

  <h2 id="rules">Rules</h2>
  <table>
    <tr><td><b>First run counts</b></td><td>Later runs are practice.</td></tr>
    <tr><td><b>Your time</b></td><td>The game's official time plus its penalties (Light).</td></tr>
    <tr><td><b>Damage</b></td><td>Light damage and wear, no failures, manual respawn on.</td></tr>
    <tr><td><b>DNF</b></td><td>Restart, retire, quit or stop for 30 seconds. A run never finished is a DNF after an hour.</td></tr>
    <tr><td><b>Shortcuts</b></td><td>You must pass 90 % of the route checkpoints.</td></tr>
    <tr><td><b>Car and stage</b></td><td>Only the daily's count.</td></tr>
    <tr><td><b>New stages</b></td><td>Every day at 00:00 UTC.</td></tr>
  </table>

  <h2 id="credits">Credits ${coin}</h2>
  <table>
    <tr><td><b>Welcome</b></td><td>${cr(CREDITS.welcome)} on your first day.</td></tr>
    <tr><td><b>Daily bonus</b></td><td>${cr(CREDITS.daily)} each day you open the app or the website.</td></tr>
    <tr><td><b>Finish SS1</b></td><td>${cr(CREDITS.finish)}.</td></tr>
    <tr><td><b>Spend them on</b></td><td>The SS2 stake, 1V1 stakes, cup entry fees and <a href="#shop">the shop</a>.</td></tr>
  </table>
  <p class="note">You can't buy credits, sell them or give them away.</p>

  <h2 id="1v1"><span class="tag m-1v1">1V1</span>Head to head</h2>
  <div class="part">
    <p>Challenge any driver from their <a href="#driver">page</a>, the <a href="/1v1">1V1 page</a> or the app's <b>1V1</b> tab.
    You choose the stages, car, conditions, how long it's open (up to ${H2H.windowDays} days) and a stake (0 to ${cr(H2H.maxStake)} each).</p>
    <p>They have ${H2H.answerMs / 3600000} hours to accept. Lower total wins both stakes; a tie or no finisher returns them. It's paid as soon as you have both driven. <b>Rematch</b> sends the same challenge again.</p>
  </div>

  <h2 id="cups"><span class="tag m-cups">CUPS</span>Knockout cups</h2>
  <div class="part">
    <p>Knockouts of 1V1s for up to ${CUP.sizes[CUP.sizes.length - 1]} drivers. Join on the <a href="/cups">cups page</a> or in the app before it starts.
    Seeds go by <a href="#rating">rating</a>; if the cup isn't full, the top seeds get byes.</p>
    <p>Drive your match before the round closes. Lower total goes through; if nobody finishes, the higher seed does. Your inbox reminds you a day before.</p>
    <p>Anyone can run a cup and decide how the pot is shared: a % for each place, down the bracket.
    <b>Official</b> cups are ours: prize credits on top, sometimes new stages each round, and posts on <a href="/discord">Discord</a>.</p>
  </div>

  <h2 id="leagues"><span class="tag m-leagues">LEAGUES</span>Leagues</h2>
  <div class="part">
    <p>Clubs that run their own multi-stage rallies and championships. Anyone can start one, public or invite-only. Free, no credits.</p>
    <p>An event can have several car classes, and a league can have divisions such as PRO and AM. Each class and division gets its own standings and championship.</p>
  </div>

  <h2 id="rating">Rating</h2>
  <div class="part">
    <p>Everyone starts at <b>${RATING.start}</b>. Dailies and cup matches count. Beating higher-rated drivers gains more; a DNF counts as last.
    It never resets. Dailies are rated after the day ends. See the <a href="/ranking">world ranking</a>.</p>
  </div>

  <h2 id="driver">Your page and teams</h2>
  <div class="part">
    <p>Every driver has a page (<a href="/me">yours</a>) with their rating, results, stats and achievements.
    On yours you can set a name (one change a week), a picture and a team. A team's coloured tag shows next to its drivers' names (<a href="/teams">teams</a>).</p>
  </div>

  <h2 id="shop">Shop</h2>
  <div class="part">
    <p>Spend credits on a name colour, a badge or a frame for your picture. Looks only, they don't change your times (<a href="/shop">shop</a>).</p>
  </div>

  <h2 id="inbox"><span class="tag m-inbox">INBOX</span>Inbox ${envelopeSvg()}</h2>
  <div class="part">
    <p>Challenges, cup matches, results and messages from other drivers. You can block or report anyone.</p>
  </div>

  <h2 id="app">The app</h2>
  <table>
    <tr><td><span class="badge muted">STANDBY</span></td><td>Waiting for the game, stage or car.</td></tr>
    <tr><td><span class="badge ready">READY</span></td><td>Right stage and car. Timing starts with the stage clock.</td></tr>
    <tr><td><span class="badge live">LIVE</span></td><td>On the stage.</td></tr>
    <tr><td><span class="badge">FINISHED</span></td><td>Your time is sent once you leave the game's results screen.</td></tr>
    <tr><td><span class="badge live">DNF</span> / <span class="badge live">INVALID</span></td><td>Restarted or quit / missed part of the route.</td></tr>
    <tr><td><span class="badge ready">UNDER REVIEW</span></td><td>Reported by three people. An admin will check it.</td></tr>
  </table>
  <p class="lead">Optional overlays: a stage strip with you, the leaders and anyone else on the stage, and your gap to P1.</p>

  ${release ? `<h2 id="verify">Is the download the open-source code?</h2>
  <p class="lead">Yes. GitHub builds it from the public <a href="${env.SOURCE_URL}">code</a> and signs a
  <a href="https://docs.github.com/en/actions/security-for-github-actions/using-artifact-attestations">build attestation</a>. You can check it:</p>
  <table>
    <tr><td><b>Version</b></td><td>v${latestVersion(env)} · <a href="${release}">release and build log</a></td></tr>
    <tr><td><b>SHA-256</b></td><td><code id="sha">loading…</code></td></tr>
    <tr><td><b>Quick check</b></td><td><code>certutil -hashfile ACR-Daily.exe SHA256</code> should print the same.</td></tr>
    <tr><td><b>Full check</b></td><td><code>gh attestation verify ACR-Daily.exe --repo ${repo}</code> (<a href="https://cli.github.com">GitHub CLI</a>)</td></tr>
  </table>` : ''}

  <h2 id="faq">FAQ</h2>
  <dl class="faq">
    <dt>Can I buy credits?</dt>
    <dd>No. You earn them by driving.</dd>
    <dt>Why is DRIVE locked on SS2?</dt>
    <dd>It needs a ${WAGER.stake} credit stake. Short? Finish SS1 (${CREDITS.finish}) and come back tomorrow (${CREDITS.daily}).</dd>
    <dt>Where are my 1V1 and cup matches?</dt>
    <dd>In the app's <b>1V1</b> and <b>CUPS</b> tabs.</dd>
    <dt>How do I update?</dt>
    <dd>Click the red <b>UPDATE</b> bar in the app.</dd>
    <dt>The timer doesn't show over the game.</dt>
    <dd>Set the game to Borderless and tick “Show timer” in the app.</dd>
    <dt>Can I drive without signing in?</dt>
    <dd>Yes. Your run is sent when you sign in, if the stage is still open.</dd>
    <dt>Does the app change my game?</dt>
    <dd>Only the stage setup in your save, when you click DRIVE, with a backup. A rally you had in progress is set aside and <b>PUT BACK</b> returns it.
    <b>AUTO</b> (off by default) clicks through the menus for you and stops when you touch the keyboard or mouse.</dd>
    <dt>Can I see how a run was driven?</dt>
    <dd>Click a time on the timing sheet.</dd>
  </dl>
</main>
<script>
fetch('/api/version').then(function(r){return r.json()}).then(function(v){
  var el=document.getElementById('sha'); if(el) el.textContent=v.sha256||'not published yet';
}).catch(function(){var el=document.getElementById('sha'); if(el) el.textContent='could not load';});
</script>
<footer><div class="wrap">ACR Daily is a free, open-source fan project, not affiliated with the makers of Assetto Corsa Rally or with Valve. Steam and the Steam logo are trademarks of Valve Corporation.</div></footer>
</body>
</html>`;
}
