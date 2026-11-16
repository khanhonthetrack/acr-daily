// Liveries from ModsCloud.net (src/liveryimport.js): the car read from the title, the author's credit, the post as a
// livery card (its page the link, its picture ModsCloud's), kept in step without touching stars, downloads or a hide.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { carForTitle, creditOf, fromModscloud, MODSCLOUD, shotOf, syncModscloud, upserts } from '../src/liveryimport.js';
import { liveriesApi } from '../src/liveries.js';
import { fakeD1 } from './faked1.mjs';

test('the car from the title (and the brand tag): a model number first, a brand with one car, never a guess', () => {
  const cases = [
    ['Peugeot 206 WRC – Valentino Rossi – Network Q Rally of GB 2002', [], 'Peugeot206'],
    ['#22 Peugeot 208 R4 – Maxi F2000 – Cedric Davanier', ['ACR Peugeot'], 'Peugeot208Rally4'],   // (208, not the Maxi)
    ['306MAXI TAMIYA', ['ACR Peugeot'], 'Peugeot306IIMaxiKitCar'],
    ['#43 Škoda Fabia R5 – Ken Block | Alessandro Gelsomino v1.2', ['ACR Skoda'], 'SkodaFabiaRSRally2'],   // (R5: the Polo's too)
    ['Fiat 131 Abarth GR4 Fiat Auto MS Team 1.3', ['ACR Fiat'], 'Fiat131Abarth'],
    ['Vincent Verschueren Polo R5 2021 V1.1', ['ACR Polo'], 'VWPoloGTIR5'],
    ['Aipine Renault elf A110_Speeder Rally Betty Luck Goddess 3.0', ['ACR Renault'], 'AlpineA110'],
    ['Ruben Rodrigues CPR 2026', ['ACR Skoda'], 'SkodaFabiaRSRally2'],         // (Skoda: one car in the game)
    ['Hyundai i20N Rally2 – Oliver Solberg & Aaron Johnston', [], 'HyundaiI20NRally2'],
    ['Supports ACR 0.6-AlfaRomeo GiuliaGTA 1300Junior : Speeder Rally. 3.0', [], 'AlfaRomeoGTA1300'],
    ['Citroën Xsara WRC Sordo 2006 2.02', [], 'CitroenXsaraWRC'],
    ['Lancia Martini #11 / #7 (1992) 1.0', ['ACR Lancia'], null],               // (four Lancias: which?)
    ['#9 Peugeot 306 – RX 208 livery – Sébastien Loeb', ['ACR Peugeot'], null],   // (two models named)
    ['Sebastien Loeb 2012 RaceSuit v1.2', [], null],                           // (not a car)
  ];
  for (const [title, brands, car] of cases) assert.equal(carForTitle(title, brands), car, title);
});

test('the author\'s credit from the post\'s text', () => {
  assert.equal(creditOf('PEUGEOT 206 WRC adaptation 207 S2000 Credits: olivier brasseur Rate this mod'), 'olivier brasseur');
  assert.equal(creditOf('Credits: TSAMS Rate this mod'), 'TSAMS');
  assert.equal(creditOf('Credit - Xardas'), 'Xardas');
  assert.equal(creditOf('A nice livery. Rate this mod'), '');
});

const POST = { id: 84668, date: '2026-11-12T15:18:44', date_gmt: '2026-11-12T14:18:44', tags: [163], featured_media: 900,
  link: 'https://modscloud.net/assetto-corsa-rally/acr-skins/peugeot-206-wrc-snijers-ypres-2008-1-0/',
  title: { rendered: 'PEUGEOT 206 WRC adaptation 207 S2000 Patrick Snijers Ypres 2008 1.0' },
  content: { rendered: '<p>PEUGEOT 206 WRC adaptation 207 S2000 Patrick Snijers Ypres 2008</p><p>Credits: olivier brasseur</p><div>Rate this mod</div>' } };
const MEDIA = { id: 900, source_url: 'https://modscloud.net/wp-content/uploads/2026/11/P206.webp',
  media_details: { sizes: { large: { source_url: 'https://modscloud.net/wp-content/uploads/2026/11/P206-1024x640.webp' },
    medium: { source_url: 'https://modscloud.net/wp-content/uploads/2026/11/P206-300x188.webp' } } } };

