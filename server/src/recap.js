// The daily report: after each day (cron, 01:05 UTC, once late runs are in) Claude writes a short, fun report of the
// day before for the website, from its facts: both stages' results, splits and DNFs, the telemetry records (top speed,
// the longest jump, the longest flat-out blast, the perfect run from everyone's best sections), the drivers' history,
// the last time each stage came up and the week's hall of fame. Without an API key (secret ANTHROPIC_API_KEY), or if
// the call fails, a plain report is made from the same facts.

import Anthropic from '@anthropic-ai/sdk';

const MODEL = 'claude-opus-5-5';

const SYSTEM = `You write the daily report of ACR Daily, a daily time-trial challenge in the sim racing game Assetto Corsa Rally.
Every day there are two special stages (SS1 and SS2), each with one car, fixed weather and time of day, and its own
leaderboard. A driver's first run is the one that counts; a reset to the road costs 60 seconds; a restart or quitting
is a DNF. Points from every stage go into a weekly hall of fame (Monday to Sunday).

You get the facts of one finished day as JSON. Write the report people read on the website the next morning.

- A headline of at most 10 words, then 2 to 4 short paragraphs, 120 to 200 words in all. Plain text: no markdown,
  lists, emoji or hashtags.
- Cover both stages: who won and how (margins, who led at the splits, the closest battle, resets and DNFs).
- Work in one or two of the fun records (top speed, the longest jump, the longest flat-out blast, the perfect run),
  and put the day in context: the hall of fame, a lead that changed hands, a first daily, a driver's history, the last
  time a stage came up.
- Use only the facts given. Never invent times, gaps, corners, crashes, reasons or feelings. Copy times, gaps and
  speeds exactly as written, and the drivers' names too.
- A lively rally reporter's voice, warm to everyone in the field, accurate above all. If only a few people drove,
  keep it short and still friendly.`;

const SCHEMA = {
  type: 'object',
  properties: {
    title: { type: 'string', description: 'The headline, at most 10 words.' },
    paragraphs: { type: 'array', items: { type: 'string' }, description: '2 to 4 short paragraphs of plain text.' },
  },
  required: ['title', 'paragraphs'],
  additionalProperties: false,
};

// ------------------------------------------------------------------ facts

const fmt = (ms) => {
  if (ms == null) return null;
  const m = Math.floor(ms / 60000), s = (ms % 60000) / 1000;
  return `${m}:${s < 10 ? '0' : ''}${s.toFixed(3)}`;
};
const gap = (ms) => (ms == null ? null : `${ms >= 0 ? '+' : '-'}${(Math.abs(ms) / 1000).toFixed(3)} s`);
const secs = (ms) => (ms == null ? null : `${(ms / 1000).toFixed(1)} s`);

/** The points each driver scored on one day, from the week's standings cells ("date/slot"). */
const dayPoints = (p, date) => Object.entries(p.cells || {}).reduce((a, [k, c]) => a + (k.startsWith(date + '/') ? c.pts : 0), 0);

