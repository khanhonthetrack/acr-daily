// Leagues: invite codes, the event builder's checks (the game's Rally Weekend rules), event standings with the
// stewards' decisions, seasons and their championships, banners, the league's Discord posts.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { BANNER, catalog, checkBanner, checkEvent, checkLeague, checkPenalty, checkSeason, DEFAULT_SEASON,
  describeSeason, eventStandings, LIMITS, newCode, normCode, seasonStandings, showCode, sniffImage } from '../src/leagues.js';
import { duePosts, openMessage, resultsMessage } from '../src/leaguediscord.js';

const ROUTES = [
  { track: 'Wales Afon Bidno', stage_id: 'WelesS4HafrenSouthFullForward', length: 4793 },
  { track: 'Wales Severn', stage_id: 'WelesS4HafrenSouthFullReverse', length: 4800 },
  { track: 'Wales Cwmbiga', stage_id: 'WelesS3HafrenNorthFullForward', length: 11300 },
  { track: 'Greece Elatia', stage_id: 'GreeceS3ElatiaCut1Forward', length: 4900 },
  { track: 'Alsace Forêt', stage_id: null, length: 9000 },               // no game id: not offered
];
const CAT = catalog(ROUTES);
const NOW = Date.parse('2026-10-09T12:00:00Z');
const H = 3600000;

function ev(over = {}) {
  return { name: 'Round 1', rally: 'Wales', car: 'Hyundai i20 N Rally2', rules: { damageIntensity: 'severe' },
    stages: [{ track: 'Wales Afon Bidno', day: 1, weather: 'Clear', time: '08:00' },
      { track: 'Wales Cwmbiga', day: 1, service: true, weather: 'LightCloud', time: '11:30' },
      { track: 'Wales Severn', day: 2, weather: 'LightRain', time: '09:15' }],
    opens: NOW, closes: NOW + 72 * H, ...over };
}

test('invite codes: typed any way, no look-alike characters', () => {
  for (let i = 0; i < 50; i++) {
    const c = newCode();
    assert.match(c, /^[A-HJ-NP-Z2-9]{8}$/);
    assert.equal(normCode(showCode(c).toLowerCase() + ' '), c);
  }
  assert.equal(showCode('ABCDEFGH'), 'ABCD-EFGH');
  assert.equal(normCode('abcd-efgh'), 'ABCDEFGH');
  assert.equal(normCode('ABCD-EFG0'), null);           // 0 is not in codes
  assert.equal(normCode('ABC'), null);
});

test('the catalog: the stages with a game id, per location, and the classes', () => {
  const wales = CAT.rallies.find((r) => r.name === 'Wales');
  assert.deepEqual(wales.stages.map((s) => s.name), ['Afon Bidno - Severn', 'Cwmbiga - Afon Biga', 'Severn - Afon Bidno']);
  assert.equal(CAT.rallies.find((r) => r.name === 'Alsace').stages.length, 0);
  assert.ok(CAT.classes.some((k) => k.cls === 'Rally2/R5'));
  assert.ok(CAT.weathers.some((w) => w.id === 'Clear' && w.game === 'WT_CLEAR'));
});

test('a league: a name, public unless said otherwise', () => {
  assert.deepEqual(checkLeague({ name: '  Friday   Night  ', about: 'x'.repeat(900) }).value,
    { name: 'Friday Night', about: 'x'.repeat(LIMITS.about), public: 1 });
  assert.equal(checkLeague({ name: 'FN', public: false }).error, 'give the league a name (3 to 60 characters)');
  assert.equal(checkLeague({ name: 'Secret', public: false }).value.public, 0);
  assert.equal(checkLeague({ name: 'Club', about: ' Weekly rallies. \r\n\r\n\r\n\r\nAll  welcome!\u0007 ' }).value.about,
    'Weekly rallies.\n\nAll welcome!');
});

test('an event the game can run: days, service parks, times', () => {
  const v = checkEvent(ev(), CAT, NOW).value;
  assert.deepEqual(v.stages.map((s) => [s.day, s.service, s.time]), [[1, true, '08:00'], [1, true, '11:30'], [2, true, '09:15']]);
  assert.equal(v.car, 'Hyundai i20 N Rally2');
  assert.equal(v.car_class, null);
  assert.deepEqual(v.rules, { penalty: 'light', respawn: true, damage: true, damageIntensity: 'severe', wear: 'light', failures: 'off' });
  // a day's first stage always has its service park; between stages only if asked
  const noSp = checkEvent(ev({ stages: ev().stages.map((s) => ({ ...s, service: false })) }), CAT, NOW).value;
  assert.deepEqual(noSp.stages.map((s) => s.service), [true, false, true]);
  // a class instead of a car
  assert.equal(checkEvent(ev({ car: null, carClass: 'Rally2/R5' }), CAT, NOW).value.car_class, 'Rally2/R5');
});

