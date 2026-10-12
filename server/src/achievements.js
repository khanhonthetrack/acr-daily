// Achievements, in the way of Steam's: a badge each (an icon on a tile in its tier's colours: bronze, silver, gold,
// platinum; grey with a lock until it is unlocked), its name and what it takes, the day it was unlocked, and how rare it
// is (the share of drivers who have it). Kept once unlocked (table achievements), whatever happens after.
//
// Checked in bulk (checkAchievements: a few statements for any number of drivers, their numbers from daily_results,
// runs, credits, 1V1s, cups and the ratings): by the cron every 10 minutes for the drivers who did
// something since their last check (achievementsTick: a run, a daily of theirs taken, a 1V1 or a cup decided), and
// when a driver's page is looked at. What a check unlocks is one notice in the driver's inbox.

import { stageParts } from './conditions.js';
import { RALLIES } from './leagues.js';
import { noticesStmt } from './social.js';

const RAIN = ['LightRain', 'HeavyRain', 'Storm'], SNOW = ['LightSnow', 'HeavySnow', 'Blizzard'], FOG = ['LightFog', 'HeavyFog'];
export const JUMP_M = { big: 15, flying: 25 };      // metres in the air in one jump (take-off speed x airtime)

/** Every achievement: id, name, what it takes, tier, its icon (GLYPHS) and a figure on the tile; got(stats) -> bool. */
export const ACHIEVEMENTS = [
  { id: 'first-finish', name: 'First finish', desc: 'Finish a daily.', tier: 'bronze', glyph: 'flag', got: (s) => s.finishes >= 1 },
  { id: 'podium', name: 'Podium', desc: 'Finish a daily in the top three.', tier: 'silver', glyph: 'podium', got: (s) => s.podiums >= 1 },
  { id: 'stage-winner', name: 'Stage winner', desc: 'Win a daily.', tier: 'gold', glyph: 'trophy', got: (s) => s.wins >= 1 },
  { id: 'serial-winner', name: 'Serial winner', desc: 'Win 10 dailies.', tier: 'platinum', glyph: 'crown', label: '10', got: (s) => s.wins >= 10 },
  { id: 'regular', name: 'Regular', desc: 'Drive 50 dailies.', tier: 'silver', glyph: 'calendar', label: '50', got: (s) => s.dailies >= 50 },
  { id: 'streak-7', name: 'On a roll', desc: 'Drive a daily 7 days in a row.', tier: 'silver', glyph: 'flame', label: '7', got: (s) => s.streak >= 7 },
  { id: 'streak-30', name: 'Unstoppable', desc: 'Drive a daily 30 days in a row.', tier: 'gold', glyph: 'flame', label: '30', got: (s) => s.streak >= 30 },
  { id: 'km-100', name: 'Warming up', desc: 'Drive 100 km of finished runs (practice too).', tier: 'bronze', glyph: 'road', label: '100', got: (s) => s.km >= 100 },
  { id: 'km-1000', name: 'Mile eater', desc: 'Drive 1,000 km of finished runs.', tier: 'silver', glyph: 'road', label: '1K', got: (s) => s.km >= 1000 },
  { id: 'km-5000', name: 'Long haul', desc: 'Drive 5,000 km of finished runs.', tier: 'gold', glyph: 'road', label: '5K', got: (s) => s.km >= 5000 },
  { id: 'grand-tour', name: 'Grand tour', desc: `Finish a daily in every rally: ${RALLIES.join(', ').replace(/, ([^,]*)$/, ' and $1')}.`, tier: 'silver',
    glyph: 'globe', got: (s) => RALLIES.every((r) => s.rallies.has(r)) },
  { id: 'rain', name: 'Rain master', desc: 'Finish a daily in the rain.', tier: 'bronze', glyph: 'drop', got: (s) => s.rain >= 1 },
  { id: 'snow', name: 'Snow day', desc: 'Finish a daily in the snow.', tier: 'bronze', glyph: 'snow', got: (s) => s.snow >= 1 },
  { id: 'fog', name: 'Into the fog', desc: 'Finish a daily in fog.', tier: 'bronze', glyph: 'fog', got: (s) => s.fog >= 1 },
  { id: 'dusk', name: 'Dusk patrol', desc: 'Finish an evening daily.', tier: 'bronze', glyph: 'moon', got: (s) => s.evening >= 1 },
  { id: 'clean-10', name: 'Clean sheet', desc: 'Finish 10 dailies without a penalty.', tier: 'silver', glyph: 'shield', label: '10', got: (s) => s.clean >= 10 },
  { id: 'big-air', name: 'Big air', desc: `Fly ${JUMP_M.big} m in one jump, on a run you finished.`, tier: 'silver', glyph: 'jump', got: (s) => s.jump >= JUMP_M.big },
  { id: 'flying-finn', name: 'Flying Finn', desc: `Fly ${JUMP_M.flying} m in one jump, on a run you finished.`, tier: 'gold', glyph: 'wings', got: (s) => s.jump >= JUMP_M.flying },
  { id: 'high-roller', name: 'High roller', desc: 'Finish in the paying half of the wager daily (SS2).', tier: 'bronze', glyph: 'coin', got: (s) => s.wagers >= 1 },
  { id: 'saver', name: 'Saver', desc: 'Have 1,000 credits.', tier: 'silver', glyph: 'coins', label: '1K', got: (s) => s.balance >= 1000 },
  { id: 'dressed-up', name: 'Dressed up', desc: 'Buy a look in the shop.', tier: 'bronze', glyph: 'sparkle', got: (s) => s.looks >= 1 },
  { id: 'duellist', name: 'Duellist', desc: 'Win a 1V1.', tier: 'bronze', glyph: 'swords', got: (s) => s.duels >= 1 },
  { id: 'gunslinger', name: 'Gunslinger', desc: 'Win 10 1V1s.', tier: 'gold', glyph: 'swords', label: '10', got: (s) => s.duels >= 10 },
  { id: 'finalist', name: 'Finalist', desc: 'Reach a cup final.', tier: 'silver', glyph: 'cupline', got: (s) => s.finals >= 1 },
  { id: 'cup-winner', name: 'Cup winner', desc: 'Win a cup.', tier: 'gold', glyph: 'cup', got: (s) => s.cups >= 1 },
  { id: 'official-champion', name: 'Official champion', desc: 'Win an official ACR Daily cup.', tier: 'platinum', glyph: 'cupstar', got: (s) => s.official >= 1 },
  { id: 'rising-star', name: 'Rising star', desc: 'Reach a driver rating of 1600.', tier: 'silver', glyph: 'star', label: '1600', got: (s) => s.peak >= 1600 },
  { id: 'elite', name: 'Elite', desc: 'Reach a driver rating of 1800.', tier: 'gold', glyph: 'gem', label: '1800', got: (s) => s.peak >= 1800 },
  { id: 'team-player', name: 'Team player', desc: 'Join a team.', tier: 'bronze', glyph: 'people', got: (s) => s.team >= 1 },
  { id: 'league-racer', name: 'League racer', desc: 'Finish a league event.', tier: 'bronze', glyph: 'wheel', got: (s) => s.leagues >= 1 },
];
const BY_ID = new Map(ACHIEVEMENTS.map((a) => [a.id, a]));

