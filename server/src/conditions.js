// Each daily sets the conditions to drive in: weather + time of day.
// The weather types are the game's own (acr/Content/.../DA_<Rally><Weather>Ranges); which ones come up on which rally,
// and how often, is ours (RALLY_WEATHER). The game doesn't report weather or time of day, and its air temperature
// (physics +288, kelvin) can't stand in for them: the game draws it anew each time it sets a stage up (the same save,
// stage, time and weather gave 13.0 °C, then 15.7 °C), so nothing checks the conditions.

// game = the game's own weather name (acr.exe), written into the save by the app's "Drive daily" button
export const WEATHER = {
  Clear: { label: 'Clear', game: 'WT_CLEAR' },
  LightCloud: { label: 'Light clouds', game: 'WT_LIGHT_CLOUDS' },
  HeavyCloud: { label: 'Clouds', game: 'WT_HEAVY_CLOUDS' },
  LightFog: { label: 'Light fog', game: 'WT_LIGHT_FOG' },
  HeavyFog: { label: 'Fog', game: 'WT_HEAVY_FOG' },
  LightRain: { label: 'Light rain', game: 'WT_LIGHT_RAIN' },
  HeavyRain: { label: 'Rain', game: 'WT_HEAVY_RAIN' },
  Storm: { label: 'Storm', game: 'WT_STORM' },
  LightSnow: { label: 'Light snow', game: 'WT_LIGHT_SNOW' },
  HeavySnow: { label: 'Snow', game: 'WT_HEAVY_SNOW' },
  Blizzard: { label: 'Snow blizzard', game: 'WT_BLIZZARD' },
};

// How often each weather comes up on each rally (relative weights; a weather left out never does). The game offers
// all 11 everywhere (its Weather & Time menu); these follow the real events: Alsace in October (often wet), Greece in
// early summer (dry), Monte Carlo in January (snow on the cols now and then), Wales in November (rain and fog).
// Snow only in Monte Carlo (about 1 daily in 14 there) and Wales (1 in 27), never a blizzard in Wales.
export const RALLY_WEATHER = {
  Alsace: { Clear: 4, LightCloud: 3, HeavyCloud: 2, LightFog: 1, HeavyFog: 0.5, LightRain: 2, HeavyRain: 1, Storm: 0.5 },
  Greece: { Clear: 7, LightCloud: 3, HeavyCloud: 1, LightFog: 0.3, LightRain: 0.7, HeavyRain: 0.3, Storm: 0.3 },
  'Monte Carlo': { Clear: 4, LightCloud: 3, HeavyCloud: 2, LightFog: 1, HeavyFog: 0.5, LightRain: 1.5, HeavyRain: 0.7,
    Storm: 0.3, LightSnow: 0.6, HeavySnow: 0.3, Blizzard: 0.1 },
  Wales: { Clear: 2, LightCloud: 3, HeavyCloud: 3, LightFog: 1.5, HeavyFog: 1, LightRain: 3, HeavyRain: 1.5, Storm: 0.5,
    LightSnow: 0.4, HeavySnow: 0.2 },
  Livigno: { Clear: 3, LightCloud: 2, HeavyCloud: 2, LightFog: 1, LightSnow: 2, HeavySnow: 1.5, Blizzard: 0.5 },   // the ice circuit
};
const OTHER = RALLY_WEATHER.Alsace;   // a rally not listed: no snow

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
  const odds = RALLY_WEATHER[rallyOf(track)] || OTHER;
  const weather = weighted(Object.keys(odds), (w) => odds[w], h1);
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