test('an event the game could not run is refused', () => {
  const st = ev().stages;
  const bad = {
    'pick a location': { rally: 'Sweden' },
    'pick a car or a car class': { car: null },
    'unknown car class': { car: null, carClass: 'Group Z' },
    'add at least one stage': { stages: [] },
    'SS2: pick a stage of Wales': { stages: [st[0], { ...st[1], track: 'Greece Elatia' }] },
    'the days come in order, from day 1': { stages: [st[0], { ...st[2], day: 3 }] },
    'SS2 starts after SS1 on the same day': { stages: [st[0], { ...st[1], time: '07:00' }] },
    'SS1: pick the weather': { stages: [{ ...st[0], weather: 'Sunny' }] },
    'SS1: the start time is HH:MM': { stages: [{ ...st[0], time: '25:00' }] },
    'the event closes after it opens': { closes: NOW - H },
    'the event must stay open for at least another hour': { opens: NOW - 10 * H, closes: NOW + H / 2 },
  };
  for (const [msg, over] of Object.entries(bad)) assert.equal(checkEvent(ev(over), CAT, NOW).error, msg, msg);
  const many = Array.from({ length: LIMITS.stages + 1 }, (_, k) => ({ ...st[0], day: 1, time: `${String(Math.floor(k / 2)).padStart(2, '0')}:${k % 2 ? 30 : 10}` }));
  assert.match(checkEvent(ev({ stages: many }), CAT, NOW).error, /at most/);
  const days = Array.from({ length: LIMITS.days + 1 }, (_, k) => ({ ...st[0], day: k + 1 }));
  assert.equal(checkEvent(ev({ stages: days }), CAT, NOW).error, `at most ${LIMITS.days} days`);
  assert.match(checkEvent(ev({ closes: NOW + 100 * 86400000 }), CAT, NOW).error, /at most \d+ days/);
});

const E = { stages: [{}, {}, {}], opens: NOW - 10 * H, closes: NOW + 10 * H };
const entry = (id, name, status, done, reason = null) => ({ steam_id: id, name, status, done, reason, car: 'Hyundai i20 N Rally2', country: 'pl' });
const time = (id, k, t, p = 0) => ({ steam_id: id, stage_no: k, time_ms: t, penalty_ms: p, splits: null });

test('event standings: finished by total, then running, then DNF; stage and overall positions', () => {
  const entries = [entry('a', 'Ann', 'finished', 3), entry('b', 'Ben', 'finished', 3), entry('c', 'Cy', 'running', 2),
    entry('d', 'Di', 'dnf', 1, 'retired'), entry('e', 'Ed', 'finished', 3)];
  const times = [time('a', 0, 100000), time('a', 1, 200000, 10000), time('a', 2, 150000),
    time('b', 0, 101000), time('b', 1, 205000), time('b', 2, 149000),
    time('c', 0, 99000), time('c', 1, 230000),
    time('d', 0, 120000),
    time('e', 0, 102000), time('e', 1, 205000), time('e', 2, 148000)];
  const { rows, stages } = eventStandings(E, entries, times, NOW);
  // Ben and Ed tie on 455 s: both P1, then Ann P3
  assert.deepEqual(rows.map((r) => [r.name, r.status, r.rank, r.totalMs]),
    [['Ben', 'finished', 1, 455000], ['Ed', 'finished', 1, 455000], ['Ann', 'finished', 3, 460000],
      ['Cy', 'running', undefined, 329000], ['Di', 'dnf', undefined, 120000]]);
  assert.equal(rows[2].gapMs, 5000);
  assert.equal(rows[2].penaltyMs, 10000);
  // SS1: Cy fastest; SS2: Ann's 200 + 10 s penalty = 210 s, behind Ben and Ed (205, a tie)
  assert.deepEqual(stages[0].map((s) => [s.steamId, s.pos]), [['c', 1], ['a', 2], ['b', 3], ['e', 4], ['d', 5]]);
  assert.deepEqual(stages[1].map((s) => [s.steamId, s.pos]), [['b', 1], ['e', 1], ['a', 3], ['c', 4]]);
  const ann = rows.find((r) => r.name === 'Ann');
  assert.deepEqual(ann.stages.map((s) => [s.pos, s.cumPos]), [[2, 2], [3, 3], [3, 3]]);
  assert.deepEqual(rows.find((r) => r.name === 'Cy').stages[2], null);
});

