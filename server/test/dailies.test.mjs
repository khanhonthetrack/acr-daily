// Cars, conditions and the temperature (conditions) check.   node --test test/*.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { CARS, carByName, sameCar } from '../src/cars.js';
import { describe, pickConditions, RALLY_WEATHER, rallyOf, TIMES, WEATHER } from '../src/conditions.js';
import { compareTemps, tempProfile } from '../src/realism.js';

const wales = JSON.parse(readFileSync(new URL('./fixtures/wales.json', import.meta.url)));

test('18 cars, unique ids and names', () => {
  assert.equal(CARS.length, 18);
  assert.equal(new Set(CARS.map((c) => c.id)).size, 18);
  assert.equal(new Set(CARS.map((c) => c.name)).size, 18);
});

test('car names the game reported match, other models never do', () => {
  assert.equal(carByName('Mini Cooper S 1275').id, 'MiniCooperS1275');
  assert.equal(carByName('Peugeot 208 Rally4').id, 'Peugeot208Rally4');
  assert.ok(sameCar('Peugeot 306 II Maxi', carByName('Peugeot 306 Maxi')));
  assert.ok(sameCar('Citroën Xsara WRC', carByName('Citroen Xsara WRC')));
  assert.ok(!sameCar('Fiat 131 Abarth', carByName('Fiat 124 Abarth')));
  assert.ok(!sameCar('Peugeot 206 WRC', carByName('Peugeot 208 Rally4')));
  // every car matches only itself
  for (const a of CARS) for (const b of CARS) assert.equal(sameCar(a.name, b), a === b, `${a.name} vs ${b.name}`);
});

test('conditions: weather allowed for the rally, a valid time, stable for the same inputs', () => {
  for (let h = 0; h < 2000; h += 37) {
    const c = pickConditions('Wales Afon Bidno', h * 7919, h * 104729);
    assert.ok(c.weather in RALLY_WEATHER.Wales && WEATHER[c.weather], c.weather);
    assert.ok(TIMES.some((t) => t.id === c.time));
  }
  assert.deepEqual(pickConditions('Alsace Forêt', 123456, 654321), pickConditions('Alsace Forêt', 123456, 654321));
  assert.equal(rallyOf('Alsace Obersteigen'), 'Alsace');
  assert.equal(rallyOf('Monte Carlo Sisteron'), 'Monte Carlo');
  const d = describe('LightRain', 'afternoon');
  assert.equal(d.weatherLabel, WEATHER.LightRain.label);
  assert.match(d.timeLabel, /Afternoon/);
});

test('conditions: the weather mix is varied (not always the same)', () => {
  const seen = new Set();
  for (let h = 1; h < 400; h++) seen.add(pickConditions('Alsace Forêt', h * 2654435761 >>> 0, h * 40503).weather);
  assert.ok(seen.size >= 6, [...seen].join(','));
});

test('weather: snow only in Monte Carlo and Wales, and rare there; Greece mostly dry', () => {
  for (const odds of Object.values(RALLY_WEATHER)) for (const w of Object.keys(odds)) assert.ok(WEATHER[w], w);
  const share = (track, re) => {   // share of 20 000 days with that weather
    let n = 0;
    for (let d = 0; d < 20000; d++) if (re.test(pickConditions(track, (d * 2654435761) >>> 0, d).weather)) n++;
    return n / 20000;
  };
  for (const t of ['Alsace Forêt', 'Greece Elatia', 'Some New Rally Stage']) assert.equal(share(t, /Snow|Blizzard/), 0, t);
  const monte = share('Monte Carlo La Bollène', /Snow|Blizzard/), wales = share('Wales Afon Bidno', /Snow|Blizzard/);
  assert.ok(monte > 0.04 && monte < 0.11, `Monte Carlo snow ${monte}`);
  assert.ok(wales > 0.02 && wales < 0.06, `Wales snow ${wales}`);
  assert.equal(share('Wales Afon Bidno', /Blizzard/), 0);
  assert.ok(share('Greece Elatia', /Rain|Storm/) < 0.15);
  assert.ok(share('Wales Afon Bidno', /Rain|Storm|Fog/) > 0.4);
});

test('temperature profile of a real run: 10 sections, sensible kelvin values', () => {
  const p = tempProfile(wales.result.trace, { points: wales.route });
  assert.equal(p.length, 10);
  assert.ok(p.every((v) => v == null || (v > 250 && v < 320)), p.join(','));
  assert.ok(p.filter((v) => v != null).length >= 8);
});

test('temperature check: same conditions pass, 4 °C colder is flagged, too few drivers = no verdict', () => {
  const p = tempProfile(wales.result.trace, { points: wales.route });
  const near = (k) => p.map((v) => (v == null ? null : v + k));
  assert.deepEqual(compareTemps(p, [near(0.3), near(-0.4), near(0.1)]).flags, []);
  const cold = compareTemps(near(-4), [p, near(0.3), near(-0.2)]);
  assert.match(cold.flags[0], /colder/);
  assert.ok(cold.diff < -3.5);
  assert.deepEqual(compareTemps(near(-4), [p]).flags, []);      // one other driver: no verdict yet
  assert.deepEqual(compareTemps(null, [p, p]).flags, []);       // old app without temperatures
});
