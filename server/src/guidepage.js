// /guide - how to take part: install, sign in, set up, drive; then the two dailies, the rules, credits, 1V1s, cups,
// leagues, the rating, the driver page, the shop and the inbox, the badges and a short FAQ. The numbers come from the
// code that applies them (credits.js, h2h.js, cups.js, rating.js, drivers.js), so the page can't drift from the rules.

// the Steam logo mark (Simple Icons); Steam is a trademark of Valve Corporation
const STEAM = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M11.979 0C5.678 0 .511 4.86.022 11.037l6.432 2.658c.545-.371 1.203-.59 1.912-.59.063 0 .125.004.188.006l2.861-4.142V8.91c0-2.495 2.028-4.524 4.524-4.524 2.494 0 4.524 2.031 4.524 4.527s-2.03 4.525-4.524 4.525h-.105l-4.076 2.911c0 .052.004.105.004.159 0 1.875-1.515 3.396-3.39 3.396-1.635 0-3.016-1.173-3.331-2.727L.436 15.27C1.862 20.307 6.486 24 11.979 24c6.627 0 11.999-5.373 11.999-12S18.605 0 11.979 0zM7.54 18.21l-1.473-.61c.262.543.714.999 1.314 1.25 1.297.539 2.793-.076 3.332-1.375.263-.63.264-1.319.005-1.949s-.75-1.121-1.377-1.383c-.624-.26-1.29-.249-1.878-.03l1.523.63c.956.4 1.409 1.5 1.009 2.455-.397.957-1.497 1.41-2.454 1.012H7.54zm11.415-9.303c0-1.662-1.353-3.015-3.015-3.015-1.665 0-3.015 1.353-3.015 3.015 0 1.665 1.35 3.015 3.015 3.015 1.663 0 3.015-1.35 3.015-3.015zm-5.273-.005c0-1.252 1.013-2.266 2.265-2.266 1.249 0 2.266 1.014 2.266 2.266 0 1.251-1.017 2.265-2.266 2.265-1.253 0-2.265-1.014-2.265-2.265z"/></svg>';

