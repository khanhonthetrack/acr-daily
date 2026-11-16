// Event sign-ups on Discord: someone with Manage Events types /event in a channel (e.g. #events), fills in a form
// (title, when, length, where, description) and the bot posts a card there with three buttons: Attending, Maybe,
// Not attending. Each click is saved and the card shows who answered what (mentions in an embed: nobody is pinged).
// Clicking the answer you already gave takes it back. The bot also makes the matching Discord server Event (the
// server's Events list, its countdown and its reminder), linked from the card. Once the event is over the buttons go.
//
// Discord sends the command, the form and each click to POST /discord/interactions, signed with the application's
// Public Key: nothing is answered without a valid signature. Nothing to set up by hand but the bot (DISCORD_BOT_TOKEN):
// from the cron's Discord FAQ runs, once (and again when the command or SITE_URL changes), the server makes its two
// tables, reads the application's Public Key from Discord (DISCORD_PUBLIC_KEY, if set, is used instead), registers
// /event in the server and points the application's Interactions Endpoint URL at SITE_URL/discord/interactions.
// Data: discord_events, discord_rsvps (migration 0037 makes the same).

const API = 'https://discord.com/api/v10';
const ACR_RED = 0xE30613, GREY = 0x71717A;
const MANAGE_EVENTS = 1n << 33n;
export const ANSWERS = {
  yes: { label: 'Attending', emoji: '✅', style: 3 },
  maybe: { label: 'Maybe', emoji: '❔', style: 2 },
  no: { label: 'Not attending', emoji: '❌', style: 4 },
};
const DEFAULT_HOURS = 2;
const FIELD_MAX = 1024;

// Discord's interaction and response types
const PING = 1, COMMAND = 2, COMPONENT = 3, MODAL_SUBMIT = 5;
const PONG = 1, MESSAGE = 4, UPDATE_MESSAGE = 7, MODAL = 9;
const EPHEMERAL = 1 << 6;

/** The /event command, as registered with Discord. Only members with Manage Events see it by default; the server's
 *  admins can change that in Server Settings › Integrations › ACR Daily. */
export const EVENT_COMMAND = {
  name: 'event',
  type: 1,
  description: 'Post an event with Attending / Maybe / Not attending buttons',
  default_member_permissions: MANAGE_EVENTS.toString(),   // (a guild command: in this server only, never in DMs)
};

/** The form /event opens. */
export function eventModal() {
  const input = (custom_id, label, style, extra) => ({ type: 1, components: [{ type: 4, custom_id, label, style, ...extra }] });
  return {
    custom_id: 'event:new',
    title: 'New event',
    components: [
      input('title', 'Title', 1, { required: true, max_length: 100, placeholder: 'Sunday night rally' }),
      input('when', 'Start (UTC unless you add an offset)', 1, { required: true, max_length: 60,
        placeholder: '2026-11-22 19:00 UTC  (or +01:00, or <t:…> stamp)' }),
      input('hours', 'Length in hours', 1, { required: false, max_length: 5, placeholder: String(DEFAULT_HOURS) }),
      input('where', 'Where', 1, { required: false, max_length: 100, placeholder: 'Assetto Corsa Rally · link to the rally' }),
      input('description', 'Description', 2, { required: false, max_length: 3000,
        placeholder: 'What it is, the car, the stages, what to bring…' }),
    ],
  };
}

/**
 * A start time typed in the form -> ms, or {error}. Takes a Discord timestamp (<t:1763838000:F>), Unix seconds, or
 * YYYY-MM-DD HH:MM in UTC, optionally followed by UTC / GMT / Z or an offset (+01:00, +1, UTC-5, GMT+5:30).
 */
