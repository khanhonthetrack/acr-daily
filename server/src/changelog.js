// What's new in each app version, in plain words for drivers. One list, published four ways:
// - the app: after each update, its WHAT'S NEW screen over the app (client/acr_daily/whatsnew.py): the version's photo,
//   headline and changes, each tagged NEW / IMPROVED / FIXED / NOTE, and under them every version the driver skipped
//   since the one they last saw (GET /api/changelog/<version>?since=<last seen>). Opened again any time from
//   SETTINGS › About › WHAT'S NEW, or the "UPDATED TO ... · WHAT'S NEW" bar;
// - the website's /changelog (src/changelogpage.js), with the same tags;
// - the Discord bot's #changelog channel: one post per version, once LATEST_VERSION goes live (syncChangelog, from
//   the cron in src/index.js; the channel is made by the bot like #faq, src/discordfaq.js);
// - the GitHub Release's notes (.github/workflows/release.yml, through scripts/whatsnew.mjs).
//
// EVERY RELEASE ADDS ITS ENTRY HERE, at the top, in the commit that bumps the app's __version__: the server's tests
// (test/changelog.test.mjs) and the release workflow fail without one. Write for drivers, not for developers: what
// they will notice, one short line each, plain text (no markdown, no HTML). From 0.0.31 on each entry has, for the
// app's screen (POPUP_FROM, checked by the tests):
//   title  its headline, the big words over the photo (70 characters at most);
//   photo  the photo behind it: a key of client/acr_daily/photos/photos.json (a new photo goes there, with its
//          author and licence; it ships inside that version's app);
//   changes  2 to 12 short lines (160 characters at most each): the screen is read in passing (it scrolls when
//          they don't fit). From 0.1.6 on
//          (KINDS_FROM) each line says what kind of change it is, its tag on the screen and the website:
//            NEW(N_(line))      something to try          BETTER(N_(line))   works better than it did
//            FIX(N_(line))      a bug gone                NOTE(N_(line))     worth knowing (a version needed...)
// The list starts at 0.0.30. A version without an entry (none put out) has its changes under the next one. An entry
// newer than LATEST_VERSION stays off the website, Discord and the app until the server says that version is out.
// Its words in N_(): the website and the app's screen say them in the reader's language once the catalogs have them
// (server/src/locales, tools/i18n/extract.py check; English until then); Discord and the GitHub Release say English.

import { N_, t } from './i18n.js';

export const POPUP_FROM = '0.0.31';
export const POPUP = { title: 70, lines: [2, 12], line: 160 };
export const KINDS_FROM = '0.1.5.1';          // (0.1.6's entry, written under its test build's number)
/** A change's kind: its tag in the app's WHAT'S NEW screen and on /changelog (Discord and GitHub say the words only). */
export const KINDS = ['new', 'better', 'fix', 'note'];
const kind = (k) => (text) => ({ kind: k, text });
const NEW = kind('new'), BETTER = kind('better'), FIX = kind('fix'), NOTE = kind('note');
/** A change's words, and its kind (null: an entry from before the kinds, a plain string). */
export const lineText = (c) => (typeof c === 'string' ? c : c.text);
export const lineKind = (c) => (typeof c === 'string' ? null : c.kind);
/** The versions older than the asked one that its screen lists under it, at most (the rest: on the website). */
export const EARLIER_MAX = 8;

// The first test builds' lines (0.1.5.2, 0.1.5.3), the last six of 0.1.6's
const RALLIES_LINE = NEW(N_("LEAGUES is now RALLIES: one list that scrolls, and anyone can create a rally on the website. Championships are run by Community organizers."));
const OFFICIAL_LINE = NOTE(N_("A daily now counts only if you press START OFFICIAL RALLY (after DRIVE) and drive it in Rally Weekend mode. Runs in other modes don't count."));
const COMMENT_LINE = NEW(N_("After a run you can add a comment: shown with your time on the timing sheet once the day or the week is over, or sent to whoever runs the event."));
const LIVERIES_LINE = NEW(N_("New in COMMUNITY: LIVERIES, the drivers' liveries from the website, put into the game in one click. CUPS lists every cup, like RALLIES."));
const HEADER_LINE = BETTER(N_("A calmer header: the shop is in PROFILE, the language in SETTINGS. No timing sheet under the cards. FPS drops? Settings › Timer › Hide while driving."));
const WHATSNEW_LINE = NEW(N_("A new WHAT'S NEW screen after each update, with every version you skipped. Open it again any time: SETTINGS › About › WHAT'S NEW."));
const FIRST_TESTS = [RALLIES_LINE, OFFICIAL_LINE, COMMENT_LINE, LIVERIES_LINE, HEADER_LINE, WHATSNEW_LINE];
// (0.1.5.48 on: no START OFFICIAL RALLY to press, the start line says what makes a run count: the app's COMMIT_REQUIRED)
const WEEKEND_LINE = NOTE(N_("A daily counts only in Rally Weekend mode: runs in other modes don't count. Once the clock starts, a restart or quitting is a DNF."));
// (0.1.5.52 on: the game mod checks the game against the event before the start, and watches it during the stage)
const RULES_LINE = NOTE(N_("Before the start the app checks the game against the event: mode, settings, driving aids. Switching to what it forbids on a stage is a DNF."));

