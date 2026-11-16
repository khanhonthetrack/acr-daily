// Every ModsCloud livery (Assetto Corsa Rally > Skins) as SQL for the liveries table, the first import or a full catch-up
// (the server's hourly run keeps up with the newest: server/src/liveryimport.js, which maps them; this only fetches).
//   node tools/modscloud_liveries.mjs > modscloud.sql
//   npx wrangler d1 execute acr-daily --remote --file modscloud.sql      (from server/, after migrations 0037, 0038)
// The posts' text (the authors' credits) is slow on ModsCloud's side, so pages of 20, a second apart: ~15 minutes.
//   node tools/modscloud_liveries.mjs --links > links.sql
// only the files' links (each post's page read for its download button) for the ones kept without one: UPDATEs.
import { downloadOf, fromModscloud, MODSCLOUD, shotOf, UPSERT, upsertValues } from '../server/src/liveryimport.js';

const PER = 20;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function get(path) {
  for (let tries = 0; ; tries++) {
    try {
      const r = await fetch(MODSCLOUD.api + path, { headers: { 'User-Agent': 'ACR-Daily (+https://acrdaily.com)', Accept: 'application/json' },
        signal: AbortSignal.timeout(90000) });
      if (r.status === 400) return [];                 // (past the last page)
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return await r.json();
    } catch (e) {
      if (tries >= 3) throw e;
      await sleep(5000 * (tries + 1));
    }
  }
}
const q = (v) => (v == null ? 'NULL' : typeof v === 'number' ? String(v) : `'${String(v).replace(/'/g, "''")}'`);

const now = Date.now();
if (process.argv.includes('--links')) {          // the files' links only: every post's page, half a second apart
  const out = [];
  let found = 0, none = 0;
  for (let page = 1; ; page++) {
    const posts = await get(`/posts?categories=${MODSCLOUD.skins}&per_page=100&page=${page}&_fields=id,link`);
    if (!Array.isArray(posts) || !posts.length) break;
    for (const p of posts) {
      let html = '';
      for (let tries = 0; tries < 3 && !html; tries++) {
        try {
          const r = await fetch(p.link, { headers: { 'User-Agent': 'ACR-Daily (+https://acrdaily.com)' }, signal: AbortSignal.timeout(60000) });
          html = r.ok ? await r.text() : '';
        } catch { await sleep(3000); }
      }
      const d = downloadOf(html, p.link);
      if (d) {
        found++;
        out.push(`UPDATE liveries SET download_url = ${q(d)} WHERE source = 'modscloud' AND source_id = ${q(String(p.id))};`);
      } else none++;
      await sleep(500);
    }
    console.error(`page ${page}: ${found} links, ${none} without`);
    if (posts.length < 100) break;
  }
  process.stdout.write(out.join('\n') + '\n');
  console.error(`done: ${found} links, ${none} without`);
  process.exit(0);
}
let page = 1, kept = 0, skipped = 0;
const out = [];
for (;;) {
  const posts = await get(`/posts?categories=${MODSCLOUD.skins}&per_page=${PER}&page=${page}&_fields=id,date,date_gmt,link,title,content,tags,featured_media`);
  if (!Array.isArray(posts) || !posts.length) break;
  const mediaIds = [...new Set(posts.map((p) => p.featured_media).filter(Boolean))];
  const tagIds = [...new Set(posts.flatMap((p) => p.tags || []))];
  const media = mediaIds.length ? await get(`/media?include=${mediaIds.join(',')}&per_page=100&_fields=id,source_url,media_details`) : [];
  const tags = tagIds.length ? await get(`/tags?include=${tagIds.join(',')}&per_page=100&_fields=id,name`) : [];
  const shots = new Map(media.map((m) => [m.id, shotOf(m)])), names = new Map(tags.map((t) => [t.id, t.name]));
  for (const p of posts) {
    const r = fromModscloud(p, { shot: shots.get(p.featured_media) || null, brands: (p.tags || []).map((t) => names.get(t) || '') });
    if (!r.skip && process.argv.includes('--with-links')) {   // (each page read for its file's link too: slower)
      try { r.download = downloadOf(await (await fetch(p.link, { headers: { 'User-Agent': 'ACR-Daily (+https://acrdaily.com)' } })).text(), p.link); } catch {}
    }
    if (r.skip) { skipped++; console.error('left out:', r.skip); continue; }
    const vals = upsertValues(r, now);
    let i = 0;
    out.push(UPSERT.replace(/\s+/g, ' ').replace(/\?/g, () => q(vals[i++])) + ';');
    kept++;
  }
  console.error(`page ${page}: ${posts.length} posts (kept ${kept}, left out ${skipped})`);
  if (posts.length < PER) break;
  page++;
  await sleep(1000);
}
process.stdout.write(out.join('\n') + '\n');
console.error(`done: ${kept} liveries, ${skipped} left out`);
