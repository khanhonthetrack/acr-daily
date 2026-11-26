"""Unit tests for the in-cluster GHCR digest GitOps rollout watcher."""
import io
import json
import os
import sys
import unittest
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), 'tools'))

import auto_rollout_watcher as watcher  # noqa: E402
import rollback_to_cloudflare as rb  # noqa: E402
import stage_secrets_on_pi as sec_stage  # noqa: E402


class FakeResponse:
    def __init__(self, body_bytes, headers=None):
        self._buf = io.BytesIO(body_bytes)
        self.headers = headers or {}

    def read(self):
        return self._buf.read()

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


class FakeK8s:
    def __init__(self, initial):
        self.images = dict(initial)
        self.patches = []

    def get_workload_image(self, namespace, kind_plural, name, container_name):
        return self.images.get((namespace, kind_plural, name, container_name), '')

    def patch_workload_image(self, namespace, kind_plural, name, container_name, full_image):
        self.images[(namespace, kind_plural, name, container_name)] = full_image
        self.patches.append((namespace, kind_plural, name, container_name, full_image))
        return {'ok': True}


class AutoRolloutWatcherTest(unittest.TestCase):
    def test_reconcile_rolls_out_new_ghcr_digest_and_skips_when_current(self):
        want_digest = 'sha256:' + ('a1' * 32)

        def fake_opener(req, timeout=10):
            url = req.full_url
            if 'ghcr.io/token' in url:
                return FakeResponse(json.dumps({'token': 'tok-123'}).encode('utf-8'))
            if '/manifests/main' in url:
                return FakeResponse(b'{}', headers={'Docker-Content-Digest': want_digest})
            raise AssertionError('unexpected url: ' + url)

        k8s = FakeK8s({
            ('acr-daily', 'deployments', 'acr-relay', 'relay'): 'old:v1',
            ('acr-daily', 'statefulsets', 'acr-daily', 'server'): 'old:v1',
        })
        targets = watcher.parse_targets('deployments/acr-relay:relay,statefulsets/acr-daily:server')
        changed, note = watcher.reconcile_once(k8s, 'acr-daily', 'khanhonthetrack/acr-daily-server', 'main',
                                               targets, opener=fake_opener)
        self.assertTrue(changed)
        self.assertIn(want_digest, note)
        self.assertEqual(len(k8s.patches), 2)

        # Second check with identical digest performs zero K8s patches
        changed2, note2 = watcher.reconcile_once(k8s, 'acr-daily', 'khanhonthetrack/acr-daily-server', 'main',
                                                 targets, opener=fake_opener)
        self.assertFalse(changed2)
        self.assertIn('up_to_date', note2)
        self.assertEqual(len(k8s.patches), 2)

    def test_unpublished_or_private_ghcr_package_skips_cleanly(self):
        def opener_404(req, timeout=10):
            raise urllib.error.HTTPError(req.full_url, 404, 'Not Found', {}, None)

        k8s = FakeK8s({})
        targets = watcher.parse_targets('deployments/acr-relay:relay')
        changed, note = watcher.reconcile_once(k8s, 'acr-daily', 'khanhonthetrack/acr-daily-server', 'main',
                                               targets, opener=opener_404)
        self.assertFalse(changed)
        self.assertEqual(note, 'no_published_ghcr_image')
        self.assertEqual(k8s.patches, [])

    def test_stage_secrets_encrypt_decrypt_and_tamper_rejection(self):
        key = bytes(range(32))
        orig = {'ADMIN_KEY': 'super-secret-admin-key-123456', 'DISCORD_WEBHOOK_URL': 'https://discord.example/hook'}
        env = sec_stage.encrypt_bundle(key, orig)
        self.assertNotIn('super-secret', json.dumps(env))
        self.assertEqual(sec_stage.decrypt_bundle(key, env), orig)

        # Wrong key or tampered ciphertext must fail MAC verification
        with self.assertRaises(ValueError):
            sec_stage.decrypt_bundle(bytes(reversed(range(32))), env)
        tampered = dict(env, ct='00' + env['ct'][2:])
        with self.assertRaises(ValueError):
            sec_stage.decrypt_bundle(key, tampered)

    def test_rollback_sql_generation_and_replay_preserves_new_gke_runs_and_blobs(self):
        import sqlite3
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            old_d1 = os.path.join(tmp, 'd1.sqlite')
            pi_latest = os.path.join(tmp, 'pi.sqlite')
            ddl = """
                CREATE TABLE players (steam_id TEXT PRIMARY KEY, name TEXT NOT NULL, created INTEGER NOT NULL);
                CREATE TABLE sessions (token_hash TEXT PRIMARY KEY, steam_id TEXT NOT NULL, created INTEGER NOT NULL);
                CREATE TABLE runs (id INTEGER PRIMARY KEY AUTOINCREMENT, steam_id TEXT NOT NULL, status TEXT NOT NULL,
                                   reason TEXT, flags TEXT, trace TEXT);
                CREATE TABLE player_avatars (steam_id TEXT PRIMARY KEY, type TEXT NOT NULL, data BLOB NOT NULL, updated INTEGER NOT NULL);
                CREATE TABLE cache (key TEXT PRIMARY KEY, body TEXT NOT NULL, expires INTEGER NOT NULL);
            """
            c1 = sqlite3.connect(old_d1)
            c1.executescript(ddl)
            c1.execute("INSERT INTO players VALUES ('s1', 'Kenji', 100)")
            c1.execute("INSERT INTO runs (id, steam_id, status, trace) VALUES (1, 's1', 'finished', '[[0,0,0]]')")
            c1.execute("INSERT INTO cache VALUES ('board:1', '{}', 999999)")
            c1.commit()
            c1.close()

            # Simulate GKE having new player O'Brien (SQL quote escaping), new run #2, disqualified run #1, and binary avatar
            c2 = sqlite3.connect(pi_latest)
            c2.executescript(ddl)
            c2.execute("INSERT INTO players VALUES ('s1', 'Kenji', 100)")
            c2.execute("INSERT INTO players VALUES ('s2', 'Liam O''Brien', 200)")
            c2.execute("INSERT INTO sessions VALUES ('tok_hash_2', 's2', 205)")
            c2.execute("INSERT INTO runs (id, steam_id, status, reason, trace) VALUES (1, 's1', 'rejected', 'cut', '[[0,0,0]]')")
            c2.execute("INSERT INTO runs (id, steam_id, status, trace) VALUES (2, 's2', 'finished', '[[10,1,2]]')")
            c2.execute("INSERT INTO player_avatars VALUES ('s2', 'image/png', ?, 300)", (b'\x89PNG\r\n\x1a\n\x00\xff',))
            c2.commit()
            c2.close()

            stmts, stats = rb.build_rollback_sql_statements(
                pi_latest,
                d1_watermarks={'runs': 1, 'player_avatars': 0},
                remote_table_names={'players', 'sessions', 'runs', 'player_avatars', 'cache'},
            )
            self.assertEqual(stats['new_runs'], 1)
            for s in stmts:
                self.assertFalse(s.upper().startswith('BEGIN'))
                self.assertFalse(s.upper().startswith('COMMIT'))

            rb.execute_sql_chunks_on_d1(['npx', 'wrangler'], 'acr-daily', stmts, target_sqlite=old_d1)

            chk = sqlite3.connect(old_d1)
            try:
                players = dict(chk.execute('SELECT steam_id, name FROM players').fetchall())
                self.assertEqual(players, {'s1': 'Kenji', 's2': "Liam O'Brien"})
                runs = chk.execute('SELECT id, status, reason, trace FROM runs ORDER BY id').fetchall()
                self.assertEqual(runs, [(1, 'rejected', 'cut', '[[0,0,0]]'), (2, 'finished', None, '[[10,1,2]]')])
                av = chk.execute("SELECT data FROM player_avatars WHERE steam_id='s2'").fetchone()[0]
                self.assertEqual(av, b'\x89PNG\r\n\x1a\n\x00\xff')
                self.assertEqual(chk.execute('SELECT COUNT(*) FROM cache').fetchone()[0], 0)
            finally:
                chk.close()


if __name__ == '__main__':
    unittest.main()
