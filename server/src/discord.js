// The ACR Daily bot on Discord: a webhook in the server's #live-timing channel (secret DISCORD_WEBHOOK_URL).
// Every minute (cron) it keeps one message up to date with who is on stage right now and today's two timing
// sheets, editing it only when something changed. Once a day is over and settled (01:05 UTC) it posts that day's
// final results and the hall of fame, then the live board again below them, so the channel reads as a history
// with the live board at the bottom. index.js discordTick() decides what to send.

const ACR_RED = 0xE30613, RED = 0xE10600, GREY = 0x2B2B31, WHITE = 0xF4F4F5;
export const SHOW = 10;          // drivers listed per timing sheet

/** Who the posts come from: "ACR Daily" with the logo (served by the website) as the avatar. */
const identity = (site) => (site ? { username: 'ACR Daily', avatar_url: `${site}/brand/acr-daily-icon-512.png` } : { username: 'ACR Daily' });
const footer = (site, text) => (site ? { text, icon_url: `${site}/brand/acr-daily-icon-512.png` } : { text });

const fmt = (ms) => {
  if (ms == null) return '–';
  const m = Math.floor(ms / 60000), s = (ms % 60000) / 1000;
  return `${m}:${s < 10 ? '0' : ''}${s.toFixed(3)}`;
};
const gap = (ms) => `+${(ms / 1000).toFixed(3)}`;
/** A board entry's penalty in seconds: its total - its stage clock. */
const penaltyS = (e) => (e.totalMs != null && e.clockMs != null ? Math.round((e.totalMs - e.clockMs) / 1000) : 0);
const dayLabel = (date) => new Date(date + 'T00:00:00Z').toLocaleDateString('en-GB',
  { weekday: 'short', day: '2-digit', month: 'short', timeZone: 'UTC' });
// names are shown as plain text: no markdown or mentions from a Steam name
const clean = (s) => String(s || '?').replace(/[\\*_~`|>#@\[\]()]/g, '').slice(0, 32) || '?';

/** 'fi' -> 🇫🇮 (regional indicator letters); '' without a country. */
export function flag(code) {
  if (!/^[a-z]{2}$/i.test(code || '')) return '';
  return String.fromCodePoint(...[...code.toUpperCase()].map((c) => 0x1F1E6 + c.charCodeAt(0) - 65)) + ' ';
}

/** A daily's heading: "SS1 · Forêt de Saverne" and "Hyundai i20 N Rally2 · Light fog · Midday (12:00)". */
function heading(st) {
  const h = st.head || {};
  return {
    title: `SS${st.slot} · ${h.menuName || h.track || '?'}`,
    sub: [h.car, h.weatherLabel, h.timeLabel].filter(Boolean).join(' · '),
  };
}

/** The timing sheet lines of a daily's board entries (finishers, then how many DNF'd). */
export function sheetLines(entries, show = SHOW) {
  const fin = (entries || []).filter((e) => e.status === 'finished');
  const dnf = (entries || []).filter((e) => e.status === 'dnf').length;
  if (!fin.length && !dnf) return ['No times yet.'];
  const lines = fin.slice(0, show).map((e) => {
    const pen = penaltyS(e) > 0 ? `  (+${penaltyS(e)} s)` : '';
    return `\`${String(e.rank).padStart(2)}\` ${flag(e.country)}**${clean(e.name)}**  \`${fmt(e.totalMs)}\`` +
      (e.rank > 1 ? `  ${gap(e.gapMs)}` : '') + pen;
  });
  const more = [fin.length > show ? `${fin.length - show} more` : '', dnf ? `${dnf} DNF` : ''].filter(Boolean);
  if (more.length) lines.push(`*${more.join(' · ')}*`);
  return lines;
}

