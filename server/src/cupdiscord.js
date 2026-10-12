// ACR Daily's own cups on Discord: the bot posts when an official cup opens for entries, a day before it starts, when
// each round opens (with its stages, drawn), a day before a round closes, and the results. Into the channel of the
// webhook DISCORD_CUPS_WEBHOOK_URL (a secret; say #cups), else the bot's own (#live-timing: its live board then moves
// below the post). The cron (index.js) runs cupDiscordTick every 10 minutes: one post a run at most, the most recent
// news first; what went by unposted is marked done too (no "sign-ups open" once the cup has started). What has been
// posted: rows of the discord table, 'cup:<id>:open' | 'start24h' | 'r<n>' | 'r<n>:24h' | 'done'. Drivers' cups
// are not posted. Nothing mentions anyone; names are plain text.

import { clean, flag, footer, identity, tagText, webhook } from './discord.js';
import { stageParts } from './conditions.js';
import { bannerUrl } from './leagues.js';
import { prizeGroups, roundLength, roundName } from './cups.js';

const YELLOW = 0xFFD60A, AMBER = 0xFF9F0A, RED = 0xE30613;
const H = 3600000;
const ts = (ms, style) => `<t:${Math.floor(ms / 1000)}:${style}>`;   // Discord shows it in each reader's own time
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
// a cup's name as it is (ACR Daily's own: its brackets kept), less what Discord would read as markdown or a mention
const cupName = (s) => String(s || 'Cup').replace(/[\\*_~`|>#@[\]]/g, '').slice(0, 100);
const num = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');   // (no Intl: the cron's runs start cold)

/** What is due for a cup (a row: status, starts, round, closes of its round, round_hours, posted: [kinds]) at `now`.
 *  -> {post: kind or null, mark: [kinds]}. */
export function duePost(c, now) {
  const has = (k) => c.posted.includes(k);
  if (c.status === 'finished') return has('done') ? { post: null, mark: [] } : { post: 'done', mark: ['done'] };
  if (c.status === 'running') {
    const r = `r${c.round}`, soon = c.closes && c.closes - now <= 24 * H && now < c.closes;
    const early = ['open', 'start24h'].filter((k) => !has(k));
    if (!has(r)) return { post: 'round', mark: [...early, r, ...(soon ? [`${r}:24h`] : [])] };
    if (!has(`${r}:24h`) && soon) return c.round_hours >= 30 ? { post: 'round24h', mark: [`${r}:24h`] } : { post: null, mark: [`${r}:24h`] };
    return { post: null, mark: early };
  }
  if (c.status !== 'open') return { post: null, mark: [] };
  const soon = c.starts - now <= 24 * H;
  if (!has('open')) return { post: 'open', mark: soon ? ['open', 'start24h'] : ['open'] };
  if (!has('start24h') && soon) return { post: 'start24h', mark: ['start24h'] };
  return { post: null, mark: [] };
}

const link = (site, c) => (site ? `${site}/cup/${c.id}` : undefined);
const author = (site, c) => ({ name: 'ACR Daily · Official cup', url: link(site, c) });
/** What every match races: "Monte Carlo · 3 stages, a new draw each round · Rally2/R5 class". */
const raced = (spec) => `${spec.rally} · ${plural(spec.stages.length, 'stage', 'stages')}${spec.draw ? ', a new draw each round' : ''} · ` +
  `${spec.car || `${spec.car_class} class`}`;
const shared = (split) => (split.length === 1 ? 'winner takes all'
  : prizeGroups(split).map((g) => `${g.places} ${g.pct}%${g.each ? ' each' : ''}`).join(', '));

/** Sign-ups are open. c: the cup's row (+ banner, entrants). */
export function openMessage(c, site) {
  const spec = JSON.parse(c.spec), split = JSON.parse(c.split);
  const lines = [
    c.about ? String(c.about).replace(/[@`]/g, '').slice(0, 700) : null,
    '',
    `**Starts** ${ts(c.starts, 'F')} (${ts(c.starts, 'R')})`,
    `**Every match** ${raced(spec)}`,
    `**Rounds** ${roundLength(c.round_hours)} each, a knockout of 1V1s seeded by driver rating`,
    c.prize ? `**Prize** ${num(c.prize)} credits from ACR Daily (${shared(split)})` : null,
    `**Entry** ${c.fee ? `${num(c.fee)} credits` : 'free'} · ${c.size} drivers at most`,
    '',
    'Join on the cup\'s page, or in the ACR Daily app under CUPS.',
  ].filter((x) => x !== null);
  const banner = bannerUrl(c.id, c.banner);
  return {
    ...identity(site),
    embeds: [{
      author: author(site, c), color: YELLOW, url: link(site, c), title: `${cupName(c.name)}: sign-ups are open`.slice(0, 250),
      description: lines.join('\n').slice(0, 4000),
      ...(banner && site ? { image: { url: `${site}${banner}` } } : {}),
      footer: footer(site, 'ACR Daily cups'),
    }],
  };
}

