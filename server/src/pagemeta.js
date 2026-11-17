// What a link to a page shows where it is shared (Discord, WhatsApp, iMessage...): the page's own title, a line on it
// and a picture (Open Graph's and Twitter's tags), and whether the page is there at all.
//
// The pages are shells the API fills in the browser, so a shared link (its preview made without running the page) said
// "Event · ACR Daily" and nothing more, and an event that doesn't exist answered 200 with empty sections (a UI review,
// Nov 2026). Now an event's, a championship's, a cup's, a driver's and a team's page read their row first (one query):
// none, a 404 page (notFoundPage); else the page's <title>, and its tags. A private championship (and its events)
// keeps a plain title and no line, as the API keeps them from whoever isn't in it.
import { t, tn } from './i18n.js';

const esc = (x) => String(x == null ? '' : x).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const ICON = '/brand/acr-daily-icon-512.png';

/** The <head>'s tags for a page: title (plain text), description, image (a path or an address), large (a wide picture:
 * a banner), url (its own address). site: where the site is (images and the page's url are whole addresses). */
export function metaTags({ title = 'ACR Daily', description = '', image = '', large = false, url = '', site = '' } = {}) {
  const whole = (p) => (!p ? '' : /^https?:\/\//.test(p) ? p : site.replace(/\/+$/, '') + p);
  const img = whole(image || ICON);
  return [
    description ? `<meta name="description" content="${esc(description)}">` : '',
    '<meta property="og:site_name" content="ACR Daily">',
    '<meta property="og:type" content="website">',
    `<meta property="og:title" content="${esc(title)}">`,
    description ? `<meta property="og:description" content="${esc(description)}">` : '',
    img ? `<meta property="og:image" content="${esc(img)}">` : '',
    url ? `<meta property="og:url" content="${esc(whole(url))}">` : '',
    `<meta name="twitter:card" content="${large ? 'summary_large_image' : 'summary'}">`,
    '<meta name="theme-color" content="#0A0A0B">',
  ].filter(Boolean).join('\n');
}

/** A page's row (null: there is none). kind: event / league / cup / driver / team. */
export async function lookup(env, kind, id) {
  const q = {
    event: `SELECT e.id, e.name, e.rally, e.car, e.car_class, e.car_classes, e.stages, e.opens, e.closes, l.id AS league_id,
      l.name AS league_name, l.kind AS league_kind, l.public, l.banner FROM league_events e JOIN leagues l ON l.id = e.league_id
      WHERE e.id = ?`,
    league: 'SELECT id, name, about, kind, public, banner FROM leagues WHERE id = ?',
    cup: 'SELECT id, name, about, status, size, fee, prize, official FROM cups WHERE id = ?',
    driver: 'SELECT steam_id, name, avatar, country, banned FROM players WHERE steam_id = ?',
    team: 'SELECT id, name, tag FROM teams WHERE id = ?',
  }[kind];
  if (!q) return null;
  try {
    return await env.DB.prepare(q).bind(id).first();
  } catch (e) {
    console.error('page meta', kind, e);
    return undefined;            // (the database didn't answer: the page as before, not a 404)
  }
}

// (no Intl on the server: its first use costs a fresh Worker ~14 ms of CPU, more than the free plan's 10; the ISO day)
const day = (ms) => new Date(ms).toISOString().slice(0, 10);
const short = (s, n = 200) => { s = String(s || '').replace(/\s+/g, ' ').trim(); return s.length > n ? s.slice(0, n - 1) + '…' : s; };

/** {title, description, image, large, url} for a page's row, in the page's language (inside inLang). */
export function describe(kind, row, now = Date.now()) {
  if (!row) return {};
  if (kind === 'event') {
    if (!row.public) return { url: `/e/${row.id}` };          // (a private championship's, a 1V1's, a cup's: not told)
    let stages = 0;
    try { stages = JSON.parse(row.stages || '[]').length; } catch { stages = 0; }
    let classes = [];
    try { classes = JSON.parse(row.car_classes || 'null') || []; } catch { classes = []; }
    const what = row.league_kind === 'event' ? t('Rally') : row.league_name;
    const when = now < row.opens ? `${t('Opens')} ${day(row.opens)}` : now < row.closes ? `${t('Closes')} ${day(row.closes)}`
      : t('Finished');
    const bits = [what, row.rally, row.car || (classes.length ? classes.join(', ') : row.car_class),
      tn('{0} stage', '{0} stages', stages, stages), when];
    return { title: row.name, description: bits.filter(Boolean).join(' · '), url: `/e/${row.id}`,
      image: row.banner ? `/l/${row.league_id}/banner?v=${row.banner}` : '', large: !!row.banner };
  }
  if (kind === 'league') {
    if (!row.public) return { url: `/l/${row.id}` };
    return { title: row.name, description: short(row.about) || t('Championship'), url: `/l/${row.id}`,
      image: row.banner ? `/l/${row.id}/banner?v=${row.banner}` : '', large: !!row.banner };
  }
  if (kind === 'cup') return { title: row.name, description: short(row.about) || t('Cup'), url: `/cup/${row.id}` };
  if (kind === 'driver') {
    return { title: row.name, description: t('Driver'), url: `/d/${row.steam_id}`,
      image: row.avatar && /^https?:\/\//.test(row.avatar) ? row.avatar : '' };
  }
  if (kind === 'team') return { title: `[${row.tag}] ${row.name}`, description: t('Team'), url: `/t/${row.id}` };
  return {};
}

export { esc as escMeta };
