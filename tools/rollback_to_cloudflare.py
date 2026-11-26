#!/usr/bin/env python3
"""Rolls back ACR Daily from GKE back to the original Cloudflare Worker + Cloudflare D1 setup with zero data loss.

Usage (on the machine with wrangler access + ~/acr-standby/data/acr-daily.sqlite):
    python3 tools/rollback_to_cloudflare.py ~/acr-standby/data

What it does automatically:
1. Optional brief write-freeze on workers.dev (--var MAINTENANCE:1) while waiting up to 75s for GKE Primary (acr-eu)
   to report standby.inSync == true on /healthz so ~/acr-standby/data/acr-daily.sqlite has every latest run from GKE.
2. Compares ~/acr-standby/data/acr-daily.sqlite against remote Cloudflare D1 watermarks and generates a compact,
   D1-compatible incremental SQL file (syncing ONLY new runs/tt_runs/blobs created on GKE + current small state tables,
   never re-uploading the 80+ MiB historical database), then executes it against remote Cloudflare D1.
3. Redeploys the full original Cloudflare Worker from server/wrangler.toml (restoring workers.dev and acrdaily.com).
"""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from export_d1_to_pi import D1Source, HEAVY_TABLES, SKIP_TABLES, get_local_watermark, quote_ident  # noqa: E402

DEFAULT_GKE_HEALTHZ = 'https://acrdaily-eu.34-49-33-253.sslip.io/healthz'
MAX_STATEMENT_GROUP_BYTES = 70 * 1024  # Safely below Cloudflare D1's 100 KB per-statement limit


def sql_literal(val):
    if val is None:
        return 'NULL'
    if isinstance(val, bool):
        return '1' if val else '0'
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        if val != val or val in (float('inf'), float('-inf')):
            return 'NULL'
        return repr(val)
    if isinstance(val, (bytes, bytearray, memoryview)):
        return "X'" + bytes(val).hex() + "'"
    s = str(val).replace("'", "''")
    return "'" + s + "'"


def build_rollback_sql_statements(pi_db_path, d1_watermarks, remote_table_names, remote_table_cols=None):
    """Return an ordered list of D1-safe SQL statements (no BEGIN/COMMIT) syncing GKE state back into D1."""
    conn = sqlite3.connect(pi_db_path)
    conn.row_factory = sqlite3.Row
    stmts = []
    stats = {'new_runs': 0, 'new_tt_runs': 0, 'state_tables': 0}
    try:
        local_tables = {
            r['name']
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND sql IS NOT NULL").fetchall()
            if r['name'].lower() not in SKIP_TABLES
            and not r['name'].startswith('_cf_')
            and not r['name'].startswith('sqlite_')
        }
        target_tables = sorted(local_tables & set(remote_table_names))
        small_tables = [t for t in target_tables if t not in HEAVY_TABLES]
        heavy_tables = [t for t in target_tables if t in HEAVY_TABLES]

        def synced_cols(tbl):
            lcols = [r[1] for r in conn.execute('PRAGMA table_info(%s)' % quote_ident(tbl)).fetchall()]
            if remote_table_cols and tbl in remote_table_cols:
                rset = set(remote_table_cols[tbl])
                return [c for c in lcols if c in rset]
            return lcols

        # 1. Sync small relational/state tables (batched multi-row INSERT OR REPLACE + clean DELETE first)
        for tbl in small_tables:
            cols = synced_cols(tbl)
            if not cols:
                continue
            rows = conn.execute('SELECT * FROM %s' % quote_ident(tbl)).fetchall()
            stmts.append('DELETE FROM %s;' % quote_ident(tbl))
            stats['state_tables'] += 1
            if not rows:
                continue
            col_list = ', '.join(quote_ident(c) for c in cols)
            prefix = 'INSERT OR REPLACE INTO %s (%s) VALUES ' % (quote_ident(tbl), col_list)
            batch_tuples = []
            batch_bytes = len(prefix)
            for row in rows:
                tup_sql = '(' + ', '.join(sql_literal(row[c]) for c in cols) + ')'
                if batch_tuples and (batch_bytes + len(tup_sql) + 2 > MAX_STATEMENT_GROUP_BYTES or len(batch_tuples) >= 25):
                    stmts.append(prefix + ', '.join(batch_tuples) + ';')
                    batch_tuples = []
                    batch_bytes = len(prefix)
                batch_tuples.append(tup_sql)
                batch_bytes += len(tup_sql) + 2
            if batch_tuples:
                stmts.append(prefix + ', '.join(batch_tuples) + ';')

        # 2. Sync ONLY incremental rows above D1 watermarks for heavy trace / BLOB tables
        for tbl in heavy_tables:
            cfg = HEAVY_TABLES[tbl]
            wm_col = cfg['wm_col']
            wm_val = int(d1_watermarks.get(tbl, 0) or 0)
            cols = synced_cols(tbl)
            if not cols:
                continue
            col_list = ', '.join(quote_ident(c) for c in cols)
            rows = conn.execute(
                'SELECT * FROM %s WHERE %s > ? ORDER BY %s ASC'
                % (quote_ident(tbl), quote_ident(wm_col), quote_ident(wm_col)),
                (wm_val,),
            ).fetchall()
            if tbl == 'runs':
                stats['new_runs'] = len(rows)
            elif tbl == 'tt_runs':
                stats['new_tt_runs'] = len(rows)
            for row in rows:
                tup_sql = '(' + ', '.join(sql_literal(row[c]) for c in cols) + ')'
                stmts.append('INSERT OR REPLACE INTO %s (%s) VALUES %s;' % (quote_ident(tbl), col_list, tup_sql))

        # 3. Sync status/reason/flags updates on recent pre-existing runs
        if 'runs' in heavy_tables and int(d1_watermarks.get('runs', 0) or 0) > 0:
            wm_r = int(d1_watermarks['runs'])
            low_r = max(0, wm_r - 300)
            for r in conn.execute(
                'SELECT id, status, reason, flags FROM runs WHERE id > ? AND id <= ?', (low_r, wm_r),
            ).fetchall():
                stmts.append(
                    'UPDATE runs SET status = %s, reason = %s, flags = %s WHERE id = %d;'
                    % (sql_literal(r['status']), sql_literal(r['reason']), sql_literal(r['flags']), int(r['id']))
                )

        if 'cache' in remote_table_names:
            stmts.append('DELETE FROM cache;')
    finally:
        conn.close()
    return stmts, stats


