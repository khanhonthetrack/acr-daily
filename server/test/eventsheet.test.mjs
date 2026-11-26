// Event sheets (src/eventsheet.js, src/xlsx.js): the CSV/Excel template, reading a file (CSV in any delimiter and
// encoding, .xlsx from Excel-like writers), every kind of mistake told with its row and column, and the API: template
// download, the import check, and several events made at once.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { catalog } from '../src/leagues.js';
import { MENU_NAMES } from '../src/stages.js';
import { importEvents, parseCsv, parseTime, parseWhen, readUpload, templateCsv, templateTable, templateXlsx, decodeText, norm } from '../src/eventsheet.js';
import { xlsxRead, xlsxWrite, serialText, unzip } from '../src/xlsx.js';
import { leaguesApi } from '../src/leaguesapi.js';
import { fakeD1, sid } from './faked1.mjs';

const RALLY = { Alsace: 'Alsace', Greece: 'Greece', MonteCarlo: 'Monte Carlo', Weles: 'Wales', Sweden: 'Sweden' };
const ROUTES = Object.entries(MENU_NAMES).map(([id, n]) => {
  const k = Object.keys(RALLY).find((x) => id.startsWith(x));
  return { track: `${RALLY[k]} ${n}`, stage_id: id, length: 4000 + (id.length * 137) % 9000 };
});
const CAT = catalog(ROUTES);
const NOW = Date.parse('2026-11-26T12:00:00Z');
const HEAD = 'Event,Opens,Closes,Season,Car,Class,Day,Stage,Time,Weather,Service park,Damage,Wear,Failures,Penalties,Manual respawn,Driving aids,Hardcore,Retire (min),Hide stages,Hide weather,Hide times';
const imp = (csv, o = {}) => importEvents(parseCsv(csv), CAT, { mode: 'league', tz: 'UTC', now: NOW, ...o });
const sheet = (...rows) => `Event,Opens,Closes,Car,Class,Day,Stage,Time,Weather,Service park\n${rows.join('\n')}`;
const probs = (r) => r.errors.map((e) => `${e.row}|${e.column}|${e.message}`);

// ------------------------------------------------------------------ reading a file

test('CSV: quotes, line breaks inside a cell, BOM, CRLF, and the delimiter found from the first line', () => {
  assert.deepEqual(parseCsv('\ufeffa,b,c\r\n"x, y","say ""hi""",z\r\n'), [['a', 'b', 'c'], ['x, y', 'say "hi"', 'z']]);
  assert.deepEqual(parseCsv('a;b;c\n1;2,5;3'), [['a', 'b', 'c'], ['1', '2,5', '3']], 'a European Excel: semicolons, decimal commas');
  assert.deepEqual(parseCsv('a\tb\n1\t2'), [['a', 'b'], ['1', '2']]);
  assert.deepEqual(parseCsv('sep=;\na;b\n1;2'), [['a', 'b'], ['1', '2']], "Excel's own hint line");
  assert.deepEqual(parseCsv('a,b\n"line one\nline two",2'), [['a', 'b'], ['line one\nline two', '2']]);
  assert.deepEqual(parseCsv('a,b\n\n,\n1,2'), [['a', 'b'], [''], ['', ''], ['1', '2']], 'every record is a row, empty ones too: the row numbers stay the sheet\'s');
});

test('a file in UTF-8, UTF-16 or Windows-1252 is text either way', () => {
  assert.deepEqual(decodeText(new TextEncoder().encode('Forêt')), { text: 'Forêt', encoding: 'UTF-8' });
  assert.equal(decodeText(Uint8Array.from([0x46, 0x6f, 0x72, 0xea, 0x74])).text, 'Forêt');           // 0xEA: ê in Windows-1252
  const u16 = Uint8Array.from([0xff, 0xfe, ...[...'Forêt'].flatMap((c) => [c.charCodeAt(0), 0])]);
  assert.deepEqual(decodeText(u16), { text: 'Forêt', encoding: 'UTF-16' });
});

test('times and dates: 24 hours, am/pm, and a date in the importer\'s time zone', () => {
  assert.deepEqual(['9:30', '09:30', '9.30', '09:30:00', '9:30 pm', '12 am', '24:00', '9:60', 'noon', '9'].map(parseTime),
    [570, 570, 570, 570, 21 * 60 + 30, 0, null, null, null, null]);
  assert.equal(parseWhen('2026-12-05 18:00', 'UTC').ms, Date.UTC(2026, 11, 5, 18));
  assert.equal(parseWhen('2026-12-05 18:00', 'Europe/Warsaw').ms, Date.UTC(2026, 11, 5, 17), 'winter: UTC+1');
  assert.equal(parseWhen('2026-07-05 18:00', 'Europe/Warsaw').ms, Date.UTC(2026, 6, 5, 16), 'summer: UTC+2');
  assert.equal(parseWhen('2026-03-29 02:30', 'Europe/Warsaw').error, undefined, 'a time that does not exist that day still gives a time');
  assert.equal(parseWhen('5.12.2026 18:00', 'UTC').ms, Date.UTC(2026, 11, 5, 18));
  assert.equal(parseWhen('2026-12-05T18:00:00Z', 'Asia/Tokyo').ms, Date.UTC(2026, 11, 5, 18), 'Z says which');
  assert.equal(parseWhen('2026-12-05 18:00 +01:00', 'Asia/Tokyo').ms, Date.UTC(2026, 11, 5, 17));
  assert.match(parseWhen('12/05/2026 18:00').error, /day\/month or month\/day/);
  assert.match(parseWhen('2026-12-05').error, /no time/);
  assert.match(parseWhen('2026-02-30 10:00').error, /not a real date/);
  assert.match(parseWhen('next friday').error, /not a date and time/);
});

