// The app download: the GitHub Release built by .github/workflows/release.yml (with a build attestation).
// DOWNLOAD_URL may contain {version}; it's filled in with LATEST_VERSION, so a release only bumps that one number.

export function latestVersion(env) {
  return env.LATEST_VERSION || '0.0.0';
}

export function downloadUrl(env) {
  return (env.DOWNLOAD_URL || '').replace('{version}', latestVersion(env));
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
