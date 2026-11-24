// /developers: the public API (src/publicapi.js) and the embeds (src/embeds.js) for people, above all a championship's
// organizers putting its results on their own site. In the leagues' look (src/leaguepages.js shell), in the reader's
// language (its words in the catalogs, server/src/locales); paths, parameters and code stay as they are (placeholders).

import { N_, t } from './i18n.js';
import { shell } from './leaguepages.js';
import { embedSnippet } from './embeds.js';

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const code = (s) => `<code>${esc(s)}</code>`;

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
  ['/api/v1', N_('What there is.')],
  ['/api/v1/championships', N_('Every championship: id, name, members, events, its page.')],
  ['/api/v1/championships/{id}', N_('A championship: members (team, division), events (status, winner once known), seasons.')],
  ['/api/v1/championships/{id}/standings?season={id}', N_('Its season tables: drivers, each class and division, teams. Points per event.'), true],
  ['/api/v1/events/{id}', N_('An event: itinerary (stages, weather, times of day) and full results: total, gap, each stage, penalties, each class and division.'), true],
  ['/api/v1/events/{id}/live', N_('Who is on its stages right now: stage, progress (0-1), time, position (x, z). Ask again every pollSeconds.')],
  ['/api/v1/events/{id}/map', N_('Its stages\' routes, as points in the same x, z as the live positions: draw the map, then the cars on it.')],
  ['/api/v1/cups/{id}', N_('A cup: entrants and seeds, every match, the winner of each.')],
  ['/api/v1/dailies?date={YYYY-MM-DD}', N_('A day\'s dailies: stage, car, weather.')],
  ['/api/v1/dailies/{date}/{slot}', N_('A daily\'s results.'), true],
  ['/api/v1/dailies/{date}/{slot}/live', N_('Who is on a daily\'s stage right now: progress (0-1), time, position (x, z). Ask again every pollSeconds.')],
  ['/api/v1/timetrials?week={YYYY-MM-DD}', N_('A week\'s time trial stages (the week: its Monday).')],
  ['/api/v1/timetrials/{week}/{slot}', N_('A time trial stage\'s results.'), true],
  ['/api/v1/timetrials/{week}/{slot}/live', N_('Who is on a time trial stage right now.')],
  ['/api/v1/ranking?country={cc}&page={n}', N_('The world ranking, 100 a page.'), true],
  ['/api/v1/drivers/{steamId}', N_('A driver: country, team, rating and world rank.')],
];

