// env.DB as D1 has it (prepare / bind / first / all / run, batch all or nothing) on an in-memory SQLite with the full
// schema (schema.sql, node:sqlite), for tests of code that runs bulk SQL. count.queries: the calls to D1 (a batch is
// one): the free plan allows 50 a Worker invocation. D1's own limits too: at most 5 terms in a compound SELECT (SQLite
// allows 500; D1 refuses a 6th "UNION ALL" with "too many terms in compound SELECT", seen live 2026-10-12).
import { readFileSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';

export const D1_LIMITS = { compoundSelect: 5 };

export function fakeD1(vars = {}) {
  const db = new DatabaseSync(':memory:', { limits: D1_LIMITS });
  db.exec(readFileSync(new URL('../schema.sql', import.meta.url), 'utf8'));
  const count = { queries: 0 };
  const exec = (sql, args) => {
    const st = db.prepare(sql);
    const a = args.map((x) => (x instanceof ArrayBuffer ? new Uint8Array(x) : x));
    if (st.columns().length) return { results: st.all(...a), meta: { changes: 0 } };
    const r = st.run(...a);
    return { results: [], meta: { changes: Number(r.changes), last_row_id: Number(r.lastInsertRowid) } };
  };
  const prepare = (sql) => {
    const mk = (args) => ({ sql, args, bind: (...a) => mk(a),
      first: async () => { count.queries++; return exec(sql, args).results[0] || null; },
      all: async () => { count.queries++; return exec(sql, args); },
      run: async () => { count.queries++; return exec(sql, args); } });
    return mk([]);
  };
  const batch = async (stmts) => {
    count.queries++;
    db.exec('BEGIN');
    try {
      const out = stmts.map((s) => exec(s.sql, s.args));
      db.exec('COMMIT');
      return out;
    } catch (e) {
      db.exec('ROLLBACK');
      throw e;
    }
  };
  return { env: { DB: { prepare, batch }, ...vars }, db, count };
}

/** A Steam id for test driver i. */
export const sid = (i) => String(76561198000000000n + BigInt(i));
