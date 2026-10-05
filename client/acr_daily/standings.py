"""Where you stand against today's field at a split or at the finish (RallySimFans style)."""


def standing(entries, me_steam_id, my_ms, split=None, rows=4):
    """entries: leaderboard entries (each with 'splits' and 'totalMs'); split: split index, or None = finish.
    Compares against every other driver's best run (your own earlier best is reported separately).
    Returns {pos, of, gapLeader, rows: [(pos, name, gapToLeaderMs, isMe)], pbGap} or None without a field."""
    field, mine_before = [], None
    for e in entries or []:
        t = e.get('totalMs') if split is None else ((e.get('splits') or [None] * (split + 1))[split]
                                                     if e.get('splits') and len(e['splits']) > split else None)
        if t is None:
            continue
        if e.get('steamId') == me_steam_id:
            mine_before = t
            continue
        field.append((t, e.get('name') or '?'))
    field.sort()
    table = sorted(field + [(my_ms, None)], key=lambda r: (r[0], r[1] is None))   # ties: you after them
    pos = next(i for i, r in enumerate(table) if r[1] is None) + 1
    leader = table[0][0]
    # rows to show: the leader, the driver ahead of you, you, the driver behind you
    want = sorted({0, max(0, pos - 2), pos - 1, min(len(table) - 1, pos)})
    while len(want) < min(rows, len(table)):   # fill up from the top when the list is short
        extra = next(i for i in range(len(table)) if i not in want)
        want = sorted(set(want) | {extra})
    out = [(i + 1, table[i][1] or 'YOU', table[i][0] - leader, table[i][1] is None) for i in want[:rows]]
    return {
        'pos': pos, 'of': len(table), 'gapLeader': my_ms - leader, 'rows': out,
        'pbGap': None if mine_before is None else my_ms - mine_before,
    }