function stageFacts({ slot, st, prev }) {
  const ch = st.challenge, board = st.board || [];
  const fin = board.filter((e) => e.status === 'finished');
  const r = st.records || {}, air = st.air || {};
  const splitLeaders = [0, 1, 2].map((k) => {
    const lead = fin.filter((e) => e.splits && e.splits[k] != null).sort((a, b) => a.splits[k] - b.splits[k])[0];
    return lead ? { split: k + 1, driver: lead.name, time: fmt(lead.splits[k]) } : null;
  }).filter(Boolean);
  let closest = null;
  for (let i = 1; i < fin.length; i++) {
    const g = fin[i].totalMs - fin[i - 1].totalMs;
    if (!closest || g < closest.ms) closest = { ms: g, positions: [i, i + 1], drivers: [fin[i - 1].name, fin[i].name] };
  }
  const sectionWins = new Map();
  for (const b of (st.sections && st.sections.best) || []) if (b) sectionWins.set(b.name, (sectionWins.get(b.name) || 0) + 1);
  const [secDriver, secCount] = [...sectionWins.entries()].sort((a, b) => b[1] - a[1])[0] || [];
  const mostResets = fin.filter((e) => e.resets > 0).sort((a, b) => b.resets - a.resets)[0];
  return {
    ss: slot,
    stage: ch.menuName || ch.stageName || ch.track,
    rally: ch.rally || null, surface: ch.surface || null, lengthKm: Math.round(st.lengthM / 100) / 10,
    car: ch.car, carClass: ch.carClass || null, weather: ch.weatherLabel || null, timeOfDay: ch.timeLabel || null,
    drivers: board.length,
    results: fin.slice(0, 10).map((e) => ({ pos: e.rank, driver: e.name, time: fmt(e.totalMs),
      gapToWinner: e.rank > 1 ? gap(e.gapMs) : null, resets: e.resets || 0 })),
    moreFinishers: Math.max(0, fin.length - 10),
    dnf: board.filter((e) => e.status === 'dnf').map((e) => ({ driver: e.name, reason: e.reason || 'did not finish' })),
    splitLeaders,
    closestFight: closest && fin.length > 2 ? { positions: closest.positions, drivers: closest.drivers, gap: gap(closest.ms) } : null,
    records: {
      topSpeed: r.topSpeed ? { driver: r.topSpeed.name, kmh: r.topSpeed.kmh, atKm: r.topSpeed.km } : null,
      longestJump: air.longestJump ? { driver: air.longestJump.name, airtime: secs(air.longestJump.ms),
        takeOffKmh: air.longestJump.kmh, atKm: air.longestJump.km } : null,
      mostTimeInTheAir: air.mostAirtime && air.mostAirtime.count > 1
        ? { driver: air.mostAirtime.name, airtime: secs(air.mostAirtime.ms), jumps: air.mostAirtime.count } : null,
      longestFlatOut: r.longestFlatOut ? { driver: r.longestFlatOut.name, flatOutFor: secs(r.longestFlatOut.ms),
        fromKm: r.longestFlatOut.km } : null,
      winnersAverageKmh: r.avgSpeed || null,
      perfectRun: r.ideal && r.ideal.gainMs > 0 && fin.length > 1
        ? { stageClock: fmt(r.ideal.ms), quickerThanTheWinnersClockBy: secs(r.ideal.gainMs),
          note: "everyone's fastest tenths of the stage put together" } : null,
      fastestInMostTenths: secDriver ? { driver: secDriver, tenths: secCount, of: 10 } : null,
      cleanRuns: st.field ? st.field.cleanRuns : null,
      mostResets: mostResets ? { driver: mostResets.name, resets: mostResets.resets } : null,
    },
    lastTimeThisStageCameUp: prev || null,
  };
}

/**
 * The facts of one finished day for the report, or null if nobody drove.
 * day: {date, stages: [{slot, st: stageStats with board, prev}], week: weekData (standings incl. the day),
 *       history: [{steam_id, dailies (before the day), since}]}
 */
export function recapFacts({ date, stages, week, history }) {
  if (!stages.some((s) => (s.st.board || []).length)) return null;
  const standings = (week && week.standings) || [];
  const before = standings.map((p) => ({ name: p.name, points: p.total - dayPoints(p, date) }))
    .filter((p) => p.points > 0).sort((a, b) => b.points - a.points);
  const hist = new Map((history || []).map((h) => [h.steam_id, h]));
  const drivers = new Map();
  for (const { st } of stages) {
    for (const e of st.board || []) {
      if (drivers.has(e.steamId)) continue;
      const h = hist.get(e.steamId), p = standings.find((x) => x.steamId === e.steamId);
      drivers.set(e.steamId, { driver: e.name, country: e.country || null,
        dailiesBefore: h ? h.dailies : 0, firstDaily: !h || !h.dailies, drivingSince: h ? h.since : date,
        weekPoints: p ? p.total : 0, weekPosition: p ? p.rank : null });
    }
  }
  const dayIndex = week && week.start ? Math.round((Date.parse(date) - Date.parse(week.start)) / 86400000) + 1 : null;
  return {
    date,
    weekday: new Date(date + 'T00:00:00Z').toLocaleDateString('en-GB', { weekday: 'long', timeZone: 'UTC' }),
    stages: stages.map(stageFacts),
    drivers: [...drivers.values()].slice(0, 20),
    hallOfFame: {
      week: week ? week.week : null, dayOfWeek: dayIndex, of: 7,
      pointsPerStage: '25-18-15-12-10-8-6-4-2-1 for the top 10, then 1 per finisher; a DNF scores 0',
      standingsAfterTheDay: standings.slice(0, 5).map((p) => ({ pos: p.rank, driver: p.name, points: p.total, wins: p.wins })),
      leaderBeforeTheDay: before[0] ? { driver: before[0].name, points: before[0].points } : null,
    },
  };
}