// 0.1.6, the public release after 0.1.5 (20 Nov 2026): everything since 0.1.5, as public players get it (London the
// only community track; Lousã, Chile and WRC Generations stay the testers'). The 0.1.5.X test builds show it too, under
// their own number (entryForBuild, changelogFor).
const RANKED_LINE = NEW(N_("RANKED: a ranked rally every hour, four series in turn. Register in the 30 minutes before; at the hour its 3 stages are drawn and the start list is out."));
const TEAMS_LINE = NEW(N_("Team competitions: a championship can score its teams too, and teams take each other on in team 1V1s and team cups. Captains name up to 3 managers to help."));
const NEXT = [
  RANKED_LINE,
  NEW(N_("Ranked rallies start one car at a time. The game shows your place: red while you wait, green when it's your turn. Your rating and world rank are by your name.")),
  NEW(N_("Championships: join a public one, or ask to join a private one and its organizer lets you in. Private rallies are joined with their code.")),
  RALLIES_LINE,
  NEW(N_("ACR Daily's timer, stage strip and standings are now drawn by the game itself, next to its own HUD, and show in VR. The app adds the game mod it needs.")),
  BETTER(N_("No more windows over the game: Move the overlays, Hide while driving and the delta trend are gone. Set the displays' size and place in SETTINGS › Timer.")),
  WEEKEND_LINE,
  RULES_LINE,
  NEW(N_("New in COMMUNITY: ACR DAILY London, two stages through Westminster, installed in one click. Ready for the game's 0.7 update.")),
  TEAMS_LINE,
  COMMENT_LINE,
  LIVERIES_LINE,
];

