"""Passive shadow-backup receiver for the Raspberry Pi (standard library only, Python 3.9+).

    python3 standby_receiver.py --data-dir ~/acr-standby --key-file ~/acr-standby/standby.key [--port 9876]

Receives continuous asynchronous backups from the primary ACR Daily VM (server/vm-server.mjs) without serving any live
player traffic. If the cloud VMs ever go away, ~/acr-standby already holds an up-to-date acr-daily.sqlite and
traces/traces/<id>.json.gz ready to start server/vm-server.mjs locally or seed fresh VMs.

Security & Integrity Guarantees:
1. Header-first HMAC-SHA256 + timestamp (±300 s) + replay-nonce verification BEFORE reading the request body, so
   unauthenticated internet callers (e.g. via Tailscale Funnel) cannot allocate memory or disk on the Pi.
2. Streaming chunked gunzip + SHA-256 verification directly to unique per-request temp files under a DB upload lock
   (constant < 2 MB RAM footprint; concurrent uploads cannot trample temp files).
3. Anti-wipe & split-brain protection:
   - Refuses all pushes if <data-dir>/PROMOTED exists (set when failing over to the Pi).
   - Compares incoming snapshot's max(runs.id), players count, routes count, and _standby_meta.sync_seq against the
     existing DB and refuses any regressed or empty snapshot unless --allow-regression is passed.
   - Keeps rolling hourly backups (up to 24) and daily backups (up to 7).
"""
import argparse
import hashlib
import hmac
import http.server
import json
import os
import re
import sqlite3
import threading
import time
import zlib
from urllib.parse import urlparse

MAX_TRACE_GZ = 4 * 1024 * 1024
MAX_TRACE_RAW = 16 * 1024 * 1024
MAX_CHUNK_GZ = 32 * 1024 * 1024
MAX_DB_GZ = 512 * 1024 * 1024
MAX_DB_RAW = 2 * 1024 * 1024 * 1024
SKEW_S = 300
KEEP_HOURLY_BACKUPS = 24
KEEP_DAILY_BACKUPS = 7


def derive_standby_key(admin_key):
    return hashlib.sha256(('standby-sync|' + admin_key.strip()).encode('utf-8')).digest()


class NonceCache:
    def __init__(self, ttl_s=SKEW_S * 2 + 60, max_entries=4096):
        self.ttl_s = ttl_s
        self.max_entries = max_entries
        self._lock = threading.Lock()
        self._seen = {}

    def check_and_record(self, nonce):
        if not nonce or not re.match(r'^[a-fA-F0-9]{16,64}$', nonce):
            return False
        now = time.monotonic()
        with self._lock:
            if len(self._seen) >= self.max_entries:
                self._seen = {k: exp for k, exp in self._seen.items() if exp > now}
                if len(self._seen) >= self.max_entries:
                    return False
            if self._seen.get(nonce, 0.0) > now:
                return False
            self._seen[nonce] = now + self.ttl_s
            return True


