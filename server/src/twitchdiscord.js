// ACR Daily live on Twitch -> a post in the Discord server's #stream (the user, 27 Nov 2026: "i want discord
// notification of #stream when acrdaily is live on twitch"): the bot (src/discordfaq.js faqApi) posts once per stream,
// from the same answer as the home page's LIVE ON TWITCH strip (src/twitch.js twitchStatus), looked at by the cron.
//
//   TWITCH_DISCORD_CHANNEL  the channel's name (wrangler.toml; default "stream"): an existing text or announcement
//                           channel, found by its name with any emoji or symbols around it left out; never made
//   TWITCH_DISCORD_PING     who the post pings: "" (nobody), "everyone", "here", or a role's id (wrangler.toml)
//
// One stream = its startedAt (Twitch's): kept in the discord table as 'twitch:live', so a stream is posted once
// however many cron runs see it, and a new stream (another startedAt) gets its own post.

export const KEY = 'twitch:live';
const STALE_MS = 6 * 3600000;        // a stream on for longer than this when first seen (a deploy mid-stream): not posted

/** A channel's name as people write it: "📺┃stream" -> "stream". */
const bare = (s) => String(s || '').toLowerCase().replace(/[^a-z0-9-]+/g, '').replace(/^-+|-+$/g, '');

/** The #stream channel's id, or {error}. Never made: a wrong guess would leave a second channel behind. */
export async function streamChannel(api, name) {
  const list = await api.channels();
  if (!list.ok) return { error: `listing the channels: Discord answered ${list.status}` };
  const want = bare(name);
  const texts = (list.data || []).filter((c) => c.type === 0 || c.type === 5);
  const found = texts.find((c) => String(c.name).toLowerCase() === want) || texts.find((c) => bare(c.name) === want);
  return found ? { id: String(found.id) } : { error: `no #${want} channel: make one where the bot can send messages` };
}

/** The post: who it pings, the stream's title, the link (Discord shows Twitch's own card under it). */
export function streamMessage(s, ping) {
  const p = String(ping || '').trim();
  const who = p === 'everyone' ? '@everyone ' : p === 'here' ? '@here ' : /^\d{17,20}$/.test(p) ? `<@&${p}> ` : '';
  const title = String(s.title || '').replace(/[\\*_~`|>@[\]]/g, '').trim();
  const lines = [`${who}🔴 **ACR DAILY is live on Twitch!**`];
  if (title) lines.push(title);
  lines.push(s.url);
  return {
    content: lines.join('\n'),
    allowed_mentions: p === 'everyone' || p === 'here' ? { parse: ['everyone'] }
      : /^\d{17,20}$/.test(p) ? { parse: [], roles: [p] } : { parse: [] },
  };
}

/**
 * One cron look. status: twitchStatus's answer; api: faqApi (null: the bot is off); store: {get(key), set(key, id,
 * hash, note)} -> 'off air' | 'posted' | 'already posted' | {skipped} | {error}.
 */
export async function syncStream({ status, api, store, channelName = 'stream', ping = '', now = Date.now() }) {
  if (!status || !status.live) return 'off air';
  if (!api) return { skipped: 'the Discord bot is off (DISCORD_BOT_TOKEN)' };
  const id = String(status.startedAt || '');
  const rec = await store.get(KEY);
  if (rec && rec.id === id) return 'already posted';
  const started = Date.parse(id);
  if (Number.isFinite(started) && now - started > STALE_MS) {
    await store.set(KEY, id, 'stale', 'not posted: on for hours when first seen');
    return { skipped: 'the stream has been on for hours' };
  }
  const ch = await streamChannel(api, channelName);
  if (ch.error) return { error: ch.error };
  const r = await api.post(ch.id, streamMessage(status, ping));
  if (!r.ok) {
    return { error: `posting in #${bare(channelName)}: Discord answered ${r.status}` +
      (r.status === 403 ? ': the bot needs View Channel, Send Messages and Embed Links there' : '') };
  }
  await store.set(KEY, id, `${ch.id}/${r.data && r.data.id}`, new Date(now).toISOString().slice(0, 10));
  return 'posted';
}