// ------------------------------------------------------------------ the icons

// tiers: the tile's gradient (top, bottom) and its rim
const TIERS = {
  bronze: ['#D9955A', '#7A4A22', '#F0B98A'], silver: ['#D5DBE3', '#6B727D', '#F2F5F8'],
  gold: ['#FFD86B', '#A26F00', '#FFE9A6'], platinum: ['#A9E4FA', '#2F6380', '#D9F4FF'],
};
const LOCKED = ['#3A3A42', '#202024', '#4A4A52'];
// each glyph on a 24 x 24 grid: [path, 'fill' | 'stroke', fill-rule evenodd?]
const GLYPHS = {
  flag: [['M5 3h1.7v18H5z', 'fill'], ['M6.7 4h12v8h-12zM9.7 4h3v2h-3zM15.7 4h3v2h-3zM6.7 6h3v2h-3zM12.7 6h3v2h-3zM9.7 8h3v2h-3zM15.7 8h3v2h-3zM6.7 10h3v2h-3zM12.7 10h3v2h-3z', 'fill', true]],
  podium: [['M2 13h6v8H2zM9 8h6v13H9zM16 15h6v6h-6z', 'fill'], ['M11.3 10.5l1.4-1v4.3', 'dark']],
  trophy: [['M7 3h10v1.5h3.5V8a4 4 0 0 1-4 4h-.6A5 5 0 0 1 13 14.8V18h3v3H8v-3h3v-3.2A5 5 0 0 1 8.1 12h-.6a4 4 0 0 1-4-4V4.5H7zM5.4 6.3V8a2 2 0 0 0 1.9 2A9 9 0 0 1 7 7.6V6.3zM17 6.3v1.3a9 9 0 0 1-.3 2.4A2 2 0 0 0 18.6 8V6.3z', 'fill', true]],
  crown: [['M3 8l4.6 4L12 4.5 16.4 12 21 8l-2 11H5zM5 20h14v1.5H5z', 'fill']],
  calendar: [['M3.5 5h17v16h-17zM5.5 9.5v9.5h13V9.5z', 'fill', true], ['M7 2.5h2v4H7zM15 2.5h2v4h-2zM7.5 11.5h3v3h-3z', 'fill']],
  flame: [['M12 2c1.2 4.2 6.5 6.3 6.5 12.2A6.5 6.5 0 0 1 5.5 14.2c0-3 1.7-5.2 3.1-7 .1 2.1 1.1 3.3 2.2 3.4C10.6 7.5 10 5 12 2z', 'fill']],
  road: [['M9.2 3h2.1L10 21H3.5zM12.7 3h2.1l5.7 18H14z', 'fill'], ['M11.5 5h1v2.6h-1zM11.4 10h1.2v3.5h-1.2zM11.2 16h1.6v5h-1.6z', 'fill']],
  globe: [['M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18zM3 12h18M12 3c3.2 3.2 3.2 14.8 0 18M12 3c-3.2 3.2-3.2 14.8 0 18M4.6 7.5h14.8M4.6 16.5h14.8', 'stroke']],
  drop: [['M12 2.5c3.2 5 6.5 8.3 6.5 12.3a6.5 6.5 0 0 1-13 0c0-4 3.3-7.3 6.5-12.3z', 'fill'], ['M9 15.5a3 3 0 0 0 2.5 3', 'darkline']],
  snow: [['M12 2.5v19M3.8 7.2l16.4 9.6M3.8 16.8l16.4-9.6M9.4 4.3L12 6.9l2.6-2.6M9.4 19.7L12 17.1l2.6 2.6M4.6 11l2.6 1-2.6 1M19.4 11l-2.6 1 2.6 1', 'stroke']],
  fog: [['M4 7h13M2.5 11h19M5 15h14M7.5 19h9', 'stroke']],
  moon: [['M14.5 2.5a9.5 9.5 0 1 0 7 15.6A8 8 0 0 1 14.5 2.5z', 'fill'], ['M18 4l.5 1.5L20 6l-1.5.5L18 8l-.5-1.5L16 6l1.5-.5z', 'fill']],
  shield: [['M12 2l8.5 3.2v6.2c0 5.2-3.6 9.1-8.5 10.9-4.9-1.8-8.5-5.7-8.5-10.9V5.2zM10.6 15.8l-3.7-3.7 1.5-1.5 2.2 2.2 5.2-5.2 1.5 1.5z', 'fill', true]],
  jump: [['M2 21.5h8.5L2 16.5z', 'fill'], ['M9.8 11.6l7.4-3.4 1.6 3.3-7.4 3.4zM11.1 15.7a1.4 1.4 0 1 0 .01 0zM17 13a1.4 1.4 0 1 0 .01 0z', 'fill'], ['M3.5 13.5c2.5-5 6-7.5 10-8.3', 'dash']],
  wings: [['M12 13.5c-1.8-4.4-5.6-7-10-7.2 1 3.2 3.2 5.6 6.6 6.5-1.8.3-3.4 1.2-4.5 2.4 3.1 1 6 .1 7.9-1.7zM12 13.5c1.8-4.4 5.6-7 10-7.2-1 3.2-3.2 5.6-6.6 6.5 1.8.3 3.4 1.2 4.5 2.4-3.1 1-6 .1-7.9-1.7z', 'fill'], ['M12 13.5v6', 'stroke']],
  coin: [['M12 2.5a9.5 9.5 0 1 1 0 19 9.5 9.5 0 0 1 0-19zm0 3a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13zm-1 2.5h2v8h-2z', 'fill', true]],
  coins: [['M4.5 6.5a7.5 3 0 1 0 15 0a7.5 3 0 1 0-15 0zM4.5 11c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3V8.8c0 1.7-3.4 3-7.5 3s-7.5-1.3-7.5-3zM4.5 15.5c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-2.2c0 1.7-3.4 3-7.5 3s-7.5-1.3-7.5-3z', 'fill']],
  sparkle: [['M12 2l2.3 7.7L22 12l-7.7 2.3L12 22l-2.3-7.7L2 12l7.7-2.3z', 'fill'], ['M19 2.5l.6 1.9 1.9.6-1.9.6-.6 1.9-.6-1.9-1.9-.6 1.9-.6z', 'fill']],
  swords: [['M4 3.5l11 11M20 3.5l-11 11M12.8 16.3l3.5-3.5M11.2 16.3l-3.5-3.5M16.2 16.2l3.8 3.8M7.8 16.2L4 20', 'stroke']],
  cupline: [['M7 3.5h10v1.5h3V8a4 4 0 0 1-4 4h-.4A5 5 0 0 1 13 14.6V18h3v3H8v-3h3v-3.4A5 5 0 0 1 8.4 12H8a4 4 0 0 1-4-4V5h3z', 'stroke']],
  cup: [['M6 3h12v4.5c0 3.5-2.2 6.2-5 6.9V18h3.5v3h-9v-3H11v-3.6c-2.8-.7-5-3.4-5-6.9zM3 5h2.5v2.2A3 3 0 0 0 4.4 9.6 2.6 2.6 0 0 1 3 7.4zM21 5h-2.5v2.2a3 3 0 0 1 1.1 2.4A2.6 2.6 0 0 0 21 7.4z', 'fill']],
  cupstar: [['M6 3h12v4.5c0 3.5-2.2 6.2-5 6.9V18h3.5v3h-9v-3H11v-3.6c-2.8-.7-5-3.4-5-6.9zM12 4.6l1 2.1 2.3.3-1.7 1.6.4 2.3-2-1.1-2 1.1.4-2.3-1.7-1.6 2.3-.3z', 'fill', true]],
  star: [['M12 2.5l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.4l-5.9 3.1 1.2-6.5-4.8-4.6 6.6-.9z', 'fill']],
  gem: [['M7 3.5h10l4.5 6L12 21.5 2.5 9.5z', 'fill'], ['M2.5 9.5h19M9.5 3.5L7.5 9.5 12 21.5 16.5 9.5l-2-6', 'darkline']],
  people: [['M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM16 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM2 20.5c0-3.6 2.7-6.3 6-6.3s6 2.7 6 6.3zM12.8 14.5a6.5 6.5 0 0 1 3.2-.8c3.3 0 6 2.7 6 6.8h-6.4c0-2.5-1-4.6-2.8-6z', 'fill']],
  wheel: [['M12 2.5a9.5 9.5 0 1 1 0 19 9.5 9.5 0 0 1 0-19zm0 2.6a6.9 6.9 0 0 0-6.7 5.3h13.4A6.9 6.9 0 0 0 12 5.1zM5.2 12.8a6.9 6.9 0 0 0 5.4 6V14.6L8.6 12.8zm13.6 0l-2 1.8v4.2a6.9 6.9 0 0 0 2-6z', 'fill', true]],
};

