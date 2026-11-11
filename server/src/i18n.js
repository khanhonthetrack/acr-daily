// The website's languages: every page in the language picked in its header (a cookie), else the browser's own when it
// is one of these, else English. The app sends its own (Accept-Language), so the server's messages come back in it.
//
// The English is the key (as gettext's): t('Leagues') is 'Ligi' in Polish. Each language's words are in
// src/locales/<code>.js, English -> that language; a string not translated yet shows in English. {0}, {1}... are the
// values put in (a translation may order them as its language wants). A plural is keyed by its English plural and
// holds the language's forms (CLDR's: Polish has three, Japanese one): tn('{0} driver', '{0} drivers', n).
// tools/i18n/extract.py lists the strings the code uses and what each language still lacks.
//
// Pages are built in one go (no await while a page's words are made): inLang(lang, () => page()) sets the language
// they are made in. In a page's script, tq('...') puts a translation in as a JS string, tqp(one, other) a plural's
// forms for P(forms, n) (I18N_JS: the page's own F, FN, P).
import pl from './locales/pl.js';
import hu from './locales/hu.js';
import ja from './locales/ja.js';
import de from './locales/de.js';
import fr from './locales/fr.js';
import es from './locales/es.js';
import it from './locales/it.js';
import pt from './locales/pt.js';
import zh from './locales/zh.js';
import { API_MESSAGES } from './locales/api.js';

// [code, its own name, the BCP 47 tag for <html lang> and dates]: the order of the language picker
export const LANGS = [
  ['en', 'English', 'en-GB'], ['pl', 'Polski', 'pl'], ['hu', 'Magyar', 'hu'], ['ja', '日本語', 'ja'],
  ['de', 'Deutsch', 'de'], ['fr', 'Français', 'fr'], ['es', 'Español', 'es'], ['it', 'Italiano', 'it'],
  ['pt', 'Português (Brasil)', 'pt-BR'], ['zh', '简体中文', 'zh-CN'],
];
export const CODES = LANGS.map((l) => l[0]);
const CATALOGS = { en: {}, pl, hu, ja, de, fr, es, it, pt, zh };
const COOKIE = 'lang';

let CUR = 'en';

/** (tests) a language's words replaced: test/pages_i18n_check.mjs fills one with quotes to see no page breaks. */
export function _setCatalog(code, words) { CATALOGS[code] = words; }

/** The language a request wants: ?lang=, then the lang cookie, then Accept-Language; English otherwise. */
export function pickLang(req) {
  try {
    const q = new URL(req.url).searchParams.get('lang');
    if (q && CODES.includes(q)) return q;
  } catch { /* (not a URL: the tests' bare requests) */ }
  const cookie = (req.headers && req.headers.get('Cookie')) || '';
  const m = cookie.match(/(?:^|;\s*)lang=([a-z]{2})(?:;|$)/);
  if (m && CODES.includes(m[1])) return m[1];
  const accept = (req.headers && req.headers.get('Accept-Language')) || '';
  const wanted = accept.split(',').map((part, i) => {
    const [tag, ...params] = part.trim().split(';');
    const qv = params.map((p) => p.trim()).find((p) => p.startsWith('q='));
    return { code: tag.trim().toLowerCase().split('-')[0], q: qv ? Number(qv.slice(2)) || 0 : 1, i };
  }).filter((x) => x.code && x.q > 0).sort((a, b) => b.q - a.q || a.i - b.i);
  const hit = wanted.find((x) => CODES.includes(x.code));
  return hit ? hit.code : 'en';
}

/** The Set-Cookie that keeps a language picked with ?lang= (a year). */
export const langCookie = (lang) => `${COOKIE}=${lang}; Path=/; Max-Age=31536000; SameSite=Lax; Secure`;

/** fn() made in a language (pages: synchronous, so nothing else runs in between). */
export function inLang(lang, fn) {
  const before = CUR;
  CUR = CODES.includes(lang) ? lang : 'en';
  try { return fn(); } finally { CUR = before; }
}

export const lang = () => CUR;
export const langTag = (code = CUR) => (LANGS.find((l) => l[0] === code) || LANGS[0])[2];

/** CLDR's plural form for a whole number n, as an index into a language's forms. */
export function pluralIndex(code, n) {
  n = Math.abs(Math.trunc(Number(n) || 0));
  if (code === 'ja' || code === 'zh' || code === 'hu') return 0;   // one form (Hungarian counts with the singular)
  if (code === 'pl') return n === 1 ? 0 : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? 1 : 2;
  if (code === 'fr' || code === 'pt') return n <= 1 ? 0 : 1;      // 0 and 1 are singular
  return n === 1 ? 0 : 1;
}

/** {0}, {1}... in s replaced by args. */
export function fill(s, args) {
  return String(s).replace(/\{(\d+)\}/g, (m, i) => (args[+i] == null ? '' : String(args[+i])));
}

function word(code, s) {
  const v = (CATALOGS[code] || {})[s];
  return typeof v === 'string' && v ? v : null;
}

