// A league's own Discord posts: its owner pastes a webhook of one of their channels (league settings), and the server
// posts there when an event opens, when it has 24 hours left and its results once it has closed. The cron (every
// minute, leaguesapi.js leagueDiscordTick) decides what is due; this file only builds the messages. Nothing ever
// mentions anyone, and names are shown as plain text.

import { clean, flag, fmt, footer, identity } from './discord.js';
import { describeSeason, LIMITS } from './leagues.js';

const RED = 0xE30613, GREEN = 0x30D158, AMBER = 0xFF9F0A;
const H = 3600000;
export const SHOW = 10;          // drivers listed in a post

/** What is due for an event (a row of league_events, its posted_* columns set once done): -> {post: kind or null,
 *  mark: [kinds]} — one post at a time, the most recent news first; `mark` also closes what has gone by unposted
 *  (no "open" post after the results, no reminder for an event open less than 30 hours). */
export function duePosts(ev, now) {
  if (!ev.posted_results && now >= ev.closes + LIMITS.graceMs) return { post: 'results', mark: ['results', 'open', '24h'] };
  if (now >= ev.closes) return { post: null, mark: [] };      // closed: the results wait for the late stages
  const reminder = !ev.posted_24h && now >= ev.closes - 24 * H;
  if (!ev.posted_open && now >= ev.opens) return { post: 'open', mark: reminder ? ['open', '24h'] : ['open'] };
  if (reminder) return ev.closes - ev.opens >= 30 * H ? { post: '24h', mark: ['24h'] } : { post: null, mark: ['24h'] };
  return { post: null, mark: [] };
}

const ts = (ms, style) => `<t:${Math.floor(ms / 1000)}:${style}>`;    // Discord shows it in each reader's own time
const km = (m) => `${(m / 1000).toFixed(1)} km`;
const link = (site, path) => (site ? `${site}${path}` : undefined);
const author = (lg, site) => ({ name: clean(lg.name).slice(0, 60) || 'League', url: link(site, `/l/${lg.id}`) });
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

/** ev: eventOut() of src/leaguesapi.js (+ season {name} or null); lg: {id, name}. */
function facts(ev) {
  const car = ev.car || `${ev.carClass} class (each driver picks a car)`;
  return `${ev.rally} · ${plural(ev.stages.length, 'stage', 'stages')} over ${plural(ev.days, 'day', 'days')} · ${km(ev.lengthM)}\n${car}`;
}

export function openMessage(ev, lg, site) {
  return {
    ...identity(site),
    embeds: [{
      author: author(lg, site), color: GREEN, url: link(site, `/e/${ev.id}`),
      title: `${clean(ev.name)} is open`.slice(0, 250),
      description: `${facts(ev)}\nCloses ${ts(ev.closes, 'F')} (${ts(ev.closes, 'R')}).` +
        `\nOne go each: start it from the LEAGUES view of the ACR Daily app.`,
      fields: ev.season ? [{ name: 'Season', value: clean(ev.season.name).slice(0, 100) || '–', inline: true }] : [],
      footer: footer(site, 'ACR Daily leagues'),
    }],
  };
}

export function reminderMessage(ev, lg, site, rows) {
  const fin = rows.filter((r) => r.status === 'finished').length;
  const going = rows.filter((r) => r.status === 'running').length;
  return {
    ...identity(site),
    embeds: [{
      author: author(lg, site), color: AMBER, url: link(site, `/e/${ev.id}`),
      title: `24 hours left: ${clean(ev.name)}`.slice(0, 250),
      description: `Closes ${ts(ev.closes, 'F')} (${ts(ev.closes, 'R')}).\n` +
        (rows.length ? `${plural(fin, 'driver has', 'drivers have')} finished, ${going} still on the way.` : 'Nobody has started yet.') +
        '\nNot driven it yet? There is still time.',
      footer: footer(site, 'ACR Daily leagues'),
    }],
  };
}

/** The final results (top SHOW), the Power Stage when the season has one, and the season's top five after it.
 *  rows: eventStandings().rows; stages: eventStandings().stages; season: {name, power, ...} or null; table: its
 *  seasonStandings() or null. */
export function resultsMessage(ev, lg, site, rows, stages, season, table) {
  const fin = rows.filter((r) => r.status === 'finished');
  const lines = fin.slice(0, SHOW).map((r) => `\`${String(r.rank).padStart(2)}\` ${flag(r.country)}**${clean(r.name)}**  ` +
    `${r.rank === 1 ? fmt(r.totalMs) : `+${((r.gapMs) / 1000).toFixed(3)}`}`);
  if (fin.length > SHOW) lines.push(`…and ${fin.length - SHOW} more`);
  const out = rows.filter((r) => r.status === 'dnf' || r.status === 'dsq');
  const fields = [];
  if (out.length) fields.push({ name: 'Out', value: out.slice(0, 8).map((r) => `${clean(r.name)} (${r.status.toUpperCase()})`).join(', ').slice(0, 1000) });
  const last = stages[stages.length - 1] || [];
  if (season && season.power && season.power.length && last.length) {
    fields.push({ name: 'Power Stage', value: last.slice(0, Math.min(3, season.power.length))
      .map((x) => `${x.pos}. ${clean(x.name)} (+${season.power[x.pos - 1] || 0})`).join('\n') });
  }
  if (season && table && table.length) {
    fields.push({ name: `${clean(season.name)} after this round`.slice(0, 250), value: table.slice(0, 5)
      .map((p) => `${p.rank}. ${flag(p.country)}${clean(p.name)}: ${p.points}`).join('\n').slice(0, 1000) });
  }
  return {
    ...identity(site),
    embeds: [{
      author: author(lg, site), color: RED, url: link(site, `/e/${ev.id}`),
      title: `Results: ${clean(ev.name)}`.slice(0, 250),
      description: (lines.length ? lines.join('\n') : 'Nobody finished.').slice(0, 4000),
      fields, footer: footer(site, season ? describeSeason(season).slice(0, 200) : 'ACR Daily leagues'),
    }],
  };
}

export function testMessage(lg, site) {
  return {
    ...identity(site),
    embeds: [{
      author: author(lg, site), color: RED, title: 'ACR Daily is connected',
      description: 'This channel now gets the league\'s news: each event when it opens, when it has 24 hours left, and its results.',
      footer: footer(site, 'ACR Daily leagues'),
    }],
  };
}