const LOCK = 'M44 47.5h10v8H44zM46 47.5v-2.5a3 3 0 0 1 6 0v2.5h-1.6V45a1.4 1.4 0 0 0-2.8 0v2.5z';

/** An achievement's tile as SVG (64 x 64): its tier's gradient (grey with a lock while locked), the glyph in white with
 *  a shadow, its figure. Only our own markup: safe as HTML. */
export function achievementIcon(a, unlocked = true, size = 64) {
  const [top, bottom, rim] = unlocked ? TIERS[a.tier] : LOCKED;
  const gid = `ach-${a.id}-${unlocked ? 1 : 0}`, ink = unlocked ? '#FFFFFF' : '#77777F';
  const parts = (GLYPHS[a.glyph] || GLYPHS.star).map(([d, how, odd]) => {
    const rule = odd ? ' fill-rule="evenodd"' : '';
    if (how === 'stroke' || how === 'dash') {
      return `<path d="${d}" fill="none" stroke="${ink}" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"${how === 'dash' ? ' stroke-dasharray="1.5 2.2"' : ''}/>`;
    }
    if (how === 'dark' || how === 'darkline') {
      return `<path d="${d}" fill="none" stroke="${unlocked ? bottom : '#2A2A30'}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>`;
    }
    return `<path d="${d}" fill="${ink}"${rule}/>`;
  }).join('');
  const shadow = parts.replace(/(fill|stroke)="(#FFFFFF|#77777F)"/g, '$1="rgba(0,0,0,.35)"');
  return `<svg class="ach-ic" viewBox="0 0 64 64" width="${size}" height="${size}" role="img" aria-label="${a.name}">` +
    `<defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${top}"/><stop offset="1" stop-color="${bottom}"/></linearGradient></defs>` +
    `<rect x="1" y="1" width="62" height="62" rx="10" fill="url(#${gid})"/>` +
    `<rect x="2.5" y="2.5" width="59" height="59" rx="8.5" fill="none" stroke="${rim}" stroke-opacity=".55" stroke-width="1.2"/>` +
    `<path d="M3 13c14-7 44-7 58 0V11a8 8 0 0 0-8-8H11a8 8 0 0 0-8 8z" fill="#fff" fill-opacity="${unlocked ? '.18' : '.05'}"/>` +
    `<g transform="translate(14 ${a.label ? 9 : 14}) scale(1.5)"><g transform="translate(0 .7)">${shadow}</g>${parts}</g>` +
    (a.label ? `<text x="32" y="58" text-anchor="middle" font-family="'Barlow Condensed',sans-serif" font-weight="700" font-size="12" fill="${ink}" ` +
      `stroke="${unlocked ? bottom : '#202024'}" stroke-width="2.5" paint-order="stroke">${a.label}</text>` : '') +
    (unlocked ? '' : `<path d="${LOCK}" fill="#9A9AA2"/>`) + '</svg>';
}

