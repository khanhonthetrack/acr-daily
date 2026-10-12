// The shop (credits, src/credits.js): looks a driver buys with credits and shows on the timing sheets and the live
// map: a colour (their name, and their dot on the live map), a badge by their name, a frame round their avatar on the
// live map. Bought once and kept; one of each kind worn at a time (table looks). Nothing here changes a time, and
// nothing is sold for money: credits are only ever earned (credits that could be bought would make the wager daily
// gambling).

import { clash, takeWhenStmts } from './credits.js';

export const KINDS = ['color', 'badge', 'frame'];

// colours readable on the dark pages (the live map's palette; ACR red stays for P1 and the active stage);
// a gradient's first colour is its dot on the live map
export const ITEMS = [
  { id: 'color:sky', kind: 'color', name: 'Sky', price: 250, color: '#5BA8FF' },
  { id: 'color:mint', kind: 'color', name: 'Mint', price: 250, color: '#4CD6C0' },
  { id: 'color:ice', kind: 'color', name: 'Ice', price: 250, color: '#3DD5F3' },
  { id: 'color:lime', kind: 'color', name: 'Lime', price: 250, color: '#7BE07B' },
  { id: 'color:amber', kind: 'color', name: 'Amber', price: 250, color: '#FF9F43' },
  { id: 'color:rose', kind: 'color', name: 'Rose', price: 250, color: '#FF7AB6' },
  { id: 'color:violet', kind: 'color', name: 'Violet', price: 250, color: '#B48CFF' },
  { id: 'color:gold', kind: 'color', name: 'Gold', price: 400, color: '#FFD60A' },
  { id: 'color:sunset', kind: 'color', name: 'Sunset', price: 900, color: '#FF9F43', grad: ['#FF9F43', '#FF7AB6'] },
  { id: 'color:glacier', kind: 'color', name: 'Glacier', price: 900, color: '#3DD5F3', grad: ['#3DD5F3', '#5BA8FF', '#B48CFF'] },
  { id: 'color:goldrush', kind: 'color', name: 'Gold rush', price: 1200, color: '#FFD60A', grad: ['#FFD60A', '#FF9F43'] },
  { id: 'color:aurora', kind: 'color', name: 'Aurora', price: 1500, color: '#7BE07B', grad: ['#7BE07B', '#3DD5F3', '#B48CFF'] },
  { id: 'badge:flag', kind: 'badge', name: 'Chequered flag', price: 200, badge: '🏁' },
  { id: 'badge:fire', kind: 'badge', name: 'Fire', price: 200, badge: '🔥' },
  { id: 'badge:bolt', kind: 'badge', name: 'Lightning', price: 200, badge: '⚡' },
  { id: 'badge:rocket', kind: 'badge', name: 'Rocket', price: 300, badge: '🚀' },
  { id: 'badge:fox', kind: 'badge', name: 'Fox', price: 300, badge: '🦊' },
  { id: 'badge:forest', kind: 'badge', name: 'Forest', price: 300, badge: '🌲' },
  { id: 'badge:snow', kind: 'badge', name: 'Snowflake', price: 300, badge: '❄️' },
  { id: 'badge:goat', kind: 'badge', name: 'Goat', price: 600, badge: '🐐' },
  { id: 'badge:crown', kind: 'badge', name: 'Crown', price: 800, badge: '👑' },
  { id: 'frame:neon', kind: 'frame', name: 'Neon', price: 600, ring: '#3DD5F3', width: 3 },
  { id: 'frame:bronze', kind: 'frame', name: 'Bronze', price: 400, ring: '#CD7F32', width: 3 },
  { id: 'frame:silver', kind: 'frame', name: 'Silver', price: 700, ring: '#D7DCE3', width: 3 },
  { id: 'frame:carbon', kind: 'frame', name: 'Carbon', price: 900, ring: '#8A8F98', width: 3, dash: true },
  { id: 'frame:gold', kind: 'frame', name: 'Gold', price: 1200, ring: '#FFD60A', width: 3 },
];
const BY_ID = new Map(ITEMS.map((i) => [i.id, i]));
export const itemOf = (id) => BY_ID.get(id) || null;

/** A driver's look as the pages and the app draw it, from what they wear (ids, a looks row or {color, badge,
 *  frame}) and their team (tag: {text, color}, src/drivers.js): {color, grad?, badge?, frame?: {color, width, dash?},
 *  tag?: {text, color}}, or null when there is nothing to show. */
export function lookOf(worn) {
  if (!worn) return null;
  const out = {};
  const c = itemOf(worn.color), b = itemOf(worn.badge), f = itemOf(worn.frame);
  if (c && c.kind === 'color') {
    out.color = c.color;
    if (c.grad) out.grad = c.grad;
  }
  if (b && b.kind === 'badge') out.badge = b.badge;
  if (f && f.kind === 'frame') out.frame = { color: f.ring, width: f.width, ...(f.dash ? { dash: true } : {}) };
  if (worn.tag && worn.tag.text) out.tag = { text: worn.tag.text, color: worn.tag.color, ...(worn.tag.fmt ? { fmt: worn.tag.fmt } : {}) };
  return Object.keys(out).length ? out : null;
}

/** SQL for a query's looks: LEFT JOIN this on the driver's steam_id (alias), select LOOK_COLS, then lookOfRow(row)
 *  reads them (their team's tag too: lkt). */
