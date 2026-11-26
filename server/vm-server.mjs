// Node.js 24+ standalone Primary / Edge server for ACR Daily on VMs / Docker.
//
// Roles (ROLE env var):
// - ROLE=primary (default, e.g. acr-eu):
//     Runs unmodified Cloudflare Worker (src/index.js) on node:http + node:sqlite (WAL),
//     filesystem-backed R2 traces, in-process 5-minute cron, local live/relay.py mesh node,
//     and off-thread HMAC-signed continuous shadow backup (DB + traces) to Raspberry Pi.
// - ROLE=edge (e.g. acr-uk, acr-jp):
//     Terminates /live WebSocket upgrades on the local regional live/relay.py mesh node (~10 ms),
//     answers /healthz and /api/endpoints locally (with cached Primary + local relay health),
//     caches strictly public read-only GET endpoints in memory for short TTLs, and forwards all
//     writes/auth/dynamic requests over persistent keep-alive connections to PRIMARY_URL.

import { createHash, createHmac, randomBytes } from 'node:crypto';
import {
  createReadStream,
  createWriteStream,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  renameSync,
  rmSync,
  unlinkSync,
  writeFileSync,
} from 'node:fs';
import { open as openFileAsync, readFile as readFileAsync } from 'node:fs/promises';
import http from 'node:http';
import https from 'node:https';
import net from 'node:net';
import { dirname, join, resolve, sep } from 'node:path';
import { spawn } from 'node:child_process';
import { DatabaseSync } from 'node:sqlite';
import { pipeline } from 'node:stream/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { Worker as ThreadWorker } from 'node:worker_threads';
import { createGunzip } from 'node:zlib';

import worker, { scheduleAhead } from './src/index.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const MAX_REQ_BYTES = 6 * 1024 * 1024;

export function deriveStandbyKey(adminKey) {
  return createHash('sha256').update(`standby-sync|${String(adminKey || '').trim()}`, 'utf8').digest();
}

export function deriveLiveKeyHex(adminKey) {
  return createHash('sha256').update(`live-relay|${String(adminKey || '').trim()}`, 'utf8').digest('hex');
}

export function signStandbyRequest(standbyKey, method, pathname, tsSec, bodyBytes, nonceHex = randomBytes(12).toString('hex')) {
  const bodyHash = createHash('sha256').update(bodyBytes).digest('hex');
  const msg = `${method.toUpperCase()}|${pathname}|${tsSec}|${nonceHex}|${bodyHash}`;
  const sig = createHmac('sha256', standbyKey).update(msg, 'utf8').digest('hex');
  return { ts: String(tsSec), nonce: nonceHex, sha256: bodyHash, sig };
}

function loadWranglerVars(overrides = {}) {
  const vars = {};
  try {
    const toml = readFileSync(join(HERE, 'wrangler.toml'), 'utf8');
    const varsBlock = toml.split(/^\[vars\]/m)[1] || '';
    for (const line of varsBlock.split(/\r?\n/)) {
      if (/^\s*\[/.test(line)) break;
      const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*"([^"]*)"/);
      if (m) vars[m[1]] = m[2];
    }
  } catch (e) {
    console.error('wrangler.toml parse warning:', e.message);
  }
  for (const [k, v] of Object.entries(process.env)) {
    if (v !== undefined) vars[k] = v;
  }
  for (const [k, v] of Object.entries(overrides)) {
    if (v !== undefined) vars[k] = v;
  }
  return vars;
}

// Ignore ephemeral live-map position tables so 5s stage pings don't trigger full DB standby pushes.
export function isDurableMutationSql(sql) {
  const s = String(sql || '').trim();
  if (/^(?:SELECT|PRAGMA|EXPLAIN|WITH\b[\s\S]*?\bSELECT)\b/i.test(s) && !/\b(?:INSERT|UPDATE|DELETE|REPLACE)\b/i.test(s)) {
    return false;
  }
  if (/^(?:INSERT(?:\s+OR\s+\w+)?\s+INTO|UPDATE|DELETE\s+FROM|REPLACE\s+INTO)\s+(?:live|event_live|tt_live|casual_signals)\b/i.test(s)) {
    return false;
  }
  return /\b(?:INSERT|UPDATE|DELETE|REPLACE|CREATE|ALTER|DROP)\b/i.test(s);
}