export function developersPage(env) {
  const site = env.SITE_URL || '';
  const rows = ENDPOINTS.map(([p, what, c]) => `<tr><td>${esc(p)}</td><td>${esc(t(what))}${c ? '<span class="csv">CSV</span>' : ''}</td></tr>`).join('');
  return shell(`${esc(t('Developers'))} · ACR Daily`, `${CSS}
  <div class="dev">
  <div class="top"><div class="kick">ACR Daily</div><h1>${esc(t('Results on your own site'))}</h1>
  <p class="note">${esc(t("Every result, table and live timing on ACR Daily, for your championship's page, your club's site or your stream overlay. Copy an embed, or read the API. Free, no key, no sign-in."))}</p></div>

  <h2>${esc(t('Embeds'))}</h2>
  <p class="note">${esc(t("Paste one into your page. It keeps itself up to date: results every minute while an event is open, live timing every few seconds. Your championship's page gives you these with its own events filled in."))}</p>
  <table class="ep">
    <tr><td>/embed/event/{id}</td><td>${esc(t("An event's results, each class and division to pick."))}</td></tr>
    <tr><td>/embed/event/{id}/live</td><td>${esc(t("Live timing: the stage's map and who is on it."))}</td></tr>
    <tr><td>/embed/championship/{id}</td><td>${t("A championship's standings: drivers, classes, divisions, teams. {0} for one season.", code('?season={id}'))}</td></tr>
  </table>
  <p class="note">${t('Options: {0} (dark by default), {1} (a colour, no #), {2} (no heading).', code('theme=light'), code('accent=FF4655'), code('title=0'))}
  ${t("{0} for its language (else the visitor's own).", code('lang=pl'))}</p>
  <pre>${esc(embedSnippet(site, '/embed/championship/{id}?theme=light', 560))}</pre>

  <h2 id="broadcast">${esc(t('For broadcasters'))}</h2>
  <p class="note">${esc(t('TV graphics for your stream, ready made: the standings tower with flags, a LIVE bug, the driver on the stage with their time and how far they are, and between cars the full classification and the stage, in turn. Made for 1920 x 1080; the background stays see-through.'))}</p>
  <table class="ep">
    <tr><td>/broadcast/daily/{1|2}</td><td>${esc(t("Today's daily stage."))}</td></tr>
    <tr><td>/broadcast/tt/{1|2}</td><td>${esc(t("This week's time trial stage."))}</td></tr>
    <tr><td>/broadcast/event/{id}</td><td>${t("An event: a championship's, a cup's or a ranked session's. {0} for a private rally.", code('?code=XXXX-XXXX'))}</td></tr>
  </table>
  <p class="note"><b>OBS / Streamlabs:</b> ${esc(t('Sources → + → Browser. Paste the address, width 1920, height 1080. Put it above your game capture.'))}
  <b>vMix:</b> ${esc(t('Add Input → Web Browser, 1920 x 1080.'))}</p>
  <p class="note">${t('Options: {0} (only these parts: tower, bug, lower, studio), {1} (seconds per studio page), {2} (a dark backdrop, to look at it in a browser), {3}, {4}.',
    code('parts=tower,lower'), code('rotate=10'), code('bg=1'), code('accent=E30613'), code('lang=pl'))}</p>
  <pre>${esc(site)}/broadcast/daily/1?parts=tower,bug,lower,studio&amp;rotate=12</pre>
  <p class="note">${esc(t('In the game, ACR DAILY\'s WATCH puts the camera on the drivers themselves (TV cameras, onboard, helicopter) with the same graphics: run WATCH on the PC you stream from and capture the game. Your own graphics instead: draw them from the live endpoints below (who is on the stage, how far, their time), asked every pollSeconds.'))}</p>

  <h2>API</h2>
  <p class="note">${t("JSON, read-only, open to every site (CORS). Times are in milliseconds. The tables marked CSV also come as {0}, ready for a spreadsheet. The ids are in each page's address: {1}, {2}, {3}, {4}.",
    code('?format=csv'), `<code>${esc(site)}/l/<b>{id}</b></code>`, '<code>/e/<b>{id}</b></code>', '<code>/cup/<b>{id}</b></code>', '<code>/d/<b>{steamId}</b></code>')}</p>
  <table class="ep">${rows}</table>
  <pre>fetch('${esc(site)}/api/v1/events/43')
  .then(r =&gt; r.json())
  .then(e =&gt; e.results.forEach(r =&gt; console.log(r.rank, r.name, r.totalMs)));</pre>

  <h2>${esc(t('What it shows'))}</h2>
  <p class="note">${t("Exactly what the website shows anyone. A private rally's results need its invite code: {0} (on the event, its live timing and its map, and on its embeds). An event that hides its weather, stages or times keeps them hidden until it closes, for everyone.", code('?code=XXXX-XXXX'))}</p>

  <h2>${esc(t('Fair use'))}</h2>
  <p class="note">${t('Answers are kept for a few seconds (live timing) to a few minutes (results and tables), so asking more often only gets the same answer. Ask live timing every {0} at most. The {1} answers keep their fields: new ones may come, none go. Questions or ideas: {2}.',
    code('pollSeconds'), code('v1'), `<a href="/discord">${esc(t('our Discord'))}</a>`)}</p>
  </div>`, 'account();', env);
}
