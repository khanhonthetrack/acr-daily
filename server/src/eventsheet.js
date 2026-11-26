// Event sheets: events built in a spreadsheet instead of the builder form. One ROW IS ONE STAGE; the settings of the
// event (its name, car, dates, rules) are written on its first row and left empty on the rows below. A new event name
// starts the next event, so a whole season of rounds is one file. For leagues, rallies and cups alike (a cup's one
// event has no name, dates or season).
//
//   templateCsv / templateXlsx   the file to start from; the Excel one has drop-down lists (the stages, the cars, the
//                                classes, the weathers, every setting), a Guide sheet and the lists as sheets
//   readUpload(bytes)            a .xlsx or a .csv (any delimiter: , ; tab; UTF-8, UTF-16 or Windows-1252) -> rows of text
//   importEvents(rows, cat, {mode, tz, now, seasons})
//                                the rows -> {events, errors, warnings}. Every problem comes with the spreadsheet row
//                                and the column it is in and says what is wrong and what is allowed (or "did you mean"),
//                                so the sheet can be fixed in one go. Nothing is saved here; an event is the same as
//                                the builder sends (src/leagues.js checkEvent has the last word on every one).
//
// The row numbers are the spreadsheet's own (the header is row 1) so "row 7" is row 7 in Excel.

import { carByName } from './cars.js';
import { checkEvent, LEVELS, LIMITS, PENALTIES, ASSISTS, text } from './leagues.js';
import { xlsxRead, xlsxWrite, STYLE } from './xlsx.js';

export const SHEET = { maxBytes: 1_000_000, maxRows: 2000, maxEvents: 50, maxErrors: 60, validatedRows: 1000 };
export const MODES = ['league', 'rally', 'cup'];
const YES = ['yes', 'y', 'true', '1', 'on', 'x', 'tak', 'ja', 'oui', 'si'];
const NO = ['no', 'n', 'false', '0', 'off', 'nie', 'nein', 'non'];

// ------------------------------------------------------------------ the columns

// key; head: the header the template has; modes: where it is used; need: the sheet can't do without it (the cup's
// Event: no); list: the drop-down's name (src below); help: the Guide sheet and the cell's tooltip; def: what an empty
// cell means.
export const COLUMNS = [
  { key: 'event', head: 'Event', modes: ['league', 'rally', 'cup'], need: true, width: 28, aliases: ['eventname', 'name', 'round', 'roundname'],
    help: 'The name of the event, 3 to 60 characters. Write it on the first row of the event and leave it empty on the rows below; the next name starts the next event.' },
  { key: 'opens', head: 'Opens', modes: ['league', 'rally'], width: 18, text: true, aliases: ['open', 'opensat', 'opening', 'from'],
    help: 'When drivers can start the event: 2026-12-05 18:00 (year-month-day hour:minute, 24 hours, in your own time zone; add Z or +01:00 for another one).',
    def: 'when the event before it closes (the first event: the next full hour)' },
  { key: 'closes', head: 'Closes', modes: ['league', 'rally'], width: 18, text: true, aliases: ['close', 'closesat', 'closing', 'to', 'until'],
    help: 'When the event ends, in the same form as Opens. At most 62 days after it opens.', def: '7 days after it opens' },
  { key: 'season', head: 'Season', modes: ['league'], width: 16, aliases: ['championship'],
    help: 'The season (championship) the event counts for: its name as on the championship page, "new" for a new season, or "none" for a one-off event.',
    def: "the league's latest season (a new one if it has none)" },
  { key: 'car', head: 'Car', modes: ['league', 'rally', 'cup'], width: 30, list: 'cars', aliases: [],
    help: 'One car for everyone. Fill Car or Class, not both.' },
  { key: 'class', head: 'Class', modes: ['league', 'rally', 'cup'], width: 16, list: 'classes', warn: true, aliases: ['carclass', 'classes', 'carclasses'],
    help: 'A class: each driver picks a car of it. Several classes (each with its own results): write them with a comma, e.g. Rally2/R5, Rally4. A cup takes one.' },
  { key: 'day', head: 'Day', modes: ['league', 'rally', 'cup'], width: 6, number: [1, LIMITS.days], aliases: [],
    help: `The day of the stage, 1 to ${LIMITS.days}, counting up one at a time. Empty: the same day as the row above (the first stage: day 1). Every day opens with a service park.`, def: 'the day of the row above' },
  { key: 'stage', head: 'Stage', modes: ['league', 'rally', 'cup'], need: true, width: 38, list: 'stages', aliases: ['ss', 'stagename'],
    help: 'The stage, from the drop-down: Location: Stage name. The stages of several locations can follow each other in one event.' },
  { key: 'time', head: 'Time', modes: ['league', 'rally', 'cup'], need: true, width: 8, text: true, aliases: ['starttime', 'start', 'stagetime'],
    help: 'The time of day the stage starts at in the game, 24 hours: 09:30. Within a day, each stage starts later than the one before.' },
  { key: 'weather', head: 'Weather', modes: ['league', 'rally', 'cup'], width: 14, list: 'weathers', aliases: [],
    help: 'The weather of the stage.', def: 'Clear' },
  { key: 'service', head: 'Service park', modes: ['league', 'rally', 'cup'], width: 9, list: 'yesno', aliases: ['servicepark', 'servicebefore', 'serviceparkbefore'],
    help: 'yes: a service park before this stage (the damage is repaired there). The first stage of each day always has one.', def: 'no' },
  { key: 'damage', head: 'Damage', modes: ['league', 'rally', 'cup'], width: 11, list: 'levels', values: ['off', ...LEVELS.slice(1)], aliases: [],
    help: 'off, light, severe or realistic. The damage is carried from stage to stage.', def: 'light' },
  { key: 'wear', head: 'Wear', modes: ['league', 'rally', 'cup'], width: 11, list: 'levels', values: LEVELS, aliases: [],
    help: 'Tyre and mechanical wear: off, light, severe or realistic.', def: 'light' },
  { key: 'failures', head: 'Failures', modes: ['league', 'rally', 'cup'], width: 11, list: 'levels', values: LEVELS, aliases: ['mechanicalfailures', 'failure'],
    help: 'Mechanical failures: off, light, severe or realistic.', def: 'off' },
  { key: 'penalty', head: 'Penalties', modes: ['league', 'rally', 'cup'], width: 11, list: 'penalties', values: PENALTIES, aliases: ['penalty'],
    help: 'The penalties for cuts, respawns, jump starts: light or realistic.', def: 'light' },
  { key: 'respawn', head: 'Manual respawn', modes: ['league', 'rally', 'cup'], width: 10, list: 'onoff', aliases: ['respawn'],
    help: 'on: a driver can respawn by hand. off: a stuck driver retires.', def: 'on' },
  { key: 'assists', head: 'Driving aids', modes: ['league', 'rally', 'cup'], width: 10, list: 'assists', values: ASSISTS, aliases: ['assists', 'aids', 'drivingassists'],
    help: "any: each driver's choice. off: no ABS, traction control or starting handbrake assist.", def: 'any' },
  { key: 'hardcore', head: 'Hardcore', modes: ['league', 'rally', 'cup'], width: 9, list: 'yesno', aliases: ['hardcoremode'],
    help: "yes: the game's Hardcore Mode, which locks damage, wear, failures and penalties at realistic.", def: 'no' },
  { key: 'retire', head: 'Retire (min)', modes: ['league', 'rally', 'cup'], width: 9, number: [0, LIMITS.retireMinutes], aliases: ['retiremin', 'retiremins', 'retireminutes', 'retirement', 'dnf'],
    help: `A retirement keeps the driver in: the slowest time + this many minutes for each stage missed (0 to ${LIMITS.retireMinutes}). 0: a retirement is out of the event.`, def: '0' },
  { key: 'hide_stages', head: 'Hide stages', modes: ['league', 'rally', 'cup'], width: 9, list: 'yesno', aliases: ['hidestages', 'stageshidden'],
    help: 'yes: the stage names, lengths and maps are kept from the drivers until the event ends (each sees them when pressing DRIVE).', def: 'yes' },
  { key: 'hide_weather', head: 'Hide weather', modes: ['league', 'rally', 'cup'], width: 9, list: 'yesno', aliases: ['hideweather', 'weatherhidden'],
    help: 'yes: the weather is kept from the drivers until the event ends.', def: 'yes' },
  { key: 'hide_times', head: 'Hide times', modes: ['league', 'rally', 'cup'], width: 9, list: 'yesno', aliases: ['hidetimes', 'timeshidden'],
    help: "yes: the stage start times and the drivers' results are kept until the event ends.", def: 'yes' },
];
const colsOf = (mode) => COLUMNS.filter((c) => c.modes.includes(mode) && !(mode === 'cup' && c.key === 'event'));
const byKey = Object.fromEntries(COLUMNS.map((c) => [c.key, c]));