export function parseWhen(text, now = Date.now()) {
  const s = String(text || '').trim();
  let ms = null;
  let m = s.match(/^<t:(-?\d{1,12})(?::[tTdDfFR])?>$/) || s.match(/^(\d{9,11})$/);
  if (m) ms = Number(m[1]) * 1000;
  else {
    m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})[ T,]+(\d{1,2})[:.h](\d{2})\s*(?:(?:UTC|GMT|Z)\s*)?(?:([+-])(\d{1,2})(?::?(\d{2}))?)?\s*(?:UTC|GMT)?$/i);
    if (!m) {
      return { error: 'I couldn\'t read the start time. Write it like `2026-11-22 19:00 UTC`, `2026-11-22 20:00 +01:00` ' +
        'or paste a Discord timestamp (`<t:1763838000:F>`).' };
    }
    const [, y, mo, d, h, mi, sign, oh, om] = m;
    if (+mo < 1 || +mo > 12 || +d < 1 || +d > 31 || +h > 23 || +mi > 59 || (oh && +oh > 14)) {
      return { error: `\`${s}\` isn't a real date and time.` };
    }
    const utc = Date.UTC(+y, +mo - 1, +d, +h, +mi);
    if (new Date(utc).getUTCDate() !== +d) return { error: `\`${s}\` isn't a real date.` };
    const offset = sign ? (sign === '-' ? -1 : 1) * ((+oh || 0) * 60 + (+om || 0)) * 60000 : 0;
    ms = utc - offset;
  }
  if (!Number.isFinite(ms)) return { error: 'I couldn\'t read the start time.' };
  if (ms < now + 60000) return { error: `That start time (<t:${Math.floor(ms / 1000)}:F>) is in the past: events have to start in the future.` };
  if (ms > now + 366 * 86400000) return { error: 'That start time is more than a year away.' };
  return { ms };
}

/** Length in hours -> ms, or {error}. Empty: DEFAULT_HOURS. */
export function parseHours(text) {
  const s = String(text || '').trim().replace(',', '.');
  if (!s) return { ms: DEFAULT_HOURS * 3600000 };
  const h = Number(s.replace(/\s*h(ours?)?$/i, ''));
  if (!Number.isFinite(h) || h < 0.25 || h > 72) return { error: 'The length is in hours, from 0.25 to 72 (e.g. `2` or `1.5`).' };
  return { ms: Math.round(h * 60) * 60000 };
}

/** Every {custom_id, value} a modal submit carries, whatever it nests them in (action rows, or labels). */
function modalValues(data) {
  const out = {};
  const walk = (c) => {
    if (!c) return;
    if (Array.isArray(c)) return c.forEach(walk);
    if (c.custom_id && typeof c.value === 'string') out[c.custom_id] = c.value;
    walk(c.components);
    walk(c.component);
  };
  walk(data && data.components);
  return out;
}

const userOf = (it) => (it.member && it.member.user) || it.user || {};
const nameOf = (it) => {
  const u = userOf(it);
  return String((it.member && it.member.nick) || u.global_name || u.username || 'someone').slice(0, 80);
};

/** Mentions for an embed field, within Discord's 1024 characters: "+N more" past that. */
function who(list) {
  if (!list.length) return '-';
  let out = '';
  for (let i = 0; i < list.length; i++) {
    const next = (out ? ', ' : '') + `<@${list[i]}>`;
    const rest = `, +${list.length - i} more`;
    if (out.length + next.length + (i < list.length - 1 ? rest.length : 0) > FIELD_MAX) return out + rest;
    out += next;
  }
  return out;
}

/**
 * The card: the event and who answered what, and the buttons until it is over.
 * ev: {id, title, description, starts, ends, location, created_by, scheduled_id, guild_id}; rsvps: [{user_id, answer}]
 * in the order they answered.
 */
export function eventCard(ev, rsvps, now = Date.now()) {
  const by = { yes: [], maybe: [], no: [] };
  for (const r of rsvps) if (by[r.answer]) by[r.answer].push(r.user_id);
  const over = now >= ev.ends;
  const s = Math.floor(ev.starts / 1000), e = Math.floor(ev.ends / 1000);
  const fields = [{ name: 'When', value: `<t:${s}:F> to <t:${e}:t> · <t:${s}:R>`, inline: false }];
  if (ev.location) fields.push({ name: 'Where', value: ev.location, inline: false });
  if (ev.scheduled_id && ev.guild_id) {
    fields.push({ name: 'Reminder', value: `[In the server's Events](https://discord.com/events/${ev.guild_id}/${ev.scheduled_id}): ` +
      'click **Interested** there for Discord\'s reminder when it starts.', inline: false });
  }
  for (const [key, a] of Object.entries(ANSWERS)) {
    fields.push({ name: `${a.emoji} ${a.label} (${by[key].length})`, value: who(by[key]), inline: true });
  }
  const embed = {
    title: ev.title,
    description: ev.description || undefined,
    color: over ? GREY : ACR_RED,
    fields,
    footer: { text: over ? 'This event is over.' : `Posted by ${ev.created_by_name || 'an organizer'} · click again to take your answer back` },
    timestamp: new Date(ev.starts).toISOString(),
  };
  const components = over ? [] : [{
    type: 1,
    components: Object.entries(ANSWERS).map(([key, a]) => ({
      type: 2, style: a.style, label: a.label, emoji: { name: a.emoji }, custom_id: `rsvp:${ev.id}:${key}`,
    })),
  }];
  return { embeds: [embed], components, allowed_mentions: { parse: [] } };
}

