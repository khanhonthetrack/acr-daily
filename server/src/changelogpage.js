// /changelog: what's new in each app version (src/changelog.js), newest first; only the versions that are out
// (LATEST_VERSION and older). Each version has its anchor (#v0.0.30): the Discord posts and the app link to it.
// In the leagues' look (src/leaguepages.js shell); in the reader's language (the entries too, once translated).

import { published } from './changelog.js';
import { t } from './i18n.js';
import { shell } from './leaguepages.js';
import { downloadUrl, latestVersion } from './release.js';

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
// a version's day: written out in the reader's language by the page's script (no Intl here: its first use costs a
// fresh Worker ~14 ms of CPU); the date as it is until then
const day = (d) => `<time datetime="${esc(d)}">${esc(d)}</time>`;
const DAYS_JS = `document.querySelectorAll('time[datetime]').forEach(function(x){try{x.textContent=new Date(x.dateTime+'T12:00:00Z')
  .toLocaleDateString(LOC,{day:'numeric',month:'long',year:'numeric',timeZone:'UTC'})}catch(e){}});`;

const CSS = `<style>
.cl{max-width:760px}
.ver{margin-top:22px;scroll-margin-top:90px}
.ver h2{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin:0}
.ver h2 a{color:inherit;text-decoration:none}
.ver .when{font:500 14px/1 Barlow,sans-serif;color:var(--fg3);letter-spacing:0;text-transform:none}
.ver .now{border:1px solid var(--good);color:var(--good);padding:3px 7px;font:600 11px/1 Barlow,sans-serif;letter-spacing:.08em;text-transform:uppercase}
.ver .head{margin:10px 0 0;font:600 18px/1.3 Barlow,sans-serif;color:var(--fg)}
.ver ul{margin:10px 0 0;padding-left:20px}
.ver li{margin-bottom:6px;color:var(--fg2)}
.ver:target{outline:1px solid var(--line2);outline-offset:10px}
</style>`;

export function changelogPage(env) {
  const latest = latestVersion(env), download = downloadUrl(env);
  const list = published(latest).map((e) => `
  <section class="ver card" id="v${esc(e.version)}">
    <h2><a href="#v${esc(e.version)}">${esc(e.version)}</a><span class="when">${day(e.date)}</span>${e.version === latest ? `<span class="now">${esc(t('Current'))}</span>` : ''}</h2>
    ${e.title ? `<p class="head">${esc(t(e.title))}</p>` : ''}
    <ul>${e.changes.map((c) => `<li>${esc(t(c))}</li>`).join('')}</ul>
  </section>`).join('');
  return shell(`${esc(t("What's new"))} · ACR Daily`, `${CSS}
  <div class="cl">
  <div class="top"><div class="kick">ACR Daily</div><h1>${esc(t("What's new"))}</h1>
  <p class="note">${t('The changes in each version of the app, newest first. The app shows a red UPDATE bar when there is a new one.')}
  ${download ? t('Or {0}.', `<a href="${esc(download)}">${esc(t('download it here'))}</a>`) : ''}
  ${t('Each new version is posted in #changelog on {0} too.', `<a href="/discord">${esc(t('our Discord'))}</a>`)}</p></div>
  ${list || `<p class="note">${esc(t('Nothing here yet.'))}</p>`}
  </div>`, DAYS_JS, env);
}