export const CHANGELOG = [
  {
    // 0.2: the app inside the game (a private build first: client/acr_daily/ingameapp.py, docs/ingame-app.md)
    version: '0.2.0', date: '2026-11-22', title: N_("ACR Daily inside the game"), photo: 'dailies',
    changes: [
      NEW(N_("Everything is in the game now: MULTIPLAYER › ACR DAILY. Events, Ranked, Online Rallies, Watch, Profile and Community, with your wheel or pad.")),
      NEW(N_("DRIVE goes straight to the Service Park, no restart. Pick your car, tyres and livery first.")),
      NEW(N_("WATCH: everyone on a stage right now, dailies, time trials and championships. Follow them live as a TV broadcast, their livery on, their engine heard.")),
      NEW(N_("TV, in-car, cockpit, onboard and helicopter cameras; AUTO cuts between them.")),
      NEW(N_("A live tower, splits against the fastest, and a WRC-style gauge with speed, gear, revs and pedals.")),
      NEW(N_("Ranked chat on the stage: press T to write to the drivers of your session.")),
      NEW(N_("Liveries: pick from tiles, and a new one works without restarting the game.")),
      BETTER(N_("Your time goes as soon as you leave the stage's results, penalties included: a game stuck loading no longer loses it.")),
      BETTER(N_("The app itself is a small launcher: sign in, WHAT'S NEW and PLAY.")),
      BETTER(N_("Ghost cars sit on the road and their wheels turn.")),
      FIX(N_("A run only counts when ACR Daily took you to the stage, not a Rally Weekend set up by hand.")),
    ],
  },  {
    // rallies over 9 stages were split by day in the game (0.1.5.39-0.1.7): event 71's day 2 looked like a new rally
    version: '0.1.8', date: '2026-11-20', title: N_("Long rallies in one go again"), photo: 'alsace',
    changes: [
      BETTER(N_("Rallies of up to 3 days are set up whole in the game again, however many stages: no more second part that looks like a new rally.")),
      NOTE(N_("A rally you are already driving in parts goes on in parts until you finish it.")),
    ],
  },
  {
    // the game's 0.7 can keep more than one Rally Weekend set-up in its save (its Challenges...): 0.1.6 stopped there
    version: '0.1.7', date: '2026-11-20', title: N_("DRIVE works again after the game's 0.7 update"), photo: 'greece',
    changes: [
      FIX(N_("DRIVE stopped for some drivers after the game's 0.7 update, saying there was no Rally Weekend set-up in the save. Fixed.")),
      BETTER(N_("The app now finds your own Rally Weekend in the game's save, whatever else the game keeps in it.")),
    ],
  },
  {
    // the 0.1.5.X test builds from 0.1.5.4 on show it as their own (changelogFor, releaseNotes)
    version: '0.1.6', date: '2026-11-20', title: N_("Ranked rallies, championships and London"), photo: 'london',
    changes: NEXT,
  },
  {
    // a test build: 0.1.5.2 and the timer showing the official time's wait (saving, then saved)
    version: '0.1.5.3', date: '2026-11-15', title: N_("Rallies for everyone, and comments on your runs"), photo: 'leagues',
    changes: FIRST_TESTS,
  },
  {
    // a test build (four parts: GitHub's prerelease, nobody offered it): 0.1.6's work with every daily run counting from
    // its start again (app.PRACTICE_CHECK off: the save can't tell START RALLY from Practice then)
    version: '0.1.5.2', date: '2026-11-15', title: N_("Rallies for everyone, and comments on your runs"), photo: 'leagues',
    changes: FIRST_TESTS,
  },
  {
    version: '0.1.5', date: '2026-11-14', title: N_("Only a Rally Weekend keeps your time"), photo: 'monte-carlo',
    changes: [
      BETTER(N_("Drove a daily as a Single Rally Stage? The app now tells you: only a Rally Weekend (DRIVE sets it up) keeps the game's time.")),
      NEW(N_("The app now plays a sound and shows a Windows notification when your official time is saved, or lost.")),
      NEW(N_("New in Settings: Send diagnostics. It sends the app's notes and the game's save with a line from you, and gives you a report number.")),
      FIX(N_("Leagues: a rally the game took back no longer ends your entry, and an event can now keep a DNF in the results at the slowest time + a few minutes.")),
    ],
  },
  {
    version: '0.1.4', date: '2026-11-13', title: N_("When the game loses your time, the app's counts"), photo: 'alsace',
    changes: [
      NEW(N_("If the game loses a finished run's time, the app's own time now counts instead, for a run without respawns.")),
      BETTER(N_("When the game loses a finished run's time, the report the app sends now says what the game did: whether it froze, and how it ended.")),
      BETTER(N_("After a finish, the app now reads the game's save only once the game has left it alone for 10 seconds, so it never gets in the way of the game saving your time.")),
      FIX(N_("After a practice run the timer now says it's practice, instead of showing \"Sending...\" for good.")),
    ],
  },
  {
    version: '0.1.2', date: '2026-11-13', title: N_('On the trail of the stuck loading screen'), photo: 'greece',
    changes: [
      NEW(N_("If the game sticks on its loading screen after a stage and your time is lost, the app now sends the game's own log of that session to ACR Daily.")),
      NOTE(N_('The log shows where the game stopped, so the cause can be found. Your Windows user and PC names are taken out.')),
      NOTE(N_('It goes as your own report: follow it under “Report a problem” on the website. The app tells you when it has gone.')),
      NOTE(N_('From the 14 November dailies on, runs need 0.1.2 (the time trial: from today). Older apps show the red UPDATE bar.')),
    ],
  },
  {
    version: '0.1.1', date: '2026-11-12', title: N_('Your official time, saved'), photo: 'wales',
    changes: [
      NEW(N_("While a finished run waits for the game's official time, the timer window says in orange what saves it: go on from the game's results screen.")),
      BETTER(N_('Restarting the stage or quitting the game from the results screen loses that time, and the app now tells you so straight away.')),
      FIX(N_('A finished first run now counts even when practice runs reach the server first (a server fix: no update needed for it).')),
    ],
  },
  {
    version: '0.1.0', date: '2026-11-11', title: N_('ACR Daily speaks your language'), photo: 'monte-carlo',
    changes: [
      NEW(N_('The app and the website now come in 10 languages: English, Polish, Hungarian, Japanese, German, French, Spanish, Italian, Portuguese (Brazil) and Chinese.')),
      NOTE(N_('Pick yours with the globe at the top of the app or in SETTINGS. The website follows your browser, or the globe in its header.')),
      FIX(N_('Fixed: a run the game had saved could still go in as a DNF ("the game closed before saving its official result"). Those runs now count.')),
      NOTE(N_('From the 12 November dailies on, runs need 0.1.0: older apps show the red UPDATE bar.')),
    ],
  },
  {
    version: '0.0.30', date: '2026-11-11', title: N_('Ghost cars: race the other drivers live, in your game'),
    changes: [
      NEW(N_('New: everyone driving your stage right now shows up as a real car in your game, so you can see who is ahead and race them live.')),
      NOTE(N_('Try it: SETTINGS, Ghost cars, switch it on. The app adds the small game mod it needs for you, and takes it out again when you switch it off. It is still a test: tell us how it goes.')),
      BETTER(N_('Smooth netcode: positions come 20 times a second and each car follows a smooth line, with no jumping ahead and snapping back.')),
      BETTER(N_('Light on your PC: ten ghost cars cost the game about a third of what they did in testing (8 ms a frame, down from 23).')),
      BETTER(N_('Ready for 30 drivers on one stage, and ghost cars appear without a hitch.')),
      NEW(N_('Also new: the window can go as narrow as 560 px, for a screen stood on its end, and AUTO gets through the Service Park with the Peugeot 206 WRC.')),
    ],
  },
];

