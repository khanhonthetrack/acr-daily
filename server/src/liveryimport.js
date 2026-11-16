// Liveries from ModsCloud.net (its Assetto Corsa Rally > Skins category, https://modscloud.net/?s&cat=147): every one
// listed on the liveries page and in the app as if a driver had sent it, with its author's credit ("Credits: ..." in
// the post) and ModsCloud named as where it is. Nothing is copied: the link is the post's page (the download is there,
// so the app's button opens it in the browser), and the preview is ModsCloud's own picture (shot_url).
//
// They come from ModsCloud's WordPress API (public, robots.txt allows it): the posts (title, page, date, the post's
// text for the credit, the car's brand as a tag), their pictures and tags. The post's text is slow to come (about
// 0.75 s a post on their side), so the scheduled run (index.js, hourly) takes only the newest 20; the first import
// of all of them (670 on 2026-11-16) went in once from tools/modscloud_liveries.mjs. A post seen again updates its
// card (title, credit, car, picture) but never its stars, downloads or status: one the admin hid stays hidden.
//
// The car is read from the title (and the brand tag): each car of src/cars.js by its brand and the words of its name
// that no other car of that brand has (Peugeot: 206, 208, 306; Fiat: 124, 131). A post that names no car of the game,
// or two, is left out.

import { CARS } from './cars.js';

export const MODSCLOUD = {
  source: 'modscloud',
  sender: 'modscloud',             // (liveries.steam_id: not a driver; the page shows the credit, not a sender)
  api: 'https://modscloud.net/wp-json/wp/v2',
  skins: 152,                      // Assetto Corsa Rally > Skins
  perRun: 20,                      // posts a scheduled run reads (the newest)
};

const words = (s) => String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
  .replace(/[^a-z0-9]+/g, ' ').trim().split(' ').filter(Boolean);
const GENERIC = new Set(['rally', 'the', 'and', 'kit', 'car', 'evo', 'evolution']);
const BRAND = { vw: 'volkswagen', volkswagen: 'volkswagen', alfa: 'alfa', romeo: 'alfa' };
const brandOf = (w) => BRAND[w] || w;

// each car: its brand, and the words of its names (name, aliases, telemetry) only it has among its brand's cars;
// `alone`: those no other car of the game has either (a title without the brand: "Polo R5", "A110")
const KEYS = (() => {
  const named = CARS.map((c) => {
    const all = [c.name, ...(c.aliases || []), String(c.telemetry || '').replace(/_/g, ' ')].flatMap(words);
    return { id: c.id, brand: brandOf(words(c.name)[0]), all: new Set(all) };
  });
  return named.map((c) => {
    const others = named.filter((o) => o.id !== c.id);
    const keys = [...c.all].filter((w) => w.length > 1 && brandOf(w) !== c.brand && !GENERIC.has(w)
      && !others.some((o) => o.brand === c.brand && o.all.has(w)));
    const alone = keys.filter((w) => !others.some((o) => o.all.has(w)) && !/^\d{4}$/.test(w));   // (not a year-like number)
    return { id: c.id, brand: c.brand, keys, alone: new Set(alone) };
  });
})();
const CARS_OF = KEYS.reduce((m, c) => m.set(c.brand, [...(m.get(c.brand) || []), c.id]), new Map());

/** Does key k name a model in the title's words? A word of it; or inside one: a model number at its start ("306maxi"),
 *  a model with letters and digits ("i20n"), a long name ("giuliagta"). */
function names(k, t) {
  if (t.includes(k)) return true;
  if (/^\d+$/.test(k)) return k.length >= 3 && t.some((w) => w.startsWith(k) && !/^\d+$/.test(w));
  if (/\d/.test(k)) return k.length >= 3 && t.some((w) => w.includes(k));
  return k.length >= 5 && t.some((w) => w.includes(k));
}

/** The car (its id in src/cars.js) a livery's title names, or null (none of the game's, or two). brands: the post's
 *  brand tags ("ACR Peugeot"), for a title without the brand. A model number counts for more than a word ("Peugeot 208
 *  R4 - Maxi F2000": the 208); a brand with one car in the game is that car when no model is named ("... CPR 2026",
 *  tagged ACR Skoda). */
export function carForTitle(title, brands = []) {
  const t = words(title);
  const all = [...t, ...brands.flatMap(words)];
  const brandsIn = new Set(all.map(brandOf));
  const pick = (cars) => {                     // the one with most (a model number counts twice), or null on a tie
    let best = null, score = 0, tie = false;
    for (const [c, hit] of cars) {
      const n = hit.reduce((a, k) => a + (/\d/.test(k) ? 2 : 1), 0);
      if (n > score) [best, score, tie] = [c.id, n, false];
      else if (n === score) tie = true;
    }
    return score ? (tie ? null : best) : undefined;
  };
  const hits = KEYS.map((c) => [c, c.keys.filter((k) => names(k, all))]).filter(([, hit]) => hit.length);
  // the brands the title (or a tag) names first: "Skoda Fabia R5" is the Fabia, though R5 names the Polo too
  const branded = pick(hits.filter(([c]) => brandsIn.has(c.brand)));
  if (branded !== undefined) return branded;
  const alone = pick(hits.filter(([c, hit]) => hit.some((k) => c.alone.has(k))));   // "Polo R5", "Aipine Renault A110"
  if (alone !== undefined) return alone;
  const only = [...brandsIn].filter((b) => CARS_OF.has(b));
  return only.length === 1 && CARS_OF.get(only[0]).length === 1 ? CARS_OF.get(only[0])[0] : null;
}