// ------------------------------------------------------------------ small helpers

/** A value compared loosely: no case, accents, spaces or punctuation ("Wales · Afon Bidno" = "wales: afon  bidno"). */
export const norm = (s) => String(s == null ? '' : s).normalize('NFD').toLowerCase().replace(/[^a-z0-9]/g, '');
const clean = (s) => String(s == null ? '' : s).replace(/[   ]/g, ' ').replace(/[\u0000-\u001f\u007f]/g, ' ').replace(/\s+/g, ' ').trim();
const shown = (s) => { const v = clean(s); return v.length > 60 ? v.slice(0, 57) + '...' : v; };
const q = (s) => `"${shown(s)}"`;
const p2 = (n) => String(n).padStart(2, '0');
const list = (a) => a.map((x) => `"${x}"`).join(', ');

function lcs(a, b) {
  let prev = new Array(b.length + 1).fill(0);
  for (let i = 1; i <= a.length; i++) {
    const row = new Array(b.length + 1).fill(0);
    for (let j = 1; j <= b.length; j++) row[j] = a[i - 1] === b[j - 1] ? prev[j - 1] + 1 : Math.max(prev[j], row[j - 1]);
    prev = row;
  }
  return prev[b.length];
}
function similarity(a, b) {
  if (!a || !b) return 0;
  if (a === b) return 1;
  let r = (2 * lcs(a, b)) / (a.length + b.length);
  if (Math.min(a.length, b.length) >= 4 && (a.includes(b) || b.includes(a))) r = Math.max(r, 0.75);
  return r;
}
/** The labels closest to what was typed: items [{label, keys: [normalised forms]}] -> up to n labels. When one is
 *  clearly the one meant, only it (and what is as near). */
function suggest(value, items, n = 3, min = 0.6) {
  const v = norm(value);
  if (!v) return [];
  const scored = items.map((it) => ({ label: it.label, s: Math.max(...it.keys.map((k) => similarity(v, k))) }))
    .filter((x) => x.s >= min).sort((a, b) => b.s - a.s);
  if (!scored.length) return [];
  return scored.filter((x) => x.s >= scored[0].s - 0.1).slice(0, n).map((x) => x.label);
}
const didYouMean = (alts) => (alts.length ? ` Did you mean ${alts.map((a) => `"${a}"`).join(' or ')}?` : '');
const mojibake = (s) => /�|Ã[\u0080-¿]|Ã©|Â/.test(s);
const encodingHint = (s) => (mojibake(s) ? ' The accents look damaged: save the file as "CSV UTF-8" (or send the .xlsx), or pick the value from the template\'s drop-down.' : '');

// ------------------------------------------------------------------ reading a file

/** Bytes of a .csv/.txt -> text. UTF-8 (with or without BOM), UTF-16 (Excel's "Unicode Text"), else Windows-1252 (what a
 *  Western Excel's plain "CSV" is). -> {text, encoding} */
export function decodeText(bytes) {
  if (bytes[0] === 0xff && bytes[1] === 0xfe) return { text: new TextDecoder('utf-16le').decode(bytes.subarray(2)), encoding: 'UTF-16' };
  if (bytes[0] === 0xfe && bytes[1] === 0xff) return { text: new TextDecoder('utf-16be').decode(bytes.subarray(2)), encoding: 'UTF-16' };
  try { return { text: new TextDecoder('utf-8', { fatal: true }).decode(bytes), encoding: 'UTF-8' }; } catch { /* (not UTF-8) */ }
  return { text: new TextDecoder('windows-1252').decode(bytes), encoding: 'Windows-1252' };
}

/** CSV text -> rows of cells. The delimiter is found from the first line (a comma; or the semicolon a European Excel
 *  saves; or a tab), quotes work as in RFC 4180, a line the file starts with as "sep=;" is Excel's own hint. */