const parts = (v) => String(v).split('.').map((x) => parseInt(x, 10) || 0);
/** a < b: -1, equal: 0, a > b: 1 (versions as 0.0.30) */
export function compareVersions(a, b) {
  const x = parts(a), y = parts(b);
  for (let i = 0; i < Math.max(x.length, y.length); i++) if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) < (y[i] || 0) ? -1 : 1;
  return 0;
}

export const entryFor = (version) => CHANGELOG.find((e) => e.version === String(version)) || null;

/** A build's entry: its own; for a test build (four parts: 0.1.5.4, made by .github/workflows/dev.yml from main, which
 *  writes none for each) without one, the release it leads to: the lowest entry above it (0.1.6). -> entry or null */
export function entryForBuild(version) {
  const own = entryFor(version);
  if (own || parts(version).length < 4) return own;
  const above = CHANGELOG.filter((e) => compareVersions(e.version, version) > 0);
  return above.length ? above[above.length - 1] : null;
}

/** The entries people can see: the version they get (LATEST_VERSION) and older, newest first; never a test build's
 *  own (four parts: 0.1.5.2, its testers' only: the release after it says it all). */
export const published = (latest) => CHANGELOG.filter((e) => compareVersions(e.version, latest) <= 0 && parts(e.version).length < 4);

/** Is a version's entry out for the app? Once the server hands that version out (LATEST_VERSION or older); a test
 *  build's (four parts, 0.1.5.1: a prerelease only its testers have, never LATEST_VERSION) for whoever runs it. */
const isOut = (e, latest) => compareVersions(e.version, latest) <= 0 || parts(e.version).length >= 4;

/** An entry as the app's screen gets it, its words in the language it is made in: changes as before (plain lines, as
 *  apps before 0.1.6 read them) and, beside them, each one's kind (null: none). */
const forApp = (e) => ({ version: e.version, date: e.date, title: e.title ? t(e.title) : null, photo: e.photo || null,
  changes: e.changes.map((c) => t(lineText(c))), kinds: e.changes.map(lineKind) });

/** What the app's WHAT'S NEW screen gets for its version (GET /api/changelog/<version>): the entry once that version
 *  is out, else null; its words in the language it is made in (index.js: the request's, inLang). A test build's (four
 *  parts: a prerelease only its testers have, never LATEST_VERSION), own or its release's (entryForBuild), is out for
 *  whoever runs it, under the build's own number (0.1.5.42: its testers never read of a release that isn't out, and
 *  the app keeps that number as the screen it saw); null for a test build after one whose screen was the same entry
 *  (since: nothing new to show; the app counts it seen). since (?since=, the version whose screen the driver saw
 *  last; '0' for all): earlier, the released versions out between that one and this one, newest first (EARLIER_MAX
 *  at most), for the updates they skipped (never a test build's own entry: the entry they lead to says it all). */
export function changelogFor(version, latest, since = null) {
  const e = entryForBuild(version);
  const test = parts(String(version)).length >= 4;
  if (!e || (compareVersions(e.version, latest) > 0 && !test)) return null;
  if (test && since && parts(since).length >= 4 && entryForBuild(since) === e) return null;
  const out = forApp(e);
  if (test) out.version = String(version);
  if (since != null) {
    out.earlier = CHANGELOG.filter((x) => compareVersions(x.version, e.version) < 0 && compareVersions(x.version, since) > 0
      && parts(x.version).length < 4 && isOut(x, latest)).slice(0, EARLIER_MAX).map(forApp);
  }
  return out;
}

/** The GitHub Release's "What's new" (Markdown), or null when the version has no entry. A test build's, under its own
 *  number: "What's new in 0.1.5.42 (test build)". */