/** For a page's script: ACH (every achievement, no icons) and achievementIcon itself, with what it draws from, so the
 *  browser draws the same tiles (a few kB instead of every icon twice). */
export const ACH_PAGE_JS = `var ACH=${JSON.stringify(ACHIEVEMENTS.map(({ id, name, desc, tier, glyph, label }) => ({ id, name, desc, tier, glyph, label })))};
var TIERS=${JSON.stringify(TIERS)},LOCKED=${JSON.stringify(LOCKED)},GLYPHS=${JSON.stringify(GLYPHS)},LOCK=${JSON.stringify(LOCK)};
${achievementIcon.toString()}
`;

// ------------------------------------------------------------------ the numbers, in bulk

/** The longest run of days in a row in a sorted list of 'YYYY-MM-DD'. */
export function longestStreak(dates) {
  let best = 0, run = 0, prev = null;
  for (const d of dates) {
    const t = Date.parse(d + 'T00:00:00Z');
    if (prev !== null && t === prev) continue;
    run = prev !== null && t - prev === 86400000 ? run + 1 : 1;
    best = Math.max(best, run);
    prev = t;
  }
  return best;
}

const empty = () => ({ dailies: 0, finishes: 0, wins: 0, podiums: 0, streak: 0, km: 0, rallies: new Set(), rain: 0, snow: 0, fog: 0,
  evening: 0, clean: 0, jump: 0, wagers: 0, balance: 0, looks: 0, duels: 0, finals: 0, cups: 0, official: 0, peak: 0,
  team: 0, leagues: 0 });