const unescape = (s) => String(s || '').replace(/<[^>]*>/g, ' ').replace(/&#(\d+);/g, (_m, n) => String.fromCodePoint(+n))
  .replace(/&#x([0-9a-f]+);/gi, (_m, n) => String.fromCodePoint(parseInt(n, 16))).replace(/&nbsp;/g, ' ')
  .replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&#039;/g, "'")
  .replace(/\s+/g, ' ').trim();

/** "Credits: olivier brasseur Rate this mod" -> 'olivier brasseur' (the post's text, as text), or ''. */
export function creditOf(text) {
  const m = String(text || '').match(/credits?\s*(?:to)?\s*[:\-–]\s*(.+?)(?:\s+rate this mod\b|$)/i);
  return m ? m[1].replace(/\s+/g, ' ').trim().slice(0, 60) : '';
}

/** One ModsCloud post (with its picture's address and its tags' names) as a livery to keep, or {skip: why}. */
export function fromModscloud(post, { shot = null, brands = [] } = {}) {
  const title = unescape(post && post.title && post.title.rendered).slice(0, 80);
  const link = String((post && post.link) || '');
  if (!post || !post.id || title.length < 2 || !/^https:\/\/(www\.)?modscloud\.net\//.test(link)) return { skip: 'not a post' };
  const car = carForTitle(title, brands);
  if (!car) return { skip: `no car of the game in "${title}"` };
  const text = unescape(post.content && post.content.rendered);
  const author = creditOf(text) || 'ModsCloud';
  let about = text.replace(/credits?\s*(?:to)?\s*[:\-–]\s*.+?(?=\s+rate this mod\b|$)/i, '').replace(/\brate this mod\b.*$/i, '').trim();
  // (the post's text starting with its title, with its version or without: not said twice)
  const bare = title.replace(/\s*v?\.?\s*\d+(?:\.\d+)+\s*$/i, '');
  for (const t of [title, bare]) {
    if (t && about.toLowerCase().startsWith(t.toLowerCase())) { about = about.slice(t.length).trim(); break; }
  }
  const published = Date.parse(String(post.date_gmt || post.date || '') + (post.date_gmt ? 'Z' : '')) || null;
  return { source: MODSCLOUD.source, sourceId: String(post.id), car, title, author, description: about.slice(0, 600), link,
    shot: shot && /^https:\/\//.test(shot) ? shot : null, published };
}

/** The picture of a post for its card: ModsCloud's 1024 px copy, else the next size down, else the original. */
export function shotOf(media) {
  const s = (media && media.media_details && media.media_details.sizes) || {};
  for (const k of ['large', 'medium_large', 'hitmag-featured', 'medium']) if (s[k] && s[k].source_url) return s[k].source_url;
  return (media && media.source_url) || null;
}

/** The statements that keep these liveries (new: published; seen before: its card updated, its stars, downloads and
 *  status as they are). */
export const UPSERT = `INSERT INTO liveries (steam_id, car, title, author, description, link, status,
      created, updated, published, source, source_id, shot_url) VALUES (?, ?, ?, ?, ?, ?, 'published', ?, ?, ?, ?, ?, ?)
    ON CONFLICT (source, source_id) WHERE source IS NOT NULL DO UPDATE SET car = excluded.car, title = excluded.title,
      author = excluded.author, description = excluded.description, link = excluded.link, shot_url = excluded.shot_url,
      updated = excluded.updated`;

/** UPSERT's values for one livery, in order. */
export const upsertValues = (r, now) => [MODSCLOUD.sender, r.car, r.title, r.author, r.description || null, r.link, now, now,
  r.published || now, r.source, r.sourceId, r.shot || null];

export function upserts(env, records, now) {
  return records.map((r) => env.DB.prepare(UPSERT).bind(...upsertValues(r, now)));
}

/** The newest posts (perRun) read from ModsCloud and kept. -> {seen, kept, skipped: [why]} or {error}. */
export async function syncModscloud(env, now = Date.now(), fetchFn = fetch, { page = 1, perPage = MODSCLOUD.perRun } = {}) {
  const get = async (path) => {
    const r = await fetchFn(`${MODSCLOUD.api}${path}`, { headers: { 'User-Agent': 'ACR-Daily (+https://acrdaily.com)', Accept: 'application/json' } });
    if (!r.ok) throw new Error(`ModsCloud ${r.status}`);
    return r.json();
  };
  try {
    const posts = await get(`/posts?categories=${MODSCLOUD.skins}&per_page=${perPage}&page=${page}` +
      '&_fields=id,date,date_gmt,link,title,content,tags,featured_media');
    if (!Array.isArray(posts) || !posts.length) return { seen: 0, kept: 0, skipped: [] };
    const mediaIds = [...new Set(posts.map((p) => p.featured_media).filter(Boolean))];
    const tagIds = [...new Set(posts.flatMap((p) => p.tags || []))];
    const [media, tags] = await Promise.all([
      mediaIds.length ? get(`/media?include=${mediaIds.join(',')}&per_page=100&_fields=id,source_url,media_details`) : [],
      tagIds.length ? get(`/tags?include=${tagIds.join(',')}&per_page=100&_fields=id,name`) : []]);
    const shots = new Map((media || []).map((m) => [m.id, shotOf(m)]));
    const tagName = new Map((tags || []).map((t) => [t.id, t.name]));
    const out = posts.map((p) => fromModscloud(p, { shot: shots.get(p.featured_media) || null,
      brands: (p.tags || []).map((t) => tagName.get(t) || '') }));
    const keep = out.filter((r) => !r.skip);
    if (keep.length) await env.DB.batch(upserts(env, keep, now));
    return { seen: posts.length, kept: keep.length, skipped: out.filter((r) => r.skip).map((r) => r.skip) };
  } catch (e) {
    return { error: String(e && e.message || e) };
  }
}
