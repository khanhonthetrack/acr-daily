// The experimental satellite page (src/labmap.js, src/geofits.js): the page, and the game -> Earth conversion.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { labMapPage } from '../src/labmap.js';
import { GEO_FITS } from '../src/geofits.js';

// the page's conversion, taken from the page itself so the test checks what the browser runs
const page = labMapPage();
const src = page.match(/function toLL\(fit,x,z\)\{[\s\S]*?\n\}/)[0];
const toLL = new Function(src + '; return toLL;')();

test('the page carries the fits and is marked experimental', () => {
  assert.match(page, /EXPERIMENTAL/);
  assert.match(page, /noindex/);
  assert.match(page, /server\.arcgisonline\.com/);          // Esri imagery, credited
  assert.match(page, /Imagery &copy; Esri/);
  assert.ok(!/(maps|khms\d?|mt\d)\.google|google\.com\/maps/i.test(page));   // no Google map imagery (fonts are fine)
});

test('fits: most stages line up, the rest are marked', () => {
  const all = Object.values(GEO_FITS), ok = all.filter((f) => f.ok);
  assert.ok(all.length >= 40);
  assert.ok(ok.length >= 25);
  for (const f of ok) assert.ok(f.p90M <= 40);
  for (const f of all) assert.equal(f.mirror, 'x');
});

test('the game origin goes to the fitted place, and 1 km of game is 1 km of Earth', () => {
  const fit = Object.values(GEO_FITS).find((f) => f.ok);
  const [lat, lon] = toLL(fit, 0, 0);
  assert.ok(Math.abs(lat - fit.lat) < 1e-9 && Math.abs(lon - fit.lon) < 1e-9);
  const [la2, lo2] = toLL(fit, 1000, 0);
  const dn = (la2 - lat) * 111132.954, de = (lo2 - lon) * 111319.49 * Math.cos(lat * Math.PI / 180);
  assert.ok(Math.abs(Math.hypot(dn, de) - 1000) < 1);
});
