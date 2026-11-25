"""community_routes.py's routes -> a server migration that adds them (kept if a route is there already; marked
game-files, so the first clean driven run replaces them): python community_routes_sql.py <routes.json> <out.sql>
<stage id>=<track> [...] (the track as the game's telemetry reports it: its location, then its track)."""
import json
import math
import sys

routes = {r['stageId']: r for r in json.load(open(sys.argv[1], encoding='utf-8'))}
out = ["-- Oxmod's Thierache stages (src/community.js, 25 Nov 2026): their routes, read from the stages' own level files",
       '-- (tools/gamefiles/community_routes.py: the centre line from the start trigger to 140 m before the end trigger),',
       '-- keyed by the track the game reports (location + track: "Thiérache S1"; both Chemin des Érables versions are one road',
       '-- and one name). contributed_by game-files: the first clean driven run replaces it; a route there already is kept.']
q = lambda s: s.replace("'", "''")  # noqa: E731
for arg in sys.argv[3:]:
    sid, track = arg.split('=', 1)
    pts = routes[sid]['points']
    length = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
    out.append("INSERT INTO routes (track, points, length, updated, stage_id, contributed_by) VALUES ('%s', '%s', %.1f, "
               "1795996800000, '%s', 'game-files')\n  ON CONFLICT (track) DO NOTHING;"
               % (q(track), json.dumps(pts, separators=(',', ':')), length, sid))
with open(sys.argv[2], 'w', encoding='utf-8', newline='\n') as f:
    f.write('\n'.join(out) + '\n')