export function releaseNotes(version) {
  const e = entryForBuild(version);
  const test = parts(String(version)).length >= 4;
  return e ? `## What's new in ${test ? `${version} (test build)` : e.version}\n\n${e.title ? `**${e.title}**\n\n` : ''}${e.changes.map((c) => `- ${lineText(c)}`).join('\n')}\n` : null;
}

// ------------------------------------------------------------------ Discord: #changelog

export const CHANNEL = 'changelog';
const ACR_RED = 0xE30613;
const RETRY_MS = 15 * 60000;   // after Discord said no, try again this much later
const md = (s) => String(s).replace(/[\\*_~`|>#@[\]]/g, '');   // the lines are plain text: nothing Discord would read

/** One version's post. */
export function changelogMessage(e, site) {
  const icon = site ? { icon_url: `${site}/brand/acr-daily-icon-512.png` } : {};
  const link = site ? `${site}/changelog#v${e.version}` : undefined;
  return {
    embeds: [{
      // a headline: under "ACR Daily x is out", as the post's title
      ...(e.title ? { author: { name: `ACR Daily ${e.version} is out`, url: link, ...icon }, title: md(e.title) }
        : { title: `ACR Daily ${e.version} is out` }),
      url: link, color: ACR_RED,
      description: `${e.changes.map((c) => `• ${md(lineText(c))}`).join('\n')}\n\n` +
        `Update with the red **UPDATE** bar in the app${site ? `, or download it from ${site}` : ''}.`,
      footer: { text: `ACR Daily · ${e.date}`, ...icon },
    }],
    allowed_mentions: { parse: [] },
  };
}

/**
 * The cron's look at #changelog for every version out (LATEST_VERSION and older), oldest first: each one not posted
 * yet gets its post, so a version the bot missed (a deploy without this code, Discord saying no) is posted before
 * the newer ones and the channel reads in order; one Discord refused stops the newer ones until it goes through.
 * The same arguments as syncChangelog, with latest (LATEST_VERSION) for version. -> {<version>: what it did}, with
 * error: the first refusal.
 */
export async function syncChangelogs({ latest, ...args }) {
  const out = {};
  for (const e of published(latest).slice().reverse()) {
    const r = await syncChangelog({ ...args, version: e.version });
    out[e.version] = r;
    if (r && r.error) return { ...out, error: r.error };
  }
  return out;
}

/**
 * The cron's look at #changelog: posts the live version's entry once (and edits it in place if its words change
 * later). api: discordfaq.js faqApi; channel(api) -> {id} | {error} (the #changelog channel, found or made);
 * store: {get(key) -> {id, hash}|null, set(key, id, hash, note?)}, keys 'changelog:<version>' (id "<channel>/<message>");
 * 'changelog:failed' keeps when Discord last said no (id) and what it said (note: the discord table's date column).
 * -> 'unchanged' | 'posted' | 'edited' | {skipped} | {error}.
 */
export async function syncChangelog({ api, channel, store, version, site, hashOf, now = Date.now() }) {
  const e = entryFor(version);
  if (!e) return { skipped: `no changelog entry for ${version}` };
  const msg = changelogMessage(e, site);
  const hash = await hashOf(JSON.stringify(msg));
  const key = `changelog:${e.version}`;
  const rec = await store.get(key);
  if (rec && rec.hash === hash) return 'unchanged';
  const failed = await store.get('changelog:failed');
  if (failed && failed.hash === hash && now - Number(failed.id) < RETRY_MS) return 'waiting (Discord said no last time)';
  const fail = async (error) => { await store.set('changelog:failed', String(now), hash, String(error).slice(0, 500)); return { error }; };
  const said = (r) => `${r.status}${r.data && r.data.message ? ' ' + r.data.message : ''}`;
  if (rec && rec.id) {   // posted before, its words changed since: edit it (deleted on Discord: left deleted)
    const [channelId, messageId] = String(rec.id).split('/');
    const r = await api.edit(channelId, messageId, msg);
    if (!r.ok && r.status !== 404) return fail(`editing the ${e.version} changelog: Discord answered ${said(r)}`);
    await store.set(key, rec.id, hash);
    return r.ok ? 'edited' : 'unchanged (its post was deleted)';
  }
  const ch = await channel(api);
  if (ch.error) return fail(ch.error);
  const r = await api.post(ch.id, msg);
  if (!r.ok || !r.data || !r.data.id) {
    return fail(`posting the ${e.version} changelog in #${CHANNEL}: Discord answered ${said(r)}: ` +
      'the bot needs Send Messages and Embed Links there');
  }
  await store.set(key, `${ch.id}/${r.data.id}`, hash);
  return 'posted';
}
