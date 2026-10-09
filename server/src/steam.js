// Steam sign-in (OpenID 2.0, the "Sign in through Steam" button). No passwords ever reach us.

const OPENID = 'https://steamcommunity.com/openid/login';
// Steam's edge sometimes answers requests from Cloudflare's shared addresses with 403 for a few minutes (seen
// 2026-10-09), more likely without a User-Agent: send one, and ask again before giving up.
const HEADERS = { 'User-Agent': 'ACR-Daily (+https://acrdaily.com)', Accept: 'text/plain, */*' };
export const STEAM_TRIES = 3;
const pause = (ms) => new Promise((ok) => setTimeout(ok, ms));

export function steamLoginUrl(base, state) {
  const p = new URLSearchParams({
    'openid.ns': 'http://specs.openid.net/auth/2.0',
    'openid.mode': 'checkid_setup',
    'openid.return_to': `${base}/auth/steam/callback?state=${encodeURIComponent(state)}`,
    'openid.realm': base,
    'openid.identity': 'http://specs.openid.net/auth/2.0/identifier_select',
    'openid.claimed_id': 'http://specs.openid.net/auth/2.0/identifier_select',
  });
  return `${OPENID}?${p}`;
}

/** Ask Steam whether the callback is genuine. -> {steamId} (the 64-bit Steam ID), or {error}: 'cancelled' (the
 *  player cancelled on Steam), 'bad' (not a sign-in reply we can use), 'invalid' (Steam says it isn't genuine, or it
 *  was used already), 'steam <HTTP status>' / 'steam unreachable' (Steam didn't answer the check, STEAM_TRIES times). */
export async function verifySteam(url, { fetchFn = fetch, wait = pause } = {}) {
  const q = url.searchParams;
  const mode = q.get('openid.mode');
  if (mode === 'cancel') return { error: 'cancelled' };
  if (mode !== 'id_res') return { error: 'bad' };
  const claimed = q.get('openid.claimed_id') || '';
  const m = claimed.match(/^https:\/\/steamcommunity\.com\/openid\/id\/(\d{17})$/);
  if (!m) return { error: 'bad' };
  // the return_to Steam signed must be our own callback
  if (!(q.get('openid.return_to') || '').startsWith(`${url.origin}/auth/steam/callback`)) return { error: 'bad' };
  const body = new URLSearchParams();
  for (const [k, v] of q) if (k.startsWith('openid.')) body.set(k, v);
  body.set('openid.mode', 'check_authentication');
  let status = 0;
  for (let k = 0; k < STEAM_TRIES; k++) {
    if (k) await wait(400 * k);
    try {
      const r = await fetchFn(OPENID, { method: 'POST', body: body.toString(),
        headers: { ...HEADERS, 'Content-Type': 'application/x-www-form-urlencoded' } });
      status = r.status;
      const text = await r.text();
      // Steam's answer is OpenID key-value text ("ns:...\nis_valid:true\n"); anything else is its edge turning us away
      if (r.ok && /^ns\s*:/m.test(text)) return /^is_valid\s*:\s*true\s*$/m.test(text) ? { steamId: m[1] } : { error: 'invalid' };
    } catch {
      status = 0;
    }
  }
  return { error: status ? `steam ${status}` : 'steam unreachable' };
}

/** Player name + avatar: Steam Web API when a key is set, otherwise the public profile XML. */
export async function steamProfile(steamId, env) {
  try {
    if (env.STEAM_API_KEY) {
      const r = await fetch(`https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key=${env.STEAM_API_KEY}&steamids=${steamId}`,
        { headers: HEADERS });
      const p = (await r.json()).response.players[0];
      if (p) return { name: p.personaname, avatar: p.avatarmedium };
    }
    const r = await fetch(`https://steamcommunity.com/profiles/${steamId}/?xml=1`, { headers: HEADERS });
    const x = await r.text();
    const name = (x.match(/<steamID><!\[CDATA\[([\s\S]*?)\]\]><\/steamID>/) || [])[1];
    const avatar = (x.match(/<avatarMedium><!\[CDATA\[([\s\S]*?)\]\]><\/avatarMedium>/) || [])[1];
    if (name) return { name, avatar };
  } catch (e) { /* fall through */ }
  return { name: `Driver ${steamId.slice(-5)}`, avatar: null };
}
