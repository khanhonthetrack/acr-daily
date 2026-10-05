// Steam sign-in (OpenID 2.0, the "Sign in through Steam" button). No passwords ever reach us.

const OPENID = 'https://steamcommunity.com/openid/login';

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

/** Ask Steam whether the callback is genuine. Returns the 64-bit Steam ID or null. */
export async function verifySteam(url) {
  const q = url.searchParams;
  if (q.get('openid.mode') !== 'id_res') return null;
  const claimed = q.get('openid.claimed_id') || '';
  const m = claimed.match(/^https:\/\/steamcommunity\.com\/openid\/id\/(\d{17})$/);
  if (!m) return null;
  // the return_to Steam signed must be our own callback
  if (!(q.get('openid.return_to') || '').startsWith(`${url.origin}/auth/steam/callback`)) return null;
  const body = new URLSearchParams();
  for (const [k, v] of q) if (k.startsWith('openid.')) body.set(k, v);
  body.set('openid.mode', 'check_authentication');
  const r = await fetch(OPENID, { method: 'POST', body, headers: { 'Content-Type': 'application/x-www-form-urlencoded' } });
  const text = await r.text();
  return /is_valid\s*:\s*true/.test(text) ? m[1] : null;
}

/** Player name + avatar: Steam Web API when a key is set, otherwise the public profile XML. */
export async function steamProfile(steamId, env) {
  try {
    if (env.STEAM_API_KEY) {
      const r = await fetch(`https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key=${env.STEAM_API_KEY}&steamids=${steamId}`);
      const p = (await r.json()).response.players[0];
      if (p) return { name: p.personaname, avatar: p.avatarmedium };
    }
    const r = await fetch(`https://steamcommunity.com/profiles/${steamId}/?xml=1`);
    const x = await r.text();
    const name = (x.match(/<steamID><!\[CDATA\[([\s\S]*?)\]\]><\/steamID>/) || [])[1];
    const avatar = (x.match(/<avatarMedium><!\[CDATA\[([\s\S]*?)\]\]><\/avatarMedium>/) || [])[1];
    if (name) return { name, avatar };
  } catch (e) { /* fall through */ }
  return { name: `Driver ${steamId.slice(-5)}`, avatar: null };
}
