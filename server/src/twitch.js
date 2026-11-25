// ACR Daily live on Twitch (the user, 25 Nov 2026: "if acrdaily is live on twitch tv then there is yet another
// notification (a thin banner like mini challenge) that ACR Daily is LIVE on twitch"): whether the channel streams now,
// from Twitch's own API (Helix: Get Streams, with an app access token), for the strip on the home page and RANKED.
//
//   TWITCH_CHANNEL        the channel's login (wrangler.toml); empty: off, nothing asked of Twitch
//   TWITCH_CLIENT_ID      the Twitch application's (dev.twitch.tv > Your Console > Applications): wrangler.toml (public)
//   TWITCH_CLIENT_SECRET  its secret (wrangler secret put): the client credentials (no user's sign-in: an app token reads public streams)
//
//   GET /api/twitch -> {live, channel, url, title, game, viewers, startedAt}
//
// One answer a minute at most (Cloudflare's cache, as the public API's): every visitor's page asks, Twitch is asked
// at most once a minute, its token kept (a day at most; it lasts about two months) and asked again when refused.

const TTL_S = 60;
const TOKEN_KEY = 'https://acrdaily.internal/twitch-token';
const STATUS_KEY = (ch) => `https://acrdaily.internal/twitch-status/${encodeURIComponent(ch)}`;
export const twitchUrl = (ch) => `https://www.twitch.tv/${encodeURIComponent(ch)}`;

const off = (ch) => ({ live: false, channel: ch || null, url: ch ? twitchUrl(ch) : null });

async function cached(cache, key) {
  if (!cache) return null;
  const hit = await cache.match(new Request(key));
  return hit ? hit.json() : null;
}
async function keep(cache, key, value, ttl) {
  if (!cache) return;
  await cache.put(new Request(key), new Response(JSON.stringify(value), {
    headers: { 'Content-Type': 'application/json', 'Cache-Control': `public, max-age=${ttl}` } }));
}

async function token(env, cache, fetcher, fresh = false) {
  if (!fresh) {
    const t = await cached(cache, TOKEN_KEY);
    if (t && t.token) return t.token;
  }
  const r = await fetcher('https://id.twitch.tv/oauth2/token', { method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ client_id: env.TWITCH_CLIENT_ID, client_secret: env.TWITCH_CLIENT_SECRET,
      grant_type: 'client_credentials' }).toString() });
  if (!r.ok) throw new Error(`twitch token ${r.status}`);
  const j = await r.json();
  await keep(cache, TOKEN_KEY, { token: j.access_token }, Math.max(60, Math.min(86400, (j.expires_in || 3600) - 300)));
  return j.access_token;
}

/** Whether the channel is live now -> the answer above. fetcher: fetch (tests: their own); cache: caches.default. */
export async function twitchStatus(env, { fetcher = fetch, cache = typeof caches !== 'undefined' ? caches.default : null } = {}) {
  const ch = String(env.TWITCH_CHANNEL || '').trim().toLowerCase();
  if (!/^[a-z0-9_]{3,25}$/.test(ch) || !env.TWITCH_CLIENT_ID || !env.TWITCH_CLIENT_SECRET) return off(ch);
  const was = await cached(cache, STATUS_KEY(ch));
  if (was) return was;
  let out = off(ch);
  try {
    let t = await token(env, cache, fetcher);
    const ask = (tk) => fetcher(`https://api.twitch.tv/helix/streams?user_login=${encodeURIComponent(ch)}`,
      { headers: { 'Client-Id': env.TWITCH_CLIENT_ID, Authorization: `Bearer ${tk}` } });
    let r = await ask(t);
    if (r.status === 401) { t = await token(env, cache, fetcher, true); r = await ask(t); }   // (the token gone stale)
    if (r.ok) {
      const s = ((await r.json()).data || [])[0];
      if (s && s.type === 'live') {
        out = { live: true, channel: ch, url: twitchUrl(ch), title: String(s.title || '').slice(0, 140),
          game: s.game_name || null, viewers: s.viewer_count ?? null, startedAt: s.started_at || null };
      }
    }
  } catch {
    out = off(ch);                                   // (Twitch not answering: no strip, asked again in a minute)
  }
  await keep(cache, STATUS_KEY(ch), out, TTL_S);
  return out;
}