/** The Discord server Event matching the card (external: somewhere else, the game). */
export function scheduledEventBody(ev, site) {
  const link = site ? `${site}` : null;
  return {
    name: ev.title.slice(0, 100),
    description: [ev.description, link && `ACR Daily: ${link}`].filter(Boolean).join('\n\n').slice(0, 1000) || undefined,
    privacy_level: 2,
    entity_type: 3,
    entity_metadata: { location: (ev.location || 'Assetto Corsa Rally').slice(0, 100) },
    scheduled_start_time: new Date(ev.starts).toISOString(),
    scheduled_end_time: new Date(ev.ends).toISOString(),
  };
}

const ephemeral = (content) => ({ type: MESSAGE, data: { content, flags: EPHEMERAL, allowed_mentions: { parse: [] } } });

/**
 * One interaction (already checked: signed by Discord). -> {response, after?}: the response is sent back at once;
 * after() (if any) runs once it has gone (ctx.waitUntil): the server Event made and the card edited to link it.
 * store: {create(ev) -> id, get(id) -> ev|null, setScheduled(id, scheduledId), answer(id, userId, name, answer|null),
 *         rsvps(id) -> [{user_id, answer}]}
 * api: {createScheduled(body) -> {ok, id}, editOriginal(appId, token, msg) -> {ok}} | null (no bot token: no server Event)
 */
export async function handleInteraction(it, { store, api = null, site = '', now = Date.now() }) {
  if (it.type === PING) return { response: { type: PONG } };

  if (it.type === COMMAND && it.data && it.data.name === EVENT_COMMAND.name) {
    if (!it.guild_id) return { response: ephemeral('Use /event in a channel of the server.') };
    return { response: { type: MODAL, data: eventModal() } };
  }

  if (it.type === MODAL_SUBMIT && it.data && it.data.custom_id === 'event:new') {
    const v = modalValues(it.data);
    const title = String(v.title || '').trim();
    const when = parseWhen(v.when, now);
    const len = parseHours(v.hours);
    const problem = !title ? 'The event needs a title.' : when.error || len.error;
    if (problem) {
      const typed = [`Title: ${v.title || ''}`, `Start: ${v.when || ''}`, `Length: ${v.hours || ''}`, `Where: ${v.where || ''}`,
        `Description:\n${v.description || ''}`].join('\n').slice(0, 1500);
      return { response: ephemeral(`${problem}\nNothing was posted. Run /event again; what you typed, to copy:\n\`\`\`\n${typed.replace(/```/g, "'''")}\n\`\`\``) };
    }
    const u = userOf(it);
    const ev = {
      guild_id: String(it.guild_id || ''), channel_id: String(it.channel_id || (it.channel && it.channel.id) || ''),
      title: title.slice(0, 100), description: String(v.description || '').trim().slice(0, 3000),
      location: String(v.where || '').trim().slice(0, 100), starts: when.ms, ends: when.ms + len.ms,
      created_by: String(u.id || ''), created_by_name: nameOf(it), created: now,
    };
    ev.id = await store.create(ev);
    const card = eventCard(ev, [], now);
    const after = api ? async () => {
      const r = await api.createScheduled(scheduledEventBody(ev, site));
      if (!r.ok || !r.id) return { scheduled: `not made: Discord answered ${r.status}` };
      await store.setScheduled(ev.id, r.id);
      ev.scheduled_id = r.id;
      const e = await api.editOriginal(it.application_id, it.token, eventCard(ev, await store.rsvps(ev.id), Date.now()));
      return { scheduled: r.id, card: e.ok ? 'linked' : `not edited: Discord answered ${e.status}` };
    } : null;
    return { response: { type: MESSAGE, data: card }, after };
  }

  if (it.type === COMPONENT && it.data && /^rsvp:\d+:(yes|maybe|no)$/.test(it.data.custom_id || '')) {
    const [, id, answer] = it.data.custom_id.split(':');
    const ev = await store.get(+id);
    if (!ev) return { response: ephemeral('This event is no longer kept.') };
    if (now >= ev.ends) return { response: { type: UPDATE_MESSAGE, data: eventCard(ev, await store.rsvps(ev.id), now) } };
    const u = userOf(it);
    if (!u.id) return { response: ephemeral('Discord didn\'t say who you are; try again.') };
    const had = (await store.rsvps(ev.id)).find((r) => r.user_id === String(u.id));
    const next = had && had.answer === answer ? null : answer;        // the same button again: answer taken back
    await store.answer(ev.id, String(u.id), nameOf(it), next, now);
    return { response: { type: UPDATE_MESSAGE, data: eventCard(ev, await store.rsvps(ev.id), now) } };
  }

  return { response: ephemeral('I don\'t know that one.') };
}

