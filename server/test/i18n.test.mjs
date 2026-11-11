// The website's languages (src/i18n.js): which one a request gets, the API's messages in it, the picker, and every
// page built in every language (test/pages_i18n_check.mjs runs the same by hand, with a pseudo-language too).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { pickLang, inLang, t, tn, apiMessage, langPicker, localized, CODES } from '../src/i18n.js';

const req = (url, headers = {}) => new Request(url, { headers });

test('the language: ?lang=, then the cookie, then the browser\'s, else English', () => {
  assert.equal(pickLang(req('https://x/?lang=ja', { Cookie: 'lang=pl', 'Accept-Language': 'de' })), 'ja');
  assert.equal(pickLang(req('https://x/', { Cookie: 'a=1; lang=pl', 'Accept-Language': 'de' })), 'pl');
  assert.equal(pickLang(req('https://x/', { 'Accept-Language': 'nl-NL, hu;q=0.8, de;q=0.9' })), 'de');
  assert.equal(pickLang(req('https://x/', { 'Accept-Language': 'nl-NL' })), 'en');
  assert.equal(pickLang(req('https://x/?lang=xx')), 'en');
});

test('Spanish and Portuguese are translated but not offered for now', () => {
  assert.ok(!CODES.includes('es') && !CODES.includes('pt'));
  assert.equal(pickLang(req('https://x/', { 'Accept-Language': 'es-ES, pt-BR;q=0.9' })), 'en');
  assert.ok(!langPicker().includes('Español'));
  assert.equal(CODES.length, 8);
});

test('words, plurals and the picker in a language', () => {
  assert.equal(inLang('de', () => t('Ranking')), 'Rangliste');
  assert.equal(inLang('pl', () => tn('{0} driver', '{0} drivers', 5, 5)), '5 kierowców');
  assert.equal(inLang('pl', () => tn('{0} driver', '{0} drivers', 3, 3)), '3 kierowców');
  assert.equal(inLang('fr', () => tn('{0} driver', '{0} drivers', 0, 0)), '0 pilote');
  assert.equal(inLang('xx', () => t('Ranking')), 'Ranking');
  const picker = inLang('ja', langPicker);
  assert.match(picker, /<option value="ja" selected>日本語<\/option>/);
  assert.match(picker, /<span aria-hidden="true">ja<\/span>/);
});

test("the API's messages in the request's language, values and a second sentence too", async () => {
  assert.equal(apiMessage('hu', 'no such driver'), 'nincs ilyen versenyző');
  assert.equal(apiMessage('de', 'the stake is 50 credits: you have 3'), 'der Einsatz ist 50 Credits: du hast 3');
  assert.equal(apiMessage('pl', 'invalid run: ACR Daily 0.0.9 is too old for the leaderboard. ' +
    'Update to 0.0.30 or newer (UPDATE button in the app, or the website).'),
  'nieważny przejazd: ACR Daily 0.0.9 jest za stare na tabelę wyników. ' +
    'Zaktualizuj do wersji 0.0.30 lub nowszej (przycisk AKTUALIZUJ w aplikacji albo strona).');
  assert.equal(apiMessage('en', 'no such driver'), 'no such driver');
  assert.equal(apiMessage('ja', 'something nobody wrote'), 'something nobody wrote');
  const res = await localized(new Response(JSON.stringify({ error: 'no such team' }), {
    status: 404, headers: { 'content-type': 'application/json' } }), 'zh', req('https://x/api/teams/9'));
  assert.equal(res.status, 404);
  assert.deepEqual(await res.json(), { error: '没有这个车队' });
});

test('every page, in every language and in a pseudo-language, is made and its scripts compile', () => {
  const check = fileURLToPath(new URL('./pages_i18n_check.mjs', import.meta.url));
  for (const arg of [[], ['pseudo']]) {
    const out = execFileSync(process.execPath, [check, ...arg], { encoding: 'utf8' });
    assert.match(out, /all pages fine/);
  }
});