export function parseCsv(input) {
  let s = String(input).replace(/^﻿/, '');
  let d = null;
  const hint = /^sep=(.)\r?\n/i.exec(s);
  if (hint) { d = hint[1]; s = s.slice(hint[0].length); }
  if (!d) {
    const n = { ',': 0, ';': 0, '\t': 0 };
    let inQ = false;
    for (const ch of s) {
      if (ch === '"') inQ = !inQ;
      else if (!inQ && (ch === '\n' || ch === '\r')) { if (n[','] + n[';'] + n['\t']) break; }
      else if (!inQ && ch in n) n[ch]++;
    }
    d = n[';'] > n[','] && n[';'] >= n['\t'] ? ';' : n['\t'] > n[','] ? '\t' : ',';
  }
  const rows = [];
  let row = [], f = '', inQ = false, any = false;
  const end = () => { row.push(f); f = ''; };
  for (let i = 0; i < s.length; i++) {
    const ch = s[i];
    if (inQ) {
      if (ch === '"') { if (s[i + 1] === '"') { f += '"'; i++; } else inQ = false; } else f += ch;
    } else if (ch === '"' && f === '') { inQ = true; any = true; }
    else if (ch === d) { end(); any = true; }
    else if (ch === '\n' || ch === '\r') {
      if (ch === '\r' && s[i + 1] === '\n') i++;
      end(); rows.push(row); row = []; any = false;
      if (rows.length > SHEET.maxRows + 50) break;
    } else { f += ch; any = true; }
  }
  if (any || f !== '' || row.length) { end(); rows.push(row); }
  return rows;
}

/** An uploaded file -> {rows, format, encoding?, notes: []}; throws an Error with what is wrong with the file itself. */
export async function readUpload(bytes) {
  if (!bytes || !bytes.length) throw new Error('the file is empty');
  if (bytes.length > SHEET.maxBytes) throw new Error(`the file is too big (${Math.round(bytes.length / 1000)} kB; at most ${SHEET.maxBytes / 1000} kB)`);
  if (bytes[0] === 0x50 && bytes[1] === 0x4b) {
    let r;
    try { r = await xlsxRead(bytes, 'Events'); } catch (e) {
      throw new Error(`this is not a readable Excel file (.xlsx): ${e.message}. Save it again as .xlsx or as CSV.`);
    }
    const notes = r.sheets.length > 1 && r.sheet.toLowerCase() !== 'events'
      ? [`Read the sheet "${r.sheet}" (a sheet called "Events" is what the template has).`] : [];
    return { rows: r.rows, format: 'xlsx', notes };
  }
  if (bytes[0] === 0xd0 && bytes[1] === 0xcf && bytes[2] === 0x11 && bytes[3] === 0xe0) {
    throw new Error('this is an old Excel file (.xls): save it as .xlsx or as CSV and send that');
  }
  const { text: t, encoding } = decodeText(bytes);
  const notes = encoding === 'Windows-1252' ? ['The file is not UTF-8: read as Windows-1252. If an accented letter shows wrong, save it as "CSV UTF-8".'] : [];
  return { rows: parseCsv(t), format: 'csv', encoding, notes };
}

// ------------------------------------------------------------------ dates

function zoneOffset(ts, tz) {
  const f = new Intl.DateTimeFormat('en-US', { timeZone: tz, hourCycle: 'h23', year: 'numeric', month: 'numeric', day: 'numeric',
    hour: 'numeric', minute: 'numeric', second: 'numeric' });
  const g = Object.fromEntries(f.formatToParts(new Date(ts)).map((x) => [x.type, +x.value]));
  return Date.UTC(g.year, g.month - 1, g.day, g.hour, g.minute, g.second) - Math.floor(ts / 1000) * 1000;
}
/** A wall-clock time in a time zone -> the instant (ms). */
export function zonedToUtc(y, mo, d, h, mi, tz) {
  let t = Date.UTC(y, mo - 1, d, h, mi);
  for (let i = 0; i < 2; i++) t = Date.UTC(y, mo - 1, d, h, mi) - zoneOffset(t, tz);
  return t;
}
export const goodZone = (tz) => { try { new Intl.DateTimeFormat('en', { timeZone: tz }); return !!tz; } catch { return false; } };

/** "2026-12-05 18:00", "5.12.2026 18:00", "2026-12-05T18:00Z", "2026-12-05 18:00 +01:00" -> ms, or {error}. */
export function parseWhen(v, tz = 'UTC') {
  const s = clean(v);
  let m = /^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ]+(\d{1,2})[:.](\d{2})(?::\d{2}(?:\.\d+)?)?)?\s*(Z|[+-]\d{2}(?::?\d{2})?)?$/i.exec(s);
  let y, mo, d, h, mi, off;
  if (m) { [y, mo, d, h, mi, off] = [+m[1], +m[2], +m[3], m[4], m[5], m[6]]; }
  else if ((m = /^(\d{1,2})\.(\d{1,2})\.(\d{4})(?:\s+(\d{1,2})[:.](\d{2})(?::\d{2})?)?$/.exec(s))) {
    [d, mo, y, h, mi, off] = [+m[1], +m[2], +m[3], m[4], m[5], undefined];
  } else if (/^\d{1,2}\/\d{1,2}\/\d{2,4}/.test(s)) {
    return { error: `${q(s)} could be day/month or month/day. Write it as year-month-day: 2026-12-05 18:00.` };
  } else return { error: `${q(s)} is not a date and time. Write it as year-month-day hour:minute: 2026-12-05 18:00.` };
  if (h === undefined || h === null) return { error: `${q(s)} has no time. Add the hour and minute: ${s} 18:00.` };
  h = +h; mi = +mi;
  const t = Date.UTC(y, mo - 1, d, h, mi);
  const c = new Date(t);
  if (mo < 1 || mo > 12 || d < 1 || h > 23 || mi > 59 || c.getUTCMonth() !== mo - 1 || c.getUTCDate() !== d) {
    return { error: `${q(s)} is not a real date and time (year-month-day hour:minute, e.g. 2026-12-05 18:00).` };
  }
  if (off) {
    if (/^z$/i.test(off)) return { ms: t };
    const sign = off[0] === '-' ? -1 : 1, digits = off.slice(1).replace(':', '');
    return { ms: t - sign * ((+digits.slice(0, 2)) * 60 + (+digits.slice(2, 4) || 0)) * 60000 };
  }
  return { ms: zonedToUtc(y, mo, d, h, mi, tz) };
}
/** "9:30", "09:30", "9.30", "09:30:00", "9:30 pm" -> minutes since midnight, or null. */
export function parseTime(v) {
  const s = clean(v);
  let m = /^(\d{1,2})[:.h](\d{2})(?::\d{2}(?:\.\d+)?)?$/i.exec(s);
  if (m) return +m[1] < 24 && +m[2] < 60 ? +m[1] * 60 + +m[2] : null;
  m = /^(\d{1,2})(?::(\d{2}))?\s*(am|pm)$/i.exec(s);
  if (m && +m[1] >= 1 && +m[1] <= 12 && (m[2] === undefined || +m[2] < 60)) return ((+m[1] % 12) + (/pm/i.test(m[3]) ? 12 : 0)) * 60 + (+m[2] || 0);
  return null;
}
const hhmm = (min) => `${p2(Math.floor(min / 60))}:${p2(min % 60)}`;
const fmtUtc = (ms) => { const d = new Date(ms); return `${d.getUTCFullYear()}-${p2(d.getUTCMonth() + 1)}-${p2(d.getUTCDate())} ${p2(d.getUTCHours())}:${p2(d.getUTCMinutes())}`; };

