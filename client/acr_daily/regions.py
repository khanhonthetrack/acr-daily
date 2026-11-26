"""Automatic lowest-RTT regional server & live-relay selection with Raspberry Pi fallback.

Standard library only (no tkinter import) so headless tests and background threads run cleanly.
Measures true steady-state HTTP RTT using a keep-alive probe on /healthz (1 warmup request + min of 2 timed warm
requests), caches bundled _regions.json once in memory, tracks API and Relay health independently, applies hysteresis
so minor jitter never causes flip-flopping, never switches an active WebSocket mid-stage, and fails back to the best
region once off-stage.
"""
import http.client
import json
import os
import ssl
import threading
import time
from urllib.parse import urlparse

FALLBACK_PI_RELAY = 'wss://immich.tail0d617f.ts.net:10000/live'

DEFAULT_REGIONS = (
    {
        'id': 'eu',
        'label': 'Central Europe',
        'api': 'https://acrdaily-eu.34-49-33-253.sslip.io',
        'relay': 'wss://acrdaily-eu.34-49-33-253.sslip.io/live',
    },
    {
        'id': 'uk',
        'label': 'UK',
        'api': 'https://acrdaily-uk.34-117-213-59.sslip.io',
        'relay': 'wss://acrdaily-uk.34-117-213-59.sslip.io/live',
    },
    {
        'id': 'jp',
        'label': 'Japan',
        'api': 'https://acrdaily-jp.136-82-36-100.sslip.io',
        'relay': 'wss://acrdaily-jp.136-82-36-100.sslip.io/live',
    },
)

REGION_CHOICES = (
    ('auto', 'AUTO'),
    ('eu', 'EU'),
    ('uk', 'UK'),
    ('jp', 'JP'),
)

PROBE_INTERVAL_S = 180.0
DEAD_COOLDOWN_S = 45.0
HYSTERESIS_MS = 12.0

_BUNDLED_REGIONS = None


def _norm_regions(items):
    out = []
    for r in items or ():
        if not isinstance(r, dict) or not r.get('id'):
            continue
        out.append({
            'id': str(r['id']).strip().lower(),
            'label': str(r.get('label') or r.get('name') or r['id']).strip(),
            'api': str(r.get('api') or '').strip().rstrip('/'),
            'relay': str(r.get('relay') or '').strip(),
        })
    return out


def _bundled_regions():
    global _BUNDLED_REGIONS
    if _BUNDLED_REGIONS is not None:
        return _BUNDLED_REGIONS
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_regions.json')
    try:
        with open(cfg_path, encoding='utf-8') as f:
            _BUNDLED_REGIONS = tuple(_norm_regions(json.load(f)))
    except (OSError, ValueError):
        _BUNDLED_REGIONS = DEFAULT_REGIONS
    return _BUNDLED_REGIONS


def load_configured_regions():
    """Regions from ACR_DAILY_REGIONS (JSON), cached _regions.json, or DEFAULT_REGIONS."""
    env_raw = os.environ.get('ACR_DAILY_REGIONS')
    if env_raw is not None:
        env_raw = env_raw.strip()
        if not env_raw or env_raw.lower() in ('off', 'none', '0'):
            return ()
        try:
            return tuple(_norm_regions(json.loads(env_raw)))
        except ValueError:
            return DEFAULT_REGIONS
    return _bundled_regions()


def probe_rtt_ms(api_url, timeout=2.5):
    """Measure warm keep-alive GET /healthz RTT in ms (min of 2 warm samples), or None if unhealthy."""
    if not api_url:
        return None
    u = urlparse(api_url)
    if u.scheme not in ('http', 'https') or not u.hostname:
        return None
    port = u.port or (443 if u.scheme == 'https' else 80)
    base_path = (u.path or '').rstrip('/')
    path = base_path + '/healthz'
    conn = None
    try:
        if u.scheme == 'https':
            conn = http.client.HTTPSConnection(u.hostname, port, timeout=timeout, context=ssl.create_default_context())
        else:
            conn = http.client.HTTPConnection(u.hostname, port, timeout=timeout)
        # 1st request: warm up DNS + TCP + TLS + verify /healthz returns 200 {"ok": true}
        conn.request('GET', path, headers={'Connection': 'keep-alive', 'User-Agent': 'ACR-Daily-RTT'})
        r1 = conn.getresponse()
        b1 = r1.read(4096)
        if r1.status != 200:
            return None
        try:
            if not json.loads(b1.decode('utf-8')).get('ok'):
                return None
        except ValueError:
            return None
        # 2 warm samples on the open socket -> take best to filter single-packet jitter
        samples = []
        for last in (False, True):
            t0 = time.monotonic()
            conn.request('GET', path, headers={
                'Connection': 'close' if last else 'keep-alive',
                'User-Agent': 'ACR-Daily-RTT',
            })
            resp = conn.getresponse()
            resp.read(4096)
            if resp.status == 200:
                samples.append((time.monotonic() - t0) * 1000.0)
        return min(samples) if samples else None
    except Exception:
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