export function openD1Database(dbPath) {
  if (dbPath !== ':memory:') {
    mkdirSync(dirname(dbPath), { recursive: true });
  }
  const db = new DatabaseSync(dbPath);
  db.exec('PRAGMA journal_mode = WAL;');
  db.exec('PRAGMA synchronous = NORMAL;');
  db.exec('PRAGMA foreign_keys = ON;');
  db.exec('PRAGMA busy_timeout = 5000;');

  const hadPlayers = !!db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name='players'").get();
  db.exec(readFileSync(join(HERE, 'schema.sql'), 'utf8'));

  db.exec('CREATE TABLE IF NOT EXISTS _migrations (name TEXT PRIMARY KEY, applied INTEGER NOT NULL);');
  db.exec('CREATE TABLE IF NOT EXISTS _standby_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);');

  const curLin = db.prepare("SELECT value FROM _standby_meta WHERE key = 'lineage_id'").get();
  if (!curLin) {
    db.prepare("INSERT INTO _standby_meta (key, value) VALUES ('lineage_id', ?)").run(randomBytes(16).toString('hex'));
    db.prepare("INSERT OR IGNORE INTO _standby_meta (key, value) VALUES ('sync_seq', '0')").run();
  }

  const migDir = join(HERE, 'migrations');
  if (existsSync(migDir)) {
    const files = readdirSync(migDir).filter((f) => f.endsWith('.sql')).sort();
    const checkMig = db.prepare('SELECT 1 FROM _migrations WHERE name = ?');
    const markMig = db.prepare('INSERT OR IGNORE INTO _migrations (name, applied) VALUES (?, ?)');
    for (const file of files) {
      if (checkMig.get(file)) continue;
      if (hadPlayers) {
        const sql = readFileSync(join(migDir, file), 'utf8');
        try {
          db.exec(sql);
        } catch (e) {
          if (!/duplicate column name|already exists/i.test(String(e.message))) {
            throw new Error(`Migration ${file} failed: ${e.message}`);
          }
        }
      }
      markMig.run(file, Date.now());
    }
  }

  const initSeqRow = db.prepare("SELECT value FROM _standby_meta WHERE key = 'sync_seq'").get();
  let writeSeq = Math.max(1, Number(initSeqRow ? initSeqRow.value : 0) + 1);
  const bumpMetaSeq = db.prepare(
    "INSERT INTO _standby_meta (key, value) VALUES ('sync_seq', ?1) ON CONFLICT(key) DO UPDATE SET value = ?1",
  );

  const normArg = (x) => {
    if (x === undefined) return null;
    if (x instanceof ArrayBuffer) return new Uint8Array(x);
    return x;
  };

  const exec = (sql, args) => {
    const st = db.prepare(sql);
    const a = args.map(normArg);
    const mutates = isDurableMutationSql(sql);
    if (st.columns().length) {
      const results = st.all(...a);
      if (mutates) writeSeq++;
      return { results, meta: { changes: 0 } };
    }
    const r = st.run(...a);
    if (mutates && Number(r.changes) > 0) writeSeq++;
    return { results: [], meta: { changes: Number(r.changes), last_row_id: Number(r.lastInsertRowid) } };
  };

  const prepare = (sql) => {
    const mk = (args) => ({
      sql,
      args,
      bind: (...a) => mk(a),
      first: async (col) => {
        const row = exec(sql, args).results[0] || null;
        return row && col ? row[col] : row;
      },
      all: async () => exec(sql, args),
      run: async () => exec(sql, args),
    });
    return mk([]);
  };

  const batch = async (stmts) => {
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

  return {
    db,
    d1: { prepare, batch },
    getWriteSeq: () => writeSeq,
    recordSyncSeq: (seq) => bumpMetaSeq.run(String(seq)),
  };
}

export function openTracesBucket(tracesDir, onPut = null) {
  if (!tracesDir) return undefined;
  const root = resolve(tracesDir);
  mkdirSync(root, { recursive: true });

  const safePath = (key) => {
    const clean = String(key || '').replace(/^\/+/, '');
    if (!/^[a-zA-Z0-9_./-]+$/.test(clean) || clean.includes('..')) {
      throw new Error(`Invalid trace key: ${key}`);
    }
    const dst = resolve(root, clean);
    if (dst !== root && !dst.startsWith(root + sep)) {
      throw new Error(`Trace path escaped root: ${key}`);
    }
    return { clean, dst };
  };

  return {
    root,
    async put(key, data) {
      const { clean, dst } = safePath(key);
      mkdirSync(dirname(dst), { recursive: true });
      const bytes = data instanceof Uint8Array ? data : new Uint8Array(await new Response(data).arrayBuffer());
      const tmp = `${dst}.tmp.${process.pid}.${Date.now()}.${Math.random().toString(36).slice(2, 8)}`;
      writeFileSync(tmp, bytes);
      renameSync(tmp, dst);
      if (onPut) {
        try { onPut(clean, dst); } catch (e) { console.error('trace onPut hook error:', e); }
      }
    },
    async get(key) {
      const { dst } = safePath(key);
      if (!existsSync(dst)) return null;
      const bytes = new Uint8Array(readFileSync(dst));
      return { body: bytes };
    },
    async delete(keys) {
      const list = Array.isArray(keys) ? keys : [keys];
      for (const k of list) {
        try {
          const { dst } = safePath(k);
          if (existsSync(dst)) unlinkSync(dst);
        } catch { /* ignore */ }
      }
    },
  };
}

function installDefaultCache() {
  const store = new Map();
  globalThis.caches = {
    default: {
      async match(req) {
        const key = typeof req === 'string' ? req : req.url;
        const hit = store.get(key);
        if (!hit) return undefined;
        if (Date.now() > hit.expires) {
          store.delete(key);
          return undefined;
        }
        return new Response(hit.body, { status: hit.status, headers: hit.headers });
      },
      async put(req, res) {
        const key = typeof req === 'string' ? req : req.url;
        const cc = res.headers.get('Cache-Control') || '';
        const m = cc.match(/max-age=(\d+)/);
        const ttlMs = (m ? Number(m[1]) : 300) * 1000;
        const body = new Uint8Array(await res.clone().arrayBuffer());
        if (store.size >= 500) {
          const firstKey = store.keys().next().value;
          if (firstKey !== undefined) store.delete(firstKey);
        }
        store.set(key, {
          body,
          status: res.status,
          headers: Object.fromEntries(res.headers.entries()),
          expires: Date.now() + ttlMs,
        });
      },
    },
  };
}

// Off-event-loop SQLite VACUUM INTO + streaming gzip in a dedicated worker_thread so Primary HTTP, WS & RAM stay flat!
function snapshotDatabaseOffThread(dbPath, snapPath, gzPath) {
  const workerCode = `
    const { createHash } = require('node:crypto');
    const { createReadStream, createWriteStream, rmSync } = require('node:fs');
    const { DatabaseSync } = require('node:sqlite');
    const { pipeline } = require('node:stream/promises');
    const { Transform } = require('node:stream');
    const { createGzip } = require('node:zlib');
    const { parentPort, workerData } = require('node:worker_threads');

    (async () => {
      const { dbPath, snapPath, gzPath } = workerData;
      const src = new DatabaseSync(dbPath, { open: true });
      try {
        src.exec('PRAGMA busy_timeout = 5000;');
        rmSync(snapPath, { force: true });
        rmSync(gzPath, { force: true });
        const escaped = snapPath.replace(/'/g, "''");
        src.exec("VACUUM INTO '" + escaped + "'");
      } finally {
        src.close();
      }
      const hasher = createHash('sha256');
      let size = 0;
      const meter = new Transform({
        transform(chunk, _enc, cb) {
          hasher.update(chunk);
          size += chunk.byteLength;
          cb(null, chunk);
        },
      });
      try {
        await pipeline(createReadStream(snapPath), createGzip({ level: 6 }), meter, createWriteStream(gzPath));
      } finally {
        rmSync(snapPath, { force: true });
      }
      parentPort.postMessage({ size, sha256: hasher.digest('hex') });
    })().catch((err) => {
      setImmediate(() => { throw err; });
    });
  `;
  return new Promise((resolveMeta, rejectMeta) => {
    const w = new ThreadWorker(workerCode, { eval: true, workerData: { dbPath, snapPath, gzPath } });
    let settled = false;
    w.once('message', (meta) => {
      settled = true;
      resolveMeta(meta);
    });
    w.once('error', (err) => {
      if (!settled) {
        settled = true;
        rejectMeta(err);
      }
    });
    w.once('exit', (code) => {
      if (!settled && code !== 0) {
        settled = true;
        rejectMeta(new Error(`Snapshot worker exited with code ${code}`));
      }
    });
  });
}

function quoteSqlIdent(name) {
  const s = String(name || '');
  if (!/^[A-Za-z0-9_]+$/.test(s)) throw new Error(`Unsafe SQL identifier: ${s}`);
  return `"${s}"`;
}

export function applyDeltaSqlite(db, deltaPath) {
  const verify = new DatabaseSync(deltaPath, { open: true });
  let meta = {};
  try {
    const ok = verify.prepare('PRAGMA quick_check').get();
    if (!ok || Object.values(ok)[0] !== 'ok') throw new Error('Delta SQLite failed quick_check');
    const hasMeta = verify.prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name='_delta_meta'").get();
    if (!hasMeta) throw new Error('Delta SQLite missing _delta_meta table');
    for (const row of verify.prepare('SELECT key, value FROM _delta_meta').all()) {
      meta[row.key] = row.value;
    }
  } finally {
    verify.close();
  }

  const replaceTables = JSON.parse(meta.replace_tables || '[]');
  const upsertTables = JSON.parse(meta.upsert_tables || '[]');
  const baseRunId = Number(meta.base_run_id || 0);
  const baseTtRunId = Number(meta.base_tt_run_id || 0);
  const authoritative = meta.authoritative_cutover === '1';
  if (baseRunId > 0) {
    const localMaxRun = Number(db.prepare('SELECT COALESCE(MAX(id), 0) AS m FROM runs').get()?.m || 0);
    if (localMaxRun < baseRunId) {
      throw new Error(`Cannot apply delta (base_run_id=${baseRunId}) before base DB (local max_run_id=${localMaxRun})`);
    }
  }
  const escapedPath = String(deltaPath).replace(/'/g, "''");

  db.exec('PRAGMA foreign_keys = OFF;');
  db.exec(`ATTACH DATABASE '${escapedPath}' AS delta_db`);
  try {
    db.exec('BEGIN IMMEDIATE');
    try {
      for (const tbl of [...replaceTables, ...upsertTables]) {
        quoteSqlIdent(tbl);
        const hasMain = db.prepare("SELECT 1 FROM main.sqlite_master WHERE type='table' AND name = ?").get(tbl);
        if (!hasMain) {
          const ddl = db.prepare("SELECT sql FROM delta_db.sqlite_master WHERE type='table' AND name = ?").get(tbl);
          if (ddl && ddl.sql) db.exec(ddl.sql);
        }
      }

      for (const tbl of replaceTables) {
        const qTbl = quoteSqlIdent(tbl);
        const mainCols = new Set(db.prepare(`PRAGMA main.table_info(${qTbl})`).all().map((r) => r.name));
        const deltaCols = db.prepare(`PRAGMA delta_db.table_info(${qTbl})`).all().map((r) => r.name);
        const shared = deltaCols.filter((c) => mainCols.has(c));
        if (!shared.length) continue;
        const colSql = shared.map(quoteSqlIdent).join(', ');
        db.exec(`DELETE FROM main.${qTbl}`);
        db.exec(`INSERT INTO main.${qTbl} (${colSql}) SELECT ${colSql} FROM delta_db.${qTbl}`);
      }

      if (authoritative && baseRunId > 0) {
        db.prepare('DELETE FROM main.runs WHERE id > ?').run(baseRunId);
      }
      if (authoritative && baseTtRunId > 0) {
        const hasTt = db.prepare("SELECT 1 FROM main.sqlite_master WHERE type='table' AND name='tt_runs'").get();
        if (hasTt) db.prepare('DELETE FROM main.tt_runs WHERE id > ?').run(baseTtRunId);
      }

      for (const tbl of upsertTables) {
        const qTbl = quoteSqlIdent(tbl);
        const mainCols = new Set(db.prepare(`PRAGMA main.table_info(${qTbl})`).all().map((r) => r.name));
        const deltaCols = db.prepare(`PRAGMA delta_db.table_info(${qTbl})`).all().map((r) => r.name);
        const shared = deltaCols.filter((c) => mainCols.has(c));
        if (!shared.length) continue;
        const colSql = shared.map(quoteSqlIdent).join(', ');
        db.exec(`INSERT OR REPLACE INTO main.${qTbl} (${colSql}) SELECT ${colSql} FROM delta_db.${qTbl}`);
      }

      const hasRpatch = db.prepare(
        "SELECT 1 FROM delta_db.sqlite_master WHERE type='table' AND name='_delta_runs_patches'",
      ).get();
      if (hasRpatch) {
        const updRun = db.prepare('UPDATE main.runs SET status = ?, reason = ?, flags = ? WHERE id = ?');
        for (const p of db.prepare('SELECT id, status, reason, flags FROM delta_db._delta_runs_patches').all()) {
          updRun.run(p.status ?? null, p.reason ?? null, p.flags ?? null, p.id);
        }
      }

      const hasTpatch = db.prepare(
        "SELECT 1 FROM delta_db.sqlite_master WHERE type='table' AND name='_delta_tt_runs_patches'",
      ).get();
      if (hasTpatch) {
        const updTt = db.prepare('UPDATE main.tt_runs SET status = ?, reason = ? WHERE id = ?');
        for (const p of db.prepare('SELECT id, status, reason FROM delta_db._delta_tt_runs_patches').all()) {
          updTt.run(p.status ?? null, p.reason ?? null, p.id);
        }
      }

      const hasCache = db.prepare("SELECT 1 FROM main.sqlite_master WHERE type='table' AND name='cache'").get();
      if (hasCache) db.exec('DELETE FROM main.cache');

      const upsertMeta = db.prepare(
        'INSERT INTO main._standby_meta (key, value) VALUES (?1, ?2) ON CONFLICT(key) DO UPDATE SET value = ?2',
      );
      if (meta.lineage_id) upsertMeta.run('lineage_id', String(meta.lineage_id));
      if (meta.delta_id) upsertMeta.run('applied_delta_id', String(meta.delta_id));

      db.exec('COMMIT');
    } catch (err) {
      try { db.exec('ROLLBACK'); } catch { /* ignore */ }
      throw err;
    }
  } finally {
    try { db.exec('DETACH DATABASE delta_db'); } catch { /* ignore */ }
    db.exec('PRAGMA foreign_keys = ON;');
  }
  return meta;
}

function resolveStandbyKey(explicitStandbyKeyHex, adminKey) {
  const clean = String(explicitStandbyKeyHex || '').trim();
  if (/^[0-9a-f]{64}$/i.test(clean)) return Buffer.from(clean.toLowerCase(), 'hex');
  if (!adminKey || adminKey === 'dev') return null;
  return deriveStandbyKey(adminKey);
}

function normalizeStandbyBaseUrl(baseUrl) {
  return String(baseUrl || '').trim().replace(/\/+$/, '').replace(/\/internal\/standby$/, '');
}

async function fetchSignedStandby(baseUrl, standbyKey, subpath, timeoutMs = 20_000, extraHeaders = {}) {
  const target = new URL(normalizeStandbyBaseUrl(baseUrl) + subpath);
  const tsSec = Math.floor(Date.now() / 1000);
  const { ts, nonce, sha256, sig } = signStandbyRequest(standbyKey, 'GET', target.pathname, tsSec, Buffer.alloc(0));
  return fetch(target.toString(), {
    method: 'GET',
    headers: {
      'X-ACR-Standby-Ts': ts,
      'X-ACR-Standby-Nonce': nonce,
      'X-ACR-Standby-Sha256': sha256,
      'X-ACR-Standby-Sig': sig,
      ...extraHeaders,
    },
    signal: AbortSignal.timeout(timeoutMs),
  });
}

async function maybeBootstrapFromStandbyListener({
  standbyUrl,
  standbyKey,
  dbPath,
  tracesDir,
  rangeChunkBytes = 12 * 1024 * 1024,
}) {
  if (!standbyUrl || !standbyKey || !dbPath || dbPath === ':memory:') return;
  let localPlayers = 0;
  let localRuns = 0;
  if (existsSync(dbPath)) {
    let chk = null;
    try {
      chk = new DatabaseSync(dbPath, { open: true });
      const hasTbl = chk.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name='players'").get();
      if (hasTbl) {
        localPlayers = Number(chk.prepare('SELECT COUNT(*) AS n FROM players').get()?.n || 0);
        localRuns = Number(chk.prepare('SELECT COUNT(*) AS n FROM runs').get()?.n || 0);
      }
    } catch { /* ignore */ } finally {
      if (chk) { try { chk.close(); } catch { /* ignore */ } }
    }
  }
  if (localPlayers > 0 || localRuns > 0) return;

  const stamp = `${process.pid}.${Date.now()}`;
  const tmpGz = `${dbPath}.bootstrap.${stamp}.gz`;
  const tmpSqlite = `${dbPath}.bootstrap.${stamp}`;
  try {
    const stRes = await fetchSignedStandby(standbyUrl, standbyKey, '/internal/standby/status', 10_000);
    if (!stRes.ok) return;
    const status = await stRes.json();
    if (!status || !status.hasDb || (Number(status.players || 0) === 0 && Number(status.runs || 0) === 0)) return;

    console.log(`Bootstrapping empty primary DB from Raspberry Pi listener (${status.players} players, ${status.runs} runs)...`);
    mkdirSync(dirname(dbPath), { recursive: true });
    rmSync(tmpGz, { force: true });
    rmSync(tmpSqlite, { force: true });

    // Chunk 0 requests at most 64 KiB so the Pi builds its cached .sqlite.gz export quickly; remaining chunks pull
    // 12 MiB slices from the warm file cache (~6s each, well below Tailscale Funnel's 40s per-request proxy timeout).
    const firstChunkMax = Math.min(65536, Math.max(1024, Number(rangeChunkBytes)));
    const chunkSize = Math.max(1024, Number(rangeChunkBytes));
    const gzHandle = await openFileAsync(tmpGz, 'w');
    const hasher = createHash('sha256');
    let offset = 0;
    let totalLength = -1;
    let wantSha = '';
    try {
      while (totalLength < 0 || offset < totalLength) {
        const reqLen = offset === 0 ? firstChunkMax : chunkSize;
        const rangeEnd = totalLength > 0 ? Math.min(offset + reqLen - 1, totalLength - 1) : (offset + reqLen - 1);
        let chunkBuf = null;
        let resStatus = 0;
        let resHeaders = null;
        let lastErr = null;
        for (let attempt = 0; attempt < 3; attempt++) {
          try {
            const dbRes = await fetchSignedStandby(
              standbyUrl,
              standbyKey,
              '/internal/standby/db',
              35_000,
              { Range: `bytes=${offset}-${rangeEnd}` },
            );
            if (dbRes.status !== 206 && dbRes.status !== 200) {
              throw new Error(`GET /internal/standby/db HTTP ${dbRes.status}`);
            }
            if (dbRes.status === 200 && Number(dbRes.headers.get('content-length') || 0) > 10 * 1024 * 1024) {
              await dbRes.body?.cancel().catch(() => {});
              const nonRetry = new Error('Standby listener returned 200 (no Range support) for >10 MiB DB; update standby_receiver.py on Pi');
              nonRetry.noRetry = true;
              throw nonRetry;
            }
            chunkBuf = new Uint8Array(await dbRes.arrayBuffer());
            resStatus = dbRes.status;
            resHeaders = dbRes.headers;
            break;
          } catch (err) {
            lastErr = err;
            if (err && err.noRetry) break;
            await new Promise((r) => setTimeout(r, 500 * (attempt + 1)));
          }
        }
        if (!chunkBuf) throw lastErr || new Error('Standby DB chunk download failed');

        const hdrSha = (resHeaders.get('x-acr-standby-sha256') || '').trim().toLowerCase();
        if (hdrSha) {
          if (wantSha && wantSha !== hdrSha) throw new Error('Standby DB snapshot changed mid-download; will retry');
          wantSha = hdrSha;
        }
        if (resStatus === 200) {
          // Single-shot fallback if listener did not honor Range
          await gzHandle.write(chunkBuf, 0, chunkBuf.byteLength, 0);
          hasher.update(chunkBuf);
          offset = chunkBuf.byteLength;
          totalLength = chunkBuf.byteLength;
          break;
        }
        const totalHdr = Number(resHeaders.get('x-acr-standby-total-length') || 0);
        const crMatch = String(resHeaders.get('content-range') || '').match(/\/(\d+)$/);
        const parsedTotal = totalHdr > 0 ? totalHdr : (crMatch ? Number(crMatch[1]) : 0);
        if (parsedTotal <= 0 || chunkBuf.byteLength === 0) {
          throw new Error('Invalid 206 Partial Content response from standby listener');
        }
        totalLength = parsedTotal;
        await gzHandle.write(chunkBuf, 0, chunkBuf.byteLength, offset);
        hasher.update(chunkBuf);
        offset += chunkBuf.byteLength;
        if (totalLength >= 1024 * 1024) {
          console.log(`  Standby DB download: ${(offset / (1024 * 1024)).toFixed(1)} / ${(totalLength / (1024 * 1024)).toFixed(1)} MiB`);
        }
      }
    } finally {
      await gzHandle.close();
    }

    if (wantSha && hasher.digest('hex') !== wantSha) {
      throw new Error('Standby DB download SHA-256 mismatch');
    }
    await pipeline(createReadStream(tmpGz), createGunzip(), createWriteStream(tmpSqlite));
    rmSync(tmpGz, { force: true });

    const verify = new DatabaseSync(tmpSqlite, { open: true });
    try {
      const ok = verify.prepare('PRAGMA quick_check').get();
      if (!ok || Object.values(ok)[0] !== 'ok') throw new Error('Downloaded SQLite failed quick_check');
    } finally {
      verify.close();
    }
    for (const ext of ['-wal', '-shm']) {
      try { if (existsSync(dbPath + ext)) unlinkSync(dbPath + ext); } catch { /* ignore */ }
    }
    renameSync(tmpSqlite, dbPath);

    if (tracesDir && Array.isArray(status.traceIds)) {
      const dstTraces = join(resolve(tracesDir), 'traces');
      mkdirSync(dstTraces, { recursive: true });
      for (const tid of status.traceIds) {
        if (!/^\d{1,15}$/.test(String(tid)) || /^(888888|999999)\d{9}$/.test(String(tid))) continue;
        const dstFile = join(dstTraces, `${tid}.json.gz`);
        if (existsSync(dstFile)) continue;
        const trRes = await fetchSignedStandby(standbyUrl, standbyKey, `/internal/standby/trace/${tid}`, 15_000);
        if (trRes.ok) {
          writeFileSync(dstFile, new Uint8Array(await trRes.arrayBuffer()));
        }
      }
    }
    console.log('Successfully bootstrapped primary DB & traces from Raspberry Pi listener!');
    return true;
  } catch (e) {
    console.error('Standby listener bootstrap check skipped:', e.message);
    return false;
  } finally {
    rmSync(tmpGz, { force: true });
    rmSync(tmpSqlite, { force: true });
  }
}

function createStandbyPusher({
  standbyUrl,
  standbyKeyHex,
  adminKey,
  dataDir,
  dbPath,
  tracesRoot,
  db,
  getWriteSeq,
  recordSyncSeq,
  intervalMs = 60_000,
  chunkBytes = 8 * 1024 * 1024,
  initiallySynced = false,
  disableDeltaPull = false,
}) {
  const standbyKey = resolveStandbyKey(standbyKeyHex, adminKey);
  if (!standbyUrl || !standbyKey || dbPath === ':memory:') return null;
  const baseUrl = normalizeStandbyBaseUrl(standbyUrl);
  const maxChunk = Math.max(1024, Number(chunkBytes));
  const queueDir = join(dataDir, 'standby-queue');
  const tmpDir = join(dataDir, 'standby-tmp');
  mkdirSync(queueDir, { recursive: true });
  mkdirSync(tmpDir, { recursive: true });

  // Clean leftover temp snapshots from any prior crash on startup
  try {
    for (const f of readdirSync(tmpDir)) rmSync(join(tmpDir, f), { force: true });
  } catch { /* ignore */ }

  const pendingTraces = new Set();
  try {
    for (const f of readdirSync(queueDir)) {
      if (f.endsWith('.pending')) {
        const id = f.slice(0, -'.pending'.length);
        if (/^\d+$/.test(id)) pendingTraces.add(id);
      }
    }
  } catch { /* ignore */ }

  let lastSyncedSeq = initiallySynced ? getWriteSeq() : 0;
  let dbSyncInFlight = false;
  let deltaCheckInFlight = false;
  let traceDrainInFlight = false;
  let stopped = false;
  let lastDbSyncAt = initiallySynced ? Date.now() : 0;

  async function pushSigned(subpath, bodyBytes, extraHeaders = {}, timeoutMs = 30_000) {
    const target = new URL(baseUrl + subpath);
    const tsSec = Math.floor(Date.now() / 1000);
    const { ts, nonce, sha256, sig } = signStandbyRequest(standbyKey, 'PUT', target.pathname, tsSec, bodyBytes);
    const res = await fetch(target.toString(), {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/gzip',
        'X-ACR-Standby-Ts': ts,
        'X-ACR-Standby-Nonce': nonce,
        'X-ACR-Standby-Sha256': sha256,
        'X-ACR-Standby-Sig': sig,
        ...extraHeaders,
      },
      body: bodyBytes,
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!res.ok) {
      const txt = await res.text().catch(() => '');
      throw new Error(`Standby PUT ${target.pathname} HTTP ${res.status}: ${txt.slice(0, 120)}`);
    }
    return res.status;
  }

  function enqueueTrace(cleanKey) {
    const m = String(cleanKey).match(/^traces\/(\d+)\.json\.gz$/);
    if (!m || stopped) return;
    const id = m[1];
    try {
      writeFileSync(join(queueDir, `${id}.pending`), cleanKey);
      pendingTraces.add(id);
    } catch (e) {
      console.error('standby queue write warning:', e.message);
    }
    void drainTraces();
  }

  async function drainTraces() {
    if (traceDrainInFlight || stopped || !tracesRoot || pendingTraces.size === 0) return;
    traceDrainInFlight = true;
    try {
      const ids = Array.from(pendingTraces).sort((a, b) => Number(a) - Number(b));
      for (const id of ids) {
        if (stopped) break;
        const marker = join(queueDir, `${id}.pending`);
        const tracePath = join(tracesRoot, 'traces', `${id}.json.gz`);
        if (!existsSync(tracePath)) {
          pendingTraces.delete(id);
          rmSync(marker, { force: true });
          continue;
        }
        try {
          const bytes = await readFileAsync(tracePath);
          await pushSigned(`/internal/standby/trace/${id}`, bytes, {}, 15_000);
          pendingTraces.delete(id);
          rmSync(marker, { force: true });
        } catch (e) {
          console.error('standby trace push warning:', e.message);
          break;
        }
      }
    } catch (e) {
      console.error('standby drain error:', e.message);
    } finally {
      traceDrainInFlight = false;
    }
  }

  async function syncDatabaseNow() {
    if (dbSyncInFlight) return false;
    const seq = getWriteSeq();
    if (seq === lastSyncedSeq) return true;
    // On initial check after a pod restart, skip re-uploading 80+ MiB if the Pi already holds the identical DB state!
    if (lastSyncedSeq === 0) {
      try {
        const stRes = await fetchSignedStandby(baseUrl, standbyKey, '/internal/standby/status', 8_000);
        if (stRes.ok) {
          const st = await stRes.json();
          const lPlayers = Number(db.prepare('SELECT COUNT(*) AS n FROM players').get()?.n || 0);
          const lRunsRow = db.prepare('SELECT COUNT(*) AS n, COALESCE(MAX(id), 0) AS m FROM runs').get();
          const lLin = String(db.prepare("SELECT value FROM _standby_meta WHERE key = 'lineage_id'").get()?.value || '');
          if (
            st && st.hasDb && !st.applying &&
            Number(st.players) === lPlayers &&
            Number(st.runs) === Number(lRunsRow?.n || 0) &&
            Number(st.maxRunId) === Number(lRunsRow?.m || 0) &&
            st.lineageId && st.lineageId === lLin
          ) {
            lastSyncedSeq = seq;
            lastDbSyncAt = Date.now();
            return true;
          }
        }
      } catch { /* proceed with normal snapshot */ }
    }
    // Refuse pushing a completely empty DB (0 players & 0 runs) automatically until real data exists or explicit syncNow
    const hasData = !!(db.prepare('SELECT 1 FROM players LIMIT 1').get() || db.prepare('SELECT 1 FROM runs LIMIT 1').get() ||
                       db.prepare('SELECT 1 FROM routes LIMIT 1').get());
    if (!hasData) return true;

    dbSyncInFlight = true;
    const tag = `${process.pid}-${Date.now()}-${randomBytes(4).toString('hex')}`;
    const snapPath = join(tmpDir, `snapshot-${tag}.sqlite`);
    const gzPath = join(tmpDir, `snapshot-${tag}.sqlite.gz`);
    try {
      recordSyncSeq(seq);
      const { size, sha256 } = await snapshotDatabaseOffThread(dbPath, snapPath, gzPath);
      if (size <= maxChunk) {
        const gzBytes = await readFileAsync(gzPath);
        await pushSigned('/internal/standby/db', gzBytes, { 'X-ACR-Standby-Seq': String(seq) }, 35_000);
      } else {
        const uploadId = randomBytes(12).toString('hex');
        const fh = await openFileAsync(gzPath, 'r');
        const buf = Buffer.allocUnsafe(maxChunk);
        let offset = 0;
        let finalStatus = 200;
        try {
          while (offset < size) {
            const toRead = Math.min(maxChunk, size - offset);
            const { bytesRead } = await fh.read(buf, 0, toRead, offset);
            if (bytesRead <= 0) throw new Error('Unexpected EOF reading compressed snapshot');
            const isFinal = offset + bytesRead >= size;
            const slice = buf.subarray(0, bytesRead);
            const headers = {
              'X-ACR-Standby-Upload-Id': uploadId,
              'X-ACR-Standby-Offset': String(offset),
              'X-ACR-Standby-Seq': String(seq),
              ...(isFinal ? { 'X-ACR-Standby-Final': '1', 'X-ACR-Standby-Total-Sha256': sha256 } : {}),
            };
            finalStatus = await pushSigned('/internal/standby/db/chunk', slice, headers, 35_000);
            offset += bytesRead;
          }
        } finally {
          await fh.close();
        }
        if (finalStatus === 202) {
          const pollMs = maxChunk < 1024 * 1024 ? 50 : 1200;
          const deadline = Date.now() + 120_000;
          while (Date.now() < deadline && !stopped) {
            await new Promise((r) => setTimeout(r, pollMs));
            const stRes = await fetchSignedStandby(baseUrl, standbyKey, '/internal/standby/status', 10_000);
            if (!stRes.ok) continue;
            const st = await stRes.json();
            if (st.applying) continue;
            if (st.lastApplyError) throw new Error(`Standby async apply rejected: ${st.lastApplyError}`);
            break;
          }
        }
      }
      lastSyncedSeq = seq;
      lastDbSyncAt = Date.now();
      return true;
    } catch (e) {
      console.error('standby DB sync warning:', e.message);
      return false;
    } finally {
      rmSync(snapPath, { force: true });
      rmSync(gzPath, { force: true });
      dbSyncInFlight = false;
    }
  }

  async function checkRemoteDeltaNow() {
    if (disableDeltaPull || deltaCheckInFlight || dbSyncInFlight || stopped) return false;
    deltaCheckInFlight = true;
    const tag = `${process.pid}-${Date.now()}-${randomBytes(4).toString('hex')}`;
    const tmpGz = join(tmpDir, `delta-${tag}.sqlite.gz`);
    const tmpDelta = join(tmpDir, `delta-${tag}.sqlite`);
    try {
      const stRes = await fetchSignedStandby(baseUrl, standbyKey, '/internal/standby/status', 10_000);
      if (!stRes.ok) return false;
      const st = await stRes.json();
      if (!st || !Array.isArray(st.traceIds)) return false;
      const deltaIds = st.traceIds.map(String).filter((id) => /^999999\d{9}$/.test(id)).sort();
      if (!deltaIds.length) return false;
      const latestDeltaId = deltaIds[deltaIds.length - 1];
      const curAppliedRow = db.prepare("SELECT value FROM _standby_meta WHERE key = 'applied_delta_id'").get();
      const curApplied = curAppliedRow ? String(curAppliedRow.value) : '';
      if (curApplied && BigInt(latestDeltaId) <= BigInt(curApplied)) return false;

      console.log(`Downloading incremental cutover delta ${latestDeltaId} from Raspberry Pi listener...`);
      const dlRes = await fetchSignedStandby(baseUrl, standbyKey, `/internal/standby/trace/${latestDeltaId}`, 35_000);
      if (!dlRes.ok) throw new Error(`GET delta ${latestDeltaId} HTTP ${dlRes.status}`);
      writeFileSync(tmpGz, new Uint8Array(await dlRes.arrayBuffer()));
      await pipeline(createReadStream(tmpGz), createGunzip(), createWriteStream(tmpDelta));
      applyDeltaSqlite(db, tmpDelta);
      lastSyncedSeq = getWriteSeq();
      lastDbSyncAt = Date.now();
      console.log(`Successfully merged incremental cutover delta ${latestDeltaId} onto primary DB!`);
      return true;
    } catch (e) {
      console.error('standby delta check warning:', e.message);
      return false;
    } finally {
      rmSync(tmpGz, { force: true });
      rmSync(tmpDelta, { force: true });
      deltaCheckInFlight = false;
    }
  }

  const deltaPollMs = Math.min(intervalMs, 25_000);
  const deltaTimer = setInterval(() => {
    void checkRemoteDeltaNow();
  }, deltaPollMs);
  deltaTimer.unref();

  const timer = setInterval(() => {
    void (async () => {
      await checkRemoteDeltaNow();
      await drainTraces();
      await syncDatabaseNow();
    })();
  }, intervalMs);
  timer.unref();

  return {
    enqueueTrace,
    checkDeltaNow: checkRemoteDeltaNow,
    syncNow: async () => {
      await checkRemoteDeltaNow();
      await drainTraces();
      return syncDatabaseNow();
    },
    stop: async () => {
      clearInterval(deltaTimer);
      clearInterval(timer);
      await drainTraces().catch(() => {});
      await syncDatabaseNow().catch(() => {});
      stopped = true;
    },
    status: () => ({
      enabled: true,
      lastDbSyncAt: lastDbSyncAt || null,
      inSync: lastSyncedSeq === getWriteSeq(),
    }),
  };
}

function edgeCacheTtlMs(method, urlObj) {
  if (method !== 'GET' && method !== 'HEAD') return 0;
  if (urlObj.searchParams.has('lang')) return 0; // ?lang= sets Set-Cookie: lang=...
  const p = urlObj.pathname.replace(/\/+$/, '') || '/';
  if (p === '/api/challenges/today' || p === '/api/challenges' || p === '/api/challenge/today' || p === '/api/challenge') {
    return 5_000;
  }
  if (p === '/api/leaderboard') return 5_000;
  if (p === '/api/stats') return 15_000;
  if (p === '/api/cars' || p === '/api/countries') return 300_000;
  if (p === '/api/routes' || p === '/api/route') return 60_000;
  if (p === '/api/version' || /^\/api\/changelog\/\d+\.\d+\.\d+(?:\.\d+)?$/.test(p)) return 60_000;
  if (/^\/api\/(?:tt\/)?runs\/\d+\/trace$/.test(p)) return 300_000;
  if (p === '/api/v1' || p.startsWith('/api/v1/')) return 5_000;
  if (p.startsWith('/brand/') || /^\/community\/[a-z0-9-]+\.webp$/.test(p)) return 3_600_000;
  return 0;
}

function edgeCacheKey(method, urlObj, reqHeaders) {
  // Normalize query parameters in deterministic sorted order to avoid cache-busting eviction
  const params = new URLSearchParams(urlObj.searchParams);
  params.sort();
  const qs = params.toString();
  const normUrl = (urlObj.pathname.replace(/\/+$/, '') || '/') + (qs ? `?${qs}` : '');
  const cookie = String(reqHeaders.cookie || '');
  // Matches server/src/i18n.js cookie name (`lang=...`)
  const langCookie = (cookie.match(/(?:^|;\s*)lang=([a-zA-Z-]{2,8})/) || [])[1] || '';
  const acceptLang = String(reqHeaders['accept-language'] || '').slice(0, 32);
  const ua = String(reqHeaders['user-agent'] || '');
  const appVer = (ua.match(/ACR-Daily\/([\d.]+(?:\s+public)?)/) || [])[1] || '';
  return `${method}:${normUrl}|lc:${langCookie}|al:${acceptLang}|av:${appVer}`;
}

function safeHostHeader(rawHost, fallback) {
  const first = String(rawHost || '').split(',')[0].trim();
  return /^[a-zA-Z0-9.-]+(?::\d{1,5})?$/.test(first) ? first : fallback;
}

function safeProtoHeader(rawProto) {
  const first = String(rawProto || '').split(',')[0].trim().toLowerCase();
  return first === 'https' ? 'https' : 'http';
}

function readBody(req) {
  return new Promise((resolveBody, rejectBody) => {
    if (req.method === 'GET' || req.method === 'HEAD') return resolveBody(undefined);
    const chunks = [];
    let total = 0;
    req.on('data', (chunk) => {
      total += chunk.length;
      if (total > MAX_REQ_BYTES) {
        rejectBody(Object.assign(new Error('Request body too large'), { statusCode: 413 }));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on('end', () => resolveBody(chunks.length ? Buffer.concat(chunks) : undefined));
    req.on('error', rejectBody);
  });
}

function parseEndpointsMetadata(vars) {
  if (vars.ENDPOINTS_JSON) {
    try {
      return JSON.parse(vars.ENDPOINTS_JSON);
    } catch (e) {
      console.error('Invalid ENDPOINTS_JSON:', e.message);
    }
  }
  return {
    regions: [
      { id: 'eu', name: 'Central Europe', api: vars.EU_API_URL || '', relay: vars.EU_RELAY_URL || '' },
      { id: 'uk', name: 'UK', api: vars.UK_API_URL || '', relay: vars.UK_RELAY_URL || '' },
      { id: 'jp', name: 'Japan', api: vars.JP_API_URL || '', relay: vars.JP_RELAY_URL || '' },
    ].filter((r) => r.api || r.relay),
    fallbackRelay: vars.FALLBACK_RELAY_URL || 'wss://immich.tail0d617f.ts.net:10000/live',
  };
}

export async function startVmServer(options = {}) {
  installDefaultCache();
  const vars = loadWranglerVars(options.env);
  const role = String(options.role || vars.ROLE || 'primary').toLowerCase();
  if (role !== 'primary' && role !== 'edge') {
    throw new Error(`Invalid ROLE "${role}" (expected "primary" or "edge")`);
  }
  const devMode = vars.DEV_LOGIN === '1';
  const adminKey = String(vars.ADMIN_KEY || '').trim();
  const explicitLiveKey = String(vars.LIVE_RELAY_KEY || '').trim();
  if (role === 'primary' && !devMode && (!adminKey || adminKey === 'dev' || adminKey.length < 16)) {
    throw new Error('Refusing to start primary without a strong ADMIN_KEY (>= 16 chars)');
  }
  if (role === 'edge' && !devMode && !explicitLiveKey && (!adminKey || adminKey === 'dev' || adminKey.length < 16)) {
    throw new Error('Refusing to start edge without LIVE_RELAY_KEY or a strong ADMIN_KEY');
  }

  const region = String(options.region || vars.REGION || (role === 'primary' ? 'eu' : 'edge'));
  const port = options.port !== undefined ? Number(options.port) : Number(vars.PORT || 8080);
  const hostBind = options.host || vars.HOST || '0.0.0.0';
  const relayPort = options.relayPort !== undefined ? Number(options.relayPort) : Number(vars.RELAY_PORT || 8765);
  const relayHost = options.relayHost || vars.RELAY_BIND_HOST || '127.0.0.1';
  const peerPort = options.peerPort !== undefined ? Number(options.peerPort) : Number(vars.RELAY_PEER_PORT || 8766);
  const peerHost = options.peerHost || vars.RELAY_PEER_BIND_HOST || '0.0.0.0';
  const dataDir = vars.DATA_DIR === ':memory:' ? ':memory:' : resolve(vars.DATA_DIR || '/data');
  const dbPath = options.dbPath || vars.DB_PATH || (dataDir === ':memory:' ? ':memory:' : join(dataDir, 'acr-daily.sqlite'));
  const tracesDir = options.tracesDir !== undefined
    ? options.tracesDir
    : (vars.TRACES_DIR !== undefined ? vars.TRACES_DIR : (dataDir === ':memory:' ? '' : join(dataDir, 'traces')));
  const endpointsMeta = parseEndpointsMetadata(vars);

  let dbObj = null;
  let env = null;
  let standby = null;
  let cronTimer = null;

  const ctx = {
    waitUntil(p) {
      Promise.resolve(p).catch((e) => console.error('waitUntil error:', e));
    },
  };

  if (role === 'primary') {
    const resolvedStandbyUrl = options.standbyUrl ?? vars.RPI_STANDBY_URL ?? '';
    const resolvedStandbyKeyHex = options.standbyKey ?? vars.STANDBY_KEY ?? '';
    if (dbPath && dbPath !== ':memory:' && existsSync(`${dbPath}.migrating`)) {
      for (const ext of ['-wal', '-shm']) {
        try { if (existsSync(dbPath + ext)) unlinkSync(dbPath + ext); } catch { /* ignore */ }
      }
      renameSync(`${dbPath}.migrating`, dbPath);
      console.log(`Applied staged migration database at ${dbPath}`);
    }
    let bootstrappedFromStandby = false;
    if (options.disableStandbyBootstrap !== true && vars.DISABLE_STANDBY_BOOTSTRAP !== '1') {
      bootstrappedFromStandby = await maybeBootstrapFromStandbyListener({
        standbyUrl: resolvedStandbyUrl,
        standbyKey: resolveStandbyKey(resolvedStandbyKeyHex, adminKey),
        dbPath,
        tracesDir,
        rangeChunkBytes: options.standbyRangeChunkBytes,
      });
    }
    dbObj = openD1Database(dbPath);
    const tracesBucket = openTracesBucket(tracesDir, (cleanKey) => {
      if (standby) standby.enqueueTrace(cleanKey);
    });
    standby = createStandbyPusher({
      standbyUrl: resolvedStandbyUrl,
      standbyKeyHex: resolvedStandbyKeyHex,
      adminKey,
      dataDir,
      dbPath,
      tracesRoot: tracesBucket ? tracesBucket.root : '',
      db: dbObj.db,
      getWriteSeq: dbObj.getWriteSeq,
      recordSyncSeq: dbObj.recordSyncSeq,
      intervalMs: Math.max(1000, Number(options.standbyIntervalMs ?? (Number(vars.STANDBY_INTERVAL_S || 60) * 1000))),
      chunkBytes: options.standbyChunkBytes,
      initiallySynced: bootstrappedFromStandby,
      disableDeltaPull: options.disableStandbyBootstrap === true || vars.DISABLE_STANDBY_BOOTSTRAP === '1',
    });
    if (standby) await standby.checkDeltaNow();
    env = {
      ...vars,
      DB: dbObj.d1,
      ...(tracesBucket ? { TRACES: tracesBucket } : {}),
    };

    if (vars.SEED_ROUTES !== '0' && options.seedRoutes !== false) {
      const countRow = await env.DB.prepare('SELECT COUNT(*) AS n FROM routes').first();
      const routesDir = resolve(HERE, '..', 'routes');
      if ((!countRow || countRow.n === 0) && existsSync(routesDir)) {
        const files = readdirSync(routesDir).filter((f) => f.endsWith('.sql') === false && f.endsWith('.json')).sort();
        for (const file of files) {
          try {
            const data = JSON.parse(readFileSync(join(routesDir, file), 'utf8'));
            await worker.fetch(new Request('http://127.0.0.1/api/admin/route', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${env.ADMIN_KEY}` },
              body: JSON.stringify(data),
            }), env, ctx);
            await worker.fetch(new Request('http://127.0.0.1/api/admin/pool', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${env.ADMIN_KEY}` },
              body: JSON.stringify({ track: data.track, car: '*' }),
            }), env, ctx);
          } catch (e) {
            console.error(`Failed to seed route ${file}:`, e);
          }
        }
        await scheduleAhead(env, Date.now()).catch((e) => console.error('initial scheduleAhead:', e));
      }
    }

    if (vars.DISABLE_CRON !== '1' && options.disableCron !== true) {
      let lastSlot = -1;
      cronTimer = setInterval(() => {
        const now = Date.now();
        const slot = Math.floor(now / (5 * 60 * 1000));
        if (slot === lastSlot) return;
        if (new Date(now).getUTCMinutes() % 5 !== 0) return;
        lastSlot = slot;
        worker.scheduled({ scheduledTime: slot * 5 * 60 * 1000, cron: '*/5 * * * *' }, env, ctx).catch((e) => {
          console.error('cron scheduled() error:', e);
        });
      }, 10_000);
      cronTimer.unref();
    }
  }

  const primaryOrigin = role === 'edge' ? new URL(options.primaryUrl || vars.PRIMARY_URL) : null;
  const keepAliveHttp = new http.Agent({ keepAlive: true, maxSockets: 64, keepAliveMsecs: 30_000 });
  const keepAliveHttps = new https.Agent({ keepAlive: true, maxSockets: 64, keepAliveMsecs: 30_000 });
  const edgeCache = new Map();
  let edgePrimaryOk = true;
  let healthProbeTimer = null;

  if (role === 'edge' && primaryOrigin) {
    const checkPrimary = async () => {
      try {
        const r = await fetch(`${primaryOrigin.origin}/healthz`, { signal: AbortSignal.timeout(4000) });
        edgePrimaryOk = r.ok;
      } catch {
        edgePrimaryOk = false;
      }
    };
    await checkPrimary();
    healthProbeTimer = setInterval(() => { void checkPrimary(); }, 5000);
    healthProbeTimer.unref();
  }

  // Optional in-container live/relay.py supervisor
  const relayDisabled = vars.DISABLE_LIVE_RELAY === '1' || options.disableLiveRelay === true;
  let relayProc = null;
  let shuttingDown = false;
  if (!relayDisabled) {
    const relayScript = resolve(HERE, '..', 'live', 'relay.py');
    if (existsSync(relayScript)) {
      const liveKeyHex = /^[0-9a-f]{64}$/i.test(explicitLiveKey)
        ? explicitLiveKey.toLowerCase()
        : deriveLiveKeyHex(adminKey || 'dev');
      const keyDir = dataDir === ':memory:' ? '/tmp' : dataDir;
      mkdirSync(keyDir, { recursive: true });
      const keyFile = join(keyDir, `.live-relay-${process.pid}.key`);
      writeFileSync(keyFile, liveKeyHex + '\n', { mode: 0o600 });

      const nodeId = Number(vars.RELAY_NODE_ID || ({ eu: 1, uk: 2, jp: 3 }[region] || 1));
      const peers = String(vars.RELAY_PEERS || '')
        .split(/[\s,]+/)
        .map((s) => s.trim())
        .filter(Boolean);
      const relayArgs = [
        relayScript,
        '--host', relayHost,
        '--port', String(relayPort),
        '--peer-host', peerHost,
        '--peer-port', String(peerPort),
        '--node-id', String(nodeId),
        '--key-file', keyFile,
      ];
      for (const p of peers) relayArgs.push('--peer', p);

      const spawnRelay = () => {
        if (shuttingDown) return;
        relayProc = spawn('python3', relayArgs, { stdio: 'inherit' });
        relayProc.on('exit', (code, sig) => {
          if (shuttingDown || sig === 'SIGTERM' || sig === 'SIGINT') return;
          console.error(`live/relay.py exited (code=${code}, sig=${sig}), restarting in 2s...`);
          setTimeout(spawnRelay, 2000).unref();
        });
      };
      spawnRelay();
    }
  }

  function proxyOnce(upstreamUrl, method, headers, body) {
    const clientMod = upstreamUrl.protocol === 'https:' ? https : http;
    const agent = upstreamUrl.protocol === 'https:' ? keepAliveHttps : keepAliveHttp;
    return new Promise((resolveRes, rejectRes) => {
      const pReq = clientMod.request(upstreamUrl, {
        method,
        headers,
        agent,
        timeout: 12_000, // Shorter than client's 15s timeout so client never times out while Primary commits
      }, (pRes) => {
        const chunks = [];
        pRes.on('data', (c) => chunks.push(c));
        pRes.on('end', () => resolveRes({ statusCode: pRes.statusCode || 502, headers: pRes.headers, body: Buffer.concat(chunks) }));
        pRes.on('error', rejectRes);
      });
      pReq.on('timeout', () => pReq.destroy(Object.assign(new Error('Primary upstream timeout'), { statusCode: 504 })));
      pReq.on('error', (err) => rejectRes(Object.assign(err, { statusCode: err.statusCode || 502 })));
      if (body && body.length) pReq.write(body);
      pReq.end();
    });
  }

  async function forwardToPrimary(req, res, proto, host) {
    const rawUrl = String(req.url || '/');
    // Strict SSRF prevention: reject scheme-relative //host or non-slash URLs and pin origin!
    if (!/^\/(?!\/)/.test(rawUrl)) {
      res.writeHead(400, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'bad request path' }));
      return;
    }
    const upstreamUrl = new URL(primaryOrigin.origin + rawUrl);
    if (upstreamUrl.origin !== primaryOrigin.origin) {
      res.writeHead(400, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'bad request origin' }));
      return;
    }

    const body = await readBody(req);
    const fwdHeaders = {};
    for (const [k, v] of Object.entries(req.headers)) {
      const lk = k.toLowerCase();
      if (lk === 'host' || lk === 'connection' || lk === 'keep-alive' || lk === 'transfer-encoding' || lk === 'x-acr-peer') {
        continue;
      }
      if (v !== undefined) fwdHeaders[k] = v;
    }
    fwdHeaders['X-Forwarded-Host'] = host;
    fwdHeaders['X-Forwarded-Proto'] = proto;
    fwdHeaders['X-ACR-Edge-Region'] = region;
    fwdHeaders.Host = primaryOrigin.host;

    const urlObj = new URL(`http://${host}${rawUrl}`);
    const method = req.method || 'GET';
    const ttlMs = edgeCacheTtlMs(method, urlObj);
    const cacheKey = ttlMs > 0 ? edgeCacheKey(method, urlObj, req.headers) : null;
    if (cacheKey) {
      const hit = edgeCache.get(cacheKey);
      if (hit && Date.now() < hit.expires) {
        res.writeHead(hit.status, { ...hit.headers, 'X-ACR-Edge-Cache': `HIT; region=${region}` });
        res.end(hit.body);
        return;
      }
      if (hit) edgeCache.delete(cacheKey);
    }

    let pRes;
    try {
      pRes = await proxyOnce(upstreamUrl, method, fwdHeaders, body);
      edgePrimaryOk = true;
    } catch (err) {
      // Retry idempotent GET/HEAD once on stale keep-alive ECONNRESET
      if ((method === 'GET' || method === 'HEAD') && err && err.code === 'ECONNRESET') {
        pRes = await proxyOnce(upstreamUrl, method, fwdHeaders, body);
        edgePrimaryOk = true;
      } else {
        edgePrimaryOk = false;
        throw err;
      }
    }

    const outHeaders = { ...pRes.headers, 'X-ACR-Edge-Region': region };
    if (cacheKey && pRes.statusCode === 200 && !pRes.headers['set-cookie']) {
      if (edgeCache.size >= 500) {
        const oldest = edgeCache.keys().next().value;
        if (oldest !== undefined) edgeCache.delete(oldest);
      }
      const cleanHeaders = { ...pRes.headers };
      delete cleanHeaders.connection;
      delete cleanHeaders['transfer-encoding'];
      edgeCache.set(cacheKey, {
        status: pRes.statusCode,
        headers: cleanHeaders,
        body: pRes.body,
        expires: Date.now() + ttlMs,
      });
      outHeaders['X-ACR-Edge-Cache'] = `MISS; region=${region}`;
    } else if (method === 'POST' && (urlObj.pathname === '/api/runs' || urlObj.pathname === '/api/tt/runs')) {
      for (const k of edgeCache.keys()) {
        if (k.includes('/api/leaderboard') || k.includes('/api/v1/dailies')) edgeCache.delete(k);
      }
    }
    res.writeHead(pRes.statusCode, outHeaders);
    res.end(pRes.body);
  }

  const server = http.createServer(async (req, res) => {
    try {
      const rawUrl = String(req.url || '/');
      if (!/^\/(?!\/)/.test(rawUrl)) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'bad request path' }));
        return;
      }
      const pathOnly = rawUrl.split('?')[0];

      if (pathOnly === '/healthz' || pathOnly === '/readyz') {
        let primaryDbStats = null;
        if (role === 'primary') {
          const pCnt = Number(dbObj.db.prepare('SELECT COUNT(*) AS n FROM players').get()?.n || 0);
          const rRow = dbObj.db.prepare('SELECT COUNT(*) AS n, COALESCE(MAX(id), 0) AS m FROM runs').get();
          const dRow = dbObj.db.prepare("SELECT value FROM _standby_meta WHERE key = 'applied_delta_id'").get();
          primaryDbStats = {
            players: pCnt,
            runs: Number(rRow?.n || 0),
            maxRunId: Number(rRow?.m || 0),
            appliedDeltaId: dRow ? dRow.value : null,
          };
        }
        const healthy = (pathOnly === '/readyz' && shuttingDown)
          ? false
          : (role === 'primary' ? true : edgePrimaryOk);
        res.writeHead(healthy ? 200 : 503, {
          'Content-Type': 'application/json',
          'Cache-Control': 'no-store',
          'Access-Control-Allow-Origin': '*',
        });
        res.end(JSON.stringify({
          ok: healthy,
          service: 'acr-daily',
          role,
          region,
          version: vars.LATEST_VERSION || '0.0.0',
          ...(primaryDbStats ? { db: primaryDbStats } : {}),
          ...(role === 'edge' ? { primaryOk: edgePrimaryOk } : {}),
          ...(standby ? { standby: standby.status() } : {}),
        }));
        return;
      }

      if (pathOnly === '/api/endpoints' && (req.method === 'GET' || req.method === 'HEAD')) {
        res.writeHead(200, {
          'Content-Type': 'application/json',
          'Cache-Control': 'public, max-age=30',
          'Access-Control-Allow-Origin': '*',
        });
        res.end(JSON.stringify({ region, role, ...endpointsMeta }));
        return;
      }

      const proto = safeProtoHeader(req.headers['x-forwarded-proto']);
      const host = safeHostHeader(req.headers['x-forwarded-host'] || req.headers.host, `127.0.0.1:${port}`);

      if (role === 'edge') {
        await forwardToPrimary(req, res, proto, host);
        return;
      }

      if (pathOnly.startsWith('/cdn-cgi/local/scheduled') && env.DEV_LOGIN === '1') {
        const pending = [];
        const syncCtx = { waitUntil(p) { pending.push(Promise.resolve(p)); } };
        await worker.scheduled({ scheduledTime: Date.now(), cron: '*/5 * * * *' }, env, syncCtx);
        await Promise.allSettled(pending);
        res.writeHead(200, { 'Content-Type': 'text/plain' });
        res.end('ok');
        return;
      }

      const fullUrl = `${proto}://${host}${rawUrl}`;
      const headers = new Headers();
      for (const [k, v] of Object.entries(req.headers)) {
        if (Array.isArray(v)) {
          for (const item of v) headers.append(k, item);
        } else if (v !== undefined) {
          headers.set(k, v);
        }
      }

      const body = await readBody(req);
      const webReq = new Request(fullUrl, { method: req.method, headers, body });
      const webRes = await worker.fetch(webReq, env, ctx);

      const outHeaders = { 'X-ACR-Region': region };
      webRes.headers.forEach((v, k) => {
        if (k.toLowerCase() !== 'set-cookie') outHeaders[k] = v;
      });
      const cookies = webRes.headers.getSetCookie ? webRes.headers.getSetCookie() : [];
      if (cookies.length) outHeaders['Set-Cookie'] = cookies;

      res.writeHead(webRes.status, outHeaders);
      res.end(Buffer.from(await webRes.arrayBuffer()));
    } catch (e) {
      const code = e && e.statusCode ? e.statusCode : 500;
      console.error('HTTP handler error:', e.message);
      if (!res.headersSent) {
        const hdrs = { 'Content-Type': 'application/json' };
        if (code === 502 || code === 503 || code === 504) hdrs['Retry-After'] = '2';
        res.writeHead(code, hdrs);
        res.end(JSON.stringify({
          error: code === 413 ? 'request body too large' : (code === 502 || code === 504 ? 'upstream unavailable' : 'server error'),
        }));
      }
    }
  });

  // Ensure Primary's keep-alive exceeds Edge's 30s pool reuse to prevent ECONNRESET races
  server.keepAliveTimeout = 65_000;
  server.headersTimeout = 66_000;

  // Proxy public WebSocket /live upgrades to local or dedicated K8s Service live/relay.py (stripping internal peer headers)
  const relayUpstreamHost = String(vars.RELAY_UPSTREAM_HOST || '127.0.0.1').trim() || '127.0.0.1';
  server.on('upgrade', (req, socket, head) => {
    const urlPath = (req.url || '/').split('?')[0];
    if (!urlPath.startsWith('/live')) {
      socket.write('HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n');
      socket.destroy();
      return;
    }
    socket.setNoDelay(true);
    socket.setTimeout(90_000);
    const upstream = net.connect(relayPort, relayUpstreamHost, () => {
      upstream.setNoDelay(true);
      let raw = `${req.method} ${req.url} HTTP/${req.httpVersion}\r\n`;
      for (let i = 0; i < req.rawHeaders.length; i += 2) {
        const hn = req.rawHeaders[i];
        if (hn.toLowerCase() === 'x-acr-peer') continue;
        const hv = String(req.rawHeaders[i + 1] || '').replace(/[\r\n]/g, '');
        raw += `${hn}: ${hv}\r\n`;
      }
      raw += '\r\n';
      upstream.write(raw);
      if (head && head.length) upstream.write(head);
      socket.pipe(upstream).pipe(socket);
    });
    const cleanup = () => {
      socket.destroy();
      upstream.destroy();
    };
    socket.on('timeout', cleanup);
    upstream.on('error', cleanup);
    socket.on('error', cleanup);
  });

  await new Promise((resolveListen, rejectListen) => {
    server.once('error', rejectListen);
    server.listen(port, hostBind, resolveListen);
  });

  const actualPort = server.address().port;
  console.log(`ACR Daily ${role} (${region}) listening on ${hostBind}:${actualPort}`);

  async function close() {
    shuttingDown = true;
    if (cronTimer) clearInterval(cronTimer);
    if (healthProbeTimer) clearInterval(healthProbeTimer);
    if (relayProc) {
      try { relayProc.kill('SIGTERM'); } catch { /* ignore */ }
    }
    keepAliveHttp.destroy();
    keepAliveHttps.destroy();
    await new Promise((r) => server.close(() => r()));
    if (standby) await standby.stop();
    if (dbObj) {
      try { dbObj.db.close(); } catch { /* ignore */ }
    }
  }

  return { server, port: actualPort, env, db: dbObj ? dbObj.db : null, standby, close };
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  const instance = await startVmServer();
  for (const sig of ['SIGTERM', 'SIGINT']) {
    process.on(sig, () => {
      console.log(`Received ${sig}, shutting down gracefully...`);
      instance.close().finally(() => process.exit(0));
      setTimeout(() => process.exit(0), 30_000).unref();
    });
  }
}
