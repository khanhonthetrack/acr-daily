// The commentator's voice for ACR DAILY: Dailies (the user, 25 Nov 2026: "Introduce an english text to speech sport
// commentary AI. Keep in mind that it's rally, so the guy should be enthusiastic"; Azure AI Speech, the user's choice):
// Claude's spoken line (src/commentary.js) read by an Azure neural voice in its excited style, for the overlay to play.
//
//   AZURE_SPEECH_KEY      a secret (wrangler secret put AZURE_SPEECH_KEY): the Speech resource's key
//   AZURE_SPEECH_REGION   wrangler.toml: the Speech resource's region (e.g. westeurope); either unset: no voice, and no
//                         Claude lines either (index.js: they are only spoken now)
//   AZURE_TTS_VOICE       optional: the voice, en-US-DavisNeural by default (one with an "excited" style)
//   AZURE_TTS_STYLE       optional: its style, excited by default (shouting: louder still)
//
//   GET /api/broadcast/dailies/speech?id=<line id> -> audio/mpeg (404: no such line lately)
//
// Only lines Claude wrote lately, found by their id (never text from the request), each synthesized once: the audio is
// kept in Cloudflare's cache, however many overlays play it.

const KEEP_S = 6 * 3600;
const AUDIO_KEY = (id) => `https://acrdaily.internal/commentary/audio/${encodeURIComponent(id)}`;
const DEFAULT_VOICE = 'en-US-DavisNeural';
const DEFAULT_STYLE = 'excited';

const xml = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;' })[c]);
const safe = (s, re, dflt) => (re.test(String(s || '')) ? String(s) : dflt);

export const speechOn = (env) => !!(env.AZURE_SPEECH_KEY && /^[a-z0-9]{3,32}$/.test(String(env.AZURE_SPEECH_REGION || '')));

/** The SSML for one line: the voice in its style, a touch quicker, as a commentator talks. */
export function ssml(env, text) {
  const voice = safe(env.AZURE_TTS_VOICE, /^[a-z]{2}-[A-Z]{2}-[A-Za-z]+Neural$/, DEFAULT_VOICE);
  const style = safe(env.AZURE_TTS_STYLE, /^[a-z-]{3,30}$/, DEFAULT_STYLE);
  return `<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="en-US">`
    + `<voice name="${voice}"><mstts:express-as style="${style}" styledegree="1.6"><prosody rate="+8%">${xml(text)}</prosody>`
    + `</mstts:express-as></voice></speak>`;
}

/** The line's audio -> {status, body, type}. line: the line's text (src/commentary.js lineById), null if none. */
export async function speech(env, id, line, { fetcher = fetch, cache = typeof caches !== 'undefined' ? caches.default : null } = {}) {
  if (!speechOn(env) || !cache) return { status: 404, body: 'no voice', type: 'text/plain' };
  if (!line) return { status: 404, body: 'no such line', type: 'text/plain' };
  const hit = await cache.match(new Request(AUDIO_KEY(id)));
  if (hit) return { status: 200, body: await hit.arrayBuffer(), type: 'audio/mpeg' };
  let r;
  try {
    r = await fetcher(`https://${env.AZURE_SPEECH_REGION}.tts.speech.microsoft.com/cognitiveservices/v1`, {
      method: 'POST',
      headers: { 'Ocp-Apim-Subscription-Key': env.AZURE_SPEECH_KEY, 'Content-Type': 'application/ssml+xml',
        'X-Microsoft-OutputFormat': 'audio-24khz-48kbitrate-mono-mp3', 'User-Agent': 'acr-daily' },
      body: ssml(env, line),
    });
  } catch (e) {
    console.log('speech: Azure not answering', e && e.message);
    return { status: 502, body: 'voice not answering', type: 'text/plain' };
  }
  if (!r.ok) {
    console.log('speech: Azure said', r.status);
    return { status: 502, body: 'voice not answering', type: 'text/plain' };
  }
  const body = await r.arrayBuffer();
  await cache.put(new Request(AUDIO_KEY(id)), new Response(body, {
    headers: { 'Content-Type': 'audio/mpeg', 'Cache-Control': `public, max-age=${KEEP_S}` } }));
  return { status: 200, body, type: 'audio/mpeg' };
}