def wait_for_gke_standby_sync(healthz_url, timeout_s=75):
    print('Waiting up to %ds for GKE Primary (%s) standby.inSync == true ...' % (timeout_s, healthz_url))
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            req = urllib.request.Request(healthz_url, headers={'User-Agent': 'acr-rollback/1.0'})
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            st = data.get('standby') or {}
            if st.get('inSync') is True:
                print('  GKE Primary standby is inSync (runs=%s, players=%s)!' % (
                    (data.get('db') or {}).get('runs'), (data.get('db') or {}).get('players'),
                ))
                return True
        except Exception:
            pass
        time.sleep(3)
    print('  Warning: timed out waiting for inSync=true; proceeding with latest local Pi snapshot.')
    return False


def execute_sql_chunks_on_d1(wrangler_cmd, d1_name, stmts, target_sqlite=None):
    if not stmts:
        return
    if target_sqlite:
        conn = sqlite3.connect(target_sqlite)
        try:
            conn.executescript('\n'.join(stmts))
            conn.commit()
        finally:
            conn.close()
        return

    # Group statements into ~1.5 MiB SQL files so wrangler d1 execute --file runs fast and well within D1 limits
    chunks = []
    cur = []
    cur_bytes = 0
    for s in stmts:
        if cur and cur_bytes + len(s) + 1 > 1500 * 1024:
            chunks.append('\n'.join(cur) + '\n')
            cur = []
            cur_bytes = 0
        cur.append(s)
        cur_bytes += len(s) + 1
    if cur:
        chunks.append('\n'.join(cur) + '\n')

    for idx, sql_text in enumerate(chunks, 1):
        fd, tmp_sql = tempfile.mkstemp(suffix='.sql', prefix='acr-rollback-%d-' % idx)
        os.close(fd)
        try:
            with open(tmp_sql, 'w', encoding='utf-8') as f:
                f.write(sql_text)
            print('  Applying D1 rollback SQL batch %d/%d (%.1f KiB)...' % (idx, len(chunks), len(sql_text) / 1024.0))
            subprocess.run(
                wrangler_cmd + ['d1', 'execute', d1_name, '--remote', '--file=' + tmp_sql],
                cwd=os.path.join(ROOT, 'server'),
                check=True,
            )
        finally:
            if os.path.exists(tmp_sql):
                os.remove(tmp_sql)


