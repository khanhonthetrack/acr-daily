// The FAQ on Discord: the bot (secret DISCORD_BOT_TOKEN, the same bot as the server Events) keeps one message in the
// server's #faq channel, posted under the bot's own name, never a person's. The text lives here: when it changes
// (a deploy), the message is edited in place on the next minute; if someone deleted it, it is posted again.
// No #faq channel yet: the bot makes one where only it can write (Manage Channels; without Manage Roles it makes a
// plain one). Run from the Discord bot's minute (index.js); costs one database read a minute while nothing changed.

const API = 'https://discord.com/api/v10';
const ACR_RED = 0xE30613, WHITE = 0xF4F4F5;
const CHANNEL = 'faq';
const SEND_MESSAGES = 1n << 11n, VIEW_CHANNEL = 1n << 10n, EMBED_LINKS = 1n << 14n, READ_HISTORY = 1n << 16n;

/** [question, answer] pairs, in reading order. Plain Discord markdown. */
export const FAQ = [
  ['What is ACR Daily?',
    'Two new special stages for Assetto Corsa Rally every day at 00:00 UTC, each with its own car, weather and ' +
    'time of day. Everyone drives the same set-up, and there is one timing sheet. It is a free, open-source fan ' +
    'project (in beta), not affiliated with the makers of Assetto Corsa Rally or with Valve.'],
  ['How do I take part?',
    '1. Download the app (**ACR-Daily.exe**) from the website. It needs no installing; if Windows says ' +
    '"Windows protected your PC", click **More info › Run anyway** (the app is not code-signed).\n' +
    '2. Sign in with Steam in the app. Steam\'s own page opens; ACR Daily never sees your password.\n' +
    '3. Set the game to **Borderless** (or Windowed), so the app\'s timer can sit over it.\n' +
    '4. Click **DRIVE** next to a stage and drive. The full guide is on the website under **How to play**.'],
  ['What does DRIVE do?',
    'It sets the day\'s stage, car, weather and time of day in the game for you, then starts the game (if the game ' +
    'is open, it closes it the normal way first: the game only reads its set-up when it starts). In the game: ' +
    'any key › Racing › Rally › Single Rally Stage › Start Race › Start Stage. The app shows **READY** when it sees ' +
    'the right stage and car. Turn on **auto-drive** in the app and it presses those menu keys for you, up to the ' +
    'Service Park; you press Start Stage.'],
  ['Which run counts?',
    'Your **first run of each stage** is your result; later runs are practice. A reset to the road is **+60 s**. ' +
    'Restarting, quitting, or stopping for more than 30 s is a **DNF**. Shortcuts don\'t count: you have to pass at ' +
    'least 90 % of the route\'s checkpoints. The car and stage must be the daily\'s, or the app won\'t time the run.'],
  ['Where do I see the results?',
    'On the website: today\'s timing sheets, a live map of who is on the stage, the live commentary bar, and every ' +
    'run\'s map, speed and section times. Here: **#live-timing** shows who is on stage and the sheets, updated every ' +
    'minute, and each day\'s final results. The weekly **hall of fame** scores every stage with WRC points ' +
    '(25, 18, 15, 12, 10, 8, 6, 4, 2, 1, then 1 for every other finisher).'],
  ['Does the app change my game?',
    'Only the Single Stage set-up in your own save, and only when you click DRIVE, with a backup first: ' +
    '**Restore save** in the app puts the old set-up back. It reads the telemetry the game publishes and changes ' +
    'nothing else. Auto-drive (off unless you turn it on) only presses menu keys, only while the game is in front, ' +
    'and stops as soon as you touch the keyboard or mouse.'],
  ['The timer doesn\'t show over the game.',
    'Set the game to Borderless, and check **Show timer** at the bottom of the app. The overlays start locked so ' +
    'your clicks reach the game: **Move overlays** to place them, **Lock overlays** when done.'],
  ['I drove without signing in.',
    'Your run is kept and sent as soon as you sign in, as long as the stage hasn\'t closed.'],
  ['How do I update the app?',
    'When there\'s a new version, a red **UPDATE** bar appears at the top of the app. One click: it updates itself ' +
    'and restarts. Every download is built by GitHub from the public code (how to check it: on the website\'s guide).'],
  ['Found a bug, or have an idea?',
    'Post it in this server. The app is in beta, so reports help a lot: say what you did, what you expected and what ' +
    'happened (a screenshot helps).'],
];