/** Each driver's numbers and what they have unlocked already, in one batch: -> {stats: Map sid -> numbers, have: Map
 *  sid -> Map id -> at}. */
export async function achievementStats(env, ids, now) {
  const j = JSON.stringify(ids), q = (sql, ...b) => env.DB.prepare(sql).bind(j, ...b);
  const IN = 'IN (SELECT value FROM json_each(?1))';
  const [days, km, jumps, other, have] = await env.DB.batch([
    q(`SELECT d.steam_id, d.date, d.status, d.place, d.track, s.weather, s.time,
         CASE WHEN r.total_ms IS NOT NULL AND r.clock_ms IS NOT NULL THEN ABS(r.total_ms - r.clock_ms) END AS pen
       FROM daily_results d LEFT JOIN schedule s ON s.date = d.date AND s.slot = d.slot LEFT JOIN runs r ON r.id = d.run_id
       WHERE d.steam_id ${IN} ORDER BY d.date`),
    q(`SELECT r.steam_id, SUM(COALESCE(ro.length, 0)) AS metres FROM runs r LEFT JOIN routes ro ON ro.track = r.track
       WHERE r.steam_id ${IN} AND r.status = 'finished' GROUP BY r.steam_id`),
    q(`SELECT r.steam_id, MAX(json_extract(x.value, '$[3]') / 3.6 * json_extract(x.value, '$[1]') / 1000.0) AS m
       FROM runs r, json_each(r.jumps) x WHERE r.steam_id ${IN} AND r.status = 'finished' AND r.jumps IS NOT NULL GROUP BY r.steam_id`),
    q(`SELECT i.value AS sid,
         (SELECT balance FROM credits WHERE steam_id = i.value) AS balance,
         (SELECT COUNT(*) FROM credit_ledger WHERE steam_id = i.value AND kind = 'wager-win') AS wagers,
         (SELECT COUNT(*) FROM shop_owned WHERE steam_id = i.value) AS looks,
         (SELECT COUNT(*) FROM team_members WHERE steam_id = i.value) AS team,
         (SELECT COUNT(*) FROM h2h WHERE status = 'settled' AND winner = i.value) AS duels,
         (SELECT COUNT(*) FROM cup_entries WHERE steam_id = i.value AND place = 1) AS cups,
         (SELECT COUNT(*) FROM cup_entries WHERE steam_id = i.value AND place <= 2) AS finals,
         (SELECT COUNT(*) FROM cup_entries ce JOIN cups c ON c.id = ce.cup_id WHERE ce.steam_id = i.value AND ce.place = 1 AND c.official = 1) AS official,
         (SELECT peak FROM ratings WHERE steam_id = i.value) AS peak,
         (SELECT COUNT(*) FROM league_entries le JOIN league_events e ON e.id = le.event_id JOIN leagues l ON l.id = e.league_id
            WHERE le.steam_id = i.value AND le.status = 'finished' AND l.kind = 'league') AS leagues
       FROM json_each(?1) i`),
    q(`SELECT steam_id, id, at FROM achievements WHERE steam_id ${IN}`),
  ]);
  const stats = new Map(ids.map((sid) => [sid, empty()]));
  const dates = new Map(ids.map((sid) => [sid, []]));
  for (const r of days.results) {
    const s = stats.get(r.steam_id);
    if (!s) continue;
    s.dailies++;
    dates.get(r.steam_id).push(r.date);
    if (r.status !== 'finished') continue;
    s.finishes++;
    if (r.place === 1) s.wins++;
    if (r.place != null && r.place <= 3) s.podiums++;
    if (r.track) s.rallies.add(stageParts(r.track).rally);
    if (RAIN.includes(r.weather)) s.rain++;
    if (SNOW.includes(r.weather)) s.snow++;
    if (FOG.includes(r.weather)) s.fog++;
    if (r.time === 'evening') s.evening++;
    if (r.pen != null && r.pen < 500) s.clean++;              // (a penalty is whole seconds; the clocks agree to the ms)
  }
  for (const [sid, ds] of dates) stats.get(sid).streak = longestStreak(ds);
  for (const r of km.results) if (stats.has(r.steam_id)) stats.get(r.steam_id).km = (r.metres || 0) / 1000;
  for (const r of jumps.results) if (stats.has(r.steam_id)) stats.get(r.steam_id).jump = r.m || 0;
  for (const r of other.results) {
    const s = stats.get(r.sid);
    if (!s) continue;
    Object.assign(s, { balance: r.balance || 0, wagers: r.wagers, looks: r.looks, team: r.team, duels: r.duels, cups: r.cups,
      finals: r.finals, official: r.official, peak: r.peak || 0, leagues: r.leagues });
  }
  const got = new Map(ids.map((sid) => [sid, new Map()]));
  for (const r of have.results) if (got.has(r.steam_id)) got.get(r.steam_id).set(r.id, r.at);
  return { stats, have: got };
}