/** s in the language being made, its {0}... filled from args. */
export function t(s, ...args) {
  const v = word(CUR, s) ?? s;
  return args.length ? fill(v, args) : v;
}

/** A plural's forms in the language being made (one, other: the English). */
export function forms(one, other) {
  const v = (CATALOGS[CUR] || {})[other];
  if (Array.isArray(v) && v.length && v.every((x) => typeof x === 'string' && x)) return v;
  if (typeof v === 'string' && v) return [v];
  return [one, other];
}

/** The form that goes with n, filled with n as {0} and args as {1}... */
export function tn(one, other, n, ...args) {
  const f = forms(one, other);
  return fill(f[Math.min(pluralIndex(CUR, n), f.length - 1)], [n, ...args]);
}

/** A string for a page's script: JSON, safe inside <script>. */
export const js = (v) => JSON.stringify(v).replace(/</g, '\\u003c').replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');
/** t() as a JS string literal, for a page's script. */
export const tq = (s, ...args) => js(t(s, ...args));
/** t() inside a JS string literal of a page's script ('...' around it already: '<span>${ts('Name')}</span>'). */
export const ts = (s, ...args) => t(s, ...args).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\n/g, '\\n').replace(/</g, '\\x3c');
/** A plural's forms as a JS array literal, for P(forms, n) in a page's script. */
export const tqp = (one, other) => js(forms(one, other));
/** An English word from data (a rally, the weather) marked for tools/i18n/extract.py; t() says it. */
export const N_ = (s) => s;

// The server's words the pages show from data (the rallies, their surfaces, the weather and times of day: src/conditions.js)
export const DATA = [
  N_('Alsace'), N_('Greece'), N_('Monte Carlo'), N_('Wales'), N_('Livigno'),
  N_('Tarmac'), N_('Gravel'), N_('Snow'),
  N_('Clear'), N_('Light clouds'), N_('Clouds'), N_('Light fog'), N_('Fog'), N_('Light rain'), N_('Rain'),
  N_('Storm'), N_('Light snow'), N_('Snow blizzard'),
  N_('Morning'), N_('Midday'), N_('Afternoon'), N_('Evening'),
];

/** The data words of the language being made, for a page's script: TD('Wales'), TD('Afternoon (16:00)'). */
export function dataWords() {
  const out = {};
  for (const w of DATA) { const v = word(CUR, w); if (v) out[w] = v; }
  return out;
}

/** More data words for a page's script (a shop's items, the credits' labels...): TD(word) says them. */
export function wordsJs(list) {
  const out = {};
  for (const w of list) { const v = word(CUR, w); if (v) out[w] = v; }
  return `Object.assign(DW,${js(out)});`;
}

/** The helpers every page's script has: LANG, LOC (dates), F (fill {0}...), FN (the same with DOM nodes: an array),
 *  P (a plural's form), TD (a data word: a rally, the weather, 'Afternoon (16:00)'). */
export function I18N_JS() {
  const rule = {
    pl: 'n==1?0:(n%10>=2&&n%10<=4&&(n%100<12||n%100>14))?1:2', fr: 'n<=1?0:1', pt: 'n<=1?0:1', ja: '0', zh: '0', hu: '0',
  }[CUR] || 'n==1?0:1';
  return `var LANG=${js(CUR)},LOC=${js(langTag())},DW=${js(dataWords())};
  function F(s){var a=arguments;return String(s).replace(/\\{(\\d+)\\}/g,function(m,i){var v=a[+i+1];return v==null?'':String(v)})}
  function FN(s){var a=[].slice.call(arguments,1),out=[];String(s).split(/(\\{\\d+\\})/).forEach(function(p){var m=/^\\{(\\d+)\\}$/.exec(p);
    if(m){var v=a[+m[1]];if(v!=null)out.push(typeof v==='object'?v:String(v))}else if(p)out.push(p)});return out}
  function PI(n){n=Math.abs(Math.trunc(+n||0));return ${rule}}
  function P(f,n){var s=typeof f==='string'?f:f[Math.min(PI(n),f.length-1)];return F.apply(null,[s].concat([].slice.call(arguments,1)))}
  function TD(w){if(w==null)return w;var m=/^(.*?)\\s*\\((\\d{1,2}:\\d\\d)\\)$/.exec(w);if(m)return (DW[m[1]]||m[1])+' ('+m[2]+')';return DW[w]||w}`;
}

/** The header's language picker: a drop-down of the languages, each in its own words (a cookie, then the page again). */
export function langPicker() {
  const opts = LANGS.map(([c, n]) => `<option value="${c}"${c === CUR ? ' selected' : ''}>${n}</option>`).join('');
  // (shown: the globe and the language's code; opened: the languages by name; the select lies over both, unseen)
  return `<label class="langpick" title="Language"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg><span aria-hidden="true">${CUR}</span><select aria-label="Language" onchange="document.cookie='lang='+this.value+'; path=/; max-age=31536000; samesite=lax';var u=new URL(location.href);u.searchParams.delete('lang');location.replace(u.href)">${opts}</select></label>`;
}
/** After a page's </header>: its one row too wide for the window (longer words in most languages than in English, the
 *  account's name or button coming in later), the header gets class "tight" (its links closer together) and, still too
 *  wide, "two" instead: its two-row layout, as on a narrower window. */