test('a post as a livery card: its page the link, ModsCloud\'s picture, the credit; one with no car left out', () => {
  const r = fromModscloud(POST, { shot: shotOf(MEDIA), brands: ['ACR Peugeot'] });
  assert.deepEqual(r, { source: 'modscloud', sourceId: '84668', car: 'Peugeot206',
    title: 'PEUGEOT 206 WRC adaptation 207 S2000 Patrick Snijers Ypres 2008 1.0', author: 'olivier brasseur', description: '',
    link: POST.link, shot: 'https://modscloud.net/wp-content/uploads/2026/11/P206-1024x640.webp', published: Date.parse('2026-11-12T14:18:44Z') });
  assert.match(fromModscloud({ ...POST, title: { rendered: 'Sebastien Loeb 2012 RaceSuit' } }).skip, /no car of the game/);
  assert.equal(fromModscloud({ ...POST, link: 'https://evil.example/x' }).skip, 'not a post');
  assert.equal(fromModscloud({ ...POST, content: { rendered: 'Rate this mod' } }, {}).author, 'ModsCloud');
});

async function list(env) {
  const url = new URL('https://acrdaily.test/api/liveries');
  const r = await liveriesApi(new Request(url), env, url.pathname, url, null, true, Date.now(),
    { json: (data) => data, err: (error) => ({ error }) });
  return r.liveries;
}

test('kept: published at once, with the credit and ModsCloud named; seen again, updated but its stars, downloads and a hide kept', async () => {
  const { env, db } = fakeD1();
  const r = fromModscloud(POST, { shot: shotOf(MEDIA), brands: [] });
  await env.DB.batch(upserts(env, [r], 1000));
  let [lv] = await list(env);
  assert.equal(lv.author, 'olivier brasseur');
  assert.equal((lv.sourceName), 'ModsCloud');
  assert.equal(lv.hostName, 'ModsCloud');
  assert.equal(lv.shot, r.shot);                                      // (ModsCloud's picture, not a copy)
  assert.equal(lv.direct, false);                                     // (its page: the app's button opens the browser)
  assert.equal(lv.published, r.published);
  db.prepare('UPDATE liveries SET clicks = 7, votes = 2, stars_sum = 9').run();
  await env.DB.batch(upserts(env, [{ ...r, title: 'Peugeot 206 WRC Snijers Ypres 2008 v1.1' }], 2000));
  [lv] = await list(env);
  assert.equal(lv.title, 'Peugeot 206 WRC Snijers Ypres 2008 v1.1');
  assert.deepEqual([lv.clicks, lv.votes, lv.stars], [7, 2, 4.5]);
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM liveries').get().n, 1);   // (the same post: the same card)
  db.prepare("UPDATE liveries SET status = 'hidden'").run();             // the admin took it off
  await env.DB.batch(upserts(env, [r], 3000));
  assert.deepEqual(await list(env), []);                              // (it stays off)
});

test('the hourly run: the newest posts, their pictures and tags from ModsCloud\'s API, kept', async () => {
  const { env, db } = fakeD1();
  const asked = [];
  const fetchFn = async (u) => {
    asked.push(u);
    const body = u.includes('/posts?') ? [POST, { ...POST, id: 5, title: { rendered: 'Racesuit 2025' }, tags: [] }]
      : u.includes('/media?') ? [MEDIA] : u.includes('/tags?') ? [{ id: 163, name: 'ACR Peugeot' }] : null;
    return new Response(JSON.stringify(body), { status: body ? 200 : 404 });
  };
  const r = await syncModscloud(env, 5000, fetchFn);
  assert.deepEqual([r.seen, r.kept, r.skipped.length], [2, 1, 1]);
  assert.match(asked[0], new RegExp(`categories=${MODSCLOUD.skins}&per_page=${MODSCLOUD.perRun}&page=1`));
  assert.ok(asked.some((u) => u.includes('/media?include=900')));
  assert.equal(db.prepare("SELECT shot_url FROM liveries WHERE source = 'modscloud'").get().shot_url, shotOf(MEDIA));
  assert.ok((await syncModscloud(env, 6000, async () => new Response('', { status: 503 }))).error);   // (ModsCloud down: said)
});
