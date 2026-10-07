// Built results kept in the database (table cache): the boards, the week and the stage stats are asked for far more
// often than they change (every open app and website tab), and building them reads every run of the day. A copy is
// used until its time is up or something it is built from changes (dropCached: a run, a report, an admin action).

const MAX_BODY = 1_500_000;   // D1 rows hold 2 MB at most; anything bigger is just built every time

/** The value under key if it is still good, else build() it and keep it for ttlMs. */
export async function cached(env, key, ttlMs, build) {
  const now = Date.now();
  const hit = await env.DB.prepare('SELECT body FROM cache WHERE key = ? AND expires > ?').bind(key, now).first();
  if (hit) return JSON.parse(hit.body);
  const value = await build();
  const body = JSON.stringify(value);
  if (body.length <= MAX_BODY) {
    await env.DB.prepare(`INSERT INTO cache (key, body, expires) VALUES (?, ?, ?)
                           ON CONFLICT (key) DO UPDATE SET body = excluded.body, expires = excluded.expires`)
      .bind(key, body, now + ttlMs).run()
      .catch((e) => console.error('cache', key, e));   // a copy that could not be kept is no reason to fail
  }
  return value;
}

/** Forget these copies (keys), or every copy (no keys). */
export async function dropCached(env, keys = null) {
  if (!keys) return env.DB.prepare('DELETE FROM cache').run();
  if (!keys.length) return null;
  return env.DB.prepare(`DELETE FROM cache WHERE key IN (${keys.map(() => '?').join(',')})`).bind(...keys).run();
}

/** Copies past their time (the cron, hourly). */
export async function dropExpired(env, now = Date.now()) {
  return env.DB.prepare('DELETE FROM cache WHERE expires < ?').bind(now).run();
}