def main():
    ap = argparse.ArgumentParser(description='Roll back ACR Daily from GKE to Cloudflare Worker + D1 with zero data loss.')
    ap.add_argument('data_dir', help='Raspberry Pi standby data dir holding acr-daily.sqlite (e.g. ~/acr-standby/data)')
    ap.add_argument('--db-name', default='acr-daily', help='Cloudflare D1 database name (default: acr-daily)')
    ap.add_argument('--healthz-url', default=DEFAULT_GKE_HEALTHZ, help='GKE Primary /healthz URL')
    ap.add_argument('--skip-d1-sync', action='store_true', help='Skip syncing new GKE DB rows back to D1 (redeploy Worker only)')
    ap.add_argument('--skip-worker-deploy', action='store_true', help='Sync D1 data only without running wrangler deploy')
    ap.add_argument('--target-sqlite', help='Optional local SQLite target instead of remote D1 (for testing)')
    args = ap.parse_args()

    pi_db = os.path.join(os.path.abspath(os.path.expanduser(args.data_dir)), 'acr-daily.sqlite')
    local_wrangler = os.path.join(ROOT, 'server', 'node_modules', '.bin', 'wrangler')
    wrangler_cmd = [local_wrangler] if os.path.exists(local_wrangler) else ['npx', 'wrangler']

    if not args.target_sqlite and not args.skip_d1_sync:
        print('=== [1/3] Pausing workers.dev writes during final GKE -> Pi -> D1 sync ===')
        proxy_cfg = os.path.join(ROOT, 'tools', 'cloudflare-cutover-proxy', 'wrangler.toml')
        if os.path.exists(proxy_cfg):
            subprocess.run(
                wrangler_cmd + ['deploy', '--config', proxy_cfg, '--var', 'MAINTENANCE:1'],
                cwd=ROOT,
                check=False,
            )
        wait_for_gke_standby_sync(args.healthz_url, timeout_s=75)

    if not args.skip_d1_sync:
        if not os.path.exists(pi_db):
            raise SystemExit('Missing %s — cannot sync GKE state without Pi standby DB.' % pi_db)
        print('=== [2/3] Syncing incremental GKE changes from %s back into Cloudflare D1 ===' % pi_db)
        if not args.target_sqlite:
            subprocess.run(
                wrangler_cmd + ['d1', 'migrations', 'apply', args.db_name, '--remote'],
                cwd=os.path.join(ROOT, 'server'),
                input='y\n',
                text=True,
                check=False,
            )
        d1 = D1Source(db_name=args.db_name, source_sqlite=args.target_sqlite)
        master_rows = d1.query_one("SELECT name FROM sqlite_master WHERE type='table' AND sql IS NOT NULL")
        remote_tables = sorted(
            r['name'] for r in master_rows
            if r['name'].lower() not in SKIP_TABLES
            and not r['name'].startswith('_cf_')
            and not r['name'].startswith('sqlite_')
        )
        remote_table_cols = {}
        for i in range(0, len(remote_tables), 12):
            bt = remote_tables[i:i + 12]
            res_list = d1.query_batch(['PRAGMA table_info(%s)' % quote_ident(t) for t in bt])
            for t, rows in zip(bt, res_list):
                remote_table_cols[t] = [r['name'] for r in rows if 'name' in r]
        d1_watermarks = {}
        for tbl, cfg in HEAVY_TABLES.items():
            if tbl in remote_table_cols:
                rows = d1.query_one('SELECT COALESCE(MAX(%s), 0) AS m FROM %s' % (quote_ident(cfg['wm_col']), quote_ident(tbl)))
                d1_watermarks[tbl] = int((rows[0]['m'] if rows else 0) or 0)
        stmts, stats = build_rollback_sql_statements(pi_db, d1_watermarks, set(remote_tables), remote_table_cols)
        print('  Prepared rollback delta: +%d new runs, +%d new tt_runs, %d state tables (%d SQL statements)' % (
            stats['new_runs'], stats['new_tt_runs'], stats['state_tables'], len(stmts),
        ))
        execute_sql_chunks_on_d1(wrangler_cmd, args.db_name, stmts, target_sqlite=args.target_sqlite)

    if not args.skip_worker_deploy and not args.target_sqlite:
        print('=== [3/3] Redeploying original Cloudflare Worker (server/wrangler.toml) ===')
        res = subprocess.run(wrangler_cmd + ['deploy'], cwd=os.path.join(ROOT, 'server'))
        if res.returncode != 0:
            print(
                '\nNOTE: If wrangler reported a DNS record conflict on acrdaily.com:\n'
                '  1. In Cloudflare Dashboard -> DNS -> Records, delete the manual A record (acrdaily.com -> 34.49.33.253).\n'
                '  2. Re-run: python3 tools/rollback_to_cloudflare.py ~/acr-standby/data --skip-d1-sync\n'
                '     so Cloudflare automatically re-attaches the Worker Custom Domain on acrdaily.com!',
                file=sys.stderr,
            )
            raise SystemExit(res.returncode)
        print('\nRollback complete! Both workers.dev and acrdaily.com are back on Cloudflare Worker + D1.')


if __name__ == '__main__':
    main()
