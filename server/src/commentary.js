// Live commentary: each run event (start, split, reset, finish, DNF) becomes one short line, written by Claude
// from the facts of the moment (who, where on the stage, place and gap against the field). Without an API key
// (secret ANTHROPIC_API_KEY), or if the call fails, a plain line from a template is used instead.
// The website and the app show the last few lines of each daily.

import Anthropic from '@anthropic-ai/sdk';

export const SHOW = 5;                   // lines shown
const MAX_PER_DAY = 2000;               // safety cap on lines (and so on API calls) per day
const MODEL = 'claude-haiku-4-5';

const SYSTEM = `You are the live commentator of ACR Daily, a daily time-trial challenge in the sim racing game Assetto Corsa Rally.
You get one event from a rally stage as JSON, plus the most recent lines you already said.
Write ONE line of live commentary about that event for the website's live ticker.

Rules:
- One sentence, at most 22 words, plain text: no quotes, emoji, hashtags or markdown.
- Use only the facts in the event. Never invent times, places, gaps, corners or incidents.
- Copy times and gaps exactly as given (they are already formatted).
- Use the driver's name as given. Energetic rally-commentator tone, but accurate.
- Do not reuse the wording of the recent lines.`;

const fmt = (ms) => {
  if (ms == null) return null;
  const m = Math.floor(ms / 60000), s = (ms % 60000) / 1000;
  return `${m}:${s < 10 ? '0' : ''}${s.toFixed(3)}`;
};
const gap = (ms) => (ms == null ? null : `${ms >= 0 ? '+' : '-'}${(Math.abs(ms) / 1000).toFixed(3)} s`);
const ordinal = (n) => `P${n}`;

/** The plain line when Claude isn't available. */
export function templateLine(e) {
  const who = e.driver;
  switch (e.kind) {
    case 'start': return `${who} is away on ${e.stage}${e.car ? ' in the ' + e.car : ''}.`;
    case 'split':
      return e.place
        ? `${who} at split ${e.split}: ${e.time}, ${ordinal(e.place)} of ${e.of}${e.gapToLeader ? ', ' + e.gapToLeader + ' to ' + e.leader : ''}.`
        : `${who} through split ${e.split} in ${e.time}.`;
    case 'reset': return `${who} has gone off and reset at ${e.at}: plus 60 seconds.`;
    case 'finish':
      return e.place === 1
        ? `${who} goes fastest: ${e.time}${e.resets ? ' with ' + e.resets + ' reset(s)' : ''}!`
        : `${who} finishes in ${e.time}, ${ordinal(e.place)}${e.gapToLeader ? ', ' + e.gapToLeader + ' off ' + e.leader : ''}.`;
    case 'dnf': return `${who} is out: ${e.reason || 'did not finish'}.`;
    default: return `${who}: ${e.kind}.`;
  }
}

async function claudeLine(env, event, recent) {
  const client = new Anthropic({ apiKey: env.ANTHROPIC_API_KEY, timeout: 15000, maxRetries: 1 });
  const response = await client.messages.create({
    model: env.COMMENTARY_MODEL || MODEL,
    max_tokens: 120,
    system: SYSTEM,
    messages: [{ role: 'user', content: JSON.stringify({ event, recentLines: recent }) }],
  });
  if (response.stop_reason === 'refusal') return null;
  const text = response.content.filter((b) => b.type === 'text').map((b) => b.text).join(' ').trim();
  return text ? text.replace(/\s+/g, ' ').replace(/^["']|["']$/g, '').slice(0, 220) : null;
}

/** Write the line for one event (call through ctx.waitUntil so the app's request isn't held up). */
export async function comment(env, date, slot, event, steamId = null) {
  const n = await env.DB.prepare('SELECT COUNT(*) AS n FROM commentary WHERE date = ?').bind(date).first();
  if (n.n >= MAX_PER_DAY) return;
  const { results } = await env.DB.prepare(
    'SELECT text FROM commentary WHERE date = ? AND slot = ? ORDER BY id DESC LIMIT ?').bind(date, slot, SHOW).all();
  let text = null;
  if (env.ANTHROPIC_API_KEY) {
    try {
      text = await claudeLine(env, event, results.map((r) => r.text).reverse());
    } catch (e) {
      if (e instanceof Anthropic.AuthenticationError) console.error('commentary: the ANTHROPIC_API_KEY secret is not valid');
      else if (e instanceof Anthropic.RateLimitError) console.error('commentary: rate limited');
      else if (e instanceof Anthropic.APIError) console.error('commentary: API error', e.status, e.message);
      else console.error('commentary:', e);
    }
  }
  await env.DB.prepare('INSERT INTO commentary (date, slot, created, kind, steam_id, text) VALUES (?, ?, ?, ?, ?, ?)')
    .bind(date, slot, Date.now(), event.kind, steamId, text || templateLine(event)).run();
}

/** Admin check: the line Claude would write for an event, nothing stored. -> {text, by: 'claude' | 'template', error} */
export async function previewLine(env, event) {
  if (!env.ANTHROPIC_API_KEY) return { text: templateLine(event), by: 'template', error: 'ANTHROPIC_API_KEY is not set' };
  try {
    const text = await claudeLine(env, event, []);
    return text ? { text, by: 'claude' } : { text: templateLine(event), by: 'template', error: 'refused or empty' };
  } catch (e) {
    return { text: templateLine(event), by: 'template', error: e instanceof Anthropic.APIError ? `${e.status} ${e.message}` : String(e) };
  }
}

export async function recentLines(env, date, slot) {
  const { results } = await env.DB.prepare(
    'SELECT text, kind, created FROM commentary WHERE date = ? AND slot = ? ORDER BY id DESC LIMIT ?').bind(date, slot, SHOW).all();
  return results;
}

export { fmt as fmtMs, gap as fmtGap };
