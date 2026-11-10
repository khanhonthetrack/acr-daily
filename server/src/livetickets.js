// Live ghost cars: the app's live relay (live/relay.py, on its own machine) passes each driver's position on to the
// others on the same stage. So nobody can drive there under someone else's name, the app first asks this server for a
// ticket: its driver's Steam id and name, signed, for a few hours. The relay checks the signature with LIVE key (a
// one-way hash of ADMIN_KEY: it can check tickets, not make admin calls); the app's session token never leaves here.
//
//   POST /api/live/ticket    (the app, signed in)  -> {ticket, steamId, name, expires}
//
// ticket = base64url(JSON {k: 'live', s: steamId, n: name, e: expiry ms}) + '.' + base64url(HMAC-SHA256(liveKey, payload))
// Changing ADMIN_KEY changes the relay's key too: put the new sha256('live-relay|' + key) on the relay (live/README.md).

const utf8 = new TextEncoder();
export const LIVE_TICKET_MS = 6 * 3600 * 1000;

const b64url = (bytes) => btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

/** The relay's key: sha256('live-relay|' + ADMIN_KEY) (32 bytes). */
export async function liveKey(env) {
  return new Uint8Array(await crypto.subtle.digest('SHA-256', utf8.encode(`live-relay|${(env.ADMIN_KEY || 'dev').trim()}`)));
}

async function sig(env, payload) {
  const key = await crypto.subtle.importKey('raw', await liveKey(env), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  return b64url(new Uint8Array(await crypto.subtle.sign('HMAC', key, utf8.encode(payload))));
}

/** player: a players row -> {ticket, steamId, name, expires}. */
export async function liveTicket(env, player, now = Date.now()) {
  const e = now + LIVE_TICKET_MS;
  const payload = b64url(utf8.encode(JSON.stringify({ k: 'live', s: player.steam_id, n: player.name, e })));
  return { ticket: `${payload}.${await sig(env, payload)}`, steamId: player.steam_id, name: player.name, expires: e };
}

/** A ticket -> what it carries, or null (not ours, changed or out of date). The relay does the same in Python. */
export async function readLiveTicket(env, ticket, now = Date.now()) {
  const [payload, s, extra] = String(ticket || '').split('.');
  if (!payload || !s || extra !== undefined || s !== await sig(env, payload)) return null;
  try {
    const t = JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(payload.replace(/-/g, '+').replace(/_/g, '/')), (ch) => ch.charCodeAt(0))));
    return t && t.k === 'live' && typeof t.s === 'string' && typeof t.n === 'string' && Number(t.e) > now ? t : null;
  } catch {
    return null;
  }
}