/** The FAQ message: a heading embed and the questions, split over embeds within Discord's limits. */
export function faqMessage(site) {
  const icon = site ? { icon_url: `${site}/brand/acr-daily-icon-512.png` } : {};
  const embeds = [{
    title: 'ACR Daily · FAQ', url: site ? `${site}/guide` : undefined, color: ACR_RED,
    description: 'Two new rally stages every day, one timing sheet.' +
      (site ? `\nWebsite and app: ${site}\nFull guide: ${site}/guide` : ''),
  }];
  let cur = null;
  for (const [q, a] of FAQ) {
    const block = `**${q}**\n${a}\n\n`;
    if (!cur || cur.description.length + block.length > 3800) {
      cur = { color: WHITE, description: '' };
      embeds.push(cur);
    }
    cur.description += block;
  }
  for (const e of embeds) e.description = e.description.trim();
  embeds[embeds.length - 1].footer = { text: 'ACR Daily · kept up to date by the bot', ...icon };
  return { embeds, allowed_mentions: { parse: [] } };
}

/** Discord's API as the bot, for the FAQ: channels and messages. Each call returns {ok, status, data}. */
export function faqApi(token, guildId, fetchFn = fetch) {
  if (!/^[\w.-]{20,}$/.test(token || '') || !/^\d{17,20}$/.test(guildId || '')) return null;
  const call = async (method, path, body) => {
    let res;
    try {
      res = await fetchFn(API + path, {
        method,
        headers: { Authorization: `Bot ${token}`, 'Content-Type': 'application/json',
          'User-Agent': 'DiscordBot (https://github.com/khanhonthetrack/acr-daily, 1.0)' },
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch {
      return { ok: false, status: 0, data: null };
    }
    let data = null;
    try { data = res.status === 204 ? null : await res.json(); } catch { data = null; }
    return { ok: res.ok, status: res.status, data };
  };
  return {
    me: () => call('GET', '/users/@me'),
    channels: () => call('GET', `/guilds/${guildId}/channels`),
    createChannel: (body) => call('POST', `/guilds/${guildId}/channels`, body),
    post: (channelId, msg) => call('POST', `/channels/${channelId}/messages`, msg),
    edit: (channelId, messageId, msg) => call('PATCH', `/channels/${channelId}/messages/${messageId}`, msg),
    pin: (channelId, messageId) => call('PUT', `/channels/${channelId}/pins/${messageId}`),
    guildId,
  };
}

/** The #faq channel's id: an existing text channel called faq, or a new one (read-only for everyone but the bot). */
async function faqChannel(api) {
  const list = await api.channels();
  if (!list.ok) return { error: `listing the channels: Discord answered ${list.status}` };
  const found = (list.data || []).find((c) => c.type === 0 && String(c.name).toLowerCase() === CHANNEL);
  if (found) return { id: String(found.id) };
  const me = await api.me();
  const base = { name: CHANNEL, type: 0, topic: 'How ACR Daily works. Kept up to date by the bot.' };
  const overwrites = me.ok && me.data && me.data.id ? [
    { id: api.guildId, type: 0, allow: VIEW_CHANNEL.toString(), deny: SEND_MESSAGES.toString() },   // @everyone: read only
    { id: String(me.data.id), type: 1, allow: (VIEW_CHANNEL | SEND_MESSAGES | EMBED_LINKS | READ_HISTORY).toString(), deny: '0' },
  ] : null;
  let made = overwrites ? await api.createChannel({ ...base, permission_overwrites: overwrites }) : { ok: false };
  if (!made.ok) made = await api.createChannel(base);            // no Manage Roles: a plain channel
  if (!made.ok || !made.data) {
    return { error: `no #${CHANNEL} channel, and the bot may not make one (Discord answered ${made.status}): ` +
      `make a #${CHANNEL} text channel where the bot can send messages` };
  }
  return { id: String(made.data.id), created: true };
}

/**
 * One minute of the FAQ. store: {get(key) -> {id, hash}|null, set(key, id, hash)}; the id kept is
 * "<channel id>/<message id>". -> what it did: 'unchanged' | 'edited' | 'posted' | {error}.
 */
export async function syncFaq({ api, store, site, hashOf }) {
  const msg = faqMessage(site);
  const hash = await hashOf(JSON.stringify(msg));
  const rec = await store.get('faq');
  if (rec && rec.hash === hash && rec.id) return 'unchanged';
  if (rec && rec.id) {
    const [channelId, messageId] = String(rec.id).split('/');
    const r = await api.edit(channelId, messageId, msg);
    if (r.ok) {
      await store.set('faq', rec.id, hash);
      return 'edited';
    }
    if (r.status !== 404) return { error: `editing the FAQ: Discord answered ${r.status}` };
  }
  const ch = await faqChannel(api);
  if (ch.error) return ch;
  const r = await api.post(ch.id, msg);
  if (!r.ok || !r.data || !r.data.id) return { error: `posting the FAQ in #${CHANNEL}: Discord answered ${r.status}` };
  await api.pin(ch.id, String(r.data.id));        // best effort (needs Manage Messages)
  await store.set('faq', `${ch.id}/${r.data.id}`, hash);
  return ch.created ? 'posted (made #faq)' : 'posted';
}