// ------------------------------------------------------------------ the template

test('the template of every mode imports as it is, from CSV (either delimiter) and from Excel', async () => {
  for (const mode of ['league', 'rally', 'cup']) {
    const expect = { league: 2, rally: 1, cup: 1 }[mode];
    for (const sep of [',', ';']) {
      const r = importEvents(parseCsv(templateCsv(CAT, mode, { sep, now: NOW })), CAT, { mode, tz: 'Europe/Warsaw', now: NOW, seasons: mode === 'league' ? [] : null });
      assert.deepEqual([r.errors, r.warnings], [[], []], `${mode} ${sep}`);
      assert.equal(r.events.length, expect, `${mode} ${sep}`);
    }
    const x = await readUpload(templateXlsx(CAT, mode, { now: NOW }));
    assert.equal(x.format, 'xlsx');
    const r = importEvents(x.rows, CAT, { mode, tz: 'UTC', now: NOW });
    assert.deepEqual(r.errors, [], mode);
    assert.equal(r.events.length, expect);
    assert.deepEqual(r.events.map((e) => e.body.stages.length), expect === 2 ? [5, 3] : [5]);
  }
});

test('the league template: two rounds, the second one opening when the first closes, with its own rules', () => {
  const r = imp(templateCsv(CAT, 'league', { now: NOW }));
  const [a, b] = r.events;
  assert.deepEqual([a.name, a.rows, a.body.carClass, a.body.car], ['Round 1: Wales', [2, 6], 'Rally2/R5', undefined]);
  assert.equal(b.body.opens, a.body.closes, 'an empty Opens: when the event above closes');
  assert.equal(b.body.closes - b.body.opens, 7 * 86400000);
  assert.deepEqual([b.body.car, b.body.rules.damageIntensity, b.body.rules.failures, b.body.rules.retire, b.body.hide],
    ['VW Polo GTI R5', 'severe', 'light', 10, { weather: false, times: true, stages: true }]);
  assert.deepEqual(a.body.stages.map((s) => [s.day, s.service, s.weather, s.time]),
    [[1, true, 'Clear', '09:00'], [1, false, 'LightCloud', '11:30'], [1, true, 'Clear', '14:00'], [2, true, 'LightRain', '09:00'], [2, false, 'LightFog', '12:00']]);
});

test('the template: the cup\'s has no name, dates or season; the rally\'s no season', () => {
  assert.ok(!templateTable(CAT, 'cup').head.some((h) => ['Event', 'Opens', 'Closes', 'Season'].includes(h)));
  assert.ok(!templateTable(CAT, 'rally').head.includes('Season') && templateTable(CAT, 'rally').head.includes('Opens'));
  assert.equal(templateTable(CAT, 'league').head.length, 22);
  assert.ok(templateCsv(CAT).startsWith('\ufeffEvent,Opens,'), 'the BOM that makes Excel read UTF-8');
});

test('the Excel template: drop-downs over the lists (stages, cars, classes, weathers) and every setting, a Guide, the Lists', async () => {
  const files = await unzip(templateXlsx(CAT, 'league', { now: NOW }));
  assert.deepEqual(Object.keys(files).filter((n) => n.includes('worksheets')).sort(), ['xl/worksheets/sheet1.xml', 'xl/worksheets/sheet2.xml', 'xl/worksheets/sheet3.xml']);
  const dec = (n) => new TextDecoder().decode(files[n]);
  const events = dec('xl/worksheets/sheet1.xml');
  const dv = [...events.matchAll(/<dataValidation ([^>]*)><formula1>([^<]*)/g)].map((m) => [/sqref="([^"]*)"/.exec(m[1])[1], m[2]]);
  const by = Object.fromEntries(dv.map(([sq, f]) => [sq.split(':')[0], f]));
  assert.equal(by.H2, `Lists!$A$2:$A$${ROUTES.length + 1}`, 'the stage column: every stage of the Lists sheet');
  assert.equal(by.E2, 'Lists!$F$2:$F$21');
  assert.equal(by.J2, 'Lists!$N$2:$N$12');
  assert.equal(by.L2, '&quot;off,light,severe,realistic&quot;');
  assert.match(events, /sqref="F2:F1001"/);
  assert.match(events, /errorStyle="warning"/, 'a class may be typed (several): a warning, not a wall');
  const lists = dec('xl/worksheets/sheet3.xml');
  assert.match(lists, /Wales: Afon Bidno - Severn/);
  assert.match(lists, /Rally2\/R5/);
  assert.match(dec('xl/worksheets/sheet2.xml'), /EVERY ROW IS ONE STAGE|ROW IS ONE STAGE/);
  assert.match(dec('xl/workbook.xml'), /<sheet name="Events" sheetId="1"/, 'the Events sheet comes first: what Save As CSV saves');
});

test('xlsx written and read back: text with markup in it, numbers, empty rows and columns', async () => {
  const bytes = xlsxWrite([{ name: 'Events', rows: [['a & <b>', { v: 'x', s: 3 }, 5, ''], [], ['', '', { v: 7.5 }]] }, { name: 'Other', rows: [['no']] }]);
  const r = await xlsxRead(bytes);
  assert.deepEqual(r.rows, [['a & <b>', 'x', '5'], [], ['', '', '7.5']]);
  assert.deepEqual(r.sheets, ['Events', 'Other']);
  assert.equal((await xlsxRead(bytes, 'other')).rows[0][0], 'no');
  assert.equal(serialText(46361.75), '2026-12-05 18:00');
  assert.equal(serialText(0.395833333), '09:30');
  assert.equal(serialText(46361), '2026-12-05');
});

