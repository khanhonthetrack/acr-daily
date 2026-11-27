// /donate: support ACR Daily (the user, 27 Nov 2026: "a nice page of COMMUNITY called Donate", two buttons: Buy Me a
// Coffee, as in the app, and PayPal, paypal.me/blugyke). Under them, the current supporters (GET /api/supporters,
// src/supporters.js: the app's thank-you bar's list). In the leagues' look (src/leaguepages.js shell), in the reader's
// language.

import { shell } from './leaguepages.js';
import { t, tq } from './i18n.js';

export const BMC_LINK = 'https://www.buymeacoffee.com/acrdaily';
export const PAYPAL_LINK = 'https://paypal.me/blugyke';
const BMC_IMG = 'https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png';

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

const CUP = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9h13v5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5V9Z"/><path d="M17 11h1.5a2.5 2.5 0 0 1 0 5H17"/><path d="M8 3.5c0 1.2 1 1.3 1 2.5M12 3.5c0 1.2 1 1.3 1 2.5"/></svg>';
const HEART = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20s-7.5-4.6-7.5-10A4.3 4.3 0 0 1 12 7.4 4.3 4.3 0 0 1 19.5 10c0 5.4-7.5 10-7.5 10Z"/></svg>';
// PayPal's double P, drawn plain (white on its blue button)
const PP = '<svg class="ppm" viewBox="0 0 24 24" aria-hidden="true"><path d="M8.2 20.5H4.6L7.3 3.5h6.2c3.4 0 5.4 1.8 4.9 4.9-.6 3.6-3.1 5.4-6.6 5.4H9.4l-1.2 6.7Z" opacity=".55"/><path d="M10.3 22h-3l2.4-15.2h5.6c3 0 4.8 1.6 4.3 4.4-.5 3.2-2.8 4.8-5.9 4.8h-2.4L10.3 22Z"/></svg>';

const CSS = `<style>
.don{max-width:860px}
.don .top{position:relative;padding-bottom:26px;border-bottom:1px solid var(--line)}
.don .top .kick{display:flex;align-items:center;gap:8px;color:#FFDD00}
.don .top .kick svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.don .lead{max-width:620px;color:var(--fg2);font-size:17px;line-height:1.55;margin:10px 0 0}
.ways{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:28px}
@media(max-width:680px){.ways{grid-template-columns:1fr}}
.way{position:relative;display:flex;flex-direction:column;background:var(--panel);border:1px solid var(--line);padding:24px 22px 22px;overflow:hidden}
.way::before{content:'';position:absolute;left:0;top:0;right:0;height:3px;background:var(--w)}
.way h2{display:flex;align-items:center;gap:10px;margin:0;font:600 22px/1.1 'Barlow Condensed',sans-serif;letter-spacing:.08em;text-transform:uppercase}
.way h2 svg{width:22px;height:22px;flex:none;fill:none;stroke:var(--w);stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.way p{flex:1;color:var(--fg2);font-size:15px;line-height:1.5;margin:10px 0 20px}
.way .go{align-self:flex-start;display:inline-flex;align-items:center;justify-content:center;transition:transform .12s,filter .12s}
.way .go:hover{transform:translateY(-1px);filter:brightness(1.06)}
.way .go:focus-visible{outline:2px solid var(--fg);outline-offset:3px}
.way .bmc img{display:block;height:60px;width:217px}
.way .pp{gap:10px;height:60px;min-width:217px;padding:0 26px;border-radius:8px;background:#0070BA;color:#fff;text-decoration:none;
  font:700 22px/1 Barlow,sans-serif;letter-spacing:.01em;box-shadow:0 1px 0 rgba(255,255,255,.12) inset}
.way .pp .ppm{width:24px;height:24px;fill:#fff}
.way .pp i{font-style:italic;font-weight:800}
.way small{display:block;margin-top:10px;color:var(--fg3);font-size:13px}
.thanks{margin-top:34px}
.thanks h2{display:flex;align-items:center;gap:8px}
.thanks h2 svg{width:18px;height:18px;fill:#FF453A}
.sup{display:flex;flex-wrap:wrap;gap:8px;list-style:none;padding:0;margin:12px 0 0}
.sup li{display:inline-flex;align-items:center;gap:7px;padding:7px 12px;background:var(--panel);border:1px solid var(--line);font-size:14px}
.sup li.m{border-color:#5A4E12}
.sup li .tag{font:600 10px/1 Barlow,sans-serif;letter-spacing:.1em;text-transform:uppercase;color:#FFDD00}
.sup li .n{color:var(--fg3);font-size:13px}
</style>`;

export function donatePage(env) {
  return shell(esc(t('Donate')) + ' · ACR Daily', `${CSS}
  <div class="don">
  <div class="top"><div class="kick">${HEART}${esc(t('Community'))}</div><h1>${esc(t('Support ACR Daily'))}</h1>
  <p class="lead">${esc(t('Keep servers running and features coming.'))}</p></div>

  <div class="ways">
    <div class="way" style="--w:#FFDD00">
      <h2>${CUP}Buy Me a Coffee</h2>
      <p>${esc(t('A coffee once, or a membership every month. Your name shows in the app\'s thank-you bar.'))}</p>
      <a class="go bmc" href="${BMC_LINK}" target="_blank" rel="noopener"><img src="${BMC_IMG}" alt="Buy Me a Coffee" width="217" height="60"></a>
      <small>buymeacoffee.com/acrdaily</small>
    </div>
    <div class="way" style="--w:#0070BA">
      <h2>${HEART}PayPal</h2>
      <p>${esc(t('Send any amount you like, straight from your PayPal account or a card.'))}</p>
      <a class="go pp" href="${PAYPAL_LINK}" target="_blank" rel="noopener" aria-label="PayPal">${PP}<span><i>Pay</i>Pal</span></a>
      <small>paypal.me/blugyke</small>
    </div>
  </div>

  <div class="thanks" id="thanks" hidden>
    <h2>${HEART}${esc(t('Thank you'))}</h2>
    <p class="note">${esc(t('The drivers supporting ACR Daily right now.'))}</p>
    <ul class="sup" id="sup"></ul>
  </div>
  </div>`, `account();
fetch('/api/supporters').then(function(r){return r.ok?r.json():null}).then(function(j){
  var s=j&&j.supporters||[];if(!s.length)return;var ul=document.getElementById('sup');
  s.forEach(function(p){var li=document.createElement('li'),m=p.kind==='member'||p.kind==='monthly';if(m)li.className='m';
    var b=document.createElement('b');b.textContent=p.name;li.appendChild(b);
    if(m){var g=document.createElement('span');g.className='tag';g.textContent=p.level||${tq('Member')};li.appendChild(g)}
    else if(p.coffees>1){var n=document.createElement('span');n.className='n';n.textContent='\\u2615 \\u00d7 '+p.coffees;li.appendChild(n)}
    ul.appendChild(li)});
  document.getElementById('thanks').hidden=false},function(){});`, env,
  { title: t('Donate'), description: t('Support ACR Daily: Buy Me a Coffee or PayPal.') });
}