import { downloadUrl, latestVersion, releasePage } from './release.js';
import { coinSvg, envelopeSvg, FAVICON, logoSvg } from './logo.js';
import { CREDITS, WAGER } from './credits.js';
import { H2H } from './h2h.js';
import { CUP, OFFICIAL } from './cups.js';
import { RATING } from './rating.js';
import { NAME, TEAM } from './drivers.js';
import { MSG } from './social.js';
import { ITEMS } from './shop.js';

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
<meta name="description" content="How to take part in ACR Daily: install the app, sign in with Steam, set up the daily stage and drive.">
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
    <p class="lead">Two new special stages every day, the same car and conditions for everyone, one timing sheet.
    Around them: credits to stake, 1V1s against other drivers, knockout cups, leagues, a driver rating and a world ranking.
    You need Assetto Corsa Rally on Steam and a Windows PC. Setting up takes about five minutes.</p>
  </div>
  <nav class="toc" aria-label="Contents">
    <a href="#start">Set up</a><a href="#dailies">The two dailies</a><a href="#rules">Rules</a><a href="#credits">Credits</a>
    <a class="mode m-1v1" href="#1v1">1V1</a><a class="mode m-cups" href="#cups">Cups</a><a class="mode m-leagues" href="#leagues">Leagues</a>
    <a href="#rating">Rating</a><a href="#driver">Your page</a><a href="#shop">Shop</a><a class="mode m-inbox" href="#inbox">Inbox</a>
    <a href="#app">The app</a><a href="#faq">FAQ</a>
  </nav>

  <ol class="steps" id="start">
    <li><div>
      <h3>Get the app</h3>
      <p>Download <b>ACR-Daily.exe</b> and put it anywhere, for example on your desktop. It doesn't need installing.</p>
      <p>The first time you open it, Windows may show <b>“Windows protected your PC”</b> because the app isn't code-signed. Click <b>More info › Run anyway</b>.</p>
      ${download ? `<a class="btn dl" href="${download}">Download the app</a>` : ''}
      ${release ? `<p class="small">v${latestVersion(env)}, built by GitHub from the public code. <a href="#verify">How to check it</a>.</p>` : ''}
    </div></li>
    <li><div>
      <h3>Sign in with Steam</h3>
      <p>Click the Steam button at the bottom of the app. Your browser opens Steam's own sign-in page; ACR Daily never sees your password.
      Your Steam name goes on the timing sheet, and your country flag comes from your driver profile in the game.</p>
      <span class="btn steam">${STEAM} Sign in with Steam</span>
    </div></li>
    <li><div>
      <h3>Set the game to borderless</h3>
      <p>In the game's graphics settings, set <b>Display mode</b> to <b>Borderless</b> (or Windowed). The app's timer sits over the game, and exclusive fullscreen would hide it.</p>
    </div></li>
    <li><div>
      <h3>Click DRIVE</h3>
      <p>Click <b>DRIVE</b> next to a stage in the app. It sets the stage up in the game for you as a one-stage <b>Rally Weekend</b>: car, weather, time of day and the race settings, then starts the game.
      If the game is already open, the app closes it the normal way, sets the daily up and starts it again (the game only reads its set-up when it starts). A backup is kept: <b>Restore save</b> puts your old set-up back.</p>
      <p>In the game:</p>
      <p class="path">any key <i>›</i> Racing <i>›</i> Rally <i>›</i> Rally Weekend <i>›</i> Start Rally <i>›</i> J (automatic tyres) <i>›</i> Confirm and start rally <i>›</i> Start Stage</p>
      <p>Everything is already set. The app shows <span class="badge ready">READY</span> when it sees the right stage and car.</p>
    </div></li>
    <li><div>
      <h3>Place the timer once</h3>
      <p>The overlays start locked, so your clicks go through to the game. To place them, click <b>Move overlays</b>, drag the app's timer box over the game's own timer, then click <b>Lock overlays</b>. It remembers the spot.</p>
    </div></li>
    <li><div>
      <h3>Drive</h3>
      <p>The run starts when the stage clock starts. The badge turns <span class="badge live">LIVE</span>, and you appear as a moving dot on the website's map.
      At each split you see where you stand against everyone's best run of the day. Cross the line and your time goes onto the sheet.</p>
    </div></li>
  </ol>

  <h2 id="dailies">The two dailies</h2>
  <table>
    <tr><td><b>SS1 · free</b></td><td>Drive it as you like. Finishing your first run of the day earns ${cr(CREDITS.finish)} at once.</td></tr>
    <tr><td><b>SS2 · wager</b></td><td>Driven with a stake of ${cr(WAGER.stake)}: DRIVE asks for it before your first run of the day and stays locked until you stake.
      A run without a stake doesn't count. ACR Daily (the house) stakes ${cr(WAGER.stake)} too, so even a driver on their own can win.
      Once the day is over, the faster half of the drivers who staked (rounded up) get <b>double</b> their stake back, the rest lose theirs,
      and anything left over goes to the fastest. Nobody finishing, or a stake you never drove: it comes back.</td></tr>
  </table>

  <h2 id="rules">The rules</h2>
  <table>
    <tr><td><b>First run counts</b></td><td>Your first run of each stage is your result. Later runs are practice, so warm up on another stage.</td></tr>
    <tr><td><b>Your time</b></td><td>The game's own: its official stage time plus its penalties (respawns, cuts, jump starts; penalty level Light). The app reads it from the game once the stage is over.</td></tr>
    <tr><td><b>Damage</b></td><td>On (light damage, light wear), no mechanical failures. Manual respawn is on.</td></tr>
    <tr><td><b>DNF</b></td><td>Restarting, retiring, quitting, or stopping for more than 30 seconds, or no official result from the game. A run that's started and never finished becomes a DNF after an hour.</td></tr>
    <tr><td><b>Shortcuts</b></td><td>Don't count: you have to pass at least 90 % of the route's checkpoints.</td></tr>
    <tr><td><b>Car and stage</b></td><td>Must be the daily's. The app won't start timing otherwise.</td></tr>
    <tr><td><b>Conditions</b></td><td>Weather and time of day are set by DRIVE. Once others have finished, the app warns you on the start line if your game's conditions look different.</td></tr>
    <tr><td><b>New stages</b></td><td>Two at 00:00 UTC every day.</td></tr>
  </table>

  <h2 id="credits">Credits ${coin}</h2>
  <div class="part"><p>ACR Daily's own points: earned by driving, spent on stakes, entry fees and looks.</p></div>
  <table>
    <tr><td><b>Welcome</b></td><td>${cr(CREDITS.welcome)} once, with your first daily bonus. Credits start with your first finished run (any daily, a practice run too).</td></tr>
    <tr><td><b>Daily bonus</b></td><td>${cr(CREDITS.daily)} every day you come back: the app claims it when it starts (or the <a href="/credits">credits page</a>).</td></tr>
    <tr><td><b>Finish SS1</b></td><td>${cr(CREDITS.finish)} for finishing the free daily, paid as soon as the run is in.</td></tr>
    <tr><td><b>SS2 stake</b></td><td>${cr(WAGER.stake)} a day; the faster half get ${cr(2 * WAGER.stake)} back (above).</td></tr>
    <tr><td><b>Spend on</b></td><td>1V1 stakes, cup entry fees and <a href="#shop">the shop</a>.</td></tr>
  </table>
  <p class="note">Credits are only ever earned. They can't be bought, sold, cashed out or given to another driver.</p>

  <h2 id="1v1"><span class="tag m-1v1">1V1</span>Head to head</h2>
  <div class="part">
    <p>Challenge any driver: on their <a href="#driver">driver page</a> (<b>Challenge to a 1V1</b>), on the <a href="/1v1">1V1 page</a>, or in the app's <b>1V1</b> tab.
    You pick the rally, one stage or a few, the car (or a class), the conditions and the window to drive it in (up to ${H2H.windowDays} days), and a stake of 0 to ${cr(H2H.maxStake)} each (0: a friendly).</p>
    <p>They have ${H2H.answerMs / 3600000} hours to accept (their stake is taken then) or decline; unanswered, it expires and your stake comes back.
    Accepted, you both drive it in the app under <b>1V1</b>, whenever you like inside the window. Your first run of each stage counts.
    The lower total wins both stakes; nobody finishing, or a dead heat, and the stakes go back. After a 1V1, <b>Rematch</b> sends the same challenge again.</p>
  </div>

  <h2 id="cups"><span class="tag m-cups">CUPS</span>Knockout cups</h2>
  <div class="part">
    <p>A cup is a knockout of 1V1s for ${CUP.sizes[0]} to ${CUP.sizes[CUP.sizes.length - 1]} drivers. Join on the <a href="/cups">cups page</a> or in the app's <b>CUPS</b> tab before it starts; leaving before the start gives the entry fee back.
    At the start the drivers are seeded by their <a href="#rating">rating</a>, and the bracket is the smallest that holds them: in a cup that isn't full, the top seeds get byes.</p>
    <p>Every round, each match is open to its two drivers only, until the round closes. Drive it in the app under <b>CUPS</b>. The lower total goes through;
    the only finisher goes through; nobody finishing, or a dead heat, and the higher seed goes through. The rounds close at fixed times, a round's length apart from the start,
    so a weekly cup always closes on the same day and hour. Before a round closes, your inbox reminds you if you haven't driven your match yet.</p>
    <p>Anyone can run a cup (up to ${CUP.perOwner} at a time): the size, the entry fee (0 to ${cr(CUP.maxFee)}), how the pot is shared (${Object.values(CUP.splits).map((s) => s.label.toLowerCase()).join('; ')}), what every match races and how long a round is open (${CUP.roundHours.join(', ')} hours).</p>
    <p><b>Official cups</b> are ACR Daily's own: marked OFFICIAL, run by ACR Daily, with credits from ACR Daily added to the pot. Their rounds can be up to ${OFFICIAL.maxRoundHours / 24} days long,
    and some draw new stages for every round (never two on the same road). Their sign-ups, rounds and results are posted on <a href="/discord">Discord</a> too.</p>
  </div>

  <h2 id="leagues"><span class="tag m-leagues">LEAGUES</span>Leagues</h2>
  <div class="part">
    <p>Clubs that run their own events: rallies of several stages over one or more days, with service parks, a car or a class, and a window to drive them in.
    Anyone can start a league, public or private (joined with an invite code); its owner and admins make the events and seasons (points, a power stage, dropped rounds), and can steward results.
    Leagues are free: no credits. Drive their events in the app under <b>LEAGUES</b>; the first start of each stage counts.</p>
  </div>

  <h2 id="rating">Rating and the world ranking</h2>
  <div class="part">
    <p>Every driver starts at <b>${RATING.start}</b>. Both dailies and cup matches are rated (1V1s and league events aren't): each race compares you with everyone in it,
    so beating drivers rated above you gains more than beating those below, and finishing behind them costs less. A DNF counts as last.
    Your first ${RATING.newRaces} races move your rating faster.</p>
    <p>A day's dailies are rated once the day is settled (01:05 UTC the next day); a cup match as soon as it is decided. The <a href="/ranking">world ranking</a> lists everyone rated, by country too. Cups are seeded by rating.</p>
  </div>

  <h2 id="driver">Your driver page and teams</h2>
  <div class="part">
    <p>Every driver has a page (<a href="/me">yours</a>): rating and its history, world rank, career (dailies, wins, podiums, kilometres, favourite car and rally, 1V1 record), recent dailies, leagues and cups.
    Names on the timing sheets link there.</p>
    <p>On your own page: your <b>name</b> on ACR Daily (${NAME.min} to ${NAME.max} characters, no two drivers alike, one change a week), your <b>picture</b>, and your <b>team</b>.
    A team has a tag of 2 to 4 letters or digits in its own colour, shown by its drivers' names everywhere; up to ${TEAM.maxMembers} drivers, one team each, joined with its invite code (<a href="/teams">teams</a>).</p>
  </div>

  <h2 id="shop">The shop</h2>
  <div class="part">
    <p>Looks bought with credits (${cr(Math.min(...ITEMS.map((i) => i.price)))} to ${cr(Math.max(...ITEMS.map((i) => i.price)))}): a <b>colour</b> for your name and your dot on the map, a <b>badge</b> by your name, a <b>frame</b> round your picture on the map.
    Bought once and kept; wear one of each at a time. Nothing in the <a href="/shop">shop</a> changes a time.</p>
  </div>

  <h2 id="inbox"><span class="tag m-inbox">INBOX</span>The inbox ${envelopeSvg()}</h2>
  <div class="part">
    <p>The letter in the header (and in the app) fills, with a count by it, when something is unread: notices (a challenge, a cup match ready, results, a reminder) and messages.
    Message a driver from their page: short private messages (up to ${MSG.maxLen} characters), with <b>Block</b> and <b>Report</b>. A notice opens what it is about: in the app, the right tab.</p>
  </div>

  <h2 id="app">What the app shows</h2>
  <div class="part"><p>Tabs at the top: <b>DAILIES</b>, <b class="m-leagues" style="color:var(--m)">LEAGUES</b>, <b class="m-1v1" style="color:var(--m)">1V1</b> and <b class="m-cups" style="color:var(--m)">CUPS</b>, the inbox letter, and under them you: your rating, world rank and credits, and a link to your page. DRIVE works the same in every tab.</p></div>
  <table>
    <tr><td><span class="badge muted">STANDBY</span></td><td>Waiting for the game, or for the right stage and car.</td></tr>
    <tr><td><span class="badge ready">READY</span></td><td>Right stage, right car. Timing starts with the stage clock.</td></tr>
    <tr><td><span class="badge live">LIVE</span></td><td>On the stage. Splits are counted.</td></tr>
    <tr><td><span class="badge">FINISHED</span></td><td>Your stage time. The game saves its official time and penalties once you go on from its results screen; that is what goes onto the sheet. If ACR Daily closes before then, it picks the run up when you open it again.</td></tr>
    <tr><td><span class="badge live">DNF</span> / <span class="badge live">INVALID</span></td><td>Restarted, quit or stopped / missed part of the route.</td></tr>
    <tr><td><span class="badge ready">UNDER REVIEW</span></td><td>On the website: three people reported the run, so an admin will look at it.</td></tr>
  </table>
  <p class="lead">Optional <b>in-game displays</b> (switch them on in the app): a vertical stage strip with you, the leaders and whoever else is on the stage right now, and your gap trend to P1. Unlock the overlays to drag them, lock them again to drive.</p>

  ${release ? `<h2 id="verify">Is the download really the open-source code?</h2>
  <p class="lead">Yes, and you can check it yourself. The app isn't built on anyone's PC: GitHub builds it from the public
  <a href="${env.SOURCE_URL}">source code</a> every time a version is tagged, and signs a record of exactly which code it came from
  (a <a href="https://docs.github.com/en/actions/security-for-github-actions/using-artifact-attestations">build attestation</a>).
  The download button, and the app's UPDATE button, use that file.</p>
  <table>
    <tr><td><b>Version</b></td><td>v${latestVersion(env)} · <a href="${release}">release page and build log</a></td></tr>
    <tr><td><b>SHA-256</b></td><td><code id="sha">loading…</code></td></tr>
    <tr><td><b>Quick check</b></td><td>In a Command Prompt, in your Downloads folder:<br><code>certutil -hashfile ACR-Daily.exe SHA256</code><br>It must print the same SHA-256 as above.</td></tr>
    <tr><td><b>Full check</b></td><td>With the <a href="https://cli.github.com">GitHub CLI</a>:<br><code>gh attestation verify ACR-Daily.exe --repo ${repo}</code><br>It confirms this exact file was built by GitHub from that repository, and shows the commit, so you can read the code that went into it.</td></tr>
  </table>` : ''}

  <h2 id="faq">FAQ</h2>
  <dl class="faq">
    <dt>Can I buy credits?</dt>
    <dd>No, and you never will: credits are only earned by driving and coming back. They can't be bought, sold, cashed out or sent to another driver.</dd>
    <dt>Why is DRIVE locked on SS2?</dt>
    <dd>SS2 is the wager daily: click DRIVE and the app asks for the ${WAGER.stake} credit stake first. Not enough credits yet? Finish SS1 (${CREDITS.finish}) and come back tomorrow (${CREDITS.daily}). SS1 is always free.</dd>
    <dt>Where are my 1V1 and cup matches?</dt>
    <dd>In the app's <b>1V1</b> and <b>CUPS</b> tabs, with DRIVE next to each, and on the website under 1V1 and Cups. Your inbox tells you when a match is ready.</dd>
    <dt>How do I update the app?</dt>
    <dd>When there's a new version, a red <b>UPDATE</b> bar appears at the top of the app. One click and it updates itself and restarts.</dd>
    <dt>The timer doesn't show over the game.</dt>
    <dd>Set the game to Borderless (step 3), and check “Show timer” at the bottom of the app.</dd>
    <dt>DRIVE says there are no (online) single stage settings in the save.</dt>
    <dd>That was a bug in the app up to 0.0.5, for players who had never driven a <b>Single Rally Stage</b>. Click <b>UPDATE</b> in the app (0.0.6 and newer don't need it).
    On an older app: in the game, Racing › Rally › Single Rally Stage › START RACE once, with any stage and car, then click DRIVE again.</dd>
    <dt>Can I drive without signing in?</dt>
    <dd>Yes. DRIVE works without a Steam sign-in, so you can try it first. Your run is kept and sent as soon as you sign in, as long as the stage hasn't closed (00:00 UTC). Sign in with the same Steam account the game runs under.
    While signed out you don't show up live (the map, Discord), and the app can't compare your splits with the others during the run.</dd>
    <dt>Does the app change my game?</dt>
    <dd>Only the Single Stage and Rally Weekend set-ups in your own save, and only when you click DRIVE (with a backup). The game keeps one Rally Weekend at a time, so a rally of yours in progress is set aside first (the app asks), never thrown away: <b>PUT BACK</b> in the app returns it to the game. It reads the telemetry the game publishes, and the game's own result from its save, and changes nothing else.
    <b>AUTO</b> next to DRIVE (off unless you switch it on) presses the menu keys up to the Service Park, only while the game is in front, and stops as soon as you touch the keyboard or mouse.</dd>
    <dt>Can I see how a run was driven?</dt>
    <dd>Click any time on the timing sheet: you get the run's map, speed, gaps and section times. If something looks wrong, there's a Report button.</dd>
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