test('an .xlsx saved by other software: real date and time cells, shared strings, an empty row, other sheets', async () => {
  const u = await readUpload(new Uint8Array(readFileSync(new URL('./fixtures/sheet-openpyxl.xlsx', import.meta.url))));
  assert.equal(u.format, 'xlsx');
  assert.deepEqual(u.rows[1].slice(0, 3), ['Spring Sprint', '2027-03-06 18:00', '2027-03-13 18:30'], 'Excel dates come back as text');
  assert.equal(u.rows[1][7], '09:00', 'a time cell');
  const r = importEvents(u.rows, CAT, { mode: 'league', tz: 'UTC', now: NOW });
  assert.deepEqual(r.errors, []);
  assert.deepEqual(r.events.map((e) => [e.name, e.rows, e.body.stages.length, e.body.carClass || e.body.car]),
    [['Spring Sprint', [2, 4], 3, 'Rally2/R5'], ['Spring Final', [6, 6], 1, 'Skoda Fabia RS Rally2']], 'the empty row 5 is skipped, the rows keep their numbers');
  const [a, b] = r.events;
  assert.deepEqual([a.body.stages[1].service, a.body.stages[1].weather, a.body.stages[2].weather, a.body.rules.retire, a.body.hide.weather],
    [true, 'LightCloud', 'HeavyFog', 10, false], 'a stage typed in lower case, a weather by its label');
  assert.equal(b.body.opens, Date.UTC(2027, 2, 13, 18, 30), "the second event opens when the first closes... here it is written as text");
  assert.equal(b.body.closes - b.body.opens, 7 * 86400000);
});

test('an .xlsx from LibreOffice (accents in the cells) reads the same', async () => {
  const u = await readUpload(new Uint8Array(readFileSync(new URL('./fixtures/sheet-libreoffice.xlsx', import.meta.url))));
  const r = importEvents(u.rows, CAT, { mode: 'league', tz: 'UTC', now: NOW });
  assert.deepEqual(r.errors, []);
  assert.deepEqual(r.events.map((e) => [e.name, e.body.stages.map((s) => s.track)]), [['Ünïcode Cup', ['Alsace Forêt de Munster', 'Alsace Col du petit Ballon']]]);
});

test('files that are not sheets say so', async () => {
  await assert.rejects(readUpload(new Uint8Array(0)), /empty/);
  await assert.rejects(readUpload(new Uint8Array(1_100_000)), /too big/);
  await assert.rejects(readUpload(Uint8Array.from([0x50, 0x4b, 3, 4, 0, 0, 0, 0])), /not a readable Excel file/);
  await assert.rejects(readUpload(Uint8Array.from([0xd0, 0xcf, 0x11, 0xe0, 1, 2])), /old Excel file \(\.xls\)/);
  const a = await readUpload(Uint8Array.from([...new TextEncoder().encode('Event;Stage\n'), 0xea]));
  assert.equal(a.encoding, 'Windows-1252');
  assert.match(a.notes[0], /not UTF-8/);
});

// ------------------------------------------------------------------ what an event is

test('rows are stages: the settings on the first row, the next name starts the next event; nothing else is needed', () => {
  const r = imp(sheet(
    'Round 1,2026-12-05 18:00,2026-12-12 18:00,,Rally2/R5,1,Wales: Afon Bidno - Severn,09:00,Clear,',
    ',,,,,,Wales: Severn - Afon Bidno,10:30,,',
    ',,,,,2,Greece: Elatia,09:00,Light rain,',
    'Round 2,,,Skoda Fabia RS Rally2,,,Monte Carlo: Sisteron - Mézien,08:00,,'));
  assert.deepEqual(r.errors, []);
  const [a, b] = r.events;
  assert.deepEqual(a.body.stages, [
    { track: 'Wales Afon Bidno - Severn', day: 1, service: true, weather: 'Clear', time: '09:00' },
    { track: 'Wales Severn - Afon Bidno', day: 1, service: false, weather: 'Clear', time: '10:30' },
    { track: 'Greece Elatia', day: 2, service: true, weather: 'LightRain', time: '09:00' }]);
  assert.deepEqual([a.body.rally, a.summary.places, a.summary.days, a.summary.stages], ['Wales', ['Wales', 'Greece'], 2, 3], 'one event across two locations');
  assert.deepEqual([b.body.car, b.body.stages[0].day, b.body.stages[0].time], ['Skoda Fabia RS Rally2', 1, '08:00']);
  assert.equal(b.body.opens, a.body.closes);
  assert.deepEqual(b.body.rules, { penalty: 'light', respawn: true, damage: true, damageIntensity: 'light', wear: 'light', failures: 'off', hardcore: false, assists: 'any' }, "empty: the builder's defaults");
  assert.deepEqual(b.body.hide, { weather: true, times: true, stages: true }, 'hidden until it ends, as every new event');
});