// ------------------------------------------------------------------ Discord's signature

const hexBytes = (hex) => {
  if (!/^([0-9a-f]{2})+$/i.test(hex || '')) return null;
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.substr(i * 2, 2), 16);
  return out;
};

/** True when Discord signed this body: Ed25519 over timestamp + body with the application's Public Key. */
export async function verifySignature(publicKeyHex, signatureHex, timestamp, body) {
  const key = hexBytes(String(publicKeyHex || '').trim()), sig = hexBytes(signatureHex);
  if (!key || key.length !== 32 || !sig || sig.length !== 64 || !timestamp) return false;
  try {
    const k = await crypto.subtle.importKey('raw', key, { name: 'Ed25519' }, false, ['verify']);
    return await crypto.subtle.verify({ name: 'Ed25519' }, k, sig, new TextEncoder().encode(timestamp + body));
  } catch {
    return false;
  }
}

// ------------------------------------------------------------------ the bot's side of Discord's API

/** The two tables (as migration 0037), made by the server itself before /event is registered. */
export const RSVP_TABLES = [
  `CREATE TABLE IF NOT EXISTS discord_events (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id TEXT NOT NULL,
    channel_id TEXT NOT NULL DEFAULT '', title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '', starts INTEGER NOT NULL, ends INTEGER NOT NULL, created_by TEXT NOT NULL DEFAULT '',
    created_by_name TEXT NOT NULL DEFAULT '', scheduled_id TEXT, created INTEGER NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS discord_rsvps (event_id INTEGER NOT NULL, user_id TEXT NOT NULL, name TEXT NOT NULL DEFAULT '',
    answer TEXT NOT NULL, updated INTEGER NOT NULL, PRIMARY KEY (event_id, user_id))`,
];

