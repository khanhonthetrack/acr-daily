// What's new in each app version, in plain words for drivers. One list, published four ways:
// - the website's /changelog (src/changelogpage.js);
// - the Discord bot's #changelog channel: one post per version, once LATEST_VERSION goes live (syncChangelog, from
//   the cron in src/index.js; the channel is made by the bot like #faq, src/discordfaq.js);
// - the GitHub Release's notes (.github/workflows/release.yml, through scripts/whatsnew.mjs);
// - the app: on the first start of a new version, a popup with the entry's photo, headline and changes (GET
//   /api/changelog/<version>, client/acr_daily/whatsnew.py), and an "UPDATED TO ... · WHAT'S NEW" bar.
//
// EVERY RELEASE ADDS ITS ENTRY HERE, at the top, in the commit that bumps the app's __version__: the server's tests
// (test/changelog.test.mjs) and the release workflow fail without one. Write for drivers, not for developers: what
// they will notice, one short line each, plain text (no markdown, no HTML). From 0.0.31 on each entry has, for the
// app's popup (POPUP_FROM, checked by the tests):
//   title  its headline, the big words over the photo (70 characters at most);
//   photo  the photo behind it: a key of client/acr_daily/photos/photos.json (a new photo goes there, with its
//          author and licence; it ships inside that version's app);
//   changes  2 to 5 short lines (160 characters at most each): the popup is read in passing.
// The list starts at 0.0.30. A version without an entry (none put out) has its changes under the next one. An entry
// newer than LATEST_VERSION stays off the website, Discord and the app until the server says that version is out.
// Its words in N_(): the website and the app's popup say them in the reader's language once the catalogs have them
// (server/src/locales, tools/i18n/extract.py check; English until then); Discord and the GitHub Release say English.

import { N_, t } from './i18n.js';

export const POPUP_FROM = '0.0.31';
export const POPUP = { title: 70, lines: [2, 5], line: 160 };

export const CHANGELOG = [
  {
    version: '0.1.1', date: '2026-11-12', title: N_('Your official time, saved'), photo: 'wales',
    changes: [
      N_("While a finished run waits for the game's official time, the timer window says in orange what saves it: go on from the game's results screen."),
      N_('Restarting the stage or quitting the game from the results screen loses that time, and the app now tells you so straight away.'),
      N_('A finished first run now counts even when practice runs reach the server first (a server fix: no update needed for it).'),
    ],
  },
  {
    version: '0.1.0', date: '2026-11-11', title: N_('ACR Daily speaks your language'), photo: 'monte-carlo',
    changes: [
      N_('The app and the website now come in 10 languages: English, Polish, Hungarian, Japanese, German, French, Spanish, Italian, Portuguese (Brazil) and Chinese.'),
      N_('Pick yours with the globe at the top of the app or in SETTINGS. The website follows your browser, or the globe in its header.'),
      N_('Fixed: a run the game had saved could still go in as a DNF ("the game closed before saving its official result"). Those runs now count.'),
      N_('From the 12 November dailies on, runs need 0.1.0: older apps show the red UPDATE bar.'),
    ],
  },
  {
    version: '0.0.30', date: '2026-11-11', title: N_('Ghost cars: race the other drivers live, in your game'),
    changes: [
      N_('New: everyone driving your stage right now shows up as a real car in your game, so you can see who is ahead and race them live.'),
      N_('Try it: SETTINGS, Ghost cars, switch it on. The app adds the small game mod it needs for you, and takes it out again when you switch it off. It is still a test: tell us how it goes.'),
      N_('Smooth netcode: positions come 20 times a second and each car follows a smooth line, with no jumping ahead and snapping back.'),
      N_('Light on your PC: ten ghost cars cost the game about a third of what they did in testing (8 ms a frame, down from 23).'),
      N_('Ready for 30 drivers on one stage, and ghost cars appear without a hitch.'),
      N_('Also new: the window can go as narrow as 560 px, for a screen stood on its end, and AUTO gets through the Service Park with the Peugeot 206 WRC.'),
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

/** The entries people can see: the version they get (LATEST_VERSION) and older, newest first. */
export const published = (latest) => CHANGELOG.filter((e) => compareVersions(e.version, latest) <= 0);

/** What the app's popup gets for its version (GET /api/changelog/<version>): the entry once that version is out,
 *  else null; its words in the language it is made in (index.js: the request's, inLang). */
export function changelogFor(version, latest) {
  const e = entryFor(version);
  if (!e || compareVersions(e.version, latest) > 0) return null;
  return { version: e.version, date: e.date, title: e.title ? t(e.title) : null, photo: e.photo || null,
    changes: e.changes.map((c) => t(c)) };
}

/** The GitHub Release's "What's new" (Markdown), or null when the version has no entry. */
export function releaseNotes(version) {
  const e = entryFor(version);
  return e ? `## What's new in ${e.version}\n\n${e.title ? `**${e.title}**\n\n` : ''}${e.changes.map((c) => `- ${c}`).join('\n')}\n` : null;
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
      description: `${e.changes.map((c) => `• ${md(c)}`).join('\n')}\n\n` +
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