export const lookJoin = (sid) => `LEFT JOIN looks lk ON lk.steam_id = ${sid} LEFT JOIN team_members lkm ON lkm.steam_id = ${sid}
  LEFT JOIN teams lkt ON lkt.id = lkm.team_id`;
export const LOOK_COLS = 'lk.color AS look_color, lk.badge AS look_badge, lk.frame AS look_frame, lkt.tag AS look_tag, lkt.color AS look_tag_color, lkt.tag_fmt AS look_tag_fmt';
export const lookOfRow = (r) => lookOf(r && { color: r.look_color, badge: r.look_badge, frame: r.look_frame,
  tag: r.look_tag ? { text: r.look_tag, color: r.look_tag_color, fmt: r.look_tag_fmt || null } : null });
/** A row without its look columns (what lookOfRow read). */
export const unlooked = ({ look_color, look_badge, look_frame, look_tag, look_tag_color, look_tag_fmt, ...rest }) => rest;

/** What a driver wears: {color, badge, frame} (ids, null for nothing). */
async function wornBy(env, steamId) {
  const r = await env.DB.prepare('SELECT color, badge, frame FROM looks WHERE steam_id = ?').bind(steamId).first();
  return { color: (r && r.color) || null, badge: (r && r.badge) || null, frame: (r && r.frame) || null };
}

/** Wear an item (or nothing of that kind: item null). */
const wearStmt = (env, steamId, kind, item, now) => env.DB.prepare(
  `INSERT INTO looks (steam_id, ${kind}, updated) VALUES (?1, ?2, ?3)
   ON CONFLICT(steam_id) DO UPDATE SET ${kind} = ?2, updated = ?3`).bind(steamId, item, now);

/** GET /api/shop, POST /api/shop/buy {item}, POST /api/shop/wear {kind, item|null}. -> a Response, or null when the
 *  path is not one of them. lookChanged(): the copies to drop when a look changes (today's timing sheets). */
export async function shopApi(req, env, path, me, sameOrigin, now, { json, err, balanceOf, lookChanged }) {
  if (!path.startsWith('/api/shop')) return null;
  const post = req.method === 'POST';
  const on = !!env.CREDITS_FROM;
  if (path === '/api/shop' && !post) {
    const owned = me ? new Set((await env.DB.prepare('SELECT item FROM shop_owned WHERE steam_id = ?').bind(me.steam_id).all())
      .results.map((r) => r.item)) : new Set();
    return json({ enabled: on, signedIn: !!me, balance: me ? (await balanceOf(env, me.steam_id)).balance : null,
      worn: me ? await wornBy(env, me.steam_id) : null, items: ITEMS.map((i) => ({ ...i, owned: owned.has(i.id) })) });
  }
  if (!post) return err('not found', 404);
  if (!on) return err('the shop opens with credits', 409);
  if (!me) return err('sign in with Steam first', 401);
  if (me.banned) return err('this account is banned', 403);
  if (!sameOrigin) return err('refused: not from this site', 403);
  const b = await req.json().catch(() => ({})) || {};
  if (path === '/api/shop/buy') {                        // buy (once) and wear it straight away
    const it = itemOf(b.item);
    if (!it) return err('no such item', 404);
    const had = await env.DB.prepare('SELECT 1 AS x FROM shop_owned WHERE steam_id = ? AND item = ?').bind(me.steam_id, it.id).first();
    if (!had) {
      // the row and the payment together: the row only when the driver has the credits, the payment only with it
      try {
        await env.DB.batch([
          env.DB.prepare(`INSERT OR IGNORE INTO shop_owned (steam_id, item, price, bought) SELECT ?1, ?2, ?3, ?4
            WHERE (SELECT balance FROM credits WHERE steam_id = ?1) >= ?3`).bind(me.steam_id, it.id, it.price, now),
          ...takeWhenStmts(env, me.steam_id, it.price, 'shop', it.id, it.name, now,
            'EXISTS (SELECT 1 FROM shop_owned WHERE steam_id = ? AND item = ? AND bought = ?)', [me.steam_id, it.id, now]),
        ]);
      } catch (e) {
        if (!clash(e)) throw e;
      }
      const got = await env.DB.prepare('SELECT 1 AS x FROM shop_owned WHERE steam_id = ? AND item = ?').bind(me.steam_id, it.id).first();
      if (!got) return err(`${it.name} is ${it.price} credits: you have ${(await balanceOf(env, me.steam_id)).balance}`, 402);
    }
    await wearStmt(env, me.steam_id, it.kind, it.id, now).run();
    await lookChanged();
    return json({ owned: true, ...(had ? { already: true } : {}), worn: await wornBy(env, me.steam_id),
      balance: (await balanceOf(env, me.steam_id)).balance });
  }
  if (path === '/api/shop/wear') {                       // wear something bought, or take a kind off (item null)
    if (!KINDS.includes(b.kind)) return err('no such kind of look', 400);
    let id = null;
    if (b.item != null) {
      const it = itemOf(b.item);
      if (!it || it.kind !== b.kind) return err('no such item', 404);
      if (!await env.DB.prepare('SELECT 1 AS x FROM shop_owned WHERE steam_id = ? AND item = ?').bind(me.steam_id, it.id).first()) {
        return err(`buy ${it.name} first`, 403);
      }
      id = it.id;
    }
    await wearStmt(env, me.steam_id, b.kind, id, now).run();
    await lookChanged();
    return json({ worn: await wornBy(env, me.steam_id) });
  }
  return err('not found', 404);
}