/** Discord's API as the bot: the server Event, the card's edit, the /event command. Each returns {ok, status, data, id}. */
export function rsvpApi(token, guildId, fetchFn = fetch) {
  if (!/^[\w.-]{20,}$/.test(token || '') || !/^\d{17,20}$/.test(guildId || '')) return null;
  const call = async (method, path, body, auth = true) => {
    let res;
    try {
      res = await fetchFn(API + path, {
        method,
        headers: { ...(auth ? { Authorization: `Bot ${token}` } : {}), 'Content-Type': 'application/json',
          'User-Agent': 'DiscordBot (https://github.com/khanhonthetrack/acr-daily, 1.0)' },
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch {
      return { ok: false, status: 0, data: null, id: null };
    }
    let data = null;
    try { data = res.status === 204 ? null : await res.json(); } catch { data = null; }
    return { ok: res.ok, status: res.status, data, id: data && data.id ? String(data.id) : null };
  };
  return {
    createScheduled: (body) => call('POST', `/guilds/${guildId}/scheduled-events`, body),
    // the interaction's own webhook: no bot token needed (valid 15 minutes after the interaction)
    editOriginal: (appId, itToken, msg) => call('PATCH', `/webhooks/${appId}/${itToken}/messages/@original`, msg, false),
    application: () => call('GET', '/oauth2/applications/@me'),
    putGuildCommands: (appId, cmds) => call('PUT', `/applications/${appId}/guilds/${guildId}/commands`, cmds),
    // Discord checks the URL there and then (a signed PING to it, and a badly signed one it must refuse)
    setEndpoint: (url) => call('PATCH', '/applications/@me', { interactions_endpoint_url: url }),
  };
}

/**
 * Everything /event needs, done once (and again when the command or the endpoint changes): the tables made
 * (ensure()), the application's Public Key kept (store 'app': id, hash = the key), /event registered in the server,
 * and the Interactions Endpoint URL pointed at `endpoint` (left alone when empty or already so).
 * store: {get(key) -> {hash}|null, set(key, id, hash)}. -> 'unchanged' | 'registered...' | {error} (tried again later).
 */
export async function syncCommands({ api, store, hashOf, endpoint = '', ensure = null }) {
  const cmds = [EVENT_COMMAND];
  const hash = await hashOf(JSON.stringify({ cmds, endpoint }));
  const rec = await store.get('commands');
  if (rec && rec.hash === hash) return 'unchanged';
  if (ensure) await ensure();
  const app = await api.application();
  if (!app.ok || !app.id) return { error: `reading the bot's application: Discord answered ${app.status}` };
  if (app.data.verify_key) await store.set('app', app.id, String(app.data.verify_key));
  const r = await api.putGuildCommands(app.id, cmds);
  if (!r.ok) {
    return { error: `registering /event: Discord answered ${r.status}${r.data && r.data.message ? ' ' + r.data.message : ''}` +
      (r.status === 403 ? ': add the bot again with the applications.commands scope (SETUP.md)' : '') };
  }
  let did = 'registered';
  if (endpoint && app.data.interactions_endpoint_url !== endpoint) {
    const e = await api.setEndpoint(endpoint);
    if (!e.ok) {
      return { error: `/event registered, but setting the Interactions Endpoint URL to ${endpoint}: Discord answered ${e.status}` +
        `${e.data ? ' ' + JSON.stringify(e.data).slice(0, 300) : ''}` };
    }
    did += ', endpoint set';
  }
  await store.set('commands', app.id, hash);
  return did;
}

// ------------------------------------------------------------------ cards queued by the admin, posted by the bot

/** A discord_events row whose channel_id is 'queued' (or 'queued:<channel id>') is posted by the bot itself: in that
 *  channel, else the server's #events (a text or announcement channel called "events", else the first whose name has
 *  "event" in it). The way to post a card without typing /event in Discord (an INSERT, e.g. with `wrangler d1 execute`). */
export const QUEUED = 'queued';

export async function eventsChannel(api) {
  const list = await api.channels();
  if (!list.ok) return { error: `listing the channels: Discord answered ${list.status}` };
  const text = (list.data || []).filter((c) => c.type === 0 || c.type === 5);
  const ch = text.find((c) => String(c.name).toLowerCase() === 'events') ||
    text.find((c) => /event/i.test(String(c.name)));
  return ch ? { id: String(ch.id) } : { error: 'no #events channel: make one, or queue the card as queued:<channel id>' };
}

/**
 * Every queued card posted: the server Event made first, then the card (linking it) in its channel.
 * store: {queued() -> [ev], posted(id, channelId), setScheduled(id, scheduledId)}
 * api: {channels(), post(channelId, msg) -> {ok, status, data}, createScheduled(body) -> {ok, id}}
 * -> {<id>: 'posted' | error text}
 */
export async function postQueued({ api, store, site = '', now = Date.now() }) {
  const out = {};
  let fallback = null;
  for (const ev of await store.queued()) {
    let channel = String(ev.channel_id).slice(QUEUED.length + 1);
    if (!channel) {
      fallback = fallback || await eventsChannel(api);
      if (fallback.error) { out[ev.id] = fallback.error; continue; }
      channel = fallback.id;
    }
    if (!ev.scheduled_id && ev.starts > now + 60000) {
      const s = await api.createScheduled(scheduledEventBody(ev, site));
      if (s.ok && s.id) {
        await store.setScheduled(ev.id, s.id);
        ev.scheduled_id = s.id;
      }
    }
    const r = await api.post(channel, eventCard(ev, [], now));
    if (!r.ok) {
      out[ev.id] = `posting in channel ${channel}: Discord answered ${r.status}${r.data && r.data.message ? ' ' + r.data.message : ''}`;
      continue;
    }
    await store.posted(ev.id, channel);
    out[ev.id] = 'posted';
  }
  return out;
}
