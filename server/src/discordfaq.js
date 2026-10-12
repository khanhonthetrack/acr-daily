// The FAQ on Discord: the bot (secret DISCORD_BOT_TOKEN, the same bot as the server Events) keeps one message in the
// server's #faq channel, posted under the bot's own name, never a person's. The text lives here: when it changes
// (a deploy), the message is edited in place within 10 minutes; if someone deleted it, it is posted again.
// No #faq channel yet: the bot makes one where only it can write (Manage Channels; without Manage Roles it makes a
// plain one). Run every 10 minutes from the Discord bot's minute (index.js); one database read while nothing changed.

const API = 'https://discord.com/api/v10';
const ACR_RED = 0xE30613, WHITE = 0xF4F4F5;
const CHANNEL = 'faq';
const RETRY_MS = 15 * 60000;   // after Discord said no (permissions), try again this much later, not every minute
const SEND_MESSAGES = 1n << 11n, VIEW_CHANNEL = 1n << 10n, EMBED_LINKS = 1n << 14n, READ_HISTORY = 1n << 16n;

/** [question, answer] pairs, in reading order. Plain Discord markdown. */
export const FAQ = [
  ['What is ACR Daily?',
    'Two new Assetto Corsa Rally stages every day at 00:00 UTC. Same car and conditions for everyone, one timing ' +
    'sheet. A free, open-source fan project in beta.'],
  ['How do I start?',
    '1. Download **ACR-Daily.exe** from the website and run it (Windows warning: **More info › Run anyway**).\n' +
    '2. Sign in with Steam in the app.\n' +
    '3. Set the game to **Borderless**.\n' +
    '4. Click **DRIVE** and race. The full guide is under **How to play** on the website.'],
  ['What does DRIVE do?',
    'Sets up the stage, car and conditions in your game and starts it. Then: Racing › Rally › Rally Weekend › Start ' +
    'Rally › **J** › Confirm › Start Stage. **AUTO** can click through the menus for you.'],
  ['Which run counts?',
    'Your **first run** of each stage. The game\'s official time plus penalties goes on the sheet. Restart, retire or ' +
    'stop for 30 s and it\'s a **DNF**.'],
  ['Where are the results?',
    'On the website, and in **#live-timing** here (updated every 5 minutes).'],
  ['Does the app change my game?',
    'Only the stage setup in your save, when you click DRIVE, with a backup (**Restore save**).'],
  ['The timer doesn\'t show over the game.',
    'Set the game to Borderless and tick **Show timer** in the app. **Move overlays** to place it.'],
  ['Can I drive without signing in?',
    'Yes. Your run is sent when you sign in, if the stage is still open.'],
  ['How do I update?',
    'Click the red **UPDATE** bar in the app.'],
  ['Found a bug?',
    'Post it here: what you did, what you expected, what happened.'],
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
export async function syncFaq({ api, store, site, hashOf, now = Date.now() }) {
  const msg = faqMessage(site);
  const hash = await hashOf(JSON.stringify(msg));
  const rec = await store.get('faq');
  if (rec && rec.hash === hash && rec.id) return 'unchanged';
  const failed = await store.get('faq:failed');
  if (failed && failed.hash === hash && now - Number(failed.id) < RETRY_MS) return 'waiting (Discord said no last time)';
  const out = await sendFaq(api, store, rec, msg, hash);
  if (out && out.error) await store.set('faq:failed', String(now), hash);
  return out;
}

async function sendFaq(api, store, rec, msg, hash) {
  if (rec && rec.id) {
    const [channelId, messageId] = String(rec.id).split('/');
    const r = await api.edit(channelId, messageId, msg);
    if (r.ok) {
      await store.set('faq', rec.id, hash);
      return 'edited';
    }
    if (r.status !== 404) return { error: `editing the FAQ: Discord answered ${r.status}${r.data && r.data.message ? ' ' + r.data.message : ''}` };
  }
  const ch = await faqChannel(api);
  if (ch.error) return ch;
  const r = await api.post(ch.id, msg);
  if (!r.ok || !r.data || !r.data.id) {
    return { error: `posting the FAQ in #${CHANNEL} (${ch.created ? 'made just now' : 'channel ' + ch.id}): Discord answered ` +
      `${r.status}${r.data && r.data.message ? ' ' + r.data.message : ''}: the bot needs Send Messages and Embed Links there` };
  }
  await api.pin(ch.id, String(r.data.id));        // best effort (needs Manage Messages)
  await store.set('faq', `${ch.id}/${r.data.id}`, hash);
  return ch.created ? 'posted (made #faq)' : 'posted';
}