export function startMessage(c, site) {
  const room = c.size - c.entrants;
  return {
    ...identity(site),
    embeds: [{
      author: author(site, c), color: YELLOW, url: link(site, c), title: `${cupName(c.name)} starts in 24 hours`.slice(0, 250),
      description: `${plural(c.entrants, 'driver is', 'drivers are')} in${room > 0 ? `, room for ${room} more` : ': it is full'}. ` +
        `Sign-ups close at the start, ${ts(c.starts, 'F')} (${ts(c.starts, 'R')}); then the draw is made.` +
        (room > 0 ? '\nJoin on the cup\'s page, or in the ACR Daily app under CUPS.' : ''),
      footer: footer(site, 'ACR Daily cups'),
    }],
  };
}

const SHOW = 12;                 // matches listed in a round's post

/** A round is open. matches: [{a, b, a_name, a_country, a_tag, b_name, b_country, b_tag}] of the round; stages: its event's (the
 *  draw), or null. */
export function roundMessage(c, site, rounds, matches, stages) {
  const games = matches.filter((m) => m.a && m.b), byes = matches.length - games.length;
  const who = (n, cc, tag) => `${flag(cc)}${tagText({ team: { tag } })}${clean(n)}`;
  const lines = [
    `${plural(games.length, 'match', 'matches')}${byes ? `, ${plural(byes, 'bye', 'byes')}` : ''}.` +
      (stages ? ` **The stages:** ${stages.map((s) => stageParts(s.track).stageName).join(', ')}.` : ''),
    `Drive your match in the ACR Daily app, under CUPS, by ${ts(c.closes, 'F')} (${ts(c.closes, 'R')}).`,
    '',
    ...games.slice(0, SHOW).map((m) => `${who(m.a_name, m.a_country, m.a_tag)} vs ${who(m.b_name, m.b_country, m.b_tag)}`),
    games.length > SHOW ? `…and ${games.length - SHOW} more on the cup's page` : null,
  ].filter((x) => x !== null);
  return {
    ...identity(site),
    embeds: [{
      author: author(site, c), color: YELLOW, url: link(site, c), title: `${cupName(c.name)}: the ${roundName(c.round, rounds).toLowerCase()} is open`.slice(0, 250),
      description: lines.join('\n').slice(0, 4000), footer: footer(site, 'ACR Daily cups'),
    }],
  };
}

/** A day left in the round. drivers: in its matches; finished: those who have finished theirs. */
export function round24hMessage(c, site, rounds, drivers, finished) {
  return {
    ...identity(site),
    embeds: [{
      author: author(site, c), color: AMBER, url: link(site, c),
      title: `24 hours left in the ${roundName(c.round, rounds).toLowerCase()} of ${cupName(c.name)}`.slice(0, 250),
      description: `${finished} of ${drivers} drivers have driven their match. The round closes ${ts(c.closes, 'F')} (${ts(c.closes, 'R')}).` +
        '\nNot driven yours yet? There is still time: the ACR Daily app, under CUPS.',
      footer: footer(site, 'ACR Daily cups'),
    }],
  };
}

/** The results. top: [{place, name, country, won}] (places 1 to 3). */
export function doneMessage(c, site, top) {
  const w = top.find((p) => p.place === 1);
  const line = (p) => `${flag(p.country)}**${tagText(p)}${clean(p.name)}**${p.won ? ` · ${num(p.won)} credits` : ''}`;
  const lines = [1, 2, 3].map((k) => {
    const at = top.filter((p) => p.place === k);
    return at.length ? `\`${k}\` ${at.map(line).join(', ')}` : null;
  }).filter(Boolean);
  return {
    ...identity(site),
    embeds: [{
      author: author(site, c), color: RED, url: link(site, c),
      title: (w ? `${tagText(w)}${clean(w.name)} wins ${cupName(c.name)}` : `${cupName(c.name)} is over`).slice(0, 250),
      description: (lines.join('\n') || 'No places.').slice(0, 4000) + '\n\nThe whole bracket is on the cup\'s page.',
      footer: footer(site, 'ACR Daily cups'),
    }],
  };
}