// ------------------------------------------------------------------ importing

/** What the sheet's words mean in the catalog (src/leagues.js catalog()): the stage, car, class and weather names. */
function lookups(cat) {
  const stages = [];
  for (const r of cat.rallies) for (const st of r.stages) {
    const label = `${r.name}: ${st.name}`;
    stages.push({ label, st, rally: r.name, keys: [norm(label), norm(st.name), norm(st.track), norm(st.stageId)] });
  }
  return { stages, weathers: cat.weathers.map((w) => ({ label: w.label, id: w.id, keys: [norm(w.label), norm(w.id)] })) };
}
export const stageLabels = (cat) => lookups(cat).stages.map((x) => x.label);

function boolOf(v) { const n = norm(v); return YES.includes(n) ? true : NO.includes(n) ? false : null; }

/**
 * rows (a sheet's cells as text) -> {events, errors, warnings}. mode: 'league' | 'rally' | 'cup'. tz: the time zone the
 * dates are in (IANA name). seasons: a league's seasons [{id, name}] to resolve the Season column against (null: the
 * names stay as written). An event: {name, rows: [first, last], season, body, summary}: body is what POST
 * /api/leagues/:id/events, /api/rallies and a cup's `event` take; summary is for the preview.
 */
export function importEvents(rows, cat, { mode = 'league', tz = 'UTC', now = Date.now(), seasons = null } = {}) {
  const errors = [], warnings = [], events = [];
  const col = new Map();                                   // key -> its column index
  const order = new Map();                                 // (an error's place in its row: the sheet's own column order)
  const fail = (row, key, message, o = {}) => { const e = { row, column: key ? (byKey[key] ? byKey[key].head : key) : null, message, ...o }; order.set(e, col.has(key) ? col.get(key) : -1); errors.push(e); };
  const warn = (message, row = null) => warnings.push({ row, message });
  if (!MODES.includes(mode)) mode = 'league';
  const L = lookups(cat);

  // the header: the first row with anything in it
  const hi = rows.findIndex((r) => r.some((c) => clean(c)));
  if (hi < 0) { fail(null, null, 'The file is empty: it needs the header row of the template and a row for each stage.'); return { events, errors, warnings }; }
  const known = [];
  for (const [j, h] of rows[hi].entries()) {
    const n = norm(h);
    if (!n) continue;
    const c = COLUMNS.find((x) => norm(x.head) === n || x.aliases.includes(n) || norm(x.key) === n);
    if (!c) { known.push(h); continue; }
    if (col.has(c.key)) fail(hi + 1, c.key, `The column "${c.head}" is there twice (columns ${colLetter(col.get(c.key))} and ${colLetter(j)}). Keep one.`);
    else col.set(c.key, j);
    if (!c.modes.includes(mode)) col.set('~' + c.key, j);       // (in the file, but not used here)
  }
  for (const h of known) {
    const alts = suggest(h, COLUMNS.map((c) => ({ label: c.head, keys: [norm(c.head), ...c.aliases] })), 1, 0.7);
    warn(`The column "${shown(h)}" is not one of the template's, so it is ignored.${alts.length ? ` (Did you mean "${alts[0]}"?)` : ''}`, hi + 1);
  }
  const need = mode === 'cup' ? ['stage', 'time'] : ['event', 'stage', 'time'];
  for (const k of need) if (!col.has(k)) fail(hi + 1, null, `The column "${byKey[k].head}" is missing from the header row. Use the template's header, or add a column called "${byKey[k].head}".`);
  if (!col.has('car') && !col.has('class')) fail(hi + 1, null, 'The columns "Car" and "Class" are both missing from the header row: the cars of the event are written there.');
  if (errors.length) return { events, errors, warnings };

  // the rows: each non-empty one is a stage; an event is the rows from its name to the next name
  const recs = [];
  for (let i = hi + 1; i < rows.length; i++) {
    const cells = rows[i] || [];
    if (!cells.some((c) => clean(c))) continue;
    recs.push({ row: i + 1, v: (k) => (col.has(k) && !col.has('~' + k) ? clean(cells[col.get(k)]) : '') ,
      raw: (k) => (col.has(k) ? clean(cells[col.get(k)]) : '') });
  }
  if (rows.length - hi - 1 > SHEET.maxRows) { fail(null, null, `The file has more than ${SHEET.maxRows} rows: split it into several files.`); return { events, errors, warnings }; }
  if (!recs.length) { fail(null, null, 'There is a header row but no stages below it: every row under the header is one stage of an event.'); return { events, errors, warnings }; }
  if (mode !== 'league') for (const k of ['season', 'opens', 'closes']) {
    if (mode === 'rally' && k !== 'season') continue;
    const r = recs.find((x) => x.raw(k));
    if (r && col.has('~' + k)) warn(`The "${byKey[k].head}" column is not used ${mode === 'cup' ? 'for a cup (it sets its own rounds and has no season)' : 'for a rally (it is no championship\'s)'}: ignored.`, r.row);
  }

  const groups = [];
  const seen = new Map();
  let cur = null;
  for (const r of recs) {
    const name = col.has('event') ? r.v('event') : '';
    if (name && (!cur || norm(name) !== norm(cur.name))) {
      if (seen.has(norm(name))) {
        fail(r.row, 'event', `"${shown(name)}" is the name of the event at row ${seen.get(norm(name))} too. The rows of an event must follow each other: give this event another name, or move its rows up under the first.`);
        cur = { name, rows: [], first: r.row };                   // (read on, so its own mistakes show too)
      } else {
        cur = { name, rows: [], first: r.row };
        seen.set(norm(name), r.row);
      }
      groups.push(cur);
    } else if (!cur) {
      if (mode === 'cup' || !col.has('event')) { cur = { name: '', rows: [], first: r.row }; groups.push(cur); }
      else { fail(r.row, 'event', 'This row has no event name, and no event has begun above it. Write the name of the event on its first row.'); continue; }
    }
    cur.rows.push(r);
  }
  if (groups.length > SHEET.maxEvents) fail(groups[SHEET.maxEvents].first, 'event', `At most ${SHEET.maxEvents} events in one file: this is event number ${SHEET.maxEvents + 1}. Split the file.`);

  let prevClose = null;
  for (const g of groups.slice(0, SHEET.maxEvents)) {
    const ev = buildEvent(g);
    if (ev) { events.push(ev); if (ev.body.closes) prevClose = ev.body.closes; }
  }
  // (the problems in the order of the sheet: the rows, then those of the whole file)
  errors.sort((a, b) => (a.row == null ? -1 : b.row == null ? 1 : a.row - b.row || order.get(a) - order.get(b)));
  return { events, errors, warnings };

  function buildEvent(g) {
    const e0 = errors.length;
    const label = g.name || 'the event';
    const first = g.rows[0].row;
    const bad = (row, key, message, o = {}) => fail(row, key, message, { event: g.name || null, ...o });
    // an event-level setting: written on the first row, empty or the same below (read once: a clash is told once)
    const memo = new Map();
    const setting = (key) => {
      if (memo.has(key)) return memo.get(key);
      let val = '', at = null;
      for (const r of g.rows) {
        const v = r.v(key);
        if (!v) continue;
        if (!val) { val = v; at = r.row; }
        else if (norm(v) !== norm(val)) {
          bad(r.row, key, `${q(v)} is not the same as ${q(val)} in row ${at}, a row of ${g.name ? `the event "${g.name}"` : 'the same event'}. "${byKey[key].head}" is one setting for the whole event: write it on its first row and leave it empty below, or repeat the same value.`, { value: shown(v) });
        }
      }
      const out = { val, at: at || first };
      memo.set(key, out);
      return out;
    };
    if (g.name && g.name.length > LIMITS.name) bad(first, 'event', `The event name has ${g.name.length} characters: ${LIMITS.name} at most.`, { value: shown(g.name) });
    else if (mode !== 'cup' && text(g.name, LIMITS.name).length < 3) bad(first, 'event', 'The event name needs 3 to 60 characters.', { value: shown(g.name) });

    // the car
    const carC = setting('car'), clsC = setting('class');
    let car = null, carClass = null, carClasses = null;
    if (carC.val && clsC.val) {
      const later = carC.at > clsC.at ? 'car' : 'class';
      bad(later === 'car' ? carC.at : clsC.at, later, `Car (${q(carC.val)}, row ${carC.at}) and Class (${q(clsC.val)}, row ${clsC.at}) are both filled for this event. Fill Car when everyone drives one car, or Class when each driver picks a car of it, and leave the other empty.`);
    }
    else if (!carC.val && !clsC.val) bad(first, 'car', 'No car for this event: fill "Car" (everyone drives it) or "Class" (each driver picks a car of it) on its first row.');
    else if (carC.val) {
      const names = cat.cars.map((c) => ({ label: c.name, keys: [norm(c.name)] }));
      const found = cat.cars.find((c) => norm(c.name) === norm(carC.val)) || (() => { const c = carByName(carC.val); return c && cat.cars.find((x) => x.name === c.name); })();
      if (found) car = found.name;
      else bad(carC.at, 'car', `${q(carC.val)} is not a car in the game.${didYouMean(suggest(carC.val, names))}${encodingHint(carC.val)} Pick it from the drop-down, or see the Lists sheet.`, { value: shown(carC.val) });
    } else {
      const picks = [];
      let ok = true;
      for (const part of clsC.val.split(/[,;+|]/).map(clean).filter(Boolean)) {
        const exact = cat.classes.filter((k) => norm(k.cls) === norm(part));
        const prefix = exact.length ? exact : cat.classes.filter((k) => norm(k.cls.split('/')[0]) === norm(part));
        if (prefix.length === 1) { if (!picks.includes(prefix[0].cls)) picks.push(prefix[0].cls); continue; }
        ok = false;
        bad(clsC.at, 'class', `${q(part)} is not a car class.${didYouMean(suggest(part, cat.classes.map((k) => ({ label: k.cls, keys: [norm(k.cls)] }))))} The classes: ${list(cat.classes.map((k) => k.cls))}.`, { value: shown(part) });
      }
      if (ok && !picks.length) bad(clsC.at, 'class', 'The class is empty.');
      else if (ok && picks.length > 1 && mode === 'cup') bad(clsC.at, 'class', `A cup's matches take one car or one class: this has ${picks.length} (${picks.join(', ')}).`);
      else if (ok) { if (picks.length > 1) carClasses = picks; else carClass = picks[0]; }
    }

    // the rules: what is left empty is the builder's default
    const rules = {};
    const level = (key, rk, opts) => {
      const s = setting(key);
      if (!s.val) return;
      const n = norm(s.val), hit = opts.find((o) => norm(o) === n) || (key === 'assists' && ['on', 'yes', 'all'].includes(n) ? 'any' : null) || (n === 'none' && opts.includes('off') ? 'off' : null);
      if (!hit) bad(s.at, key, `${q(s.val)} is not allowed for "${byKey[key].head}". Use ${list(opts)}.`, { value: shown(s.val) });
      else if (key === 'damage') { rules.damage = hit !== 'off'; if (hit !== 'off') rules.damageIntensity = hit; }
      else rules[rk] = hit;
    };
    level('damage', 'damage', byKey.damage.values);
    level('wear', 'wear', LEVELS);
    level('failures', 'failures', LEVELS);
    level('penalty', 'penalty', PENALTIES);
    level('assists', 'assists', ASSISTS);
    const flag = (key) => {
      const s = setting(key);
      if (!s.val) return undefined;
      const b = boolOf(s.val);
      if (b === null) bad(s.at, key, `${q(s.val)} is not yes or no${key === 'respawn' ? ' (on or off)' : ''}.`, { value: shown(s.val) });
      return b === null ? undefined : b;
    };
    const rs = flag('respawn'); if (rs !== undefined) rules.respawn = rs;
    const hc = flag('hardcore'); if (hc !== undefined) rules.hardcore = hc;
    if (rules.hardcore && ['damage', 'wear', 'failures', 'penalty'].some((k) => setting(k).val)) {
      warn(`Event "${g.name}": Hardcore Mode locks damage, wear, failures and penalties at realistic, so what is written in those cells is not used.`, first);
    }
    const rt = setting('retire');
    if (rt.val) {
      if (!/^\d+(\.0+)?$/.test(rt.val) || +rt.val > LIMITS.retireMinutes) bad(rt.at, 'retire', `${q(rt.val)} is not allowed for "Retire (min)": a whole number of minutes from 0 to ${LIMITS.retireMinutes}.`, { value: shown(rt.val) });
      else if (+rt.val > 0) rules.retire = Math.round(+rt.val);
    }
    let hide;
    for (const [key, k] of [['hide_stages', 'stages'], ['hide_weather', 'weather'], ['hide_times', 'times']]) {
      const b = flag(key);
      if (b !== undefined) (hide = hide || {})[k] = b;
    }

    // the stages, one a row: every cell of a row is read, so one pass over the sheet shows all that is wrong
    const stages = [], where = [];
    let prev = null, prevRow = null, skip = false;
    for (const r of g.rows) {
      let ok = true;
      const rowBad = (key, message, value) => { ok = false; bad(r.row, key, message, value === undefined ? {} : { value: shown(value) }); };
      // the stage
      const sv = r.v('stage');
      let hit = null;
      if (!sv) rowBad('stage', 'This row has no stage. Every row of an event is one stage: the first row carries the settings of the event and its first stage. Delete the row if it is not one.');
      else {
        const nv = norm(sv);
        let hits = L.stages.filter((x) => x.keys[0] === nv);
        if (!hits.length) hits = L.stages.filter((x) => x.keys.includes(nv));
        if (hits.length > 1) rowBad('stage', `${q(sv)} is the name of stages in several locations: ${list(hits.map((h) => h.label))}. Write the location in front: "Location: Stage".`, sv);
        else if (!hits.length) rowBad('stage', `${q(sv)} is not a stage the game has.${didYouMean(suggest(sv, L.stages))}${encodingHint(sv)} Pick it from the drop-down; the Lists sheet has all of them.`, sv);
        else hit = hits[0];
      }
      // the day (empty: the day of the stage above)
      let day = prev ? prev.day : 1, dayOk = true;
      const dv = r.v('day');
      if (dv) {
        if (!/^\d+(\.0+)?$/.test(dv)) { rowBad('day', `${q(dv)} is not a day number. Use 1, 2, 3...`, dv); dayOk = false; }
        else day = Math.round(+dv);
      }
      if (dayOk) {
        if (!prev && day !== 1) { rowBad('day', `The first stage of an event is on day 1, not day ${day}.`, dv); dayOk = false; }
        else if (prev && day < prev.day) { rowBad('day', `Day ${day} comes after day ${prev.day} (row ${prevRow}). The days go up, never back: the stages are driven in the order of the rows.`, dv); dayOk = false; }
        else if (prev && day > prev.day + 1) { rowBad('day', `Day ${day} follows day ${prev.day} (row ${prevRow}): the days count up one at a time, so day ${prev.day + 1} is next.`, dv); dayOk = false; }
        else if (day > LIMITS.days) { rowBad('day', `At most ${LIMITS.days} days in an event.`, dv); dayOk = false; }
      }
      // the time
      const tv = r.v('time');
      const min = tv ? parseTime(tv) : null;
      if (min === null) rowBad('time', tv ? `${q(tv)} is not a time of day. Write it as hour:minute in 24 hours, e.g. 09:30 or 14:00.` : 'The start time is empty. Write it as hour:minute in 24 hours, e.g. 09:30.', tv);
      else if (dayOk && prev && prev.day === day && min <= prev.min) {
        rowBad('time', `This stage starts at ${hhmm(min)}, which is not after ${hhmm(prev.min)} (row ${prevRow}), the stage before it on day ${day}. Within a day the stages start in time order: change a time, or move the stage to the next day.`, tv);
      }
      // the weather
      let weather = 'Clear';
      const wv = r.v('weather');
      if (wv) {
        const w = L.weathers.find((x) => x.keys.includes(norm(wv)));
        if (!w) rowBad('weather', `${q(wv)} is not a weather.${didYouMean(suggest(wv, L.weathers))} The weathers: ${list(cat.weathers.map((x) => x.label))}.`, wv);
        else weather = w.id;
      }
      let service = false;
      const sv2 = r.v('service');
      if (sv2) {
        const b = boolOf(sv2);
        if (b === null) rowBad('service', `${q(sv2)} is not yes or no.`, sv2); else service = b;
      }
      // (a stage with a good day and time still counts for the order of those after it)
      if (dayOk && min !== null && !(prev && prev.day === day && min <= prev.min)) { prev = { day, min }; prevRow = r.row; }
      if (!ok) { skip = true; continue; }
      if (stages.length >= LIMITS.stages) { bad(r.row, 'stage', `At most ${LIMITS.stages} stages in an event: this is stage number ${stages.length + 1}. Split the event in two.`); skip = true; break; }
      if (stages.filter((x) => x.day === day).length >= LIMITS.stagesPerDay) { bad(r.row, 'stage', `At most ${LIMITS.stagesPerDay} stages on a day: day ${day} is full. Put this stage on day ${day + 1}.`); skip = true; continue; }
      stages.push({ track: hit.st.track, day, service, weather, time: hhmm(min) });
      where.push({ row: r.row, rally: hit.rally, len: hit.st.lengthM });
    }

    // when it opens and closes
    let opens = null, closes = null;
    if (mode !== 'cup') {
      const o = setting('opens'), c = setting('closes');
      if (o.val) { const p = parseWhen(o.val, tz); if (p.error) bad(o.at, 'opens', p.error, { value: shown(o.val) }); else opens = p.ms; }
      else opens = mode === 'league' && prevClose ? prevClose : Math.ceil(now / 3600000) * 3600000;
      if (c.val) { const p = parseWhen(c.val, tz); if (p.error) bad(c.at, 'closes', p.error, { value: shown(c.val) }); else closes = p.ms; }
      else if (opens !== null) closes = opens + 7 * 86400000;
      if (opens !== null && closes !== null) {
        if (closes <= opens) bad(c.val ? c.at : first, 'closes', `The event closes before it opens: Closes (${c.val || 'the default'}) must be later than Opens (${o.val || 'the default'}).`, { value: shown(c.val) });
        else if (closes - opens > LIMITS.windowDays * 86400000) bad(c.val ? c.at : first, 'closes', `The event would be open ${Math.ceil((closes - opens) / 86400000)} days: at most ${LIMITS.windowDays}.`, { value: shown(c.val) });
        else if (closes < now + 3600000) bad(c.val ? c.at : first, 'closes', 'The event closes in the past, or within the hour: it must stay open for at least another hour.', { value: shown(c.val) });
      }
    }
    let seasonId, seasonName = '';
    if (mode === 'league') {
      const s = setting('season');
      seasonName = s.val;
      if (seasons) {
        const n = norm(s.val);
        if (!s.val) seasonId = seasons.length ? seasons[seasons.length - 1].id : 'new';
        else if (['none', 'oneoff', 'no', 'nochampionship'].includes(n)) seasonId = null;
        else if (n === 'new') seasonId = 'new';
        else {
          const hit = seasons.find((x) => norm(x.name) === n);
          if (hit) seasonId = hit.id;
          else bad(s.at, 'season', `This league has no season called ${q(s.val)}.${didYouMean(suggest(s.val, seasons.map((x) => ({ label: x.name, keys: [norm(x.name)] }))))} ${seasons.length ? `Its seasons: ${list(seasons.map((x) => x.name))}.` : 'It has no season yet.'} Write "new" for a new season or "none" for a one-off event.`, { value: shown(s.val) });
        }
      }
    }

    if (errors.length > e0 || skip || !stages.length) {
      if (!stages.length && errors.length === e0) bad(first, 'stage', 'This event has no stages.');
      return null;
    }
    // the last word: the builder's own checks (what the rows can't see)
    const input = { name: g.name || 'Cup match', rally: where[0].rally, ...(car ? { car } : carClass ? { carClass } : { carClasses }), rules, stages, hide,
      opens: mode === 'cup' ? now : opens, closes: mode === 'cup' ? now + 2 * 3600000 : closes };
    const c = checkEvent(input, cat, now);
    if (c.error) {
      const m = /^SS(\d+):/.exec(c.error);
      bad(m && where[+m[1] - 1] ? where[+m[1] - 1].row : first, null, c.error);
      return null;
    }
    const v = c.value;
    const places = [...new Set(where.map((w) => w.rally))];
    const body = { name: g.name || '', rally: where[0].rally, ...(v.car ? { car: v.car } : v.car_classes ? { carClasses: v.car_classes } : { carClass: v.car_class }),
      rules: v.rules, stages: v.stages, hide: v.hide || { weather: false, times: false, stages: false },
      hideSet: v.hide || { weather: false, times: false, stages: false } };
    if (mode !== 'cup') { body.opens = v.opens; body.closes = v.closes; }
    return { name: g.name, rows: [first, g.rows[g.rows.length - 1].row], season: mode === 'league' ? (seasons ? seasonId : seasonName) : undefined,
      seasonName: mode === 'league' ? seasonName : undefined, body,
      summary: { stages: v.stages.length, days: v.stages[v.stages.length - 1].day, km: Math.round(where.reduce((a, w) => a + (w.len || 0), 0) / 100) / 10,
        places, car: v.car || null, classes: v.car_classes || (v.car_class ? [v.car_class] : []),
        ...(mode === 'cup' ? {} : { opens: v.opens, closes: v.closes }) } };
  }
}
const colLetter = (i) => { let s = ''; for (i++; i > 0; i = Math.floor((i - 1) / 26)) s = String.fromCharCode(65 + ((i - 1) % 26)) + s; return s; };

