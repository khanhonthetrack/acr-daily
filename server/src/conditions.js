// Each daily sets the conditions to drive in: weather + time of day.
// Weather types per rally come from the game files (acr/Content/.../DA_<Rally><Weather>Ranges).
// The game doesn't report weather or time of day, but its air temperature (physics +288, kelvin) depends on
// time of day, weather and height on the stage, so runs are checked against the other drivers' temperatures
// at the same points of the stage (realism.js: tempProfile / compareTemps).

// game = the game's own weather name (acr.exe), written into the save by the app's "Drive daily" button
export const WEATHER = {
  Clear: { label: 'Clear', weight: 4, game: 'WT_CLEAR' },
  LightCloud: { label: 'Light clouds', weight: 3, game: 'WT_LIGHT_CLOUDS' },
  HeavyCloud: { label: 'Clouds', weight: 2, game: 'WT_HEAVY_CLOUDS' },
  LightFog: { label: 'Light fog', weight: 1, game: 'WT_LIGHT_FOG' },
  HeavyFog: { label: 'Fog', weight: 1, game: 'WT_HEAVY_FOG' },
  LightRain: { label: 'Light rain', weight: 2, game: 'WT_LIGHT_RAIN' },
  HeavyRain: { label: 'Rain', weight: 1, game: 'WT_HEAVY_RAIN' },
  Storm: { label: 'Storm', weight: 1, game: 'WT_STORM' },
  LightSnow: { label: 'Light snow', weight: 1, game: 'WT_LIGHT_SNOW' },
  HeavySnow: { label: 'Snow', weight: 1, game: 'WT_HEAVY_SNOW' },
  Blizzard: { label: 'Snow blizzard', weight: 0.5, game: 'WT_BLIZZARD' },
};

const ALL = Object.keys(WEATHER);
// every rally offers the same 11 (checked in the game's Weather & Time menu)
export const RALLY_WEATHER = { Alsace: ALL, 'Monte Carlo': ALL, Livigno: ALL, Wales: ALL, Greece: ALL };

// Start times of the dailies. The game stores any time of day (seconds since midnight), and time stands still
// during the run (TimeSpeed WT_SPEEDFIX) so everyone drives in the same light.
export const TIMES = [
  { id: 'morning', label: 'Morning', hour: '08:00', weight: 3 },
  { id: 'midday', label: 'Midday', hour: '12:00', weight: 3 },
  { id: 'afternoon', label: 'Afternoon', hour: '16:00', weight: 3 },
  { id: 'evening', label: 'Evening', hour: '19:00', weight: 1 },
];

export const SURFACE = { Alsace: 'Tarmac', 'Monte Carlo': 'Tarmac', Wales: 'Gravel', Greece: 'Gravel', Livigno: 'Snow' };

/** "Wales Afon Bidno" -> {rally: 'Wales', stageName: 'Afon Bidno', surface: 'Gravel'} */
export function stageParts(track) {
  const rally = rallyOf(track);
  const t = String(track || '');
  return {
    rally: rally || t.split(' ')[0] || null,
    stageName: rally ? t.slice(rally.length).trim() || t : t.split(' ').slice(1).join(' ') || t,
    surface: rally ? SURFACE[rally] || null : null,
  };
}

export const rallyOf = (track) => {
  const t = String(track || '');
  return Object.keys(RALLY_WEATHER).find((r) => t.toLowerCase().startsWith(r.toLowerCase())) || null;
};

function weighted(list, weightOf, h) {
  const total = list.reduce((a, x) => a + weightOf(x), 0);
  let r = (h % 100000) / 100000 * total;
  for (const x of list) { r -= weightOf(x); if (r < 0) return x; }
  return list[list.length - 1];
}

/** Conditions for a daily, chosen from a stable hash (same day + slot + stage = same conditions). */
export function pickConditions(track, h1, h2) {
  const rally = rallyOf(track);
  const weathers = RALLY_WEATHER[rally] || ALL.filter((w) => !/Snow|Blizzard/.test(w));
  const weather = weighted(weathers, (w) => WEATHER[w].weight, h1);
  const time = weighted(TIMES, (t) => t.weight, h2);
  return { weather, time: time.id };
}

export function describe(weather, time) {
  const w = WEATHER[weather], t = TIMES.find((x) => x.id === time);
  const [hh, mm] = t ? t.hour.split(':').map(Number) : [null, null];
  return {
    weather, weatherLabel: w ? w.label : weather || null, weatherGame: w ? w.game : null,
    time, timeLabel: t ? `${t.label} (${t.hour})` : time || null,
    startSeconds: t ? hh * 3600 + mm * 60 : null,
  };
}
