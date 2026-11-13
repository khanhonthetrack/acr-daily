// Every page in every language: made, and its scripts compile (a translation can't break a page's script).
// node test/pages_i18n_check.mjs [lang]
import { inLang, CODES, _setCatalog } from '../src/i18n.js';
import { sitePage } from '../src/site.js';
import { guidePage } from '../src/guidepage.js';
import { statsPage } from '../src/statspage.js';
import { viewerPage } from '../src/viewer.js';
import { labMapPage } from '../src/labmap.js';
import { leaguesPage, leaguePage, eventPage, eventEditPage, joinPage } from '../src/leaguepages.js';
import { timeTrialPage } from '../src/timetrialpage.js';
import { creditsPage } from '../src/creditspage.js';
import { reportPage } from '../src/reportpage.js';
import { inboxPage, h2hPage, cupsPage, cupPage } from '../src/socialpages.js';
import { driverPage, rankingPage, teamsPage, teamPage } from '../src/driverpages.js';
import { changelogPage } from '../src/changelogpage.js';
import { teamH2hPage, teamCupsPage, teamCupPage } from '../src/teampages.js';

const env = { CREDITS_FROM: '2026-10-12', SOURCE_URL: 'https://github.com/x/y', DISCORD_URL: 'https://discord.gg/x', LATEST_VERSION: '0.0.30',
  DOWNLOAD_URL: 'https://example.com/ACR-Daily.exe', TIME_TRIAL_FROM: '2026-11-09' };
const pages = {
  site: () => sitePage(env), guide: () => guidePage(env), stats: () => statsPage('2026-11-10', 1), viewer: () => viewerPage(5),
  lab: () => labMapPage(), leagues: () => leaguesPage(env), league: () => leaguePage('7', env), event: () => eventPage(3, env),
  newEvent: () => eventEditPage({ leagueId: '7' }, env), editEvent: () => eventEditPage({ eventId: 3 }, env), join: () => joinPage('ABCDEFGH', env),
  tt: () => timeTrialPage(env), credits: () => creditsPage(env), report: () => reportPage(env), inbox: () => inboxPage(env),
  h2h: () => h2hPage(env), cups: () => cupsPage(env), cup: () => cupPage('abcd1234', env), driver: () => driverPage('76561198000000000', env),
  ranking: () => rankingPage(env), teams: () => teamsPage(env), team: () => teamPage('12', env), changelog: () => changelogPage(env),
  teamH2h: () => teamH2hPage(env), teamCups: () => teamCupsPage(env), teamCup: () => teamCupPage('abcd1234', env),
};
let bad = 0;
// pseudo: every word in Polish with quotes, a backslash and a < around it (a translation must not break a page's script)
if (process.argv[2] === 'pseudo') {
  _setCatalog('pl', new Proxy({}, { get: (o, k) => (typeof k === 'string' ? `Ł'\\<${k}>'ł` : undefined) }));
  process.argv[2] = 'pl';
}
for (const code of (process.argv[2] ? [process.argv[2]] : CODES)) {
  for (const [name, make] of Object.entries(pages)) {
    let html;
    try { html = inLang(code, make); } catch (e) { bad++; console.log('MAKE', code, name, e.message); continue; }
    const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
    scripts.forEach((s, i) => { try { new Function(s); } catch (e) { bad++; console.log('SCRIPT', code, name, i, e.message); } });
    // a helper put in as a function's text (\${X} for \${X()}) still compiles: look for it
    if (/\(\) => `/.test(html)) { bad++; console.log('FUNCTION TEXT', code, name); }
    if (!html.includes(`<html lang=`)) { bad++; console.log('NO LANG', code, name); }
    const handlers = [...html.matchAll(/ on\w+="([^"]*)"/g)].map((m) => m[1].replace(/&quot;/g, '"'));
    handlers.forEach((s) => { try { new Function(s); } catch (e) { bad++; console.log('HANDLER', code, name, e.message, s.slice(0, 80)); } });
  }
}
console.log(bad ? `${bad} problems` : 'all pages fine');
process.exit(bad ? 1 : 0);