/** What a driver's numbers unlock: the ids. */
export const unlockedBy = (s) => ACHIEVEMENTS.filter((a) => a.got(s)).map((a) => a.id);

/** The check: each driver's new achievements kept, and one notice for them. -> Map sid -> Map id -> at (all of theirs). */
export async function checkAchievements(env, ids, now, extra = []) {
  if (!ids.length) return new Map();
  const { stats, have } = await achievementStats(env, ids, now);
  const rows = [], notes = [];
  for (const sid of ids) {
    const fresh = unlockedBy(stats.get(sid)).filter((id) => !have.get(sid).has(id));
    if (!fresh.length) continue;
    for (const id of fresh) { rows.push({ s: sid, a: id }); have.get(sid).set(id, now); }
    const names = fresh.map((id) => BY_ID.get(id).name);
    notes.push({ to: sid, body: fresh.length === 1 ? `Achievement unlocked: ${names[0]}. ${BY_ID.get(fresh[0]).desc}`
      : `${fresh.length} achievements unlocked: ${names.join(', ')}.` });
  }
  const stmts = [...extra];
  if (rows.length) {
    const key = JSON.stringify(rows);
    stmts.push(env.DB.prepare(`INSERT OR IGNORE INTO achievements (steam_id, id, at)
      SELECT json_extract(j.value, '$.s'), json_extract(j.value, '$.a'), ? FROM json_each(?) j`).bind(now, key));
    // the notices: only for what this check put in (a check at the same time elsewhere sends none twice)
    for (const n of notes) {
      stmts.push(noticesStmt(env, 'ach', [n], `ach:${n.to}`, now,
        'EXISTS (SELECT 1 FROM achievements WHERE steam_id = ? AND at = ?)', [n.to, now]));
    }
  }
  if (stmts.length) await env.DB.batch(stmts);
  return have;
}

