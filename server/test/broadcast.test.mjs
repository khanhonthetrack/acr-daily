// The broadcast overlays' and the special event's pages (src/broadcast.js, src/rankedpage.js) through the worker's
// router: each answers, and each page's script parses (a page whose script fails shows nothing in OBS).
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { fakeD1 } from './faked1.mjs';
import worker from '../src/index.js';

const env = () => fakeD1({ LIVE_FROM: '2026-11-17T17:30:00Z', LIVE_PUBLIC: '1', SITE_URL: 'https://acrdaily.com' }).env;
const get = (path, e = env()) => worker.fetch(new Request('https://acrdaily.com' + path), e, { waitUntil() {} });
const scripts = (html) => [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);

test('the overlays: a ranked series\', a special event\'s, one session\'s, a championship\'s, an event\'s, the dailies\'', async () => {
  for (const p of ['/broadcast/ranked/skoda', '/broadcast/ranked/rally2', '/broadcast/ranked/rally2/1795867200000',
    '/broadcast/championship/qtfpdhhu?pages=entry,champ&studio=always', '/broadcast/event/12?parts=studio,side', '/broadcast/daily/1',
    '/broadcast/dailies', '/broadcast/dailies?feed=1&bg=1&rows=5&lang=pl']) {
    const r = await get(p);
    assert.equal(r.status, 200, p);
    assert.match(r.headers.get('Content-Security-Policy'), /img-src 'self'/);
    for (const s of scripts(await r.text())) assert.doesNotThrow(() => new Function(s), p);   // eslint-disable-line no-new-func
  }
  assert.equal((await get('/broadcast/championship/nope')).status, 404);
});

test('the special event\'s page, its pictures; no page for a key that is no special event', async () => {
  const r = await get('/ranked/skoda');
  assert.equal(r.status, 200);
  const html = await r.text();
  assert.match(html, /Skoda Saturday Challenge/);
  assert.match(html, /\/series\/skoda-banner\.webp/);
  for (const s of scripts(html)) assert.doesNotThrow(() => new Function(s));   // eslint-disable-line no-new-func
  for (const p of ['/series/skoda.webp', '/series/skoda-logo.webp', '/series/skoda-banner.webp']) {
    const x = await get(p);
    assert.equal(x.status, 200, p);
    assert.equal(x.headers.get('Content-Type'), 'image/webp');
  }
  assert.equal((await get('/ranked/rally2')).status, 404);
  const ranked = await (await get('/ranked')).text();
  for (const s of scripts(ranked)) assert.doesNotThrow(() => new Function(s));   // eslint-disable-line no-new-func
});
