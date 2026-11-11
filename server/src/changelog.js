// What's new in each app version, in plain words for drivers. One list, published four ways:
// - the website's /changelog (src/changelogpage.js);
// - the Discord bot's #changelog channel: one post per version, once LATEST_VERSION goes live (syncChangelog, from
//   the cron in src/index.js; the channel is made by the bot like #faq, src/discordfaq.js);
// - the GitHub Release's notes (.github/workflows/release.yml, through scripts/whatsnew.mjs);
// - the app's "UPDATED TO ... · WHAT'S NEW" bar after an update, which opens /changelog.
//
// EVERY RELEASE ADDS ITS ENTRY HERE, at the top, in the commit that bumps the app's __version__: the server's tests
// (test/changelog.test.mjs) and the release workflow fail without one. Write for drivers, not for developers: what
// they will notice, one short line each, plain text (no markdown, no HTML). A version never put out (as 0.0.25) has
// no entry: its changes go under the next one. An entry newer than LATEST_VERSION stays off the website and Discord
// until the server says that version is out.

export const CHANGELOG = [
  {
    version: '0.0.30', date: '2026-11-11', changes: [
      'Ghost cars move smoothly: no more jumping ahead and snapping back.',
      'Your own dash screen no longer goes black when a ghost car is near.',
      'No more boxes flashing over the cars for a moment.',
      'Ready for 30 drivers on the same stage, with less load on your PC.',
    ],
  },
  {
    version: '0.0.29', date: '2026-11-10', changes: [
      'Ghost cars: the other drivers on your stage drive as real cars in the game. The app adds the game mod for you, and takes it out again when you switch it off.',
      'The window can go as narrow as 560 px and lays itself out to fit, for a screen stood on its end.',
      'AUTO gets through the Service Park with the Peugeot 206 WRC.',
    ],
  },
  {
    version: '0.0.28', date: '2026-11-10', changes: [
      'Leagues: a stage start sent twice no longer gives a "started again" DNF.',
      'Only one copy of the app runs at a time. A second copy says the app is already open.',
    ],
  },
  {
    version: '0.0.27', date: '2026-11-09', changes: [
      'Sign in with Steam first: the app loads everything of your account once you are in.',
      'Your own ACR Daily picture, in your shop frame, and your name in the header.',
      'League and cup banners on the event cards.',
      'How to play, the shop, the leagues and the Steam sign-in open on acrdaily.com.',
      'The LIVE page is gone.',
      'Fixed: the view could go black after leaving HOME.',
    ],
  },
  {
    version: '0.0.26', date: '2026-11-08', changes: [
      'A new HOME of photo tiles, where the app now opens, with a header menu: HOME, DAILIES, TIME TRIAL, COMPETITIONS and PROFILE.',
      'COMPETITIONS holds LEAGUES, 1V1 and CUPS as tabs.',
      'Hidden events: an event can keep its stages, weather and times hidden until it ends. You get them when you press DRIVE.',
      'Fixed: the app could make the game stick on its loading screen by reading the save while the game was writing it.',
      'Leagues: CONTINUE finds your rally again after an admin reinstates your entry.',
    ],
  },
  {
    version: '0.0.24', date: '2026-11-07', changes: [
      'The game\'s random weather is switched off when DRIVE sets up a stage, so the weather is the one picked.',
      'The game\'s save is no longer read while the game writes it, when waiting for a stage\'s result.',
      'A league run that didn\'t count says so after the finish, and the event\'s button reads DRIVE AGAIN.',
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

/** The GitHub Release's "What's new" (Markdown), or null when the version has no entry. */
export function releaseNotes(version) {
  const e = entryFor(version);
  return e ? `## What's new in ${e.version}\n\n${e.changes.map((c) => `- ${c}`).join('\n')}\n` : null;
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
      title: `ACR Daily ${e.version} is out`, url: link, color: ACR_RED,
      description: `${e.changes.map((c) => `• ${md(c)}`).join('\n')}\n\n` +
        `Update with the red **UPDATE** bar in the app${site ? `, or download it from ${site}` : ''}.`,
      footer: { text: `ACR Daily · ${e.date}`, ...icon },
    }],
    allowed_mentions: { parse: [] },
  };
}

/**
 * The cron's look at #changelog: posts the live version's entry once (and edits it in place if its words change
 * later). api: discordfaq.js faqApi; channel(api) -> {id} | {error} (the #changelog channel, found or made);
 * store: {get(key) -> {id, hash}|null, set(key, id, hash)}, keys 'changelog:<version>' (id "<channel>/<message>").
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
  const fail = async (error) => { await store.set('changelog:failed', String(now), hash); return { error }; };
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