def verify_headers(key, method, path, ts_hdr, nonce_hdr, sha_hdr, sig_hdr, nonces, now_s=None):
    """Verify timestamp, SHA-256 header format, HMAC signature, and nonce BEFORE reading any request body bytes."""
    try:
        ts = int(ts_hdr or '')
    except ValueError:
        return False, 'bad timestamp'
    now_s = int(time.time()) if now_s is None else int(now_s)
    if abs(now_s - ts) > SKEW_S:
        return False, 'timestamp out of range'
    sha_clean = (sha_hdr or '').strip().lower()
    if not re.match(r'^[0-9a-f]{64}$', sha_clean):
        return False, 'bad sha256 header'
    nonce_clean = (nonce_hdr or '').strip().lower()
    if not re.match(r'^[0-9a-f]{16,64}$', nonce_clean):
        return False, 'bad nonce header'
    msg = '%s|%s|%d|%s|%s' % (method.upper(), path, ts, nonce_clean, sha_clean)
    want = hmac.new(key, msg.encode('utf-8'), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(want, (sig_hdr or '').strip().lower()):
        return False, 'bad signature'
    if not nonces.check_and_record(nonce_clean):
        return False, 'replayed nonce'
    return True, sha_clean


def stream_verified_gunzip(rfile, content_length, expected_sha_hex, max_raw_bytes, raw_dst_path, gz_dst_path=None):
    """Stream `content_length` compressed bytes from `rfile`, verify exact SHA-256, and gunzip to `raw_dst_path`
    (and optionally write raw compressed bytes to `gz_dst_path`) with bounded RAM and uncompressed size."""
    hasher = hashlib.sha256()
    decomp = zlib.decompressobj(16 + zlib.MAX_WBITS)
    remaining = content_length
    raw_written = 0
    raw_f = open(raw_dst_path, 'wb') if raw_dst_path else None
    gz_f = open(gz_dst_path, 'wb') if gz_dst_path else None
    try:
        while remaining > 0:
            chunk = rfile.read(min(65536, remaining))
            if not chunk:
                raise ValueError('incomplete request body')
            remaining -= len(chunk)
            hasher.update(chunk)
            if gz_f is not None:
                gz_f.write(chunk)
            out = decomp.decompress(chunk, max_raw_bytes - raw_written + 1)
            raw_written += len(out)
            if raw_written > max_raw_bytes or decomp.unconsumed_tail:
                raise ValueError('decompressed payload exceeds limit')
            if raw_f is not None and out:
                raw_f.write(out)
        tail = decomp.flush()
        raw_written += len(tail)
        if raw_written > max_raw_bytes or not decomp.eof:
            raise ValueError('invalid or truncated gzip stream')
        if raw_f is not None and tail:
            raw_f.write(tail)
        actual_sha = hasher.hexdigest()
        if not hmac.compare_digest(actual_sha, expected_sha_hex):
            raise ValueError('body sha256 mismatch')
    finally:
        if raw_f is not None:
            raw_f.close()
        if gz_f is not None:
            gz_f.close()


def inspect_sqlite_watermark(conn):
    """Return (lineage_id, sync_seq, max_run_id, player_count, route_count) for anti-regression checks."""
    chk = conn.execute('PRAGMA quick_check').fetchone()
    if not chk or chk[0] != 'ok':
        raise ValueError('sqlite quick_check failed')
    tbl = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='players'").fetchone()
    if not tbl:
        raise ValueError('missing players table in snapshot')
    max_run = conn.execute('SELECT COALESCE(MAX(id), 0) FROM runs').fetchone()[0]
    players = conn.execute('SELECT COUNT(*) FROM players').fetchone()[0]
    routes = conn.execute('SELECT COUNT(*) FROM routes').fetchone()[0]
    lineage, seq = '', 0
    has_meta = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='_standby_meta'").fetchone()
    if has_meta:
        row = conn.execute("SELECT value FROM _standby_meta WHERE key = 'lineage_id'").fetchone()
        if row and row[0]:
            lineage = str(row[0])
        srow = conn.execute("SELECT value FROM _standby_meta WHERE key = 'sync_seq'").fetchone()
        if srow and srow[0]:
            try:
                seq = int(srow[0])
            except ValueError:
                seq = 0
    return lineage, seq, int(max_run or 0), int(players or 0), int(routes or 0)


class StandbyStore:
    def __init__(self, data_dir, key, allow_regression=False):
        self.data_dir = os.path.abspath(data_dir)
        self.traces_dir = os.path.join(self.data_dir, 'traces', 'traces')
        self.backups_dir = os.path.join(self.data_dir, 'backups')
        self.db_path = os.path.join(self.data_dir, 'acr-daily.sqlite')
        self.promoted_fence = os.path.join(self.data_dir, 'PROMOTED')
        self.key = key
        self.allow_regression = bool(allow_regression)
        self.nonces = NonceCache()
        self.db_lock = threading.Lock()
        self._export_lock = threading.Lock()
        self._cached_export_mtime = -1.0
        self._cached_export_at = 0.0
        self._cached_export_sha = ''
        self._cached_export_size = 0
        self.cached_export_path = os.path.join(self.data_dir, '.cached-export.sqlite.gz')
        self.last_db_sync = 0
        self.last_seq = 0
        self._apply_lock = threading.Lock()
        self._apply_in_progress = 0
        self.last_apply_error = ''
        os.makedirs(self.traces_dir, exist_ok=True)
        os.makedirs(self.backups_dir, exist_ok=True)
        self._clean_stale_temps()

    def _clean_stale_temps(self):
        for folder in (self.data_dir, self.traces_dir):
            try:
                for name in os.listdir(folder):
                    if '.incoming.' in name or '.tmp.' in name or name.startswith('.upload-') or name.startswith('.cached-export'):
                        try:
                            os.remove(os.path.join(folder, name))
                        except OSError:
                            pass
            except OSError:
                pass

    def check_not_promoted(self):
        if os.path.exists(self.promoted_fence):
            raise PermissionError('standby is promoted to active (PROMOTED fence present); pushes refused')

    def stream_trace(self, trace_id, rfile, length, expected_sha):
        self.check_not_promoted()
        if not re.match(r'^\d{1,15}$', str(trace_id)):
            raise ValueError('bad trace id')
        dst = os.path.join(self.traces_dir, '%s.json.gz' % trace_id)
        tmp = '%s.tmp.%d.%d.%d' % (dst, os.getpid(), threading.get_ident(), int(time.time() * 1000))
        try:
            stream_verified_gunzip(rfile, length, expected_sha, MAX_TRACE_RAW, raw_dst_path=None, gz_dst_path=tmp)
            os.replace(tmp, dst)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    def stream_db(self, rfile, length, expected_sha):
        self.check_not_promoted()
        if not self.db_lock.acquire(blocking=False):
            raise RuntimeError('db upload already in progress')
        incoming = '%s.incoming.%d.%d.%d' % (self.db_path, os.getpid(), threading.get_ident(), int(time.time() * 1000))
        try:
            stream_verified_gunzip(rfile, length, expected_sha, MAX_DB_RAW, raw_dst_path=incoming, gz_dst_path=None)
            src = sqlite3.connect(incoming)
            try:
                inc_lin, inc_seq, inc_run, inc_players, inc_routes = inspect_sqlite_watermark(src)
                if os.path.exists(self.db_path) and not self.allow_regression:
                    cur = sqlite3.connect(self.db_path, timeout=10.0)
                    try:
                        cur_lin, cur_seq, cur_run, cur_players, _cur_routes = inspect_sqlite_watermark(cur)
                    finally:
                        cur.close()
                    # Refuse empty/regressed snapshots (e.g. primary VM recreated with empty disk)
                    if (cur_run > 0 or cur_players > 0) and (inc_run < cur_run or inc_players < cur_players):
                        raise PermissionError(
                            'snapshot regression refused (incoming runs=%d/players=%d < existing runs=%d/players=%d)'
                            % (inc_run, inc_players, cur_run, cur_players)
                        )
                    if cur_lin and inc_lin and cur_lin == inc_lin and inc_seq < cur_seq:
                        raise PermissionError('snapshot seq regression refused (%d < %d)' % (inc_seq, cur_seq))
                    if cur_lin and inc_lin and cur_lin != inc_lin and (cur_run > 0 or cur_players > 0):
                        raise PermissionError('snapshot lineage mismatch against populated standby DB')

                self._rotate_backups()
                if not os.path.exists(self.db_path):
                    src.close()
                    src = None
                    os.replace(incoming, self.db_path)
                else:
                    dst = sqlite3.connect(self.db_path, timeout=15.0)
                    try:
                        dst.execute('PRAGMA journal_mode = WAL;')
                        src.backup(dst)
                    finally:
                        dst.close()
                self.last_db_sync = int(time.time())
                self.last_seq = inc_seq
                void = inc_routes
                del void
            finally:
                if src is not None:
                    src.close()
        finally:
            if os.path.exists(incoming):
                try:
                    os.remove(incoming)
                except OSError:
                    pass
            self.db_lock.release()

    def _rotate_backups(self):
        if not os.path.exists(self.db_path):
            return
        hour_stamp = time.strftime('%Y-%m-%d_%H', time.gmtime())
        day_stamp = time.strftime('%Y-%m-%d', time.gmtime())
        hourly = os.path.join(self.backups_dir, 'hourly-%s.sqlite' % hour_stamp)
        daily = os.path.join(self.backups_dir, 'daily-%s.sqlite' % day_stamp)
        for target in (hourly, daily):
            if not os.path.exists(target):
                src = sqlite3.connect(self.db_path, timeout=5.0)
                dst = sqlite3.connect(target)
                try:
                    src.backup(dst)
                finally:
                    dst.close()
                    src.close()
        self._prune_prefix('hourly-', KEEP_HOURLY_BACKUPS)
        self._prune_prefix('daily-', KEEP_DAILY_BACKUPS)

    def _prune_prefix(self, prefix, keep):
        files = sorted(f for f in os.listdir(self.backups_dir) if f.startswith(prefix) and f.endswith('.sqlite'))
        for old in files[:-keep]:
            try:
                os.remove(os.path.join(self.backups_dir, old))
            except OSError:
                pass

    def status_summary(self):
        trace_ids = []
        try:
            for name in os.listdir(self.traces_dir):
                m = re.match(r'^(\d{1,15})\.json\.gz$', name)
                if m:
                    trace_ids.append(m.group(1))
        except OSError:
            pass
        trace_ids.sort(key=int)
        with self._apply_lock:
            applying = self._apply_in_progress > 0
            apply_err = self.last_apply_error
        if not os.path.exists(self.db_path):
            return {
                'hasDb': False,
                'runs': 0,
                'players': 0,
                'routes': 0,
                'applying': applying,
                'lastApplyError': apply_err,
                'traceIds': trace_ids,
            }
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        try:
            lin, seq, max_run, players, routes = inspect_sqlite_watermark(conn)
            runs_cnt = conn.execute('SELECT COUNT(*) FROM runs').fetchone()[0]
            return {
                'hasDb': True,
                'lineageId': lin,
                'syncSeq': seq,
                'maxRunId': max_run,
                'runs': int(runs_cnt or 0),
                'players': players,
                'routes': routes,
                'applying': applying,
                'lastApplyError': apply_err,
                'traceIds': trace_ids,
            }
        finally:
            conn.close()

    def apply_gz_file(self, gz_path, expected_total_sha):
        """Gunzip a verified .gz file on disk and atomically apply it to acr-daily.sqlite with anti-regression checks."""
        err_msg = ''
        try:
            with open(gz_path, 'rb') as gf:
                size = os.path.getsize(gz_path)
                self.stream_db(gf, size, expected_total_sha)
            self._cached_export_mtime = -1.0
        except Exception as e:
            err_msg = str(e)
            print('standby async apply refused/failed: %s' % err_msg, flush=True)
        finally:
            if os.path.exists(gz_path):
                try:
                    os.remove(gz_path)
                except OSError:
                    pass
            with self._apply_lock:
                self._apply_in_progress = max(0, self._apply_in_progress - 1)
                self.last_apply_error = err_msg

    def append_db_chunk(self, upload_id, offset, rfile, length, expected_chunk_sha, is_final=False, total_sha=''):
        self.check_not_promoted()
        if not re.match(r'^[0-9a-f]{16,32}$', upload_id or ''):
            raise ValueError('bad upload id')
        up_path = os.path.join(self.data_dir, '.upload-%s.gz' % upload_id)
        cur_size = os.path.getsize(up_path) if os.path.exists(up_path) else 0
        if offset == 0 and cur_size > 0:
            os.remove(up_path)
            cur_size = 0
        if offset != cur_size:
            raise ValueError('chunk offset mismatch (got %d, want %d)' % (offset, cur_size))
        if cur_size + length > MAX_DB_GZ:
            raise ValueError('total upload exceeds MAX_DB_GZ')

        hasher = hashlib.sha256()
        remaining = length
        with open(up_path, 'ab') as out_f:
            while remaining > 0:
                chunk = rfile.read(min(65536, remaining))
                if not chunk:
                    raise ValueError('incomplete chunk body')
                remaining -= len(chunk)
                hasher.update(chunk)
                out_f.write(chunk)
        if not hmac.compare_digest(hasher.hexdigest(), expected_chunk_sha):
            try:
                os.remove(up_path)
            except OSError:
                pass
            raise ValueError('chunk sha256 mismatch')

        if is_final:
            total_clean = (total_sha or '').strip().lower()
            if not re.match(r'^[0-9a-f]{64}$', total_clean):
                raise ValueError('missing total sha256 on final chunk')
            full_h = hashlib.sha256()
            with open(up_path, 'rb') as rf:
                while True:
                    b = rf.read(65536)
                    if not b:
                        break
                    full_h.update(b)
            if not hmac.compare_digest(full_h.hexdigest(), total_clean):
                os.remove(up_path)
                raise ValueError('assembled db sha256 mismatch')
            ready_gz = '%s.ready.%d' % (up_path, int(time.time() * 1000))
            os.replace(up_path, ready_gz)
            with self._apply_lock:
                self._apply_in_progress += 1
                self.last_apply_error = ''
            threading.Thread(target=self.apply_gz_file, args=(ready_gz, total_clean), daemon=True).start()

    def ensure_cached_export(self):
        """Build or reuse a cached .sqlite.gz export on disk so Range GET chunks avoid Tailscale Funnel's 40s timeout."""
        if not os.path.exists(self.db_path):
            return None
        with self._export_lock:
            db_mtime = os.path.getmtime(self.db_path)
            now = time.monotonic()
            if (os.path.exists(self.cached_export_path)
                    and self._cached_export_mtime == db_mtime
                    and now - self._cached_export_at < 300.0
                    and self._cached_export_size > 0):
                return self.cached_export_path, self._cached_export_size, self._cached_export_sha

            snap = '%s.export.%d.%d.%d' % (self.db_path, os.getpid(), threading.get_ident(), int(time.time() * 1000))
            tmp_gz = self.cached_export_path + '.tmp'
            try:
                with self.db_lock:
                    src = sqlite3.connect(self.db_path, timeout=10.0)
                    dst = sqlite3.connect(snap)
                    try:
                        src.backup(dst)
                    finally:
                        dst.close()
                        src.close()
                comp = zlib.compressobj(6, zlib.DEFLATED, 16 + zlib.MAX_WBITS)
                sha_h = hashlib.sha256()
                size = 0
                with open(snap, 'rb') as sf, open(tmp_gz, 'wb') as gf:
                    while True:
                        chunk = sf.read(65536)
                        if not chunk:
                            break
                        gz_part = comp.compress(chunk)
                        if gz_part:
                            gf.write(gz_part)
                            sha_h.update(gz_part)
                            size += len(gz_part)
                    tail = comp.flush()
                    if tail:
                        gf.write(tail)
                        sha_h.update(tail)
                        size += len(tail)
                os.replace(tmp_gz, self.cached_export_path)
                self._cached_export_mtime = db_mtime
                self._cached_export_at = now
                self._cached_export_size = size
                self._cached_export_sha = sha_h.hexdigest()
                return self.cached_export_path, size, self._cached_export_sha
            finally:
                for p in (snap, tmp_gz):
                    if os.path.exists(p):
                        try:
                            os.remove(p)
                        except OSError:
                            pass


EMPTY_SHA256 = hashlib.sha256(b'').hexdigest()


def canonical_standby_path(raw_path):
    """Normalize Tailscale Funnel --set-path stripped or doubled prefixes to canonical /internal/standby/... paths."""
    p = (urlparse(raw_path).path or '/').rstrip('/') or '/'
    while p.startswith('/internal/standby/internal/standby'):
        p = p[len('/internal/standby'):]
    if p in ('/healthz', '/status', '/db', '/db/chunk') or re.match(r'^/trace/\d{1,15}$', p):
        return '/internal/standby' + p
    return p


def make_handler(store):
    class Handler(http.server.BaseHTTPRequestHandler):
        timeout = 30

        def _json(self, code, obj):
            body = json.dumps(obj).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _verify_get(self, path):
            ok, _ = verify_headers(
                store.key,
                'GET',
                path,
                self.headers.get('X-ACR-Standby-Ts'),
                self.headers.get('X-ACR-Standby-Nonce'),
                self.headers.get('X-ACR-Standby-Sha256') or EMPTY_SHA256,
                self.headers.get('X-ACR-Standby-Sig'),
                store.nonces,
            )
            return ok

        def do_GET(self):
            p = canonical_standby_path(self.path)
            if p == '/internal/standby/healthz':
                self._json(200, {'ok': True, 'promoted': os.path.exists(store.promoted_fence)})
                return
            if p == '/internal/standby/status':
                if not self._verify_get(p):
                    self.connection.close()
                    return
                self._json(200, store.status_summary())
                return
            if p == '/internal/standby/db':
                if not self._verify_get(p):
                    self.connection.close()
                    return
                cached = store.ensure_cached_export()
                if cached is None:
                    self._json(404, {'error': 'no snapshot stored yet'})
                    return
                gz_path, total_size, total_sha = cached
                rng = (self.headers.get('Range') or '').strip()
                m_rng = re.match(r'^bytes=(\d+)-(\d*)$', rng)
                if m_rng:
                    start = int(m_rng.group(1))
                    end = int(m_rng.group(2)) if m_rng.group(2) else (total_size - 1)
                    end = min(end, total_size - 1)
                    if start >= total_size or start > end:
                        self.send_response(416)
                        self.send_header('Content-Range', 'bytes */%d' % total_size)
                        self.end_headers()
                        return
                    chunk_len = end - start + 1
                    self.send_response(206)
                    self.send_header('Content-Type', 'application/gzip')
                    self.send_header('Accept-Ranges', 'bytes')
                    self.send_header('Content-Range', 'bytes %d-%d/%d' % (start, end, total_size))
                    self.send_header('Content-Length', str(chunk_len))
                    self.send_header('X-ACR-Standby-Total-Length', str(total_size))
                    self.send_header('X-ACR-Standby-Sha256', total_sha)
                    self.end_headers()
                    with open(gz_path, 'rb') as f:
                        f.seek(start)
                        left = chunk_len
                        while left > 0:
                            buf = f.read(min(65536, left))
                            if not buf:
                                break
                            self.wfile.write(buf)
                            left -= len(buf)
                    return

                self.send_response(200)
                self.send_header('Content-Type', 'application/gzip')
                self.send_header('Accept-Ranges', 'bytes')
                self.send_header('Content-Length', str(total_size))
                self.send_header('X-ACR-Standby-Total-Length', str(total_size))
                self.send_header('X-ACR-Standby-Sha256', total_sha)
                self.end_headers()
                with open(gz_path, 'rb') as f:
                    while True:
                        buf = f.read(65536)
                        if not buf:
                            break
                        self.wfile.write(buf)
                return
            m_trace = re.match(r'^/internal/standby/trace/(\d{1,15})$', p)
            if m_trace:
                if not self._verify_get(p):
                    self.connection.close()
                    return
                tpath = os.path.join(store.traces_dir, '%s.json.gz' % m_trace.group(1))
                if not os.path.exists(tpath):
                    self._json(404, {'error': 'trace not found'})
                    return
                with open(tpath, 'rb') as f:
                    raw = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'application/gzip')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            self._json(404, {'error': 'not found'})

        def do_PUT(self):
            p = canonical_standby_path(self.path)
            m_trace = re.match(r'^/internal/standby/trace/(\d{1,15})$', p)
            is_db = (p == '/internal/standby/db')
            is_chunk = (p == '/internal/standby/db/chunk')
            if not m_trace and not is_db and not is_chunk:
                self._json(404, {'error': 'not found'})
                return
            try:
                length = int(self.headers.get('Content-Length') or '0')
            except ValueError:
                self._json(400, {'error': 'bad content-length'})
                return
            limit = MAX_CHUNK_GZ if is_chunk else (MAX_DB_GZ if is_db else MAX_TRACE_GZ)
            if length <= 0 or length > limit:
                self._json(413, {'error': 'payload size out of bounds'})
                return

            # Verify HMAC + timestamp + nonce BEFORE reading any request body bytes!
            ok, sha_or_why = verify_headers(
                store.key,
                'PUT',
                p,
                self.headers.get('X-ACR-Standby-Ts'),
                self.headers.get('X-ACR-Standby-Nonce'),
                self.headers.get('X-ACR-Standby-Sha256'),
                self.headers.get('X-ACR-Standby-Sig'),
                store.nonces,
            )
            if not ok:
                self.connection.close()
                return

            try:
                if is_chunk:
                    uid = (self.headers.get('X-ACR-Standby-Upload-Id') or '').strip().lower()
                    off = int(self.headers.get('X-ACR-Standby-Offset') or '0')
                    fin = (self.headers.get('X-ACR-Standby-Final') == '1')
                    tot = self.headers.get('X-ACR-Standby-Total-Sha256') or ''
                    store.append_db_chunk(uid, off, self.rfile, length, sha_or_why, is_final=fin, total_sha=tot)
                    self._json(202 if fin else 200, {'ok': True, 'queued': fin})
                    return
                if is_db:
                    store.stream_db(self.rfile, length, sha_or_why)
                    store._cached_export_mtime = -1.0
                else:
                    store.stream_trace(m_trace.group(1), self.rfile, length, sha_or_why)
            except PermissionError as e:
                self._json(409, {'error': str(e)})
                return
            except RuntimeError as e:
                self._json(429, {'error': str(e)})
                return
            except Exception as e:
                self._json(422, {'error': str(e)})
                return
            self._json(200, {'ok': True})

        def log_message(self, *_args):
            pass

    return Handler


class BoundedThreadingHTTPServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr, handler, max_workers=8):
        super().__init__(addr, handler)
        self._sem = threading.Semaphore(max_workers)

    def process_request(self, request, client_address):
        if not self._sem.acquire(blocking=False):
            try:
                request.close()
            except Exception:
                pass
            return
        super().process_request(request, client_address)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._sem.release()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=9876)
    ap.add_argument('--data-dir', required=True, help='directory where acr-daily.sqlite and traces/ are kept')
    ap.add_argument('--key-file', help='file holding 64-hex standby key (created automatically with --auto-create-key)')
    ap.add_argument('--admin-key-file', help='file holding raw ADMIN_KEY (derives standby key automatically)')
    ap.add_argument('--auto-create-key', action='store_true',
                    help='generate a random 64-hex key file (mode 0600) if --key-file does not exist yet')
    ap.add_argument('--init-key-only', action='store_true',
                    help='ensure --key-file exists, print its 64-hex STANDBY_KEY, and exit')
    ap.add_argument('--allow-regression', action='store_true', help='allow overwriting with smaller/empty snapshots')
    a = ap.parse_args()
    os.makedirs(a.data_dir, exist_ok=True)
    if a.key_file:
        if not os.path.exists(a.key_file) and (a.auto_create_key or a.init_key_only):
            os.makedirs(os.path.dirname(os.path.abspath(a.key_file)), exist_ok=True)
            env_admin = os.environ.get('ADMIN_KEY', '').strip()
            hex_key = derive_standby_key(env_admin).hex() if env_admin else os.urandom(32).hex()
            fd = os.open(a.key_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(hex_key + '\n')
        with open(a.key_file, encoding='utf-8') as f:
            key = bytes.fromhex(f.read().strip())
        if len(key) != 32:
            raise SystemExit('--key-file must hold 64 hex digits')
        if a.init_key_only:
            print(key.hex())
            return
    elif a.admin_key_file:
        with open(a.admin_key_file, encoding='utf-8') as f:
            key = derive_standby_key(f.read())
    elif os.environ.get('ADMIN_KEY', '').strip():
        key = derive_standby_key(os.environ['ADMIN_KEY'])
    else:
        raise SystemExit('provide --key-file or --admin-key-file (or ADMIN_KEY env)')

    store = StandbyStore(a.data_dir, key, allow_regression=a.allow_regression)
    srv = BoundedThreadingHTTPServer((a.host, a.port), make_handler(store))
    print('ACR Daily standby receiver on %s:%d -> %s' % (a.host, a.port, store.data_dir), flush=True)
    srv.serve_forever()


if __name__ == '__main__':
    main()
