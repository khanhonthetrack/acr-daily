#!/usr/bin/env python3
"""Exports Cloudflare D1 (acr-daily) into the Raspberry Pi listener directory (full or fast --delta mode!).

Modes:
1. Initial full export (when ~/acr-standby/data/acr-daily.sqlite does not exist yet, or with --full):
       python3 tools/export_d1_to_pi.py ~/acr-standby/data [optional-existing-dump.sql]

2. Fast cutover delta sync (fetches ONLY new runs/traces/blobs + small state tables since the base export, ~1 MiB
   instead of re-downloading and re-uploading the full 80+ MiB database!):
       python3 tools/export_d1_to_pi.py --delta ~/acr-standby/data

   Updates ~/acr-standby/data/acr-daily.sqlite in place AND writes ~/acr-standby/data/cutover-delta.sqlite.gz (~1 MiB),
   which GKE Primary (acr-eu) automatically detects and merges within 30 seconds without restarting or re-transferring
   the 80+ MiB historical traces!
"""
import argparse
import glob
import gzip
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SKIP_TABLES = {
    '_cf_kv',
    'd1_migrations',
    'sqlite_sequence',
    '_migrations',
    '_standby_meta',
    '_delta_meta',
    '_delta_runs_patches',
    '_delta_tt_runs_patches',
    'cache',
    'live',
    'event_live',
    'tt_live',
    'casual_signals',
}

# Heavy tables synced incrementally by watermark so historical traces & image BLOBs are never re-transferred.
HEAVY_TABLES = {
    'runs': {'wm_col': 'id', 'pk': 'id', 'blob_col': None, 'page': 25},
    'tt_runs': {'wm_col': 'id', 'pk': 'id', 'blob_col': None, 'page': 25},
    'routes': {'wm_col': 'updated', 'pk': 'track', 'blob_col': None, 'page': 10},
    'player_avatars': {'wm_col': 'updated', 'pk': 'steam_id', 'blob_col': 'data', 'page': 20},
    'league_banners': {'wm_col': 'updated', 'pk': 'league_id', 'blob_col': 'data', 'page': 10},
    'livery_shots': {'wm_col': 'created', 'pk': 'livery_id', 'blob_col': 'data', 'page': 10},
    'bug_files': {'wm_col': 'id', 'pk': 'id', 'blob_col': 'data', 'page': 10},
}


def quote_ident(name):
    return '"' + str(name).replace('"', '""') + '"'