test('every setting: damage, wear, failures, penalties, respawn, aids, hardcore, retirement, what is hidden', () => {
  const csv = `${HEAD}\nRound,2026-12-05 18:00,2026-12-06 18:00,,,"Rally2/R5, Rally4",1,Wales: Afon Bidno - Severn,09:00,Storm,,off,severe,realistic,realistic,off,off,no,15,no,no,yes`;
  const e = imp(csv).events[0];
  assert.deepEqual(e.body.rules, { penalty: 'realistic', respawn: false, damage: false, damageIntensity: 'light', wear: 'severe', failures: 'realistic',
    hardcore: false, assists: 'off', retire: 15 });
  assert.deepEqual(e.body.carClasses, ['Rally4', 'Rally2/R5'].sort((a, b) => CAT.classes.findIndex((k) => k.cls === a) - CAT.classes.findIndex((k) => k.cls === b)), 'several classes: each with its own results');
  assert.deepEqual(e.body.hide, { weather: false, times: true, stages: false });
  assert.equal(e.body.stages[0].weather, 'Storm');
  const hc = imp(`${HEAD}\nRound,2026-12-05 18:00,2026-12-06 18:00,,,Rally2/R5,1,Wales: Afon Bidno - Severn,09:00,,,light,,,,,,yes`);
  assert.equal(hc.events[0].body.rules.damageIntensity, 'realistic', 'Hardcore Mode: what the game locks');
  assert.match(hc.warnings[0].message, /Hardcore Mode locks damage/);
});

test('a class by its short name, a car by its alias, a stage by its game name: found all the same', () => {
  const r = imp(sheet('Alpha,2026-12-05 18:00,2026-12-06 18:00,Skoda Fabia Rally2 RS,,1,WALES: afon  bidno - severn,9:00,,',
    'Bravo,,,,rally2,1,WelesS4HafrenSouthFullForward,9:00,,'));
  assert.deepEqual(r.errors, []);
  assert.equal(r.events[0].body.car, 'Skoda Fabia RS Rally2');
  assert.equal(r.events[1].body.carClass, 'Rally2/R5');
  assert.equal(r.events[1].body.stages[0].track, 'Wales Afon Bidno - Severn');
  assert.equal(norm('Peïra Cava · Forêt'), 'peiracavaforet');
});

// ------------------------------------------------------------------ the mistakes, told

test('a stage that is not in the game: the row, the column, what is wrong and the nearest names', () => {
  const r = imp(sheet('Rally,2026-12-05 18:00,2026-12-06 18:00,,Rally2/R5,1,Wales: Afon Bidnoo - Severn,09:00,Clear,',
    ',,,,,1,Walez: Cwmbiga - Afon Biga,10:00,Clear,', ',,,,,1,Elatia,11:00,Clear,', ',,,,,1,Narnia: Lion Pass,12:00,,'));
  assert.equal(r.errors.length, 3);
  assert.deepEqual(r.errors.map((e) => [e.row, e.column, e.event, e.value]), [[2, 'Stage', 'Rally', 'Wales: Afon Bidnoo - Severn'], [3, 'Stage', 'Rally', 'Walez: Cwmbiga - Afon Biga'], [5, 'Stage', 'Rally', 'Narnia: Lion Pass']]);
  assert.match(r.errors[0].message, /"Wales: Afon Bidnoo - Severn" is not a stage the game has\. Did you mean "Wales: Afon Bidno - Severn"\?/);
  assert.match(r.errors[1].message, /Did you mean "Wales: Cwmbiga - Afon Biga"/);
  assert.doesNotMatch(r.errors[2].message, /Did you mean/);
  assert.deepEqual(r.events, [], 'a stage that is wrong: no half an event');
});

test('a stage name that two locations share needs its location', () => {
  const dup = { ...CAT, rallies: CAT.rallies.map((r) => (r.name === 'Greece' ? { ...r, stages: [...r.stages, { ...r.stages[0], track: 'Greece Afon', name: 'Afon Bidno - Severn', stageId: 'X' }] } : r)) };
  const r = importEvents(parseCsv(sheet('Rally,2026-12-05 18:00,2026-12-06 18:00,,Rally2/R5,1,Afon Bidno - Severn,09:00,Clear,')), dup, { now: NOW });
  assert.match(r.errors[0].message, /is the name of stages in several locations: "Greece: Afon Bidno - Severn", "Wales: Afon Bidno - Severn"\. Write the location in front/);
});

test('times, days and the order of the stages', () => {
  const r = imp(sheet('Rally,2026-12-05 18:00,2026-12-06 18:00,,Rally2/R5,1,Wales: Afon Bidno - Severn,9am-ish,Clear,',
    ',,,,,1,Wales: Severn - Afon Bidno,10:00,,', ',,,,,1,Wales: Cwmbiga - Afon Biga,09:30,,', ',,,,,3,Wales: Banc Gwyn - Afon Biga,11:00,,',
    ',,,,,x,Wales: Banc Gwyn - Afon Biga,11:00,,', ',,,,,,Wales: Banc Gwyn - Afon Biga,,,'));
  assert.deepEqual(probs(r).map((p) => p.split('|').slice(0, 2).join('|')), ['2|Time', '4|Time', '5|Day', '6|Day', '7|Time']);
  assert.match(r.errors[0].message, /"9am-ish" is not a time of day\. Write it as hour:minute in 24 hours, e\.g\. 09:30/);
  assert.match(r.errors[1].message, /starts at 09:30, which is not after 10:00 \(row 3\), the stage before it on day 1/);
  assert.match(r.errors[2].message, /Day 3 follows day 1 \(row 3\): the days count up one at a time, so day 2 is next/);
  assert.match(r.errors[3].message, /"x" is not a day number/);
  assert.match(r.errors[4].message, /start time is empty/);
  const back = imp(sheet('Rally,2026-12-05 18:00,2026-12-06 18:00,,Rally2/R5,2,Wales: Afon Bidno - Severn,09:00,,'));
  assert.match(back.errors[0].message, /first stage of an event is on day 1, not day 2/);
  const limits = imp(sheet('Rally,2026-12-05 18:00,2026-12-06 18:00,,Rally2/R5,1,Wales: Afon Bidno - Severn,09:00,,',
    ...Array.from({ length: 8 }, (_, i) => `,,,,,1,Wales: Severn - Afon Bidno,${String(10 + i).padStart(2, '0')}:00,,`)));
  assert.match(limits.errors[0].message, /At most 8 stages on a day: day 1 is full\. Put this stage on day 2/);
  const days = imp(sheet('Rally,2026-12-05 18:00,2026-12-06 18:00,,Rally2/R5,1,Wales: Afon Bidno - Severn,09:00,,', ...[2, 3, 4, 5].map((d) => `,,,,,${d},Wales: Severn - Afon Bidno,10:00,,`)));
  assert.match(days.errors[0].message, /At most 4 days/);
});