// ------------------------------------------------------------------ writing it

/** The plain report, from the facts alone (no API key, or the call failed). -> {title, paragraphs} */
export function templateRecap(f) {
  const paras = [];
  for (const s of f.stages) {
    const w = s.results[0];
    if (!w) {
      paras.push(`SS${s.ss} ${s.stage}: ${s.drivers ? 'nobody reached the finish' : 'nobody took it on'}.`);
      continue;
    }
    const second = s.results[1];
    let t = `SS${s.ss} ${s.stage} (${s.car}${s.weather ? ', ' + s.weather.toLowerCase() : ''}): ${w.driver} won in ${w.time}`;
    t += second ? `, ${second.gapToWinner} ahead of ${second.driver}.` : '.';
    if (s.dnf.length) t += ` ${s.dnf.length} DNF.`;
    const ts = s.records.topSpeed, j = s.records.longestJump;
    if (ts) t += ` Top speed: ${ts.driver}, ${ts.kmh} km/h.`;
    if (j) t += ` Longest jump: ${j.driver}, ${j.airtime} in the air.`;
    paras.push(t);
  }
  const hof = f.hallOfFame.standingsAfterTheDay.filter((p) => p.points > 0);
  if (hof.length) paras.push(`Hall of fame, week ${f.hallOfFame.week}: ${hof.slice(0, 3).map((p) => `${p.pos}. ${p.driver} ${p.points} pts`).join(', ')}.`);
  const winners = [...new Set(f.stages.map((s) => s.results[0] && s.results[0].driver).filter(Boolean))];
  const title = winners.length === 1 ? `${winners[0]} rules ${f.weekday}`
    : winners.length ? `${winners.join(' and ')} share ${f.weekday}` : `A quiet ${f.weekday}`;
  return { title, paragraphs: paras };
}

/** Claude's report: {title, paragraphs, model}, or null if it declined or the answer is unusable. */
async function claudeRecap(env, facts) {
  const client = new Anthropic({ apiKey: env.ANTHROPIC_API_KEY, timeout: 180000, maxRetries: 2 });
  const response = await client.beta.messages.create({
    model: env.RECAP_MODEL || MODEL,
    max_tokens: 16000,
    // a declined request is re-run on Anthropic's recommended fallback model instead of failing
    betas: ['server-side-fallback-2026-07-01'],
    fallbacks: 'default',
    output_config: { effort: 'medium', format: { type: 'json_schema', schema: SCHEMA } },
    system: SYSTEM,
    messages: [{ role: 'user', content: JSON.stringify(facts) }],
  });
  if (response.stop_reason !== 'end_turn') {
    console.error('recap: no report, stop reason', response.stop_reason, response.stop_details || '');
    return null;
  }
  const text = response.content.filter((b) => b.type === 'text').map((b) => b.text).join('');
  const out = JSON.parse(text);
  const paragraphs = (out.paragraphs || []).map((p) => String(p).replace(/\s+/g, ' ').trim()).filter(Boolean);
  if (!out.title || !paragraphs.length) return null;
  return { title: String(out.title).trim().slice(0, 120), paragraphs: paragraphs.slice(0, 5), model: response.model };
}

/** The report of a day from its facts: Claude's, or the plain one. -> {title, text, model} */
export async function writeReport(env, facts) {
  let r = null;
  if (env.ANTHROPIC_API_KEY) {
    try {
      r = await claudeRecap(env, facts);
    } catch (e) {
      if (e instanceof Anthropic.AuthenticationError) console.error('recap: the ANTHROPIC_API_KEY secret is not valid');
      else if (e instanceof Anthropic.RateLimitError) console.error('recap: rate limited');
      else if (e instanceof Anthropic.APIError) console.error('recap: API error', e.status, e.message);
      else console.error('recap:', e);       // e.g. an answer that is not the JSON asked for
    }
  }
  if (!r) r = { ...templateRecap(facts), model: 'template' };
  return { title: r.title, text: r.paragraphs.join('\n\n'), model: r.model };
}