/** The errors the way they are listed: no more than SHEET.maxErrors, and how many were left out. */
export function capErrors(errors) {
  return { errors: errors.slice(0, SHEET.maxErrors), more: Math.max(0, errors.length - SHEET.maxErrors) };
}

// ------------------------------------------------------------------ the template

/** The examples the template starts with, made of the catalog's own stages so they always import: [[row object]] (one
 *  array a event; a row object is by column key). */
function exampleEvents(cat, now) {
  const withStages = cat.rallies.filter((r) => r.stages.length);
  if (!withStages.length) return [];
  const first = withStages.find((r) => r.name === 'Wales') || withStages[0];
  const second = withStages.find((r) => r !== first) || first;
  const stage = (r, i) => `${r.name}: ${r.stages[i % r.stages.length].name}`;
  const d0 = new Date(now); d0.setUTCHours(18, 0, 0, 0);
  const at = (days) => fmtUtc(d0.getTime() + days * 86400000);
  const car = (cat.cars.find((c) => c.cls === 'Rally2/R5') || cat.cars[0]).name;
  const cls = (cat.classes.find((c) => c.cls === 'Rally2/R5') || cat.classes[0]).cls;
  const wx = (label) => (cat.weathers.some((w) => w.label === label) ? label : cat.weathers[0].label);
  const make = (head, rally, plan) => plan.map(([day, i, time, weather, service], n) =>
    ({ ...(n === 0 ? head : {}), day: String(day), stage: stage(rally, i), time, weather: wx(weather), service }));
  return [
    make({ event: `Round 1: ${first.name}`, opens: at(3), closes: at(10), class: cls }, first,
      [[1, 0, '09:00', 'Clear', ''], [1, 1, '11:30', 'Light clouds', ''], [1, 2, '14:00', 'Clear', 'yes'], [2, 3, '09:00', 'Light rain', ''], [2, 4, '12:00', 'Light fog', '']]),
    make({ event: `Round 2: ${second.name}`, closes: at(17), car, damage: 'severe', wear: 'light', failures: 'light', retire: '10', hide_weather: 'no' }, second,
      [[1, 0, '10:00', 'Clear', ''], [1, 1, '13:00', 'Clear', ''], [2, 2, '10:00', 'Light clouds', '']]),
  ];
}