class RegionSelector:
    """Thread-safe RTT prober and independent API / Relay failover ranker."""

    def __init__(self, regions=None, probe_fn=probe_rtt_ms):
        self._regions_override = regions
        self._probe_fn = probe_fn
        self._lock = threading.Lock()
        self._rtts = {}                 # region_id -> float rtt_ms
        self._dead_api_until = {}       # region_id -> monotonic timestamp
        self._dead_relay_until = {}     # region_id -> monotonic timestamp
        self._chosen_auto = None        # sticky auto choice (with HYSTERESIS_MS)
        self._last_probe = 0.0
        self._probing = False

    def regions(self):
        if self._regions_override is not None:
            return tuple(self._regions_override)
        return load_configured_regions()

    def probe_sync(self):
        """Synchronously probe all regions in parallel and update RTT rankings."""
        regs = [r for r in self.regions() if r.get('api')]
        if not regs:
            return {}
        results = {}
        res_lock = threading.Lock()

        def one(reg):
            ms = self._probe_fn(reg['api'])
            with res_lock:
                results[reg['id']] = ms

        threads = [threading.Thread(target=one, args=(r,), daemon=True) for r in regs]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=4.0)

        now = time.monotonic()
        with self._lock:
            self._rtts = {rid: ms for rid, ms in results.items() if ms is not None}
            for rid, ms in results.items():
                if ms is not None:
                    self._dead_api_until.pop(rid, None)
                else:
                    self._dead_api_until[rid] = now + DEAD_COOLDOWN_S
            if self._rtts:
                best_id = min(self._rtts, key=self._rtts.get)
                cur = self._chosen_auto
                if cur not in self._rtts or self._rtts[best_id] + HYSTERESIS_MS < self._rtts[cur]:
                    self._chosen_auto = best_id
            else:
                self._chosen_auto = None
            self._last_probe = now
            return dict(self._rtts)

    def ensure_fresh(self, max_age_s=PROBE_INTERVAL_S):
        """Trigger a non-blocking background RTT probe if results are missing or stale."""
        now = time.monotonic()
        with self._lock:
            if self._probing or (self._last_probe > 0 and now - self._last_probe < max_age_s):
                return
            self._probing = True

        def bg():
            try:
                self.probe_sync()
            finally:
                with self._lock:
                    self._probing = False

        threading.Thread(target=bg, daemon=True).start()

    def mark_api_failed(self, url_or_id):
        self._mark_kind_failed(url_or_id, relay=False)

    def mark_relay_failed(self, url_or_id):
        self._mark_kind_failed(url_or_id, relay=True)

    def mark_failed(self, url_or_id):
        target = (url_or_id or '').rstrip('/')
        self._mark_kind_failed(target, relay=target.startswith(('ws://', 'wss://')))

    def _mark_kind_failed(self, url_or_id, relay=False):
        target = (url_or_id or '').rstrip('/')
        now = time.monotonic()
        with self._lock:
            dead_map = self._dead_relay_until if relay else self._dead_api_until
            for r in self.regions():
                if target in (r['id'], r.get('api', '').rstrip('/'), r.get('relay', '').rstrip('/')):
                    dead_map[r['id']] = now + DEAD_COOLDOWN_S
                    if not relay:
                        self._rtts.pop(r['id'], None)
                        if self._chosen_auto == r['id']:
                            self._chosen_auto = min(self._rtts, key=self._rtts.get) if self._rtts else None

    def _ordered_regions(self, mode='auto', for_relay=False):
        regs = list(self.regions())
        if not regs:
            return []
        mode = (mode or 'auto').strip().lower()
        now = time.monotonic()
        with self._lock:
            rtts = dict(self._rtts)
            dead_src = self._dead_relay_until if for_relay else self._dead_api_until
            dead = {k for k, until in dead_src.items() if until > now}
            chosen = self._chosen_auto

        healthy = [r for r in regs if r['id'] not in dead]
        unhealthy = [r for r in regs if r['id'] in dead]

        def sort_key(r):
            rid = r['id']
            if mode == rid:
                return (-2, 0.0)
            if mode == 'auto' and rid == chosen:
                return (-1, rtts.get(rid, 9999.0))
            return (0 if rid in rtts else 1, rtts.get(rid, 9999.0))

        healthy.sort(key=sort_key)
        unhealthy.sort(key=lambda r: (0 if r['id'] == mode else 1))
        return healthy + unhealthy

    def relay_candidates(self, mode='auto', custom_relay='', default_pi_relay=FALLBACK_PI_RELAY, background_probe=True):
        """Ordered WebSocket relay URLs to try, always ending with the Raspberry Pi fallback."""
        env_live = (os.environ.get('ACR_DAILY_LIVE_SERVER') or '').strip()
        if env_live:
            return [env_live]
        custom = (custom_relay or '').strip()
        if custom and custom != default_pi_relay:
            return [custom]
        mode = (mode or 'auto').strip().lower()
        if mode == 'pi':
            return [default_pi_relay] if default_pi_relay else []
        if background_probe:
            self.ensure_fresh()
        urls = []
        for r in self._ordered_regions(mode, for_relay=True):
            u = r.get('relay') or ''
            if u and u not in urls:
                urls.append(u)
        if default_pi_relay and default_pi_relay not in urls:
            urls.append(default_pi_relay)
        return urls

    def api_candidates(self, settings_dict, default_server='', background_probe=True):
        """Ordered HTTP API base URLs to try, preserving explicit env / settings.json overrides."""
        s = settings_dict or {}
        env_srv = (os.environ.get('ACR_DAILY_SERVER') or '').strip().rstrip('/')
        if env_srv and os.environ.get('ACR_DAILY_MULTIREGION') != '1':
            return [env_srv]
        explicit = (s.get('server') or '').strip().rstrip('/')
        if explicit and os.environ.get('ACR_DAILY_MULTIREGION') != '1':
            return [explicit]
        default_srv = (env_srv or explicit or default_server or '').strip().rstrip('/')
        regs = self.regions()
        reg_apis = {r.get('api', '').rstrip('/') for r in regs if r.get('api')}
        official_multiregion = default_srv in reg_apis or default_srv == 'https://acrdaily.com'
        multi_on = bool(s.get('useRegionalApi') or os.environ.get('ACR_DAILY_MULTIREGION') == '1' or official_multiregion)
        if not multi_on:
            return [default_srv] if default_srv else []
        if background_probe:
            self.ensure_fresh()
        mode = (s.get('region') or (s.get('ghostCars') or {}).get('region') or 'auto').strip().lower()
        urls = []
        for r in self._ordered_regions(mode, for_relay=False):
            u = (r.get('api') or '').rstrip('/')
            if u and u not in urls:
                urls.append(u)
        if default_srv and default_srv not in urls:
            urls.append(default_srv)
        return urls

    def summary_for_url(self, url):
        """Short label like 'EU (14 ms)' or 'RPi' for UI status."""
        u = (url or '').rstrip('/')
        if not u:
            return ''
        with self._lock:
            rtts = dict(self._rtts)
        for r in self.regions():
            if u in (r.get('relay', '').rstrip('/'), r.get('api', '').rstrip('/')):
                ms = rtts.get(r['id'])
                tag = r['id'].upper()
                return '%s (%d ms)' % (tag, round(ms)) if ms is not None else tag
        if u == FALLBACK_PI_RELAY.rstrip('/'):
            return 'RPi'
        return ''


DEFAULT_SELECTOR = RegionSelector()
