// The commentator's voice (src/speech.js) with a stand-in Azure and cache: each line synthesized once, only lines
// Claude wrote (found by id), the excited style, the text escaped; off without the key and region.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { speech, speechOn, ssml } from '../src/speech.js';
import { dailiesCommentary, lineById } from '../src/commentary.js';
import { fakeD1 } from './faked1.mjs';
import worker from '../src/index.js';

const ENV = { AZURE_SPEECH_KEY: 'sk', AZURE_SPEECH_REGION: 'westeurope', ANTHROPIC_API_KEY: 'k' };
function fakeCache() {
  const m = new Map();
  return { m, match: async (r) => (m.has(r.url) ? new Response(m.get(r.url).slice(0)) : undefined),
    put: async (r, res) => { m.set(r.url, await res.arrayBuffer()); } };
}
function fakeAzure(status = 200) {
  const f = async (url, init) => { f.calls.push({ url, init }); return new Response(status === 200 ? new Uint8Array([1, 2, 3]) : 'no', { status }); };
  f.calls = [];
  return f;
}

test('on only with both the key and a region', () => {
  assert.equal(speechOn({}), false);
  assert.equal(speechOn({ AZURE_SPEECH_KEY: 'sk' }), false);
  assert.equal(speechOn({ AZURE_SPEECH_KEY: 'sk', AZURE_SPEECH_REGION: 'west europe' }), false);
  assert.equal(speechOn(ENV), true);
});

test('the SSML: the excited voice, a touch quicker, the line escaped; a bad voice setting falls back', () => {
  const s = ssml(ENV, 'Kalle <flies> & "wins"!');
  assert.match(s, /<voice name="en-US-DavisNeural"><mstts:express-as style="excited" styledegree="1.6"><prosody rate="\+8%">/);
  assert.match(s, /Kalle &lt;flies&gt; &amp; &quot;wins&quot;!/);
  assert.match(ssml({ ...ENV, AZURE_TTS_VOICE: 'en-GB-RyanNeural', AZURE_TTS_STYLE: 'shouting' }, 'x'), /name="en-GB-RyanNeural"><mstts:express-as style="shouting"/);
  assert.match(ssml({ ...ENV, AZURE_TTS_VOICE: '"><evil' }, 'x'), /name="en-US-DavisNeural"/);
});

test('a line synthesized once, then from the cache; Azure asked as its REST API says', async () => {
  const cache = fakeCache(), az = fakeAzure();
  const a = await speech(ENV, '2026-11-25:1795602862155', 'What a time!', { fetcher: az, cache });
  assert.equal(a.status, 200);
  assert.equal(a.type, 'audio/mpeg');
  assert.deepEqual([...new Uint8Array(a.body)], [1, 2, 3]);
  assert.equal(az.calls[0].url, 'https://westeurope.tts.speech.microsoft.com/cognitiveservices/v1');
  assert.equal(az.calls[0].init.headers['Ocp-Apim-Subscription-Key'], 'sk');
  assert.equal(az.calls[0].init.headers['X-Microsoft-OutputFormat'], 'audio-24khz-48kbitrate-mono-mp3');
  const b = await speech(ENV, '2026-11-25:1795602862155', 'What a time!', { fetcher: az, cache });
  assert.equal(b.status, 200);
  assert.equal(az.calls.length, 1);
});

test('no line, no voice set, or Azure refusing: no audio', async () => {
  const az = fakeAzure();
  assert.equal((await speech(ENV, 'x', null, { fetcher: az, cache: fakeCache() })).status, 404);
  assert.equal((await speech({}, 'x', 'Line', { fetcher: az, cache: fakeCache() })).status, 404);
  assert.equal(az.calls.length, 0);
  assert.equal((await speech(ENV, 'x', 'Line', { fetcher: fakeAzure(401), cache: fakeCache() })).status, 502);
});

test('Claude\'s line found again by its id (only an id of the right shape)', async () => {
  const m = new Map(), cache = { match: async (r) => (m.has(r.url) ? new Response(m.get(r.url)) : undefined), put: async (r, x) => { m.set(r.url, await x.text()); } };
  const day = { date: '2026-11-25', dailies: [{ slot: 1, stage: 'Col de Turini', rally: 'Monte Carlo', car: 'Lancia 037' }] };
  const ask = async (p) => (p === '/api/v1/dailies' ? day : {});
  const client = { beta: { messages: { create: async () => ({ stop_reason: 'end_turn', content: [{ type: 'text', text: 'Here we go on stage one!' }] }) } } };
  const r = await dailiesCommentary(ENV, ask, { client, cache, now: 1795602862155 });
  assert.equal(await lineById(r.id, { cache }), 'Here we go on stage one!');
  assert.equal(await lineById('../../etc', { cache }), null);
  assert.equal(await lineById('2026-11-25:1', { cache }), null);
});

test('the endpoints: no voice set, no lines and no audio', async () => {
  const get = (p, extra = {}) => worker.fetch(new Request('https://acrdaily.com' + p), fakeD1({ SITE_URL: 'https://acrdaily.com', ANTHROPIC_API_KEY: 'k', ...extra }).env, { waitUntil() {} });
  assert.deepEqual(await (await get('/api/broadcast/dailies/commentary')).json(), { on: false });
  assert.equal((await get('/api/broadcast/dailies/speech?id=2026-11-25:1795602862155')).status, 404);
});
