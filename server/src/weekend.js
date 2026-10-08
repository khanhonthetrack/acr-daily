// From OFFICIAL_FROM (wrangler.toml) on, each daily is a one-stage Rally Weekend in the game: the app sets it up with
// these settings (client/acr_daily/rallyweekend.py) and sends the game's own result, its stage time + its penalties
// (respawns, cuts, jump starts), which is the board time. The app's resets then add nothing (penaltyMs 0).

export const WEEKEND_RULES = { penalty: 'light', respawn: true, damage: true, damageIntensity: 'light', wear: 'light',
  failures: 'off' };

/** The daily of that date (YYYY-MM-DD) is a Rally Weekend; without a date: today's (UTC). */
export const officialDay = (env, date = new Date().toISOString().slice(0, 10)) =>
  !!(env && env.OFFICIAL_FROM) && date >= env.OFFICIAL_FROM;
