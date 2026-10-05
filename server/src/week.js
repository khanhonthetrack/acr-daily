// Weekly hall of fame: Monday 00:00 UTC to Sunday, 7 days x 2 dailies = 14 stages. Each stage gives points
// (WRC scale for the top 10, 1 point for every other finisher, DNF 0); the week's total decides the order.

export const POINTS = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1];
export const pointsFor = (rank) => (rank == null ? 0 : rank <= POINTS.length ? POINTS[rank - 1] : 1);

/** Monday (UTC) of the week the date is in, as YYYY-MM-DD. */
export function weekStart(date) {
  const d = new Date(date + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
  return d.toISOString().slice(0, 10);
}

export function weekDays(start) {
  const out = [];
  for (let i = 0; i < 7; i++) {
    const d = new Date(start + 'T00:00:00Z');
    d.setUTCDate(d.getUTCDate() + i);
    out.push(d.toISOString().slice(0, 10));
  }
  return out;
}

/** ISO week number, for the page title. */
export function isoWeek(start) {
  const d = new Date(start + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() + 3);   // the week's Thursday
  const jan4 = new Date(Date.UTC(d.getUTCFullYear(), 0, 4));
  return 1 + Math.round(((d - jan4) / 86400000 - 3 + ((jan4.getUTCDay() + 6) % 7)) / 7);
}

/**
 * stages: [{date, slot, stageName, car, board: leaderboard entries | null (future)}]
 * -> standings sorted by total (then wins, then stages scored)
 */
export function weekStandings(stages) {
  const players = new Map();
  for (const st of stages) {
    if (!st.board) continue;
    for (const e of st.board) {
      if (!players.has(e.steamId)) {
        players.set(e.steamId, { steamId: e.steamId, name: e.name, country: e.country, total: 0, wins: 0, scored: 0, cells: {} });
      }
      const p = players.get(e.steamId);
      const dnf = e.status === 'dnf';
      const pts = dnf ? 0 : pointsFor(e.rank);
      p.cells[st.date + '/' + st.slot] = { pos: dnf ? null : e.rank, pts, dnf, runId: e.runId };
      p.total += pts;
      if (!dnf) p.scored++;
      if (e.rank === 1) p.wins++;
      if (e.country) p.country = e.country;
    }
  }
  const list = [...players.values()].sort((a, b) => b.total - a.total || b.wins - a.wins || b.scored - a.scored || a.name.localeCompare(b.name));
  let rank = 0, prev = null;
  list.forEach((p, i) => {
    const key = p.total + '|' + p.wins + '|' + p.scored;
    if (key !== prev) rank = i + 1;
    p.rank = rank;
    prev = key;
  });
  return list;
}