/** The template's table for a mode: {cols, head: [..], rows: [[..]]}. A league's has two events, a rally's and a cup's one. */
export function templateTable(cat, mode = 'league', now = Date.now()) {
  if (!MODES.includes(mode)) mode = 'league';
  const cols = colsOf(mode);
  const events = exampleEvents(cat, now).slice(0, mode === 'league' ? 2 : 1);
  return { cols, head: cols.map((c) => c.head), rows: events.flat().map((r) => cols.map((c) => r[c.key] || '')) };
}

const csvLine = (cells, d) => cells.map((c) => { const s = String(c == null ? '' : c); return s.includes(d) || /["\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; }).join(d);
/** The CSV template: UTF-8 with the BOM Excel wants, CRLF lines. sep: ',' or ';' (a European Excel's list separator). */
export function templateCsv(cat, mode = 'league', { sep = ',', now = Date.now() } = {}) {
  const t = templateTable(cat, mode, now);
  const d = sep === ';' ? ';' : ',';
  return '﻿' + [t.head, ...t.rows].map((r) => csvLine(r, d)).join('\r\n') + '\r\n';
}

const WHAT = { league: 'a league', rally: 'a rally', cup: "a cup's matches" };
const WHERE = { league: "the league's NEW EVENT page", rally: 'the NEW RALLY page', cup: "the cup's creation form (CUPS page)" };
const lines = (s, width) => Math.max(1, Math.ceil(String(s).length / width));

/** The Excel template: the Events sheet (header, an example, a drop-down and a tip on every cell that takes a set of
 *  values), a Guide and the Lists (stages with their lengths, cars, classes, weathers). */
export function templateXlsx(cat, mode = 'league', { now = Date.now() } = {}) {
  if (!MODES.includes(mode)) mode = 'league';
  const t = templateTable(cat, mode, now);
  const L = lookups(cat);
  const stageList = L.stages, cars = cat.cars, classes = cat.classes, weathers = cat.weathers;
  const last = SHEET.validatedRows + 1;
  const range = (k) => { const l = colLetter(t.cols.findIndex((c) => c.key === k)); return `${l}2:${l}${last}`; };
  const inline = (a) => `"${a.join(',')}"`;
  const SRC = { stages: `Lists!$A$2:$A$${stageList.length + 1}`, cars: `Lists!$F$2:$F$${cars.length + 1}`,
    classes: `Lists!$J$2:$J$${classes.length + 1}`, weathers: `Lists!$N$2:$N$${weathers.length + 1}`,
    yesno: inline(['yes', 'no']), onoff: inline(['on', 'off']), penalties: inline(PENALTIES), assists: inline(ASSISTS) };
  const validations = t.cols.map((c) => {
    const v = { sqref: range(c.key), title: c.head, prompt: c.help + (c.def ? ` Empty: ${c.def}.` : '') };
    if (c.list) {
      const values = c.values || (c.list === 'yesno' ? ['yes', 'no'] : c.list === 'onoff' ? ['on', 'off'] : null);
      Object.assign(v, { type: 'list', f1: c.list === 'levels' ? inline(c.values) : SRC[c.list], warn: !!c.warn, errorTitle: c.head,
        error: c.warn ? 'Not in the list. A class can be typed (several with commas); the import checks it.'
          : values ? `Pick one of: ${values.join(', ')}.` : `Pick it from the list (the Lists sheet has them all).` });
    } else if (c.number) {
      Object.assign(v, { type: 'whole', op: 'between', f1: String(c.number[0]), f2: String(c.number[1]), errorTitle: c.head, error: `A whole number from ${c.number[0]} to ${c.number[1]}.` });
    }
    return v;
  });
  const events = {
    name: 'Events', freeze: { rows: 1 }, heights: { 0: 32 }, validations,
    cols: t.cols.map((c) => ({ width: c.width, style: c.number ? 0 : STYLE.text })),
    rows: [t.cols.map((c) => ({ v: c.head, s: c.need || c.key === 'car' || c.key === 'class' ? STYLE.headRequired : STYLE.headOptional })),
      ...t.rows.map((r) => r.map((v, j) => (t.cols[j].number ? (v === '' ? '' : { v: +v }) : { v, s: STYLE.text })))],
  };

  // the guide
  const W = 112;
  const g = [], merges = [], heights = {};
  const para = (v, s = STYLE.wrap) => { heights[g.length] = 15 * lines(v, W) + 3; merges.push(`A${g.length + 1}:B${g.length + 1}`); g.push([{ v, s }]); };
  g.push([{ v: `ACR Daily: events for ${WHAT[mode]}, in a spreadsheet`, s: STYLE.title }]);
  g.push([]);
  g.push([{ v: 'How it works', s: STYLE.bold }]);
  para(`1. On the Events sheet every ROW IS ONE STAGE. ${mode === 'cup' ? 'The first row carries the settings of the match (car or class, rules); leave them empty on the rows below.'
    : 'The first row of an event carries its settings (its name, dates, car or class, rules); leave them empty on the rows below. A new name in the Event column starts the next event, so a whole season fits in one file.'}`);
  para('2. Pick the stage, car, class, weather and each setting from the drop-down of its cell; select a cell to read what it takes. Red headers must be filled, grey ones are optional and have a default.');
  para('3. Replace the example (or delete its rows) with your own. The example works as it is: import it to see what it makes.');
  para(`4. Save it and import it on ${WHERE[mode]}. The .xlsx works as it is; a CSV works too (File > Save As > "CSV UTF-8", with the Events sheet open). Every problem is listed with its row and column, and nothing is saved until you press the button.`);
  g.push([]);
  g.push([{ v: 'The columns', s: STYLE.bold }]);
  g.push([{ v: 'Column', s: STYLE.headList }, { v: 'What it takes', s: STYLE.headList }]);
  for (const c of t.cols) {
    const must = c.need ? 'Always filled. ' : c.key === 'car' || c.key === 'class' ? 'Fill Car or Class. ' : '';
    const body = `${must}${c.help}${c.def ? ` Empty: ${c.def}.` : ''}`;
    heights[g.length] = 15 * lines(body, 100) + 3;
    g.push([{ v: c.head, s: STYLE.bold }, { v: body, s: STYLE.wrap }]);
  }
  g.push([]);
  g.push([{ v: 'Good to know', s: STYLE.bold }]);
  para(`Limits: ${LIMITS.stages} stages, ${LIMITS.days} days and ${LIMITS.stagesPerDay} stages a day for an event${mode === 'cup' ? '.' : `; open at most ${LIMITS.windowDays} days${mode === 'league' ? `; ${SHEET.maxEvents} events in a file` : ''}.`}`);
  para('The stages of an event may come from several locations. Each day opens with a service park; put "yes" in Service park to have one more before a stage.');
  if (mode === 'cup') para("A cup has one event: every row under the header is a stage of it. Its dates and season are not used: the cup sets its rounds.");
  else if (mode === 'rally') para('A rally is one event. The Season column is not used.');
  else {
    para('An empty Opens means "when the event above closes": give the first event its date and the rounds follow each other. An empty Closes means 7 days after it opens.');
    para('Season: leave it empty for the latest season of the league, write a season\'s name, "new" for a new season or "none" for a one-off event.');
  }
  if (mode !== 'cup') para('Dates are read in the time zone of the browser that imports the file. Add Z (or +01:00) after the time to say another one.');
  para('The game changed, or a stage is missing from the lists? Download the template again: its lists come from the website.');
  const guide = { name: 'Guide', noGrid: true, cols: [{ width: 24 }, { width: 100 }], rows: g, merges, heights };

  // the lists
  const n = Math.max(stageList.length, cars.length, classes.length, weathers.length);
  const H = (v) => ({ v, s: STYLE.headList });
  const lrows = [[H('Stage (as in the drop-down)'), H('Location'), H('Length (km)'), H('Surface'), '', H('Car'), H('Class'), H('Group'), '', H('Class'), H('Group'), H('Cars of the class'), '', H('Weather')]];
  const surface = new Map(cat.rallies.map((r) => [r.name, r.surface || '']));
  for (let i = 0; i < n; i++) {
    const s = stageList[i], car = cars[i], k = classes[i], w = weathers[i];
    lrows.push([s ? s.label : '', s ? s.rally : '', s ? Math.round(s.st.lengthM / 100) / 10 : '', s ? surface.get(s.rally) : '', '',
      car ? car.name : '', car ? car.cls : '', car ? car.group : '', '', k ? k.cls : '', k ? k.group : '',
      k ? cars.filter((c) => c.cls === k.cls).map((c) => c.name).join(', ') : '', '', w ? w.label : '']);
  }
  const lists = { name: 'Lists', freeze: { rows: 1 }, rows: lrows,
    cols: [42, 14, 11, 10, 3, 34, 11, 12, 3, 11, 12, 60, 3, 16].map((width) => ({ width })) };
  return xlsxWrite([events, guide, lists]);
}