/** The cron's part (every 10 minutes): the drivers who did something since their last check (a run, a daily of theirs
 *  taken, a 1V1 or a cup of theirs decided, their rating moved, a team joined, a league event driven, credits in or
 *  out: a bonus, a prize, a look bought), a few at a time. -> {checked, unlocked?} */
export async function achievementsTick(env, now, limit = 25) {
  const since = new Date(now - 3 * 86400000).toISOString().slice(0, 10), from = now - 3 * 86400000;
  // (D1 takes at most 5 terms in a compound SELECT, each nested one counted on its own: a 1V1's two drivers come from
  // one term, the last four sources from a compound of their own)
  const { results } = await env.DB.prepare(`SELECT sid FROM (
      SELECT r.steam_id AS sid, MAX(r.created) AS at FROM runs r WHERE r.date >= ?1 GROUP BY r.steam_id
      UNION ALL SELECT d.steam_id, dd.created FROM daily_results d JOIN daily_done dd ON dd.date = d.date AND dd.slot = d.slot WHERE d.date >= ?1
      UNION ALL SELECT j.value, h.settled FROM h2h h, json_each(json_array(h.challenger, h.opponent)) j WHERE h.settled > ?2
      UNION ALL SELECT e.steam_id, c.settled FROM cup_entries e JOIN cups c ON c.id = e.cup_id WHERE c.settled > ?2
      UNION ALL SELECT * FROM (SELECT steam_id, updated FROM ratings WHERE updated > ?2
        UNION ALL SELECT steam_id, joined FROM team_members WHERE joined > ?2
        UNION ALL SELECT steam_id, updated FROM league_entries WHERE updated > ?2
        UNION ALL SELECT steam_id, created FROM credit_ledger WHERE created > ?2)
    ) x JOIN players p ON p.steam_id = x.sid WHERE p.banned = 0 GROUP BY sid HAVING MAX(x.at) > COALESCE(MAX(p.ach_at), 0)
    ORDER BY MAX(x.at) LIMIT ?3`).bind(since, from, limit).all();
  const ids = results.map((r) => r.sid);
  if (!ids.length) return { checked: 0 };
  const before = Date.now();
  await checkAchievements(env, ids, now, [env.DB.prepare('UPDATE players SET ach_at = ? WHERE steam_id IN (SELECT value FROM json_each(?))')
    .bind(now, JSON.stringify(ids))]);
  return { checked: ids.length, ms: Date.now() - before };
}
