// Discord server Events for the two dailies: every day the bot creates "SS1 · <stage>" and "SS2 · <stage>" (car,
// conditions, length, link; the logo as the cover), starts them so they show as live all day, and ends them when the
// day is over. Needs a bot account (secret DISCORD_BOT_TOKEN) in the server with the Create Events permission, and
// DISCORD_GUILD_ID. Webhooks cannot make events. Run from the Discord bot's minute (index.js discordTick).

const API = 'https://discord.com/api/v10';
const START_AFTER_MS = 90 * 1000;   // an event must start in the future: created at 00:00, live from 00:01:30

/** The event for one daily. head: {slot, menuName, car, weatherLabel, timeLabel, lengthM, rally, surface}. */
export function eventPayload(head, date, site, imageDataUri, now) {
  const dayEnd = Date.parse(date + 'T00:00:00Z') + 86400000;
  const km = head.lengthM ? `${(head.lengthM / 1000).toFixed(1)} km` : null;
  const where = [head.rally, head.surface, km].filter(Boolean).join(' · ');
  const lines = [
    where && `${where}`,
    `Car: ${head.car}`,
    [head.weatherLabel, head.timeLabel].filter(Boolean).length ? `Conditions: ${[head.weatherLabel, head.timeLabel].filter(Boolean).join(', ')}` : null,
    'Your first run of the day counts. The ACR Daily app sets the stage up for you (DRIVE).',
    site ? `Timing sheet and live map: ${site}` : null,
  ].filter(Boolean);
  const body = {
    name: `SS${head.slot} · ${head.menuName || head.track}`.slice(0, 100),
    description: lines.join('\n').slice(0, 1000),
    privacy_level: 2,                    // guild only
    entity_type: 3,                      // external: somewhere else (the game)
    entity_metadata: { location: (site || 'Assetto Corsa Rally').slice(0, 100) },
    scheduled_start_time: new Date(now + START_AFTER_MS).toISOString(),
    scheduled_end_time: new Date(dayEnd - 60000).toISOString(),
  };
  if (imageDataUri) body.image = imageDataUri;
  return body;
}

/** Discord's API as the bot: create / update / delete a scheduled event. Each returns {ok, status, id}. */
export function eventsApi(token, guildId, fetchFn = fetch) {
  if (!/^[\w.-]{20,}$/.test(token || '') || !/^\d{17,20}$/.test(guildId || '')) return null;
  const call = async (method, path, body) => {
    let res;
    try {
      res = await fetchFn(`${API}/guilds/${guildId}/scheduled-events${path}`, {
        method,
        headers: { Authorization: `Bot ${token}`, 'Content-Type': 'application/json',
          'User-Agent': 'DiscordBot (https://github.com/khanhonthetrack/acr-daily, 1.0)' },
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch {
      return { ok: false, status: 0, id: null };
    }
    let data = null;
    try { data = res.status === 204 ? null : await res.json(); } catch { data = null; }
    return { ok: res.ok, status: res.status, id: data && data.id ? String(data.id) : null };
  };
  return {
    create: (body) => call('POST', '', body),
    status: (id, status) => call('PATCH', `/${id}`, { status }),   // 2 active, 3 completed, 4 cancelled
    remove: (id) => call('DELETE', `/${id}`),
  };
}

/**
 * One minute of the events: today's two are created, then started; yesterday's are ended.
 * store: {get(key) -> {id, hash, updated}|null, set(key, id, state, date)}; heads(date) -> the dailies' headings.
 * State per event: created -> live -> done ('gone' when someone deleted it: it is not made again).
 */
export async function syncEvents({ api, store, heads, site, image, now }) {
  const out = {};
  const day = (ms) => new Date(ms).toISOString().slice(0, 10);
  const today = day(now), yday = day(now - 86400000);
  for (const h of await heads(yday)) {          // yesterday's: end them
    const key = `event:${yday}/${h.slot}`, rec = await store.get(key);
    if (!rec || !rec.id || rec.hash === 'done' || rec.hash === 'gone') continue;
    // a live event is completed; one that never went live can only be cancelled
    const r = await api.status(rec.id, rec.hash === 'live' ? 3 : 4);
    if (r.ok || r.status === 404) await store.set(key, rec.id, r.ok ? 'done' : 'gone', yday);
    out[key] = r.ok ? 'ended' : r.status === 404 ? 'gone' : `error ${r.status}`;
  }
  for (const h of await heads(today)) {
    const key = `event:${today}/${h.slot}`, rec = await store.get(key);
    if (!rec) {
      const r = await api.create(eventPayload(h, today, site, image, now));
      if (r.ok && r.id) await store.set(key, r.id, 'created', today);
      out[key] = r.ok ? 'created' : `error ${r.status}`;
    } else if (rec.hash === 'created' && now - rec.updated >= START_AFTER_MS) {
      const r = await api.status(rec.id, 2);
      if (r.ok || r.status === 404) await store.set(key, rec.id, r.ok ? 'live' : 'gone', today);
      out[key] = r.ok ? 'live' : r.status === 404 ? 'gone' : `error ${r.status}`;
    }
  }
  return out;
}
