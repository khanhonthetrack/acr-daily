// The live maps' cars (the home page's map, /lab/map): smooth, a few seconds behind. Each app sends how far along the
// route its driver is every liveSendS; the website keeps each driver's last updates and plays them back LIVE_DELAY
// late, along the route, so a car moves steadily on the road between two updates it already has: it never cuts across
// a corner, nor stops and catches up when a check of the website's comes between two of the app's.
// The pages run these functions' own source (GLIDE_JS); test/glide.test.mjs checks that source.

/** A route [[x, z], ...] in game metres -> {len, at(progress)}: the point that far along it (0..1 of its length, as the
 *  app measures progress: the route's own points, client/acr_daily/route.py). */
export function routeTrack(pts) {
  pts = pts || [];
  var cum = [0];
  for (var i = 1; i < pts.length; i++) cum.push(cum[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  var len = cum[cum.length - 1];
  return {
    len: len,
    at: function (p) {
      if (!pts.length) return null;
      var d = Math.max(0, Math.min(1, +p || 0)) * len, lo = 0, hi = pts.length - 1;
      while (hi - lo > 1) { var mid = (lo + hi) >> 1; if (cum[mid] <= d) lo = mid; else hi = mid; }
      var seg = cum[hi] - cum[lo], f = seg > 0 ? (d - cum[lo]) / seg : 0;
      return [pts[lo][0] + (pts[hi][0] - pts[lo][0]) * f, pts[lo][1] + (pts[hi][1] - pts[lo][1]) * f];
    },
  };
}

/** The playback of one map's cars. feed(drivers, serverNow, now) with each answer of /api/live (each driver's progress,
 *  state and `updated`: when the server got it); at(id, now) -> {p, state} where and how to show that driver at this
 *  browser's time `now` (null: not any more). delayMs: how far behind the server's clock the cars run; gapMs: two
 *  updates further apart than this (the tab was hidden, the app lost its connection) are not driven between: the car
 *  waits, then jumps. Going back along the route (a new run) is a jump too, never a drive backwards. */
export function livePlayback(delayMs, gapMs) {
  // off: the server's clock - this browser's, from the quickest answer (a slow one says less: the cars never go back);
  // taken afresh when it is 5 s out (this computer's clock was set)
  var cars = {}, off = null;
  function time(now) { return now + (off || 0) - delayMs; }
  return {
    set: function (delay, gap) { delayMs = delay; gapMs = gap; },
    feed: function (drivers, serverNow, now) {
      var o = serverNow - now;
      off = off == null || Math.abs(o - off) > 5000 ? o : Math.max(o, off);
      var seen = {}, r = time(now);
      drivers.forEach(function (d) {
        var id = String(d.steamId), c = cars[id] || (cars[id] = { s: [] }), s = c.s, last = s[s.length - 1];
        var t = d.updated || serverNow, p = Math.max(0, Math.min(1, +d.progress || 0));
        seen[id] = 1;
        c.gone = false;
        if (last && t <= last.t) { if (t === last.t) last.state = d.state; return; }   // the same update again
        s.push({ t: t, p: p, state: d.state, jump: !!last && (p < last.p - 0.002 || t - last.t > gapMs) });
        var k = 0;   // what playback still needs: the last update before now's playback time, and those after it
        while (k + 1 < s.length && s[k + 1].t <= r) k++;
        if (k) s.splice(0, k);
      });
      Object.keys(cars).forEach(function (id) { if (!seen[id]) cars[id].gone = true; });
    },
    at: function (id, now) {
      var c = cars[id];
      if (!c || !c.s.length) return null;
      var s = c.s, r = time(now), i = s.length - 1;
      if (r <= s[0].t) return { p: s[0].p, state: s[0].state };   // not there yet: where it was first seen
      while (i > 0 && s[i].t > r) i--;
      var a = s[i], b = s[i + 1];
      if (!b) {
        if (c.gone) { delete cars[id]; return null; }   // off the server's list, and all of it shown
        return { p: a.p, state: a.state };
      }
      if (b.jump) return { p: a.p, state: a.state };
      return { p: a.p + (b.p - a.p) * (r - a.t) / (b.t - a.t), state: a.state };
    },
  };
}

/** For a page's script: routeTrack and livePlayback. (wrangler's bundle keeps function names with __name(fn, 'name')
 *  calls inside their source: the page gets a stand-in.) */
export const GLIDE_JS = `var __name=function(f){return f};
${routeTrack.toString()}
${livePlayback.toString()}
`;
