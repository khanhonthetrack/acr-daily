import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { copyFileSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import http from 'node:http';
import net from 'node:net';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';

import { deriveStandbyKey, isDurableMutationSql, signStandbyRequest, startVmServer } from '../vm-server.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const STANDBY_SCRIPT = resolve(HERE, '..', '..', 'live', 'standby_receiver.py');
const DELTA_EXPORT_SCRIPT = resolve(HERE, '..', '..', 'tools', 'export_d1_to_pi.py');

function freePort() {
  return new Promise((res, rej) => {
    const s = net.createServer();
    s.listen(0, '127.0.0.1', () => {
      const p = s.address().port;
      s.close((err) => (err ? rej(err) : res(p)));
    });
  });
}

function rawGetStatus(port, rawPath) {
  return new Promise((resolveCode, rejectErr) => {
    const req = http.request({ host: '127.0.0.1', port, method: 'GET', path: rawPath }, (res) => {
      res.resume();
      res.on('end', () => resolveCode(res.statusCode));
    });
    req.on('error', rejectErr);
    req.end();
  });
}

async function waitReady(url, timeoutMs = 5000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const r = await fetch(url);
      if (r.ok) return;
    } catch { /* retry */ }
    await new Promise((r) => setTimeout(r, 40));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

test('isDurableMutationSql ignores SELECTs, CTEs, and ephemeral live tables', () => {
  assert.equal(isDurableMutationSql('SELECT * FROM runs'), false);
  assert.equal(isDurableMutationSql('WITH t AS (SELECT 1) SELECT * FROM t'), false);
  assert.equal(isDurableMutationSql('DELETE FROM live WHERE updated < ?'), false);
  assert.equal(isDurableMutationSql('INSERT OR REPLACE INTO event_live (event_id) VALUES (?)'), false);
  assert.equal(isDurableMutationSql('UPDATE tt_live SET x = 1'), false);
  assert.equal(isDurableMutationSql('INSERT INTO casual_signals (lobby_id, from_id, to_id, data, updated) VALUES (?, ?, ?, ?, ?)'), false);
  assert.equal(isDurableMutationSql('DELETE FROM casual_signals WHERE lobby_id = ?'), false);
  assert.equal(isDurableMutationSql('INSERT INTO runs (date) VALUES (?)'), true);
  assert.equal(isDurableMutationSql('UPDATE players SET name = ? RETURNING steam_id'), true);
});

test('vm-server refuses weak ADMIN_KEY in production mode', async () => {
  await assert.rejects(
    () => startVmServer({
      role: 'primary',
      host: '127.0.0.1',
      port: 0,
      disableCron: true,
      disableLiveRelay: true,
      env: { DATA_DIR: ':memory:', ADMIN_KEY: 'dev', DEV_LOGIN: '0' },
    }),
    /strong ADMIN_KEY/,
  );
});

test('vm-server primary + hardened edge + anti-wipe Raspberry Pi standby failover', async () => {
  const workDir = mkdtempSync(join(tmpdir(), 'acr-vm-test-'));
  const primaryData = join(workDir, 'primary');
  const wipedPrimaryData = join(workDir, 'wiped-primary');
  const standbyData = join(workDir, 'rpi-standby');
  const adminKey = 'test-super-secret-admin-key-9876543210';
  const standbyKey = deriveStandbyKey(adminKey);
  const keyFile = join(workDir, 'standby.key');
  writeFileSync(keyFile, standbyKey.toString('hex') + '\n');

  const standbyPort = await freePort();
  const standbyProc = spawn('python3', [
    STANDBY_SCRIPT,
    '--host', '127.0.0.1',
    '--port', String(standbyPort),
    '--data-dir', standbyData,
    '--key-file', keyFile,
  ], { stdio: 'pipe' });

  let primary = null;
  let edge = null;
  let wipedPrimary = null;
  let recovered = null;

  try {
    await waitReady(`http://127.0.0.1:${standbyPort}/healthz`);

    // 1. Forged & replayed standby requests are rejected before body processing
    await assert.rejects(
      () => fetch(`http://127.0.0.1:${standbyPort}/internal/standby/trace/1`, {
        method: 'PUT',
        headers: {
          'X-ACR-Standby-Ts': String(Math.floor(Date.now() / 1000)),
          'X-ACR-Standby-Nonce': '00112233445566778899aabb',
          'X-ACR-Standby-Sha256': '00'.repeat(32),
          'X-ACR-Standby-Sig': '11'.repeat(32),
        },
        body: new Uint8Array([1, 2, 3]),
      }),
    );

    const gzTrace = gzipSync(Buffer.from('[[0,0,0,100,0]]'));
    const nowSec = Math.floor(Date.now() / 1000);
    const validSig = signStandbyRequest(standbyKey, 'PUT', '/internal/standby/trace/999', nowSec, gzTrace, 'abcdef0123456789abcdef01');
    const firstTrace = await fetch(`http://127.0.0.1:${standbyPort}/internal/standby/trace/999`, {
      method: 'PUT',
      headers: {
        'X-ACR-Standby-Ts': validSig.ts,
        'X-ACR-Standby-Nonce': validSig.nonce,
        'X-ACR-Standby-Sha256': validSig.sha256,
        'X-ACR-Standby-Sig': validSig.sig,
      },
      body: gzTrace,
    });
    assert.equal(firstTrace.status, 200);

    // Replaying exact same signed header+nonce within ±300s window is dropped
    await assert.rejects(
      () => fetch(`http://127.0.0.1:${standbyPort}/internal/standby/trace/999`, {
        method: 'PUT',
        headers: {
          'X-ACR-Standby-Ts': validSig.ts,
          'X-ACR-Standby-Nonce': validSig.nonce,
          'X-ACR-Standby-Sha256': validSig.sha256,
          'X-ACR-Standby-Sig': validSig.sig,
        },
        body: gzTrace,
      }),
    );

    // 2. Start Primary (EU) and Edge (JP)
    primary = await startVmServer({
      role: 'primary',
      region: 'eu',
      host: '127.0.0.1',
      port: 0,
      seedRoutes: false,
      disableCron: true,
      disableLiveRelay: true,
      standbyUrl: `http://127.0.0.1:${standbyPort}`,
      standbyIntervalMs: 60_000,
      standbyChunkBytes: 1024,
      env: {
        DATA_DIR: primaryData,
        ADMIN_KEY: adminKey,
        DEV_LOGIN: '1',
        MIN_APP_VERSION: '0.1.8',
        OFFICIAL_FROM: '',
        EU_API_URL: 'https://eu.example',
        JP_API_URL: 'https://jp.example',
      },
    });

    edge = await startVmServer({
      role: 'edge',
      region: 'jp',
      host: '127.0.0.1',
      port: 0,
      primaryUrl: `http://127.0.0.1:${primary.port}`,
      disableLiveRelay: true,
      env: {
        DATA_DIR: ':memory:',
        ADMIN_KEY: adminKey,
        EU_API_URL: 'https://eu.example',
        JP_API_URL: 'https://jp.example',
      },
    });

    // 3. Edge SSRF guard rejects scheme-relative //attacker paths with 400
    assert.equal(await rawGetStatus(edge.port, '//127.0.0.1:9/ssrf'), 400);
    assert.equal(await rawGetStatus(primary.port, '//127.0.0.1:9/ssrf'), 400);

    // 4. Upload routes + submit run via Edge
    const pts = Array.from({ length: 120 }, (_, i) => [i * 25, 0]);
    for (const track of ['Test Stage 1', 'Test Stage 2']) {
      const routeRes = await fetch(`http://127.0.0.1:${edge.port}/api/admin/route`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${adminKey}`,
          Origin: `http://127.0.0.1:${edge.port}`,
        },
        body: JSON.stringify({ track, points: pts }),
      });
      assert.equal(routeRes.status, 200);
      await fetch(`http://127.0.0.1:${edge.port}/api/admin/pool`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${adminKey}` },
        body: JSON.stringify({ track, car: '*' }),
      });
    }

    const ch1 = await fetch(`http://127.0.0.1:${edge.port}/api/challenges/today`);
    assert.equal(ch1.status, 200);
    assert.match(ch1.headers.get('x-acr-edge-cache') || '', /^MISS/);
    const todayData = await ch1.json();

    // Language cookie `lang=pl` does NOT collide with `lang=en` cache entry
    const chEn = await fetch(`http://127.0.0.1:${edge.port}/api/challenges/today`, { headers: { Cookie: 'lang=en' } });
    assert.match(chEn.headers.get('x-acr-edge-cache') || '', /^MISS/);
    const chEnHit = await fetch(`http://127.0.0.1:${edge.port}/api/challenges/today`, { headers: { Cookie: 'lang=en' } });
    assert.match(chEnHit.headers.get('x-acr-edge-cache') || '', /^HIT/);

    const state = 'teststate1234567890abcdef';
    await fetch(`http://127.0.0.1:${edge.port}/auth/dev?state=${state}&steamId=76561198000000042&name=Kenji`);
    const authData = await (await fetch(`http://127.0.0.1:${edge.port}/auth/poll?state=${state}`)).json();

    const ch = todayData.challenges[0];
    const trace = pts.map(([x, z], idx) => [Math.round((idx / (pts.length - 1)) * 95_000), x, z, 110, 0]);
    const subRes = await fetch(`http://127.0.0.1:${edge.port}/api/runs`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${authData.token}`,
        Origin: `http://127.0.0.1:${edge.port}`,
        'User-Agent': 'ACR-Daily/0.2.0 public',
      },
      body: JSON.stringify({
        challengeId: ch.id,
        status: 'finished',
        track: ch.track,
        car: ch.car,
        clockMs: 95_000,
        resets: 0,
        appVersion: '0.2.0',
        trace,
      }),
    });
    assert.equal(subRes.status, 200);

    const lbAfter = await (await fetch(`http://127.0.0.1:${edge.port}/api/leaderboard?slot=1`)).json();
    assert.equal(lbAfter.entries.length, 1);
    const runId = lbAfter.entries[0].runId;

    // 5. Off-thread standby sync succeeds
    assert.equal(await primary.standby.syncNow(), true);
    await primary.close();
    primary = null;

    // 6. When Primary is down, Edge returns 502 Bad Gateway (not 500) and /healthz turns 503
    const downRes = await fetch(`http://127.0.0.1:${edge.port}/api/me/events`);
    assert.equal(downRes.status, 502);
    const edgeHz = await fetch(`http://127.0.0.1:${edge.port}/healthz`);
    assert.equal(edgeHz.status, 503);
    await edge.close();
    edge = null;

    // 7a. Automatic bootstrap from Raspberry Pi listener: a fresh Primary pulls DB + traces over HMAC HTTPS!
    const bootstrapDir = join(workDir, 'bootstrapped-primary');
    const bootPrimary = await startVmServer({
      role: 'primary',
      region: 'eu',
      host: '127.0.0.1',
      port: 0,
      seedRoutes: false,
      disableCron: true,
      disableLiveRelay: true,
      standbyUrl: `http://127.0.0.1:${standbyPort}/internal/standby`,
      standbyIntervalMs: 60_000,
      standbyChunkBytes: 1024,
      standbyRangeChunkBytes: 1024,
      env: {
        DATA_DIR: bootstrapDir,
        ADMIN_KEY: adminKey,
        OFFICIAL_FROM: '',
      },
    });
    const bootLb = await (await fetch(`http://127.0.0.1:${bootPrimary.port}/api/leaderboard?slot=1`)).json();
    assert.equal(bootLb.entries.length, 1);
    assert.equal(bootLb.entries[0].name, 'Kenji');
    const bootTrace = await (await fetch(`http://127.0.0.1:${bootPrimary.port}/api/runs/${runId}/trace`)).json();
    assert.equal(bootTrace.trace.length, trace.length);

    // 7a-delta. Incremental cutover delta sync (--delta): simulate new Cloudflare D1 runs/players arriving later in
    // the day and verify bootPrimary merges ONLY the tiny delta live without restarting or re-sending the base DB!
    const simulatedD1Path = join(workDir, 'simulated-d1.sqlite');
    copyFileSync(join(standbyData, 'acr-daily.sqlite'), simulatedD1Path);
    const simDb = new DatabaseSync(simulatedD1Path, { open: true });
    try {
      simDb.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, ?)').run(
        '76561198000000099', 'Takumi', Date.now(),
      );
      simDb.prepare(
        'INSERT INTO runs (date, slot, steam_id, track, car, status, clock_ms, resets, total_ms, app_version, created, trace) ' +
        'VALUES (?, 1, ?, ?, ?, ?, 89000, 0, 89000, ?, ?, ?)',
      ).run(ch.date, '76561198000000099', ch.track, ch.car, 'finished', '0.2.0', Date.now(), JSON.stringify(trace));
    } finally {
      simDb.close();
    }
    const deltaOut = spawnSync('python3', [
      DELTA_EXPORT_SCRIPT,
      '--delta',
      standbyData,
      '--source-sqlite', simulatedD1Path,
    ], { encoding: 'utf8' });
    assert.equal(deltaOut.status, 0, deltaOut.stderr || deltaOut.stdout);
    assert.equal(await bootPrimary.standby.checkDeltaNow(), true);

    const deltaHz = await (await fetch(`http://127.0.0.1:${bootPrimary.port}/healthz`)).json();
    assert.equal(deltaHz.db.players, 2);
    assert.equal(deltaHz.db.runs, 2);
    assert.match(String(deltaHz.db.appliedDeltaId || ''), /^999999\d{9}$/);
    const deltaLb = await (await fetch(`http://127.0.0.1:${bootPrimary.port}/api/leaderboard?slot=1`)).json();
    assert.equal(deltaLb.entries.length, 2);
    assert.equal(deltaLb.entries[0].name, 'Takumi');
    await bootPrimary.close();

    // 7b. Anti-wipe check (C2): even if bootstrap is disabled, a wiped Primary CANNOT overwrite the Pi DB!
    wipedPrimary = await startVmServer({
      role: 'primary',
      region: 'eu',
      host: '127.0.0.1',
      port: 0,
      seedRoutes: false,
      disableCron: true,
      disableLiveRelay: true,
      disableStandbyBootstrap: true,
      standbyUrl: `http://127.0.0.1:${standbyPort}`,
      standbyIntervalMs: 60_000,
      standbyChunkBytes: 1024,
      env: {
        DATA_DIR: wipedPrimaryData,
        ADMIN_KEY: adminKey,
        DEV_LOGIN: '1',
      },
    });
    // Add 1 route so wipedPrimary has routes > 0 (passes local empty guard) and attempts to push -> Pi rejects with 409!
    await fetch(`http://127.0.0.1:${wipedPrimary.port}/api/admin/route`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${adminKey}` },
      body: JSON.stringify({ track: 'Wiped Stage', points: pts }),
    });
    assert.equal(await wipedPrimary.standby.syncNow(), false);
    await wipedPrimary.close();
    wipedPrimary = null;

    // 8. Promote Pi standby (write PROMOTED fence) and verify Kenji's run + trace are 100% intact!
    writeFileSync(join(standbyData, 'PROMOTED'), 'promoted\n');
    const hzPromoted = await (await fetch(`http://127.0.0.1:${standbyPort}/healthz`)).json();
    assert.equal(hzPromoted.promoted, true);

    recovered = await startVmServer({
      role: 'primary',
      region: 'rpi-failover',
      host: '127.0.0.1',
      port: 0,
      seedRoutes: false,
      disableCron: true,
      disableLiveRelay: true,
      env: {
        DATA_DIR: standbyData,
        ADMIN_KEY: adminKey,
        OFFICIAL_FROM: '',
      },
    });

    const recLb = await (await fetch(`http://127.0.0.1:${recovered.port}/api/leaderboard?slot=1`)).json();
    assert.equal(recLb.entries.length, 2);
    assert.equal(recLb.entries[0].name, 'Takumi');

    const recTrace = await (await fetch(`http://127.0.0.1:${recovered.port}/api/runs/${runId}/trace`)).json();
    assert.equal(recTrace.id, runId);
    assert.equal(recTrace.trace.length, trace.length);
  } finally {
    if (edge) await edge.close().catch(() => {});
    if (primary) await primary.close().catch(() => {});
    if (wipedPrimary) await wipedPrimary.close().catch(() => {});
    if (recovered) await recovered.close().catch(() => {});
    standbyProc.kill('SIGTERM');
    rmSync(workDir, { recursive: true, force: true });
  }
});