test('still running when the event has closed: a DNF', () => {
  const late = eventStandings({ ...E, closes: NOW - 2 * H }, [entry('c', 'Cy', 'running', 2)], [time('c', 0, 1000), time('c', 1, 1000)], NOW);
  assert.deepEqual([late.rows[0].status, late.rows[0].reason], ['dnf', 'not finished in time']);
});

// the first bytes of each kind of picture, as files start (the rest: zeros)
const bytes = (...parts) => {
  const out = [];
  for (const p of parts) out.push(...(typeof p === 'string' ? [...p].map((c) => c.charCodeAt(0)) : p));
  return new Uint8Array([...out, ...new Array(64).fill(0)]);
};
const be32 = (n) => [n >>> 24, (n >>> 16) & 255, (n >>> 8) & 255, n & 255];
const png = (w, h) => bytes([0x89], 'PNG\r\n\x1a\n', [0, 0, 0, 13], 'IHDR', be32(w), be32(h));
const jpeg = (w, h) => bytes([0xff, 0xd8, 0xff, 0xe0, 0, 16], 'JFIF\0', new Array(9).fill(0),     // APP0, then a frame header
  [0xff, 0xc0, 0, 17, 8, h >> 8, h & 255, w >> 8, w & 255]);
const webp = (w, h) => bytes('RIFF', [0, 0, 0, 0], 'WEBPVP8X', [10, 0, 0, 0, 0, 0, 0, 0],
  [(w - 1) & 255, ((w - 1) >> 8) & 255, 0, (h - 1) & 255, ((h - 1) >> 8) & 255, 0]);

test('banners: a PNG, JPEG or WebP read from its bytes, nothing else', () => {
  assert.deepEqual(sniffImage(png(1200, 400)), { type: 'image/png', w: 1200, h: 400 });
  assert.deepEqual(sniffImage(jpeg(1200, 400)), { type: 'image/jpeg', w: 1200, h: 400 });
  assert.deepEqual(sniffImage(webp(1500, 500)), { type: 'image/webp', w: 1500, h: 500 });
  for (const other of [bytes('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'), bytes('GIF89a'),
    bytes('<html><body>'), bytes([0xff, 0xd8, 0xff, 0xda, 0, 4])]) assert.equal(sniffImage(other), null);
});

test('banners: wide, not too small, not too big', () => {
  assert.deepEqual(checkBanner(jpeg(1200, 400)).value, { type: 'image/jpeg', w: 1200, h: 400 });
  assert.equal(checkBanner(jpeg(800, 800)).status, 422);            // square
  assert.equal(checkBanner(png(300, 100)).status, 422);             // too small
  assert.equal(checkBanner(bytes('GIF89a')).status, 415);
  const big = new Uint8Array(BANNER.maxBytes + 1);
  big.set(jpeg(1200, 400));
  assert.equal(checkBanner(big).status, 413);
});

test('the stewards: a penalty on a stage moves its positions, one on the total moves the result, a DSQ takes none', () => {
  const entries = [entry('a', 'Ann', 'finished', 3), entry('b', 'Ben', 'finished', 3), { ...entry('e', 'Ed', 'finished', 3), dsq: 'wrong car' }];
  const times = [time('a', 0, 100000), time('a', 1, 200000), time('a', 2, 150000),
    time('b', 0, 101000), time('b', 1, 205000), time('b', 2, 149000),
    time('e', 0, 90000), time('e', 1, 190000), time('e', 2, 140000)];
  const pen = (id, stage, ms) => ({ steam_id: id, stage_no: stage, ms, reason: 'x' });
  // Ann +10 s on SS1 (a cut) and 2 s back on the total (a game glitch)
  const { rows, stages } = eventStandings(E, entries, times, NOW, [pen('a', 0, 10000), pen('a', null, -2000)]);
  assert.deepEqual(rows.map((r) => [r.name, r.status, r.rank, r.totalMs, r.stewardMs]),
    [['Ben', 'finished', 1, 455000, 0], ['Ann', 'finished', 2, 458000, 8000], ['Ed', 'dsq', undefined, 420000, 0]]);
  assert.equal(rows[2].reason, 'wrong car');
  assert.deepEqual(stages[0].map((s) => [s.steamId, s.pos, s.totalMs]), [['b', 1, 101000], ['a', 2, 110000]]);   // Ed: no place
  assert.deepEqual(rows[1].stages[0], { timeMs: 100000, penaltyMs: 0, stewardMs: 10000, totalMs: 110000, pos: 2, cumPos: 2, splits: null });
  assert.equal(rows[2].stages[0].pos, null);
});