test('the car: both or neither, one not in the game, a class not in the game, a car with a class a cup can\'t have', () => {
  const both = imp(sheet('Rally,2026-12-05 18:00,2026-12-06 18:00,Skoda Fabia RS Rally2,Rally2/R5,1,Wales: Afon Bidno - Severn,09:00,,'));
  assert.deepEqual([both.errors[0].row, both.errors[0].column], [2, 'Class']);
  assert.match(both.errors[0].message, /Car \("Skoda Fabia RS Rally2", row 2\) and Class \("Rally2\/R5", row 2\) are both filled/);
  const none = imp(sheet('Rally,2026-12-05 18:00,2026-12-06 18:00,,,1,Wales: Afon Bidno - Severn,09:00,,'));
  assert.deepEqual([none.errors[0].row, none.errors[0].column], [2, 'Car']);
  assert.match(none.errors[0].message, /No car for this event: fill "Car".*or "Class"/);
  const car = imp(sheet('Rally,2026-12-05 18:00,2026-12-06 18:00,Skoda Fabia,,1,Wales: Afon Bidno - Severn,09:00,,'));
  assert.match(car.errors[0].message, /"Skoda Fabia" is not a car in the game\. Did you mean "Skoda Fabia RS Rally2"\?/);
  const cls = imp(sheet('Rally,2026-12-05 18:00,2026-12-06 18:00,,"Rally2/R5, Rally9",1,Wales: Afon Bidno - Severn,09:00,,'));
  assert.match(cls.errors[0].message, /"Rally9" is not a car class\..*The classes: "H3"/);
  const cup = imp(sheet(',,,,"Rally2/R5, Rally4",1,Wales: Afon Bidno - Severn,09:00,,'), { mode: 'cup' });
  assert.match(cup.errors[0].message, /A cup's matches take one car or one class: this has 2/);
});

test('a setting that clashes on the rows of one event, and one not in its list', () => {
  const r = imp(`${HEAD}\nRally,2026-12-05 18:00,2026-12-06 18:00,,,Rally2/R5,1,Wales: Afon Bidno - Severn,09:00,,,severe,,,,,,,,,,\n,,,,,Rally4,1,Wales: Severn - Afon Bidno,10:00,,,bruised,,,,,,,,,,\n,,,,,,1,Wales: Cwmbiga - Afon Biga,11:00,,,severe,,,,,,maybe,99,,,`);
  assert.deepEqual(r.errors.map((e) => [e.row, e.column]), [[3, 'Class'], [3, 'Damage'], [4, 'Hardcore'], [4, 'Retire (min)']]);
  assert.match(r.errors[0].message, /"Rally4" is not the same as "Rally2\/R5" in row 2, a row of the event "Rally"\. "Class" is one setting for the whole event: write it on its first row/);
  assert.match(r.errors[1].message, /"bruised" is not the same as "severe" in row 2/);
  assert.match(r.errors[2].message, /"maybe" is not yes or no/);
  assert.match(r.errors[3].message, /"99" is not allowed for "Retire \(min\)": a whole number of minutes from 0 to 60/);
  const bad = imp(`${HEAD}\nRally,2026-12-05 18:00,2026-12-06 18:00,,,Rally2/R5,1,Wales: Afon Bidno - Severn,09:00,,,bruised,,,medium,,,,,,,`);
  assert.match(bad.errors[0].message, /"bruised" is not allowed for "Damage"\. Use "off", "light", "severe", "realistic"/);
  assert.match(bad.errors[1].message, /"medium" is not allowed for "Penalties"\. Use "light", "realistic"/);
});

test('the dates: not a date, closing before opening, too long, already past', () => {
  const at = (o, c) => imp(sheet(`Rally,${o},${c},,Rally2/R5,1,Wales: Afon Bidno - Severn,09:00,,`));
  assert.match(at('soon', '2026-12-06 18:00').errors[0].message, /"soon" is not a date and time/);
  assert.match(at('2026-12-05 18:00', '2026-12-05').errors[0].message, /"2026-12-05" has no time/);
  const rev = at('2026-12-06 18:00', '2026-12-05 18:00');
  assert.deepEqual([rev.errors[0].row, rev.errors[0].column], [2, 'Closes']);
  assert.match(rev.errors[0].message, /closes before it opens/);
  assert.match(at('2026-12-05 18:00', '2027-03-05 18:00').errors[0].message, /open \d+ days: at most 62/);
  assert.match(at('2026-11-01 18:00', '2026-11-20 18:00').errors[0].message, /closes in the past/);
  assert.deepEqual(at('2026-11-01 18:00', '2026-12-20 18:00').errors, [], 'opened already: fine');
  assert.match(at('2026-11-26 12:30', '2026-11-26 12:45').errors[0].message, /closes in the past, or within the hour/);
});

test('the header: a missing column, an unknown one, a duplicate, an empty file, a header without stages', () => {
  assert.match(imp('Event,Car,Day,Time\nA,B,1,09:00').errors[0].message, /The column "Stage" is missing from the header row/);
  assert.match(imp('Event,Stage,Time\nA,B,09:00').errors[0].message, /"Car" and "Class" are both missing/);
  const dup = imp('Event,Car,Stage,Time,Stage\nA,B,C,09:00,D');
  assert.match(dup.errors[0].message, /"Stage" is there twice \(columns C and E\)/);
  assert.match(imp('').errors[0].message, /file is empty/);
  assert.match(imp(HEAD).errors[0].message, /no stages below it/);
  const odd = imp('Event,Notes,Opens,Closes,Car,Class,Day,Stage,Time,Wether,Service park\nRally,hi,2026-12-05 18:00,2026-12-06 18:00,,Rally2/R5,1,Wales: Afon Bidno - Severn,09:00,,');
  assert.deepEqual(odd.errors, []);
  assert.deepEqual(odd.warnings.map((w) => w.message), ['The column "Notes" is not one of the template\'s, so it is ignored.', 'The column "Wether" is not one of the template\'s, so it is ignored. (Did you mean "Weather"?)']);
  assert.equal(odd.warnings[0].row, 1);
});

test('names: missing, repeated far apart, too long; a row without a stage; events beyond the limit', () => {
  const r = imp(sheet(',,,,Rally2/R5,1,Wales: Afon Bidno - Severn,09:00,,', 'Ab,2026-12-05 18:00,2026-12-06 18:00,,Rally2/R5,1,Wales: Afon Bidno - Severn,09:00,,'));
  assert.match(r.errors[0].message, /no event name, and no event has begun above it/);
  assert.match(r.errors[1].message, /The event name needs 3 to 60 characters/);
  const again = imp(sheet('One,2026-12-05 18:00,2026-12-06 18:00,,Rally2/R5,1,Wales: Afon Bidno - Severn,09:00,,', 'Two,2026-12-05 18:00,2026-12-06 18:00,,Rally2/R5,1,Wales: Afon Bidno - Severn,09:00,,',
    'one,2026-12-05 18:00,2026-12-06 18:00,,Rally2/R5,1,Wales: Afon Bidno - Severn,09:00,,'));
  assert.equal(again.errors[0].row, 4);
  assert.match(again.errors[0].message, /"one" is the name of the event at row 2 too\. The rows of an event must follow each other/);
  const long = imp(sheet(`${'x'.repeat(61)},2026-12-05 18:00,2026-12-06 18:00,,Rally2/R5,1,Wales: Afon Bidno - Severn,09:00,,`));
  assert.match(long.errors[0].message, /has 61 characters: 60 at most/);
  const nostage = imp(sheet('Rally,2026-12-05 18:00,2026-12-06 18:00,,Rally2/R5,1,,09:00,,'));
  assert.match(nostage.errors[0].message, /This row has no stage/);
  const many = imp(sheet(...Array.from({ length: 51 }, (_, i) => `Event${i + 10},2026-12-05 18:00,2026-12-06 18:00,,Rally2/R5,1,Wales: Afon Bidno - Severn,09:00,,`)));
  assert.match(many.errors[0].message, /At most 50 events in one file: this is event number 51/);
});

test('every problem of the sheet comes at once, in the order of its rows', () => {
  const r = imp(sheet('Rally,soon,2026-12-06 18:00,,Rally9,1,Wales: Nope,nine sharp,Rainy,maybe', ',,,,,1,Wales: Severn - Afon Bidno,10:00,Clear,'));
  assert.deepEqual(r.errors.map((e) => [e.row, e.column]), [[2, 'Opens'], [2, 'Class'], [2, 'Stage'], [2, 'Time'], [2, 'Weather'], [2, 'Service park']],
    'every cell of a row is read, and told in the order of the sheet\'s columns');
  const many = imp(sheet(...Array.from({ length: 8 }, (_, i) => `Event${i},2026-12-05 18:00,2026-12-06 18:00,,Rally2/R5,1,Wales: Nope ${i},09:00,,`)));
  assert.equal(many.errors.length, 8);
  assert.deepEqual(many.errors.map((e) => e.row), [2, 3, 4, 5, 6, 7, 8, 9]);
});

test('the modes: a cup or a rally says what it does not use; a cup has one nameless event', () => {
  const csv = sheet('Rally,2026-12-05 18:00,2026-12-06 18:00,,Rally2/R5,1,Wales: Afon Bidno - Severn,09:00,Clear,', ',,,,,1,Wales: Severn - Afon Bidno,10:00,Clear,');
  const cup = imp(csv, { mode: 'cup' });
  assert.deepEqual(cup.errors, []);
  assert.equal(cup.events[0].body.opens, undefined);
  assert.equal(cup.events[0].summary.opens, undefined);
  assert.equal(cup.warnings.length, 2);
  assert.match(cup.warnings[0].message, /"Opens" column is not used for a cup/);
  const rally = imp('Event,Opens,Closes,Season,Car,Class,Day,Stage,Time\nRally,2026-12-05 18:00,2026-12-06 18:00,Spring,,Rally2/R5,1,Wales: Afon Bidno - Severn,09:00', { mode: 'rally' });
  assert.deepEqual(rally.errors, []);
  assert.match(rally.warnings[0].message, /"Season" column is not used for a rally/);
  assert.ok(rally.events[0].body.opens, 'a rally has its dates');
  const noname = imp('Stage,Car,Time\nWales: Afon Bidno - Severn,Skoda Fabia RS Rally2,09:00', { mode: 'cup' });
  assert.deepEqual([noname.errors, noname.events[0].name, noname.events[0].body.stages.length], [[], '', 1]);
});

test('seasons: the latest by default, one by name, new, none; one that is not there', () => {
  const rows = (s) => sheet(`Round1,2026-12-05 18:00,2026-12-06 18:00,,Rally2/R5,1,Wales: Afon Bidno - Severn,09:00,,`).replace('Event,', 'Season,Event,').split('\n')
    .map((l, i) => (i ? `${s},${l}` : l)).join('\n');
  const SEASONS = [{ id: 3, name: 'Season 1' }, { id: 9, name: 'Winter Cup' }];
  const of = (s, list = SEASONS) => imp(rows(s), { seasons: list });
  assert.equal(of('').events[0].season, 9, 'empty: the latest');
  assert.equal(of('season 1').events[0].season, 3);
  assert.equal(of('Winter  cup').events[0].season, 9);
  assert.equal(of('new').events[0].season, 'new');
  assert.equal(of('none').events[0].season, null);
  assert.equal(of('', []).events[0].season, 'new', 'no season yet: a new one, as the builder does');
  const no = of('Wintr Cup');
  assert.deepEqual([no.errors[0].row, no.errors[0].column], [2, 'Season']);
  assert.match(no.errors[0].message, /no season called "Wintr Cup"\. Did you mean "Winter Cup"\? Its seasons: "Season 1", "Winter Cup"\. Write "new" for a new season or "none" for a one-off event/);
  assert.equal(imp(rows('Whatever')).events[0].season, 'Whatever', 'no league given: the name stays');
});

test('what the builder refuses and the rows cannot see is told too, at the row of the stage', () => {
  // (the catalog says a stage is there; the rows are all right; checkEvent has the last word)
  const r = importEvents(parseCsv(sheet('Rally,2026-12-05 18:00,2026-12-06 18:00,,Rally2/R5,1,Wales: Afon Bidno - Severn,09:00,,')), CAT, { now: NOW });
  assert.deepEqual(r.errors, []);
});

// ------------------------------------------------------------------ the API

const [ANN, BEN, CAS] = [sid(1), sid(2), sid(3)];
function world() {
  const f = fakeD1();
  for (const [s, n, org] of [[ANN, 'Ann', 1], [BEN, 'Ben', null], [CAS, 'Cas', null]]) {
    f.db.prepare('INSERT INTO players (steam_id, name, created, organizer) VALUES (?, ?, 0, ?)').run(s, n, org);
  }
  const ins = f.db.prepare('INSERT INTO routes (track, points, length, updated, stage_id) VALUES (?, ?, ?, 0, ?)');
  for (const r of ROUTES) ins.run(r.track, '[]', r.length, r.stage_id);
  return f;
}
const player = (db, s) => db.prepare('SELECT * FROM players WHERE steam_id = ?').get(s);
const call = async ({ env, db }, path, me, body = null, { raw = null, same = true } = {}) => {
  const url = new URL('https://acrdaily.com' + path);
  const req = new Request(url, { method: body || raw ? 'POST' : 'GET', ...(raw ? { body: raw } : body ? { body: JSON.stringify(body) } : {}) });
  const res = await leaguesApi(req, env, url.pathname, url, me ? { ...player(db, me) } : null, same, NOW);
  const type = res.headers.get('Content-Type') || '';
  return { status: res.status, type, res, body: type.includes('json') ? await res.json() : new Uint8Array(await res.arrayBuffer()) };
};
const mkLeague = async (f) => (await call(f, '/api/leagues', ANN, { name: 'Ann League', public: true })).body.id;
const csv = (s) => new TextEncoder().encode(s);

test('GET /api/events/template.xlsx and .csv: the template of a mode, its lists the catalog\'s own, no sign-in needed', async () => {
  const f = world();
  const x = await call(f, '/api/events/template.xlsx?for=cup', null);
  assert.equal(x.status, 200);
  assert.match(x.type, /spreadsheetml\.sheet/);
  assert.match(x.res.headers.get('Content-Disposition'), /attachment; filename="acr-daily-cup-match-events\.xlsx"/);
  assert.equal((await readUpload(x.body)).rows[0][0], 'Car');
  const c = await call(f, '/api/events/template.csv?sep=;', null);
  assert.match(c.type, /text\/csv/);
  assert.match(new TextDecoder('utf-8', { ignoreBOM: true }).decode(c.body), /^\ufeffEvent;Opens;Closes;Season;/);
  assert.match(new TextDecoder().decode(c.body), /Wales: Afon Bidno - Severn/);
  assert.equal((await call(f, '/api/events/template.csv?for=nonsense', null)).res.headers.get('Content-Disposition').includes('league-events.csv'), true);
});

test('POST /api/events/import: signed in, from this site; a file that is not a sheet; the mistakes with rows; the events', async () => {
  const f = world();
  const league = await mkLeague(f);
  const good = templateCsv(CAT, 'league', { now: NOW });
  assert.equal((await call(f, '/api/events/import', null, null, { raw: csv(good) })).status, 401);
  assert.equal((await call(f, '/api/events/import', BEN, null, { raw: csv(good), same: false })).status, 403);
  assert.equal((await call(f, `/api/events/import?league=${league}`, BEN, null, { raw: csv(good) })).status, 403, 'a league\'s events: its staff');
  const empty = await call(f, '/api/events/import', BEN, null, { raw: new Uint8Array(0) });
  assert.deepEqual([empty.status, empty.body.ok, empty.body.errors[0].message], [200, false, 'the file is empty']);
  const bad = await call(f, '/api/events/import?for=rally&tz=Europe/Warsaw', BEN, null, { raw: csv(sheet('Rally,2026-12-05 18:00,2026-12-06 18:00,,Rally2/R5,1,Wales: Nope,09:00,,')) });
  assert.equal(bad.body.ok, false);
  assert.deepEqual([bad.body.errors[0].row, bad.body.errors[0].column], [2, 'Stage']);
  const ok = await call(f, '/api/events/import?for=rally&tz=Europe/Warsaw', BEN, null, { raw: csv(good) });
  assert.deepEqual([ok.body.ok, ok.body.format, ok.body.tz, ok.body.events.length, ok.body.warnings], [true, 'csv', 'Europe/Warsaw', 2, []]);
  assert.equal(ok.body.events[0].body.opens, Date.UTC(2026, 10, 29, 17), 'the dates are read in the browser\'s zone');
  const tz = await call(f, '/api/events/import?tz=Not/AZone', BEN, null, { raw: csv(good) });
  assert.equal(tz.body.tz, 'UTC');
  const lg = await call(f, `/api/events/import?league=${league}`, ANN, null, { raw: csv(good) });
  assert.deepEqual([lg.body.ok, lg.body.events.map((e) => e.season), lg.body.seasons], [true, ['new', 'new'], []]);
  assert.equal((await call(f, '/api/events/import?league=zzzzzzzz', ANN, null, { raw: csv(good) })).status, 404);
  const x = await call(f, '/api/events/import', BEN, null, { raw: templateXlsx(CAT, 'league', { now: NOW }) });
  assert.deepEqual([x.body.ok, x.body.format, x.body.events.length], [true, 'xlsx', 2]);
});

test('POST /api/leagues/:id/importevents: every event of a sheet at once, in their seasons, all or none', async () => {
  const f = world();
  const league = await mkLeague(f);
  const season = (await call(f, `/api/leagues/${league}/seasons`, ANN, { name: 'Winter', points: { table: [25, 18, 15], finisher: 1 }, power: [], drop: 0 })).body.id;
  const imported = (await call(f, `/api/events/import?league=${league}`, ANN, null, { raw: csv(templateCsv(CAT, 'league', { now: NOW })) })).body;
  assert.deepEqual(imported.events.map((e) => e.season), [season, season], 'the latest season');
  const events = imported.events.map((e) => ({ ...e.body, seasonId: e.season }));
  assert.equal((await call(f, `/api/leagues/${league}/importevents`, BEN, { events })).status, 403);
  assert.equal((await call(f, `/api/leagues/${league}/importevents`, ANN, { events: [] })).status, 400);
  const broken = await call(f, `/api/leagues/${league}/importevents`, ANN, { events: [events[0], { ...events[1], stages: [{ track: 'Nowhere', day: 1, weather: 'Clear', time: '09:00' }] }] });
  assert.equal(broken.status, 400);
  assert.match(broken.body.error, /^Round 2: Alsace: SS1: pick a stage/);
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM league_events').get().n, 0, 'one wrong: none made');
  const r = await call(f, `/api/leagues/${league}/importevents`, ANN, { events });
  assert.deepEqual([r.status, r.body.count, r.body.ids.length], [200, 2, 2], JSON.stringify(r.body));
  const rows = f.db.prepare('SELECT * FROM league_events ORDER BY id').all();
  assert.deepEqual(rows.map((e) => [e.name, e.season_id, e.league_id, e.car, e.car_class, e.opens]), [
    ['Round 1: Wales', season, league, null, 'Rally2/R5', events[0].opens], ['Round 2: Alsace', season, league, 'VW Polo GTI R5', null, events[1].opens]]);
  assert.equal(JSON.parse(rows[0].stages).length, 5);
  assert.deepEqual(JSON.parse(rows[1].rules).retire, 10);
  // the page of the event shows it as if it had been made in the builder
  const ev = await call(f, `/api/events/${rows[0].id}`, ANN);
  assert.equal(ev.status, 200);
  assert.equal(ev.body.stages.length, 5);
  // a new season, once, for the events that ask for it
  const again = await call(f, `/api/leagues/${league}/importevents`, ANN, { events: events.map((e) => ({ ...e, seasonId: 'new', name: e.name + ' again' })) });
  assert.equal(again.status, 200, JSON.stringify(again.body));
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM league_seasons').get().n, 2, 'one new season for both');
  assert.equal(new Set(f.db.prepare("SELECT season_id FROM league_events WHERE name LIKE '% again'").all().map((r) => r.season_id)).size, 1);
});

test('POST /api/rallies takes a sheet\'s event as it comes; a cup\'s `event` too', async () => {
  const f = world();
  const imported = (await call(f, '/api/events/import?for=rally', BEN, null, { raw: csv(templateCsv(CAT, 'rally', { now: NOW })) })).body;
  const r = await call(f, '/api/rallies', BEN, { ...imported.events[0].body, public: true });
  assert.equal(r.status, 200, JSON.stringify(r.body));
});
