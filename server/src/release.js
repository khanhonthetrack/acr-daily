// The app download: the GitHub Release built by .github/workflows/release.yml (with a build attestation).
// DOWNLOAD_URL may contain {version}; it's filled in with LATEST_VERSION, so a release only bumps that one number.

export function latestVersion(env) {
  return env.LATEST_VERSION || '0.0.0';
}

export function downloadUrl(env) {
  return (env.DOWNLOAD_URL || '').replace('{version}', latestVersion(env));
}

/** The community's Discord invite (DISCORD_URL in wrangler.toml), or '' while there is none. The website links
 *  to it and /discord sends the app's Discord link there, so a new invite needs no app release. */
export function discordUrl(env) {
  const u = String(env.DISCORD_URL || '').trim();
  return /^https:\/\/(discord\.gg|discord\.com\/invite)\/[\w-]+$/.test(u) ? u : '';
}

const guildId = (env) => {
  const g = String(env.DISCORD_GUILD_ID || '').trim();
  return /^\d{17,20}$/.test(g) ? g : '';
};

/** Is there a Discord to link to (an invite, or the server's id)? Links go through /discord either way. */
export const hasDiscord = (env) => !!(discordUrl(env) || guildId(env));

/** The invite /discord sends people to. With DISCORD_GUILD_ID and the server's widget switched on (Server Settings ›
 *  Widget, with an invite channel), it is the widget's invite, which names no person ("X invited you"); otherwise
 *  DISCORD_URL. The widget's answer is cached for 5 minutes. */
export async function discordInvite(env, fetchFn = fetch) {
  const g = guildId(env);
  if (g) {
    const url = `https://discord.com/api/guilds/${g}/widget.json`;
    const cache = typeof caches !== 'undefined' ? caches.default : null;
    try {
      let res = cache && await cache.match(url);
      if (!res) {
        const r = await fetchFn(url, { headers: { 'User-Agent': 'acr-daily-server' } });
        if (r.ok) {
          res = new Response(await r.text(), { headers: { 'Cache-Control': 'public, max-age=300' } });
          if (cache) await cache.put(url, res.clone());
        }
      }
      const inv = res ? (await res.json()).instant_invite : null;
      if (typeof inv === 'string' && /^https:\/\/(discord\.gg|discord\.com\/invite)\/[\w-]+$/.test(inv)) return inv;
    } catch { /* the widget is off or Discord is not reachable: the fixed invite */ }
  }
  return discordUrl(env);
}

export function releasePage(env) {
  return env.SOURCE_URL ? `${env.SOURCE_URL}/releases/tag/v${latestVersion(env)}` : '';
}

// The release's published SHA-256 (ACR-Daily.exe.sha256 next to the exe), cached: a release never changes.
export async function releaseSha256(env, ctx) {
  const url = downloadUrl(env);
  if (!/^https:\/\//.test(url)) return null;
  const key = new Request(url + '.sha256');
  const cache = typeof caches !== 'undefined' ? caches.default : null;
  let res = cache && await cache.match(key);
  if (!res) {
    try {
      res = await fetch(url + '.sha256', { headers: { 'User-Agent': 'acr-daily-server' } });
    } catch {
      return null;
    }
    if (!res.ok) return null;
    res = new Response(await res.text(), { headers: { 'Cache-Control': 'public, max-age=86400' } });
    if (cache) {
      const put = cache.put(key, res.clone());
      if (ctx && ctx.waitUntil) ctx.waitUntil(put); else await put;
    }
  }
  const h = (await res.text()).trim().toLowerCase();
  return /^[0-9a-f]{64}$/.test(h) ? h : null;
}