/** The live board: who is on stage right now, then today's timing sheets. stages: [{slot, head, board, live}] */
export function boardMessage({ date, stages, site }) {
  const onStage = [];
  for (const st of stages) {
    for (const d of (st.live || []).filter((x) => x.state === 'live')) {
      // (the stage clock: the game's penalties come with its official time at the finish)
      onStage.push(`🔴 SS${st.slot}  ${flag(d.country)}**${clean(d.name)}**  ${Math.round((d.progress || 0) * 100)} %  \`${fmt(d.totalMs)}\``);
    }
  }
  const live = {
    title: onStage.length ? `LIVE · ${onStage.length} on stage` : 'LIVE · nobody on stage',
    color: onStage.length ? RED : GREY,
    description: onStage.length ? onStage.join('\n') : 'Drivers appear here while they are on stage.',
  };
  const sheets = stages.map((st) => {
    const h = heading(st);
    return { title: h.title, url: site ? `${site}/stage/${date}/${st.slot}` : undefined, color: ACR_RED,
      description: [h.sub && `*${h.sub}*`, ...sheetLines(st.board)].filter(Boolean).join('\n') };
  });
  return {
    content: `**Today · ${dayLabel(date)}**` + (site ? `  ·  <${site}>` : ''),
    embeds: [live, ...sheets].map((e) => ({ ...e, footer: footer(site, 'ACR Daily · updated every minute') })),
    ...identity(site),
  };
}

/** The wrap-up of a finished day: final results of both stages and the hall of fame. */
export function dayMessage({ date, stages, week, site }) {
  const embeds = stages.filter((st) => (st.board || []).length).map((st) => {
    const h = heading(st);
    const win = (st.board || []).find((e) => e.rank === 1);
    return { title: `${h.title} · final`, url: site ? `${site}/stage/${date}/${st.slot}` : undefined, color: ACR_RED,
      description: [h.sub && `*${h.sub}*`, win ? `🏆 ${flag(win.country)}**${clean(win.name)}**` : null,
        ...sheetLines(st.board)].filter(Boolean).join('\n') };
  });
  const hof = ((week && week.standings) || []).filter((p) => p.total > 0).slice(0, 5);
  if (hof.length) {
    embeds.push({ title: `Hall of fame · week ${week.week}`, url: site ? `${site}/week` : undefined, color: WHITE,
      description: hof.map((p) => `\`${String(p.rank).padStart(2)}\` ${flag(p.country)}**${clean(p.name)}**  ${p.total} pts` +
        (p.wins ? `  ·  ${p.wins} win${p.wins > 1 ? 's' : ''}` : '')).join('\n') });
  }
  return { content: `**${dayLabel(date)} · results**`, embeds: embeds.map((e) => ({ ...e, footer: footer(site, 'ACR Daily') })),
    ...identity(site) };
}

// ------------------------------------------------------------------ the webhook

const WEBHOOK_RE = /^https:\/\/(?:canary\.|ptb\.)?discord(?:app)?\.com\/api\/webhooks\/\d+\/[\w-]+$/;
const LOCAL_RE = /^http:\/\/127\.0\.0\.1:\d+\/api\/webhooks\/\d+\/[\w-]+$/;   // a stand-in for tests (local server only)

/** Calls on the webhook: post (-> message id), edit, remove. Each returns {ok, status, id?}; a 404 on edit means
 *  the message is gone (someone deleted it). Nothing ever mentions anyone. */
export function webhook(url, fetchFn = fetch, allowLocal = false) {
  if (!WEBHOOK_RE.test(url || '') && !(allowLocal && LOCAL_RE.test(url || ''))) return null;
  const call = async (method, path, body) => {
    let res;
    try {
      res = await fetchFn(url + path, {
        method,
        headers: { 'Content-Type': 'application/json', 'User-Agent': 'DiscordBot (https://github.com/khanhonthetrack/acr-daily, 1.0)' },
        body: body ? JSON.stringify({ ...body, allowed_mentions: { parse: [] } }) : undefined,
      });
    } catch {
      return { ok: false, status: 0, id: null, data: null };   // Discord not reachable: the next minute tries again
    }
    let data = null;
    try { data = res.status === 204 ? null : await res.json(); } catch { data = null; }
    return { ok: res.ok, status: res.status, id: data && data.id ? String(data.id) : null, data };
  };
  return {
    post: (msg) => call('POST', '?wait=true', msg),
    edit: (id, { username, avatar_url, ...msg }) => call('PATCH', `/messages/${id}`, msg),   // the sender is set when posting
    remove: (id) => call('DELETE', `/messages/${id}`),
  };
}
