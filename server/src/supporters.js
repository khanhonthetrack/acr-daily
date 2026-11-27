// Supporters on Buy Me a Coffee (buymeacoffee.com/acrdaily): its webhook (POST /api/bmc/webhook, signed with the
// webhook's signing secret, the Worker secret BMC_WEBHOOK_SECRET) keeps the list, GET /api/supporters gives the
// current supporters for the app's thank-you bar (client/acr_daily/supporters.py).
// Current = members and monthly supporters while their support is on (cancelled or paused: off the list), and one-time
// coffees / shop buys for 30 days. A refund takes the row away. Only the name the supporter shows on Buy Me a Coffee is
// kept (never their e-mail or note); a name the word filter catches, or none, shows as "Someone".
import { badWord } from './wordfilter.js';

export const BMC_URL = 'https://buymeacoffee.com/acrdaily';
export const ONE_TIME_DAYS = 30;
const MAX_LIST = 50;
const utf8 = new TextEncoder();

const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');

/** The x-signature-sha256 header checked: HMAC-SHA256 of the raw body with the signing secret, hex. */
export async function signatureOk(raw, secret, sig) {
  secret = String(secret || '').trim();      // (a pasted secret often carries a stray newline: every delivery refused)
  if (!secret || !sig) return false;
  const key = await crypto.subtle.importKey('raw', utf8.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const want = hex(await crypto.subtle.sign('HMAC', key, utf8.encode(raw)));
  const got = String(sig).trim().toLowerCase().replace(/^sha256=/, '');
  if (got.length !== want.length) return false;
  let d = 0;
  for (let i = 0; i < want.length; i++) d |= want.charCodeAt(i) ^ got.charCodeAt(i);
  return d === 0;
}

/** The name shown: what Buy Me a Coffee shows, short, "Someone" for none or a bad word. */
export function shownName(n) {
  const s = String(n == null ? '' : n).replace(/[\u0000-\u001f\u007f]/g, '').replace(/\s+/g, ' ').trim().slice(0, 32);
  if (!s || /^someone$/i.test(s) || badWord(s)) return 'Someone';
  return s;
}

const secs = (t) => (Number.isFinite(+t) && +t > 0 ? Math.floor(+t) : null);

/** What one event does to the list: { put: row } | { drop: id } | null (an event the list doesn't use). */
export function change(ev) {
  const t = String(ev?.type || '');
  const d = ev?.data || {};
  if (d.id == null) return null;
  const [obj, what] = t.split('.');
  const kind = { donation: 'coffee', extra_purchase: 'shop', membership: 'member', recurring_donation: 'monthly' }[obj];
  if (!kind) return null;
  const id = `${obj}:${d.id}`;
  if (what === 'refunded') return { drop: id };
  const row = { id, kind, name: shownName(d.supporter_name), coffees: Math.max(0, Math.floor(+d.coffee_count || 0)) || null,
    level: kind === 'member' ? String(d.membership_level_name || '').slice(0, 40) || null : null,
    at: secs(d.created_at) || secs(d.started_at) || secs(ev.created) || Math.floor(Date.now() / 1000), active: 1 };
  if (kind === 'coffee' || kind === 'shop') {
    if (what !== 'created' || d.status === 'refunded' || d.refunded === 'true') return null;
    return { put: row };
  }
  // member / monthly: started, updated, cancelled, paused
  const off = what === 'cancelled' || what === 'paused' || d.status === 'canceled' || d.status === 'paused'
    || d.canceled === 'true' || d.paused === 'true' || d.paused === true;
  if (!['started', 'updated', 'cancelled', 'paused'].includes(what)) return null;
  return { put: { ...row, active: off ? 0 : 1 } };
}

/** POST /api/bmc/webhook. Test events from the dashboard are answered but not kept. */
export async function bmcWebhook(req, env) {
  const raw = await req.text();
  if (!env.BMC_WEBHOOK_SECRET) return new Response('webhook not set up', { status: 503 });
  if (!(await signatureOk(raw, env.BMC_WEBHOOK_SECRET, req.headers.get('x-signature-sha256')))) {
    return new Response('bad signature', { status: 401 });
  }
  let ev;
  try {
    ev = JSON.parse(raw);
  } catch {
    return new Response('bad body', { status: 400 });
  }
  if (ev.live_mode === false) return Response.json({ ok: true, test: true });
  const c = change(ev);
  if (c?.drop) await env.DB.prepare('DELETE FROM supporters WHERE id = ?').bind(c.drop).run();
  if (c?.put) {
    const r = c.put;
    await env.DB.prepare(`INSERT INTO supporters (id, kind, name, coffees, level, active, at, updated) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT (id) DO UPDATE SET name = excluded.name, coffees = excluded.coffees, level = excluded.level,
      active = excluded.active, updated = excluded.updated`)
      .bind(r.id, r.kind, r.name, r.coffees, r.level, r.active, r.at, Date.now()).run();
  }
  return Response.json({ ok: true });
}

/** The current supporters, members and monthly first, then the newest coffees. */
export async function currentSupporters(env, now = Date.now()) {
  const since = Math.floor(now / 1000) - ONE_TIME_DAYS * 86400;
  const { results } = await env.DB.prepare(`SELECT kind, name, coffees, level, at FROM supporters
    WHERE (kind IN ('member', 'monthly') AND active = 1) OR (kind IN ('coffee', 'shop') AND at >= ?)
    ORDER BY CASE WHEN kind IN ('member', 'monthly') THEN 0 ELSE 1 END, at DESC LIMIT ?`).bind(since, MAX_LIST).all();
  return { url: BMC_URL, supporters: results.map((r) => ({ name: r.name, kind: r.kind, coffees: r.coffees || undefined,
    level: r.level || undefined })) };
}

// ------------------------------------------------------------------ the admin's (src/adminpage.js, Supporters)
// The webhook never sends what came before it was set up: the admin puts past supporters in by hand (the user, 27 Nov
// 2026), and can take any row off. Kinds by hand: coffee (shown ONE_TIME_DAYS from its date) or member (until taken off).

/** GET /api/admin/supporters: every row, newest first, with whether the app shows it now. */
export async function adminSupporters(env, now = Date.now()) {
  const since = Math.floor(now / 1000) - ONE_TIME_DAYS * 86400;
  const { results } = await env.DB.prepare(`SELECT id, kind, name, coffees, level, active, at FROM supporters
    ORDER BY at DESC LIMIT 200`).all();
  return { supporters: results.map((r) => ({ id: r.id, kind: r.kind, name: r.name, coffees: r.coffees || null, level: r.level || null,
    at: r.at * 1000, byHand: r.id.startsWith('manual:'),
    shown: (r.kind === 'member' || r.kind === 'monthly') ? r.active === 1 : r.at >= since })) };
}

/** POST /api/admin/supporters {name, kind: coffee | member, coffees?, level?, date?: YYYY-MM-DD (coffee: given that day)}. */
export async function adminSupporterAdd(env, b, now = Date.now()) {
  const name = shownName(b?.name);
  if (name === 'Someone' && !String(b?.name || '').trim()) return { error: 'admin: a name to show (or "Someone")' };
  const kind = b?.kind === 'member' ? 'member' : b?.kind === 'coffee' ? 'coffee' : null;
  if (!kind) return { error: 'admin: kind is coffee or member' };
  let at = Math.floor(now / 1000);
  if (b?.date) {
    const t = Date.parse(String(b.date) + 'T12:00:00Z');
    if (!Number.isFinite(t) || t > now + 86400000) return { error: 'admin: the date as YYYY-MM-DD, not ahead' };
    at = Math.floor(t / 1000);
  }
  const coffees = Math.max(0, Math.min(1000, Math.floor(+b?.coffees || 0))) || null;
  const level = kind === 'member' ? String(b?.level || '').trim().slice(0, 40) || null : null;
  const id = `manual:${crypto.randomUUID().slice(0, 8)}`;
  await env.DB.prepare(`INSERT INTO supporters (id, kind, name, coffees, level, active, at, updated) VALUES (?, ?, ?, ?, ?, 1, ?, ?)`)
    .bind(id, kind, name, coffees, level, at, now).run();
  return { ok: true, id, name };
}

/** POST /api/admin/supporters/<id>/remove: off the list for good (a webhook's row comes back only with a new event). */
export async function adminSupporterRemove(env, id) {
  const r = await env.DB.prepare('DELETE FROM supporters WHERE id = ?').bind(String(id)).run();
  return r.meta.changes ? { ok: true } : { error: 'admin: no such supporter' };
}