class D1Source:
    """Queries either remote Cloudflare D1 (via wrangler d1 execute --remote --json) or a local SQLite file (for tests)."""

    def __init__(self, db_name='acr-daily', source_sqlite=None):
        self.db_name = db_name
        self.source_sqlite = os.path.abspath(source_sqlite) if source_sqlite else None
        local_wrangler = os.path.join(ROOT, 'server', 'node_modules', '.bin', 'wrangler')
        self.wrangler_cmd = [local_wrangler] if os.path.exists(local_wrangler) else ['npx', 'wrangler']

    def query_batch(self, sql_list):
        if not sql_list:
            return []
        if self.source_sqlite:
            conn = sqlite3.connect(self.source_sqlite)
            conn.row_factory = sqlite3.Row
            try:
                out = []
                for sql in sql_list:
                    cur = conn.execute(sql)
                    out.append([dict(r) for r in cur.fetchall()])
                return out
            finally:
                conn.close()

        combined = '; '.join(s.rstrip().rstrip(';') for s in sql_list) + ';'
        proc = subprocess.run(
            self.wrangler_cmd + ['d1', 'execute', self.db_name, '--remote', '--json', '--command', combined],
            cwd=os.path.join(ROOT, 'server'),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            if len(sql_list) > 1:
                return [self.query_batch([s])[0] for s in sql_list]
            raise RuntimeError('wrangler d1 execute failed: %s' % (proc.stderr or proc.stdout)[-500:])

        raw = proc.stdout.strip()
        start = raw.find('[')
        if start > 0:
            raw = raw[start:]
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            parsed = [parsed]
        if len(parsed) != len(sql_list) and len(sql_list) > 1:
            return [self.query_batch([s])[0] for s in sql_list]
        return [item.get('results') or [] for item in parsed]

    def query_one(self, sql):
        return self.query_batch([sql])[0]


def get_local_watermark(conn, table, col):
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not exists:
        return 0
    val = conn.execute('SELECT COALESCE(MAX(%s), 0) FROM %s' % (quote_ident(col), quote_ident(table))).fetchone()[0]
    return int(val or 0)


def apply_delta_to_sqlite(target_db_path, delta_db_path):
    """Atomically merges a delta SQLite database into target_db_path."""
    conn = sqlite3.connect(target_db_path, timeout=30.0)
    try:
        conn.execute('PRAGMA journal_mode = WAL;')
        conn.execute('PRAGMA foreign_keys = OFF;')
        conn.execute('ATTACH DATABASE ? AS delta_db', (delta_db_path,))
        try:
            meta_rows = conn.execute('SELECT key, value FROM delta_db._delta_meta').fetchall()
            meta = {k: v for k, v in meta_rows}
            replace_tables = json.loads(meta.get('replace_tables', '[]'))
            upsert_tables = json.loads(meta.get('upsert_tables', '[]'))
            base_run_id = int(meta.get('base_run_id', '0') or 0)
            base_tt_run_id = int(meta.get('base_tt_run_id', '0') or 0)
            is_authoritative_cutover = meta.get('authoritative_cutover') == '1'

            conn.execute('BEGIN IMMEDIATE')
            try:
                for tbl in replace_tables + upsert_tables:
                    has_main = conn.execute(
                        "SELECT 1 FROM main.sqlite_master WHERE type='table' AND name=?", (tbl,)
                    ).fetchone()
                    if not has_main:
                        ddl_row = conn.execute(
                            "SELECT sql FROM delta_db.sqlite_master WHERE type='table' AND name=?", (tbl,)
                        ).fetchone()
                        if ddl_row and ddl_row[0]:
                            conn.execute(ddl_row[0])

                for tbl in replace_tables:
                    main_cols = {r[1] for r in conn.execute('PRAGMA main.table_info(%s)' % quote_ident(tbl)).fetchall()}
                    delta_cols = [r[1] for r in conn.execute('PRAGMA delta_db.table_info(%s)' % quote_ident(tbl)).fetchall()]
                    cols = [c for c in delta_cols if c in main_cols]
                    if not cols:
                        continue
                    col_sql = ', '.join(quote_ident(c) for c in cols)
                    conn.execute('DELETE FROM main.%s' % quote_ident(tbl))
                    conn.execute(
                        'INSERT INTO main.%s (%s) SELECT %s FROM delta_db.%s'
                        % (quote_ident(tbl), col_sql, col_sql, quote_ident(tbl))
                    )

                if is_authoritative_cutover and base_run_id > 0:
                    conn.execute('DELETE FROM main.runs WHERE id > ?', (base_run_id,))
                if is_authoritative_cutover and base_tt_run_id > 0:
                    has_tt = conn.execute("SELECT 1 FROM main.sqlite_master WHERE type='table' AND name='tt_runs'").fetchone()
                    if has_tt:
                        conn.execute('DELETE FROM main.tt_runs WHERE id > ?', (base_tt_run_id,))

                for tbl in upsert_tables:
                    main_cols = {r[1] for r in conn.execute('PRAGMA main.table_info(%s)' % quote_ident(tbl)).fetchall()}
                    delta_cols = [r[1] for r in conn.execute('PRAGMA delta_db.table_info(%s)' % quote_ident(tbl)).fetchall()]
                    cols = [c for c in delta_cols if c in main_cols]
                    if not cols:
                        continue
                    col_sql = ', '.join(quote_ident(c) for c in cols)
                    conn.execute(
                        'INSERT OR REPLACE INTO main.%s (%s) SELECT %s FROM delta_db.%s'
                        % (quote_ident(tbl), col_sql, col_sql, quote_ident(tbl))
                    )

                has_rpatch = conn.execute(
                    "SELECT 1 FROM delta_db.sqlite_master WHERE type='table' AND name='_delta_runs_patches'"
                ).fetchone()
                if has_rpatch:
                    for rid, status, reason, flags in conn.execute(
                        'SELECT id, status, reason, flags FROM delta_db._delta_runs_patches'
                    ).fetchall():
                        conn.execute(
                            'UPDATE main.runs SET status = ?, reason = ?, flags = ? WHERE id = ?',
                            (status, reason, flags, rid),
                        )

                has_ttpatch = conn.execute(
                    "SELECT 1 FROM delta_db.sqlite_master WHERE type='table' AND name='_delta_tt_runs_patches'"
                ).fetchone()
                if has_ttpatch:
                    for rid, status, reason in conn.execute(
                        'SELECT id, status, reason FROM delta_db._delta_tt_runs_patches'
                    ).fetchall():
                        conn.execute(
                            'UPDATE main.tt_runs SET status = ?, reason = ? WHERE id = ?',
                            (status, reason, rid),
                        )

                has_cache = conn.execute(
                    "SELECT 1 FROM main.sqlite_master WHERE type='table' AND name='cache'"
                ).fetchone()
                if has_cache:
                    conn.execute('DELETE FROM main.cache')

                conn.execute('CREATE TABLE IF NOT EXISTS main._standby_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
                if meta.get('lineage_id'):
                    conn.execute(
                        "INSERT INTO main._standby_meta (key, value) VALUES ('lineage_id', ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        (meta['lineage_id'],),
                    )
                if meta.get('sync_seq'):
                    conn.execute(
                        "INSERT INTO main._standby_meta (key, value) VALUES ('sync_seq', ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        (meta['sync_seq'],),
                    )
                if meta.get('delta_id'):
                    conn.execute(
                        "INSERT INTO main._standby_meta (key, value) VALUES ('applied_delta_id', ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        (meta['delta_id'],),
                    )
                conn.execute('COMMIT')
            except Exception:
                conn.execute('ROLLBACK')
                raise
        finally:
            conn.execute('DETACH DATABASE delta_db')
    finally:
        conn.close()


def run_delta_export(out_dir, d1_name='acr-daily', source_sqlite=None):
    dst_db = os.path.join(out_dir, 'acr-daily.sqlite')
    if not os.path.exists(dst_db):
        raise SystemExit(
            'Base database %s not found! Run without --delta once first (or keep your existing export).' % dst_db
        )

    base_conn = sqlite3.connect(dst_db)
    try:
        watermarks = {tbl: get_local_watermark(base_conn, tbl, cfg['wm_col']) for tbl, cfg in HEAVY_TABLES.items()}
        cur_lin_row = None
        if base_conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='_standby_meta'").fetchone():
            cur_lin_row = base_conn.execute("SELECT value FROM _standby_meta WHERE key='lineage_id'").fetchone()
        lineage_id = cur_lin_row[0] if (cur_lin_row and cur_lin_row[0]) else os.urandom(16).hex()
    finally:
        base_conn.close()

    print('Fetching incremental D1 delta since watermarks: runs.id > %d, tt_runs.id > %d ...' % (
        watermarks['runs'], watermarks['tt_runs'],
    ))
    src = D1Source(db_name=d1_name, source_sqlite=source_sqlite)
    master_rows = src.query_one(
        "SELECT name, sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL ORDER BY name"
    )
    remote_tables = {}
    for r in master_rows:
        tname = r['name']
        if tname.lower() in SKIP_TABLES or tname.startswith('_cf_') or tname.startswith('sqlite_'):
            continue
        remote_tables[tname] = r['sql']

    small_tables = sorted(t for t in remote_tables if t not in HEAVY_TABLES)
    heavy_present = sorted(t for t in remote_tables if t in HEAVY_TABLES)

    delta_id = '999999%09d' % (int(time.time()) % 1_000_000_000)
    fd, tmp_delta = tempfile.mkstemp(suffix='.sqlite', prefix='acr-delta-')
    os.close(fd)
    try:
        dconn = sqlite3.connect(tmp_delta)
        try:
            for tname, ddl in remote_tables.items():
                dconn.execute(ddl)
            dconn.execute('CREATE TABLE _delta_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            dconn.execute('CREATE TABLE _delta_runs_patches (id INTEGER PRIMARY KEY, status TEXT, reason TEXT, flags TEXT)')
            dconn.execute('CREATE TABLE _delta_tt_runs_patches (id INTEGER PRIMARY KEY, status TEXT, reason TEXT)')

            # 1. Fetch row counts of small state tables in batches of 12 so empty/small tables transfer in a few RPCs
            counts = {}
            for i in range(0, len(small_tables), 12):
                batch_tbls = small_tables[i:i + 12]
                res_list = src.query_batch(['SELECT COUNT(*) AS n FROM %s' % quote_ident(t) for t in batch_tbls])
                for t, rows in zip(batch_tbls, res_list):
                    counts[t] = int((rows[0]['n'] if rows else 0) or 0)

            non_empty_small = [t for t in small_tables if counts.get(t, 0) > 0]
            single_shot = [t for t in non_empty_small if counts[t] <= 800]
            paginated = [t for t in non_empty_small if counts[t] > 800]

            def insert_rows(table_name, rows, blob_col=None):
                if not rows:
                    return
                cols = [r[1] for r in dconn.execute('PRAGMA table_info(%s)' % quote_ident(table_name)).fetchall()]
                placeholders = ', '.join('?' for _ in cols)
                col_list = ', '.join(quote_ident(c) for c in cols)
                sql = 'INSERT OR REPLACE INTO %s (%s) VALUES (%s)' % (quote_ident(table_name), col_list, placeholders)
                vals = []
                for row in rows:
                    tup = []
                    for c in cols:
                        if blob_col and c == blob_col and (c + '_hex') in row:
                            hx = row.get(c + '_hex')
                            tup.append(bytes.fromhex(hx) if hx else b'')
                        else:
                            tup.append(row.get(c))
                    vals.append(tup)
                dconn.executemany(sql, vals)

            for i in range(0, len(single_shot), 8):
                batch_tbls = single_shot[i:i + 8]
                res_list = src.query_batch(['SELECT * FROM %s' % quote_ident(t) for t in batch_tbls])
                for t, rows in zip(batch_tbls, res_list):
                    insert_rows(t, rows)

            for t in paginated:
                offset = 0
                while offset < counts[t] + 1000:
                    rows = src.query_one('SELECT * FROM %s LIMIT 1000 OFFSET %d' % (quote_ident(t), offset))
                    if not rows:
                        break
                    insert_rows(t, rows)
                    if len(rows) < 1000:
                        break
                    offset += len(rows)

            # 2. Fetch heavy tables strictly above watermarks!
            new_counts = {}
            for t in heavy_present:
                cfg = HEAVY_TABLES[t]
                wm_col = cfg['wm_col']
                pk_col = cfg['pk']
                blob_col = cfg['blob_col']
                page = cfg['page']
                wm = watermarks[t]
                cols = [r[1] for r in dconn.execute('PRAGMA table_info(%s)' % quote_ident(t)).fetchall()]
                select_exprs = []
                for c in cols:
                    if blob_col and c == blob_col:
                        select_exprs.append('hex(%s) AS %s' % (quote_ident(c), quote_ident(c + '_hex')))
                    else:
                        select_exprs.append(quote_ident(c))
                sel_sql = ', '.join(select_exprs)

                fetched = 0
                if wm_col == pk_col and wm_col == 'id':
                    cursor = wm
                    while True:
                        q = 'SELECT %s FROM %s WHERE %s > %d ORDER BY %s ASC LIMIT %d' % (
                            sel_sql, quote_ident(t), quote_ident(wm_col), cursor, quote_ident(wm_col), page,
                        )
                        rows = src.query_one(q)
                        if not rows:
                            break
                        insert_rows(t, rows, blob_col=blob_col)
                        fetched += len(rows)
                        cursor = int(rows[-1][wm_col])
                        if len(rows) < page:
                            break
                else:
                    offset = 0
                    while True:
                        q = 'SELECT %s FROM %s WHERE %s > %d ORDER BY %s ASC, %s ASC LIMIT %d OFFSET %d' % (
                            sel_sql, quote_ident(t), quote_ident(wm_col), wm,
                            quote_ident(wm_col), quote_ident(pk_col), page, offset,
                        )
                        rows = src.query_one(q)
                        if not rows:
                            break
                        insert_rows(t, rows, blob_col=blob_col)
                        fetched += len(rows)
                        if len(rows) < page:
                            break
                        offset += len(rows)
                new_counts[t] = fetched

            # 3. Also sync status/reason/flags changes on recent existing runs without re-fetching their traces!
            if 'runs' in heavy_present and watermarks['runs'] > 0:
                low_id = max(0, watermarks['runs'] - 500)
                rpatches = src.query_one(
                    'SELECT id, status, reason, flags FROM runs WHERE id > %d AND id <= %d' % (low_id, watermarks['runs'])
                )
                if rpatches:
                    dconn.executemany(
                        'INSERT OR REPLACE INTO _delta_runs_patches (id, status, reason, flags) VALUES (?, ?, ?, ?)',
                        [(r['id'], r.get('status'), r.get('reason'), r.get('flags')) for r in rpatches],
                    )
            if 'tt_runs' in heavy_present and watermarks['tt_runs'] > 0:
                low_tt = max(0, watermarks['tt_runs'] - 500)
                tpatches = src.query_one(
                    'SELECT id, status, reason FROM tt_runs WHERE id > %d AND id <= %d' % (low_tt, watermarks['tt_runs'])
                )
                if tpatches:
                    dconn.executemany(
                        'INSERT OR REPLACE INTO _delta_tt_runs_patches (id, status, reason) VALUES (?, ?, ?)',
                        [(r['id'], r.get('status'), r.get('reason')) for r in tpatches],
                    )

            meta_entries = {
                'delta_id': delta_id,
                'lineage_id': lineage_id,
                'authoritative_cutover': '1',
                'base_run_id': str(watermarks['runs']),
                'base_tt_run_id': str(watermarks['tt_runs']),
                'replace_tables': json.dumps(small_tables),
                'upsert_tables': json.dumps(heavy_present),
            }
            dconn.executemany('INSERT INTO _delta_meta (key, value) VALUES (?, ?)', list(meta_entries.items()))
            dconn.commit()
        finally:
            dconn.close()

        # Apply delta to local Raspberry Pi acr-daily.sqlite first
        apply_delta_to_sqlite(dst_db, tmp_delta)

        # Publish compressed delta into traces/traces/999999<ts>.json.gz (~1 MiB) so the already-running Pi
        # standby_receiver.py exposes it immediately via /internal/standby/status + /internal/standby/trace/<id>
        # with ZERO listener restart needed!
        traces_dir = os.path.join(out_dir, 'traces', 'traces')
        os.makedirs(traces_dir, exist_ok=True)
        for old_name in os.listdir(traces_dir):
            if re.match(r'^999999\d{9}\.json\.gz$', old_name):
                try:
                    os.remove(os.path.join(traces_dir, old_name))
                except OSError:
                    pass
        delta_gz_dst = os.path.join(traces_dir, '%s.json.gz' % delta_id)
        delta_gz_tmp = delta_gz_dst + '.tmp.%d' % os.getpid()
        with open(tmp_delta, 'rb') as sf, gzip.open(delta_gz_tmp, 'wb', compresslevel=6) as gf:
            while True:
                b = sf.read(65536)
                if not b:
                    break
                gf.write(b)
        os.replace(delta_gz_tmp, delta_gz_dst)
        gz_kb = os.path.getsize(delta_gz_dst) / 1024.0

        vconn = sqlite3.connect(dst_db)
        try:
            tot_players = vconn.execute('SELECT COUNT(*) FROM players').fetchone()[0]
            tot_runs = vconn.execute('SELECT COUNT(*) FROM runs').fetchone()[0]
            tot_sessions = vconn.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]
        finally:
            vconn.close()

        print('Delta sync complete!')
        print('  New runs fetched     : +%d (total runs now: %d)' % (new_counts.get('runs', 0), tot_runs))
        print('  New tt_runs fetched  : +%d' % new_counts.get('tt_runs', 0))
        print('  Total players        : %d (active sessions: %d)' % (tot_players, tot_sessions))
        print('  Delta package size   : %.1f KiB (%s)' % (gz_kb, delta_gz_dst))
        print('GKE Primary (acr-eu) will automatically pull & merge this delta within ~30 seconds!')
    finally:
        if os.path.exists(tmp_delta):
            os.remove(tmp_delta)


def run_full_export(out_dir, dump_arg=None, d1_name='acr-daily'):
    mig_dir = os.path.join(ROOT, 'server', 'migrations')
    tmp_dump = None
    if dump_arg:
        dump_path = os.path.abspath(dump_arg)
    else:
        fd, tmp_dump = tempfile.mkstemp(suffix='.sql', prefix='acr-d1-')
        os.close(fd)
        dump_path = tmp_dump
        print('Exporting full remote Cloudflare D1 database (%s)...' % d1_name)
        subprocess.run(
            ['npx', 'wrangler', 'd1', 'export', d1_name, '--remote', '--output=' + dump_path],
            cwd=os.path.join(ROOT, 'server'),
            check=True,
        )

    try:
        with open(dump_path, 'r', encoding='utf-8') as f:
            raw_sql = f.read()

        filtered = []
        skip = False
        for line in raw_sql.splitlines():
            if re.match(
                r'^\s*(CREATE|INSERT\s+INTO|DROP)\s+(TABLE\s+)?(IF\s+EXISTS\s+|IF\s+NOT\s+EXISTS\s+)?["`]?(_cf_KV|d1_migrations)["`]?\b',
                line,
                re.I,
            ):
                skip = not line.rstrip().endswith(';')
                continue
            if skip:
                if line.rstrip().endswith(';'):
                    skip = False
                continue
            filtered.append(line)

        dst_db = os.path.join(out_dir, 'acr-daily.sqlite')
        staging = dst_db + '.staging.%d' % os.getpid()
        if os.path.exists(staging):
            os.remove(staging)

        conn = sqlite3.connect(staging)
        try:
            conn.executescript('\n'.join(filtered))
            conn.execute('CREATE TABLE IF NOT EXISTS _migrations (name TEXT PRIMARY KEY, applied INTEGER NOT NULL)')
            conn.execute('CREATE TABLE IF NOT EXISTS _standby_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            conn.execute(
                "INSERT OR IGNORE INTO _standby_meta (key, value) VALUES ('lineage_id', ?)",
                (os.urandom(16).hex(),),
            )
            now_ms = int(time.time() * 1000)
            for mpath in sorted(glob.glob(os.path.join(mig_dir, '*.sql'))):
                conn.execute(
                    'INSERT OR IGNORE INTO _migrations (name, applied) VALUES (?, ?)',
                    (os.path.basename(mpath), now_ms),
                )
            conn.commit()
            chk = conn.execute('PRAGMA integrity_check').fetchone()[0]
            if chk != 'ok':
                raise SystemExit('SQLite integrity_check failed: %s' % chk)
            for tbl in ('players', 'sessions', 'runs', 'routes', 'leagues', 'cups'):
                try:
                    cnt = conn.execute('SELECT COUNT(*) FROM %s' % tbl).fetchone()[0]
                    print('  %-10s: %d rows' % (tbl, cnt))
                except sqlite3.Error:
                    pass
        finally:
            conn.close()

        for ext in ('-wal', '-shm'):
            if os.path.exists(dst_db + ext):
                os.remove(dst_db + ext)
        os.replace(staging, dst_db)
        cutover_delta = os.path.join(out_dir, 'cutover-delta.sqlite.gz')
        if os.path.exists(cutover_delta):
            os.remove(cutover_delta)
        print('Ready at %s' % dst_db)
    finally:
        if tmp_dump and os.path.exists(tmp_dump):
            os.remove(tmp_dump)


def main():
    ap = argparse.ArgumentParser(description='Export Cloudflare D1 to Raspberry Pi listener directory (full or --delta).')
    ap.add_argument('data_dir', help='Raspberry Pi standby data dir (e.g. ~/acr-standby/data)')
    ap.add_argument('dump_sql', nargs='?', help='Optional pre-exported SQL dump file (full mode only)')
    ap.add_argument('--delta', action='store_true',
                    help='Fast incremental sync: fetch only new runs/blobs + small state tables (~1 MiB instead of 80+ MiB)')
    ap.add_argument('--db-name', default='acr-daily', help='Cloudflare D1 database name (default: acr-daily)')
    ap.add_argument('--source-sqlite', help='Optional local SQLite source DB instead of remote wrangler (for testing)')
    args = ap.parse_args()

    out_dir = os.path.abspath(os.path.expanduser(args.data_dir))
    os.makedirs(out_dir, exist_ok=True)
    if args.delta:
        run_delta_export(out_dir, d1_name=args.db_name, source_sqlite=args.source_sqlite)
    else:
        run_full_export(out_dir, dump_arg=args.dump_sql, d1_name=args.db_name)


if __name__ == '__main__':
    main()