test('a penalty: seconds either way, a stage or the total, always a reason', () => {
  assert.deepEqual(checkPenalty({ seconds: '10', stage: 2, reason: ' cut at the hairpin ' }, 3).value, { ms: 10000, stage: 1, reason: 'cut at the hairpin' });
  assert.deepEqual(checkPenalty({ seconds: -2.5, stage: '', reason: 'game glitch' }, 3).value, { ms: -2500, stage: null, reason: 'game glitch' });
  assert.match(checkPenalty({ seconds: 10, reason: '' }, 3).error, /reason/);
  assert.match(checkPenalty({ seconds: 0, reason: 'none' }, 3).error, /seconds/);
  assert.match(checkPenalty({ seconds: 4000, reason: 'long' }, 3).error, /hour/);
  assert.match(checkPenalty({ seconds: 5, stage: 4, reason: 'no SS4' }, 3).error, /stage/);
});

// an event's standings as seasonStandings() takes them: rows (status, rank) and its last stage's positions
const round = (id, finishers, others = [], power = finishers, status = 'closed') => ({
  id, status,
  rows: [...finishers.map(([sid, name], i) => ({ steamId: sid, name, status: 'finished', rank: i + 1 })),
    ...others.map(([sid, name, st]) => ({ steamId: sid, name, status: st }))],
  stages: [[], power.map(([sid, name], i) => ({ steamId: sid, name, pos: i + 1 }))],
});
const A = ['a', 'Ann'], B = ['b', 'Ben'], C = ['c', 'Cy'];

test('a season: points per event, a DNF or DSQ scores nothing, ties to wins', () => {
  const evs = [round(1, [A, B], [[...C, 'dnf']]), round(2, [B, A, C], [], [B, A, C]), round(3, [C, A], [], [C], 'upcoming')];
  const ch = seasonStandings(DEFAULT_SEASON, evs.map((e) => (e.id === 2 ? { ...e, rows: e.rows.map((r) => (r.steamId === 'c' ? { ...r, rank: 12 } : r)) } : e)));
  assert.deepEqual(ch.map((p) => [p.name, p.points, p.wins, p.rank]), [['Ann', 43, 1, 1], ['Ben', 43, 1, 1], ['Cy', 1, 0, 3]]);
  assert.deepEqual(ch[2].cells, { 1: { pos: null, pts: 0, dnf: true, dsq: false, running: false }, 2: { pos: 12, pts: 1, power: 0 } });
  assert.match(describeSeason(DEFAULT_SEASON), /^25-18-15-12-10-8-6-4-2-1 points for P1–P10, then 1 for every finisher/);
});

test('a season: the Power Stage bonus and the worst rounds dropped', () => {
  const s = { points: { table: [10, 6, 4], finisher: 0 }, power: [3, 2, 1], drop: 1 };
  // R1: Ann wins, Cy fastest on the last stage; R2: Ben wins, Ann DNF; R3: Ann wins, Ben P2 (Ben fastest at the end)
  const evs = [round(1, [A, B, C], [], [C, A, B]), round(2, [B, C], [[...A, 'dnf']]), round(3, [A, B], [], [B, A])];
  const ch = seasonStandings(s, evs);
  // Ann: 10+2, 0 (dropped), 10+2 = 24; Ben: 6+1 (dropped), 10+3, 6+3 = 22; Cy: 4+3, 6+2, missed R3 (dropped) = 15
  assert.deepEqual(ch.map((p) => [p.name, p.points]), [['Ann', 24], ['Ben', 22], ['Cy', 15]]);
  assert.deepEqual(ch[0].cells[2], { pos: null, pts: 0, dnf: true, dsq: false, running: false, dropped: true });
  assert.equal(ch[0].cells[1].power, 2);
  assert.equal(ch[1].cells[1].dropped, true);
  assert.equal(ch[2].cells[3].dropped, true);
  assert.equal(ch[2].cells[3].absent, true);
  // no more rounds run than dropped: nothing dropped (Ben's 7 now counts: he leads)
  assert.deepEqual(seasonStandings({ ...s, drop: 3 }, evs).map((p) => [p.name, p.points]), [['Ben', 29], ['Ann', 24], ['Cy', 15]]);
});

