// App versions the board takes, menu stage names, routes reported under another name, and fixing a run's resets.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { appVersionOf, fixedRun, olderThan, sameStage, tooOld } from '../src/index.js';
import { MENU_NAMES, menuName } from '../src/stages.js';
import { timesAt } from '../src/realism.js';

const ober = JSON.parse(readFileSync(new URL('./fixtures/obersteigen.json', import.meta.url)));
const req = (ua) => ({ headers: new Map([['User-Agent', ua]]) });
const ENV = { MIN_APP_VERSION: '0.14.2', MIN_APP_FROM: '2026-10-06' };

test('versions compare part by part', () => {
  assert.ok(olderThan('0.14.1', '0.14.2'));
  assert.ok(olderThan('0.9.9', '0.14.2'));
  assert.ok(!olderThan('0.14.2', '0.14.2'));
  assert.ok(!olderThan('0.15', '0.14.2'));
  assert.ok(!olderThan('1.0.0', '0.14.2'));
});

test('the app version comes from the run, else from the User-Agent', () => {
  assert.equal(appVersionOf(req('ACR-Daily/0.14.1'), { appVersion: '0.14.2' }), '0.14.2');
  assert.equal(appVersionOf(req('ACR-Daily/0.14.1'), null), '0.14.1');
  assert.equal(appVersionOf(req('curl/8.0'), {}), null);
});

test('old apps are refused (426) from MIN_APP_FROM on; that day\'s board keeps its apps', async () => {
  const r = tooOld(ENV, req('ACR-Daily/0.14.1'), { appVersion: '0.14.1' }, '2026-10-06');
  assert.equal(r.status, 426);
  assert.match((await r.json()).error, /^invalid run: .*0\.14\.1.*0\.14\.2/);    // "invalid": 0.14.1 drops it from its queue
  assert.equal(tooOld(ENV, req('ACR-Daily/0.14.1'), { appVersion: '0.14.1' }, '2026-10-05'), null);
  assert.equal(tooOld(ENV, req('ACR-Daily/0.14.2'), { appVersion: '0.14.2' }, '2026-10-06'), null);
  assert.equal(tooOld(ENV, req('ACR-Daily/0.14.1'), null, null).status, 426);       // routes: no date, always
  assert.equal(tooOld(ENV, req('python-urllib'), null, '2026-10-07').status, 426);    // no version = too old
  assert.equal(tooOld({}, req('ACR-Daily/0.3.0'), null, '2026-10-07'), null);           // no minimum set
});

test('every stage id has its menu name', () => {
  assert.equal(Object.keys(MENU_NAMES).length, 44);
  assert.equal(menuName('MonteCarloS1BolleneFullForward'), 'La Bollène-Vésubie - Peïra Cava');
  assert.equal(menuName('WelesS3HafrenNorthCut1Forward'), 'Cwmbiga - Fedw Fain');
  assert.equal(menuName('AlsaceS4SaverneFullForward'), 'Forêt de Saverne');
  assert.equal(menuName('nope'), null);
  for (const n of Object.values(MENU_NAMES)) assert.equal(n, n.trim());
});

test('a route reported under another name finds its stage by start and finish', () => {
  const stored = (track, points, extra = {}) => ({ track, points: JSON.stringify(points), length: len(points), stage_id: null, ...extra });
  const len = (p) => p.slice(1).reduce((a, q, i) => a + Math.hypot(q[0] - p[i][0], q[1] - p[i][1]), 0);
  const line = ober.route.map((p) => [...p]);
  const shifted = line.map(([x, z]) => [x + 3, z - 2]);           // the same road, driven 3 m off the centre line
  const routes = [stored('Alsace Obersteigen (guess)', line, { contributed_by: 'game-files', stage_id: 'AlsaceS4SaverneShort1Forward' }),
    stored('Alsace La Mossig', [...line].reverse()),                // the same road the other way
    stored('Alsace Longer', line.concat(line.slice(-1).map(([x, z]) => [x + 3000, z])))];   // same start, finish elsewhere
  assert.equal(sameStage({ points: shifted }, routes).track, 'Alsace Obersteigen (guess)');
  assert.equal(sameStage({ points: [...shifted].reverse() }, routes).track, 'Alsace La Mossig');
  assert.equal(sameStage({ points: shifted.map(([x, z]) => [x + 500, z]) }, routes), null);   // somewhere else
  // a stale stage id from the save never moves a run to another stage
  assert.equal(sameStage({ points: [...shifted].reverse(), stageId: 'AlsaceS4SaverneShort1Forward' }, routes).track, 'Alsace La Mossig');
});

test('fixing a run: total, and with the reset times its trace and splits', () => {
  const r = ober.result;
  const run = { clock_ms: r.clockMs, resets: 0, trace: JSON.stringify(r.trace) };
  const only = fixedRun(run, ober.route, { resets: 1 });
  assert.deepEqual(only, { resets: 1, total_ms: r.clockMs + 60000 });
  const at = 100000;                                                    // past the first two splits, before the third
  const f = fixedRun(run, ober.route, { resets: 1, at: [at] });
  const tr = JSON.parse(f.trace);
  assert.ok(tr.every((s) => s[4] === (s[0] >= at ? 1 : 0)));
  const was = timesAt(r.trace, { points: ober.route }, [0.25, 0.5, 0.75], 60000);
  const now = JSON.parse(f.splits);
  for (let k = 0; k < 3; k++) assert.equal(now[k], was[k] >= at ? was[k] + 60000 : was[k], `split ${k + 1}`);
  assert.ok(now.some((t, k) => t !== was[k]));
  // undone: no resets anywhere, the splits as they were
  const undone = fixedRun({ ...run, trace: f.trace }, ober.route, { resets: 0, at: [] });
  assert.equal(undone.total_ms, r.clockMs);
  assert.ok(JSON.parse(undone.trace).every((s) => s[4] === 0));
  assert.deepEqual(JSON.parse(undone.splits), was);
  assert.match(fixedRun(run, ober.route, { resets: -1 }).error, /resets/);
  assert.match(fixedRun(run, ober.route, { resets: 2, at: [1000] }).error, /one per reset/);
  assert.match(fixedRun(run, ober.route, { resets: 1, at: [r.clockMs + 1] }).error, /within the run/);
});