export const HEADER_FIT = `<script>(function(){var h=document.querySelector('header'),w=h&&h.querySelector('.wrap');if(!w)return;
function over(){return w.scrollWidth>w.clientWidth+1}
function fit(){h.classList.remove('tight','two');if(!over())return;h.classList.add('tight');if(over()){h.classList.remove('tight');h.classList.add('two')}}
fit();addEventListener('resize',fit);if(document.fonts&&document.fonts.ready)document.fonts.ready.then(fit);
var a=document.getElementById('acct');if(a&&window.MutationObserver)new MutationObserver(fit).observe(a,{childList:true,subtree:true})})()</script>`;

export const LANG_CSS = `.langpick{position:relative;display:inline-flex;align-items:center;gap:5px;color:var(--fg2);white-space:nowrap;cursor:pointer;padding:4px 2px;flex-shrink:0}
.langpick svg{width:15px;height:15px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.langpick span{font:600 13px/1 'Barlow Condensed',sans-serif;letter-spacing:.08em;text-transform:uppercase}
.langpick select{position:absolute;inset:0;width:100%;height:100%;opacity:0;cursor:pointer;font-size:16px}
.langpick select option{background:#141417;color:#F4F4F5}
.langpick:hover,.langpick:focus-within{color:var(--fg)}`;

// ------------------------------------------------------------------ the API's messages
// Every API answer with an `error` goes out in the request's language: the message as the code wrote it in English, or
// one of API_MESSAGES' patterns ({0}: anything) with its values put back in. API_MESSAGES: tools/i18n/extract.py
// collects them from the code (err('...'), throw new Error('...'), { error: '...' }).
const PATTERNS = API_MESSAGES.filter((m) => /\{\d+\}/.test(m)).map((m) => ({
  m,
  re: new RegExp('^' + m.split(/(\{\d+\})/).map((p) => (/^\{\d+\}$/.test(p) ? '([\\s\\S]*?)' : p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))).join('') + '$'),
  order: [...m.matchAll(/\{(\d+)\}/g)].map((x) => +x[1]),
}));

/** An API message (English) in a language: as a whole, or by its pattern; else as it is. */
export function apiMessage(code, msg) {
  if (code === 'en' || typeof msg !== 'string' || !msg) return msg;
  const whole = word(code, msg);
  if (whole) return whole;
  for (const p of PATTERNS) {
    const m = p.re.exec(msg);
    if (!m) continue;
    const v = word(code, p.m);
    if (!v) return msg;
    const args = [];
    // (a value put in is translated too when it is a word, or a message of its own: 'Update to 0.0.30 or newer...')
    p.order.forEach((k, i) => { args[k] = inLang(code, () => { const x = m[i + 1]; return word(code, x) ?? (x.length > 12 ? apiMessage(code, x) : x); }); });
    return fill(v, args);
  }
  // "Not sent: <a message>" and the like: the part after the colon on its own
  const c = msg.indexOf(': ');
  if (c > 0) {
    const head = word(code, msg.slice(0, c)), tail = apiMessage(code, msg.slice(c + 2));
    if (head && tail !== msg.slice(c + 2)) return `${head}: ${tail}`;
  }
  return msg;
}

// The API's own words in its answers (an achievement's name, a notice, a shop item...): each module registers a
// path and what to translate in its JSON (fn(json), run in the request's language: t() says them).
const DATA_HOOKS = [];
export function registerData(path, fn) { DATA_HOOKS.push([path, fn]); }

/** A response in the request's language: an API error's message translated, the API's own words in its answers
 *  (registerData), ?lang= kept in a cookie. */
export async function localized(res, code, req) {
  let out = res;
  const type = res.headers.get('Content-Type') || '';
  if (code !== 'en' && res.status >= 400 && type.startsWith('application/json')) {
    try {
      const body = await res.clone().json();
      if (body && typeof body.error === 'string') {
        const said = apiMessage(code, body.error);
        if (said !== body.error) {
          out = new Response(JSON.stringify({ ...body, error: said }), { status: res.status, headers: res.headers });
        }
      }
    } catch { /* (not JSON after all: as it is) */ }
  }
  let path = '';
  try { path = new URL(req.url).pathname; } catch { path = ''; }
  const hooks = code === 'en' || res.status >= 400 || !type.startsWith('application/json') ? [] : DATA_HOOKS.filter(([p]) => p.test(path));
  if (hooks.length) {
    try {
      const body = await res.clone().json();
      inLang(code, () => { for (const [, fn] of hooks) fn(body); });
      out = new Response(JSON.stringify(body), { status: res.status, headers: res.headers });
    } catch (e) { console.error('i18n data', path, e); }
  }
  let q = null;
  try { q = new URL(req.url).searchParams.get('lang'); } catch { q = null; }
  if (q && CODES.includes(q) && type.startsWith('text/html')) {
    out = new Response(out.body, out);
    out.headers.append('Set-Cookie', langCookie(q));
  }
  return out;
}