/** The cron's part (every 10 minutes): one post at most. -> {posted, cup} | {skipped} | {error} | {} */
export async function cupDiscordTick(env, now, fetchFn = fetch) {
  const url = env.DISCORD_CUPS_WEBHOOK_URL || env.DISCORD_WEBHOOK_URL;
  const hook = webhook(url, fetchFn, env.DEV_LOGIN === '1');
  if (!hook) return { skipped: 'no Discord webhook for the cups' };
  const site = (env.SITE_URL || '').replace(/\/+$/, '');
  const { results } = await env.DB.prepare(`SELECT c.*, h.banner,
      (SELECT COUNT(*) FROM cup_entries e WHERE e.cup_id = c.id) AS entrants,
      (SELECT COUNT(*) FROM cup_matches x WHERE x.cup_id = c.id AND x.round = 1) AS r1,
      (SELECT MAX(e.closes) FROM cup_matches m JOIN league_events e ON e.id = m.event_id WHERE m.cup_id = c.id AND m.round = c.round) AS closes,
      (SELECT json_group_array(substr(d.key, 14)) FROM discord d WHERE d.key LIKE 'cup:' || c.id || ':%') AS posted
    FROM cups c LEFT JOIN leagues h ON h.id = c.id
    WHERE c.official = 1 AND (c.status IN ('open', 'running') OR (c.status = 'finished' AND c.settled > ?)) ORDER BY c.starts`)
    .bind(now - 3 * 86400000).all();
  for (const c of results) {
    c.posted = JSON.parse(c.posted || '[]');
    const due = duePost(c, now);
    if (!due.mark.length) continue;
    const rounds = c.r1 ? Math.log2(2 * c.r1) : 0;
    let msg = null;
    if (due.post === 'open') msg = openMessage(c, site);
    else if (due.post === 'start24h') msg = startMessage(c, site);
    else if (due.post === 'round') {
      const [{ results: ms }, ev] = await env.DB.batch([
        env.DB.prepare(`SELECT m.a, m.b, pa.name AS a_name, pa.country AS a_country, pb.name AS b_name, pb.country AS b_country,
            (SELECT t.tag FROM team_members tm JOIN teams t ON t.id = tm.team_id WHERE tm.steam_id = m.a) AS a_tag,
            (SELECT t.tag FROM team_members tm JOIN teams t ON t.id = tm.team_id WHERE tm.steam_id = m.b) AS b_tag
          FROM cup_matches m LEFT JOIN players pa ON pa.steam_id = m.a LEFT JOIN players pb ON pb.steam_id = m.b
          WHERE m.cup_id = ? AND m.round = ? ORDER BY m.slot`).bind(c.id, c.round),
        env.DB.prepare(`SELECT e.stages FROM cup_matches m JOIN league_events e ON e.id = m.event_id
          WHERE m.cup_id = ? AND m.round = ? LIMIT 1`).bind(c.id, c.round),
      ]);
      const stages = JSON.parse(c.spec).draw && ev.results[0] ? JSON.parse(ev.results[0].stages) : null;
      msg = roundMessage(c, site, rounds, ms, stages);
    } else if (due.post === 'round24h') {
      const n = await env.DB.prepare(`SELECT
          (SELECT COUNT(*) FROM cup_matches m WHERE m.cup_id = ?1 AND m.round = ?2 AND m.a IS NOT NULL AND m.b IS NOT NULL) AS games,
          (SELECT COUNT(*) FROM league_entries le JOIN cup_matches m ON m.event_id = le.event_id
            WHERE m.cup_id = ?1 AND m.round = ?2 AND le.status = 'finished') AS fin`).bind(c.id, c.round).first();
      msg = round24hMessage(c, site, rounds, 2 * n.games, n.fin);
    } else if (due.post === 'done') {
      const { results: top } = await env.DB.prepare(`SELECT e.place, p.name, p.country, t.tag AS team_tag,
          (SELECT SUM(l.delta) FROM credit_ledger l WHERE l.steam_id = e.steam_id AND l.kind = 'cup-prize' AND l.ref = 'cup:' || e.cup_id) AS won
        FROM cup_entries e JOIN players p ON p.steam_id = e.steam_id LEFT JOIN team_members tm ON tm.steam_id = e.steam_id
        LEFT JOIN teams t ON t.id = tm.team_id WHERE e.cup_id = ? AND e.place <= 3 ORDER BY e.place`).bind(c.id).all();
      msg = doneMessage(c, site, top.map((p) => ({ ...p, team: p.team_tag ? { tag: p.team_tag } : null })));
    }
    let id = null;
    if (msg) {
      const r = await hook.post(msg);
      if (!r.ok) return { error: `posting ${c.id} ${due.post}: Discord answered ${r.status}` };
      id = r.id;
    }
    await env.DB.batch([
      ...due.mark.map((k) => env.DB.prepare(`INSERT OR IGNORE INTO discord (key, message_id, hash, date, updated) VALUES (?, ?, NULL, NULL, ?)`)
        .bind(`cup:${c.id}:${k}`, id, now)),
      // in the live board's channel: the board moves below the post (src/index.js discordTick, on its next run)
      ...(msg && !env.DISCORD_CUPS_WEBHOOK_URL ? [env.DB.prepare("UPDATE discord SET date = '' WHERE key = 'board'")] : []),
    ]);
    if (msg) return { posted: due.post, cup: c.id };
  }
  return {};
}
