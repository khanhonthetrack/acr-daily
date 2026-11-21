// /developers: the public API (src/publicapi.js) and the embeds (src/embeds.js) for people, above all a championship's
// organizers putting its results on their own site. In the leagues' look (src/leaguepages.js shell). Written for
// developers, in English (code, paths and field names are English whatever the reader's language).

import { shell } from './leaguepages.js';
import { embedSnippet } from './embeds.js';

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

const CSS = `<style>
.dev{max-width:880px}
.dev h2{margin-top:30px}
.dev code,.dev pre{font:13px/1.45 ui-monospace,SFMono-Regular,Consolas,monospace}
.dev code{background:#16161A;border:1px solid var(--line);padding:1px 5px}
.dev pre{background:#101013;border:1px solid var(--line);padding:12px 14px;overflow-x:auto;white-space:pre}
.ep{width:100%;border-collapse:collapse;margin:8px 0}
.ep td{border-top:1px solid var(--line);padding:8px 10px 8px 0;vertical-align:top}
.ep td:first-child{white-space:nowrap;font:13px/1.45 ui-monospace,SFMono-Regular,Consolas,monospace;color:var(--fg)}
.ep td:last-child{color:var(--fg2)}
.csv{border:1px solid var(--good);color:var(--good);font:600 10px/1 Barlow,sans-serif;padding:2px 5px;letter-spacing:.08em;margin-left:6px}
</style>`;

const ENDPOINTS = [
  ['/api/v1', 'What there is.'],
  ['/api/v1/championships', 'Every championship: id, name, members, events, its page.'],
  ['/api/v1/championships/{id}', 'A championship: members (team, division), events (status, winner once known), seasons.'],
  ['/api/v1/championships/{id}/standings?season={id}', 'Its season tables: drivers, each class and division, teams. Points per event.', true],
  ['/api/v1/events/{id}', 'An event: itinerary (stages, weather, times of day) and full results: total, gap, each stage, penalties, each class and division.', true],
  ['/api/v1/events/{id}/live', 'Who is on its stages right now: stage, progress (0-1), time, position (x, z). Ask again every pollSeconds.'],
  ['/api/v1/events/{id}/map', 'Its stages\' routes, as points in the same x, z as the live positions: draw the map, then the cars on it.'],
  ['/api/v1/cups/{id}', 'A cup: entrants and seeds, every match, the winner of each.'],
  ['/api/v1/dailies?date={YYYY-MM-DD}', 'A day\'s dailies: stage, car, weather.'],
  ['/api/v1/dailies/{date}/{slot}', 'A daily\'s results.', true],
  ['/api/v1/timetrials?week={Monday YYYY-MM-DD}', 'A week\'s time trial stages.'],
  ['/api/v1/timetrials/{week}/{slot}', 'A time trial stage\'s results.', true],
  ['/api/v1/ranking?country={cc}&page={n}', 'The world ranking, 100 a page.', true],
  ['/api/v1/drivers/{steamId}', 'A driver: country, team, rating and world rank.'],
];

export function developersPage(env) {
  const site = env.SITE_URL || '';
  const rows = ENDPOINTS.map(([p, what, c]) => `<tr><td>${esc(p)}</td><td>${esc(what)}${c ? '<span class="csv">CSV</span>' : ''}</td></tr>`).join('');
  return shell('Developers · ACR Daily', `${CSS}
  <div class="dev">
  <div class="top"><div class="kick">ACR Daily</div><h1>Results on your own site</h1>
  <p class="note">Every result, table and live timing on ACR Daily, for your championship's page, your club's site or your stream overlay.
  Copy an embed, or read the API. Free, no key, no sign-in.</p></div>

  <h2>Embeds</h2>
  <p class="note">Paste one into your page. It keeps itself up to date: results every minute while an event is open, live timing every few seconds.
  Your championship's page gives you these with its own events filled in.</p>
  <table class="ep">
    <tr><td>/embed/event/{id}</td><td>An event's results, each class and division to pick.</td></tr>
    <tr><td>/embed/event/{id}/live</td><td>Live timing: the stage's map and who is on it.</td></tr>
    <tr><td>/embed/championship/{id}</td><td>A championship's standings: drivers, classes, divisions, teams. <code>?season={id}</code> for one season.</td></tr>
  </table>
  <p class="note">Options: <code>theme=light</code> (dark by default), <code>accent=FF4655</code> (a colour, no #), <code>title=0</code> (no heading).</p>
  <pre>${esc(embedSnippet(site, '/embed/championship/{id}?theme=light', 560))}</pre>

  <h2>API</h2>
  <p class="note">JSON, read-only, open to every site (CORS). Times are in milliseconds. The tables marked CSV also come as
  <code>?format=csv</code>, ready for a spreadsheet. The ids are in each page's address: <code>${esc(site)}/l/<b>{id}</b></code>,
  <code>/e/<b>{id}</b></code>, <code>/cup/<b>{id}</b></code>, <code>/d/<b>{steamId}</b></code>.</p>
  <table class="ep">${rows}</table>
  <pre>fetch('${esc(site)}/api/v1/events/43')
  .then(r =&gt; r.json())
  .then(e =&gt; e.results.forEach(r =&gt; console.log(r.rank, r.name, r.totalMs)));</pre>

  <h2>What it shows</h2>
  <p class="note">Exactly what the website shows anyone. A private rally's results need its invite code: <code>?code=XXXX-XXXX</code>
  (on the event, its live timing and its map, and on its embeds). An event that hides its weather, stages or times keeps them hidden
  until it closes, for everyone.</p>

  <h2>Fair use</h2>
  <p class="note">Answers are kept for a few seconds (live timing) to a few minutes (results and tables), so asking more often
  only gets the same answer. Ask live timing every <code>pollSeconds</code> at most. The <code>v1</code> answers keep their fields:
  new ones may come, none go. Questions or ideas: <a href="/discord">our Discord</a>.</p>
  </div>`, 'account();', env);
}