test('a season from its form', () => {
  assert.deepEqual(checkSeason({ name: ' 2026 Spring ', points: { table: '25, 18 15;12', finisher: '1' }, power: [5, 4, 3, 0, 0], drop: '1' }).value,
    { name: '2026 Spring', points: { table: [25, 18, 15, 12], finisher: 1 }, power: [5, 4, 3], drop: 1 });
  assert.match(checkSeason({ name: 'S1', points: { table: '25' } }).error, /name/);
  assert.match(checkSeason({ name: 'Season', points: { table: '' } }).error, /points/);
  assert.match(checkSeason({ name: 'Season', points: { table: '25, -1' } }).error, /points/);
  assert.match(checkSeason({ name: 'Season', points: { table: '25' }, drop: 11 }).error, /dropped/);
  assert.match(checkSeason({ name: 'Season', points: { table: '25' }, power: '1,2,3,4,5,6,7,8,9,10,11' }).error, /Power Stage/);
});

test('the league\'s Discord: one post at a time, nothing late or twice', () => {
  const ev = { opens: 10 * H, closes: 82 * H };            // open three days
  assert.deepEqual(duePosts(ev, 9 * H), { post: null, mark: [] });
  assert.deepEqual(duePosts(ev, 10 * H), { post: 'open', mark: ['open'] });
  assert.deepEqual(duePosts({ ...ev, posted_open: 1 }, 60 * H), { post: '24h', mark: ['24h'] });
  assert.deepEqual(duePosts({ ...ev, posted_open: 1, posted_24h: 1 }, 82 * H + 10 * 60000), { post: null, mark: [] });   // the grace
  assert.deepEqual(duePosts({ ...ev, posted_open: 1, posted_24h: 1 }, 83 * H), { post: 'results', mark: ['results', 'open', '24h'] });
  // opened with less than a day to go: one post, no reminder; a short event: no reminder at all
  assert.deepEqual(duePosts(ev, 70 * H), { post: 'open', mark: ['open', '24h'] });
  assert.deepEqual(duePosts({ opens: 0, closes: 20 * H, posted_open: 1 }, 1 * H), { post: null, mark: ['24h'] });
  const o = { id: 7, name: 'Round 2', rally: 'Wales', car: null, carClass: 'Rally2/R5', stages: [{}, {}], days: 1, lengthM: 9500,
    closes: Date.parse('2026-10-12T20:00:00Z'), season: { name: 'Spring' } };
  const msg = openMessage(o, { id: 'abcdefgh', name: '**Gravel** @everyone Club' }, 'https://acrdaily.com');
  assert.equal(msg.embeds[0].author.name, 'Gravel everyone Club');                   // no markdown, no mentions
  assert.equal(msg.embeds[0].url, 'https://acrdaily.com/e/7');
  assert.match(msg.embeds[0].description, /<t:1791835200:F>/);
  const rows = [{ steamId: 'a', name: 'Ann', country: 'pl', status: 'finished', rank: 1, totalMs: 455000, gapMs: 0 },
    { steamId: 'b', name: 'Ben', status: 'finished', rank: 2, totalMs: 460000, gapMs: 5000 }, { steamId: 'c', name: 'Cy', status: 'dsq' }];
  const res = resultsMessage(o, { id: 'abcdefgh', name: 'Club' }, '', rows, [[], [{ steamId: 'b', name: 'Ben', pos: 1 }]],
    { name: 'Spring', points: DEFAULT_SEASON.points, power: [5, 4, 3], drop: 0 }, [{ rank: 1, name: 'Ann', points: 25 }]);
  assert.match(res.embeds[0].description, /Ann\*\*  7:35\.000\n` 2` \*\*Ben\*\*  \+5\.000/);
  assert.deepEqual(res.embeds[0].fields.map((f) => f.name), ['Out', 'Power Stage', 'Spring after this round']);
  assert.equal(res.embeds[0].fields[1].value, '1. Ben (+5)');
});
