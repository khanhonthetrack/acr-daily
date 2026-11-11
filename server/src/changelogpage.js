// /changelog: what's new in each app version (src/changelog.js), newest first; only the versions that are out
// (LATEST_VERSION and older). Each version has its anchor (#v0.0.30): the Discord posts and the app link to it.
// In the leagues' look (src/leaguepages.js shell).

import { published } from './changelog.js';
import { shell } from './leaguepages.js';
import { downloadUrl, latestVersion } from './release.js';

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const day = (d) => { const [y, m, n] = String(d).split('-').map(Number); return `${n} ${MONTHS[m - 1]} ${y}`; };

const CSS = `<style>
.cl{max-width:760px}
.ver{margin-top:22px;scroll-margin-top:90px}
.ver h2{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin:0}
.ver h2 a{color:inherit;text-decoration:none}
.ver .when{font:500 14px/1 Barlow,sans-serif;color:var(--fg3);letter-spacing:0;text-transform:none}
.ver .now{border:1px solid var(--good);color:var(--good);padding:3px 7px;font:600 11px/1 Barlow,sans-serif;letter-spacing:.08em;text-transform:uppercase}
.ver ul{margin:10px 0 0;padding-left:20px}
.ver li{margin-bottom:6px;color:var(--fg2)}
.ver:target{outline:1px solid var(--line2);outline-offset:10px}
</style>`;

export function changelogPage(env) {
  const latest = latestVersion(env), download = downloadUrl(env);
  const list = published(latest).map((e) => `
  <section class="ver card" id="v${esc(e.version)}">
    <h2><a href="#v${esc(e.version)}">${esc(e.version)}</a><span class="when">${day(e.date)}</span>${e.version === latest ? '<span class="now">Current</span>' : ''}</h2>
    <ul>${e.changes.map((c) => `<li>${esc(c)}</li>`).join('')}</ul>
  </section>`).join('');
  return shell('What\'s new · ACR Daily', `${CSS}
  <div class="cl">
  <div class="top"><div class="kick">ACR Daily</div><h1>What's new</h1>
  <p class="note">The changes in each version of the app, newest first. The app shows a red UPDATE bar when there is a new
  one${download ? `, or <a href="${esc(download)}">download it here</a>` : ''}. Each new version is posted in #changelog on
  <a href="/discord">our Discord</a> too.</p></div>
  ${list || '<p class="note">Nothing here yet.</p>'}
  </div>`, '', env);
}
