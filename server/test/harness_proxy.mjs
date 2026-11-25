// The broadcast overlays (src/broadcast.js) of this checkout on the live site's data (not a test: node
// test/harness_proxy.mjs, then http://127.0.0.1:8798/broadcast/championship/<id>): pages from here, every /api/ GET
// from acrdaily.com (read-only, public).
import http from 'node:http';
import { broadcastPage, BROADCAST_HEADERS } from '../src/broadcast.js';
import { dailiesOverlayPage } from '../src/dailiesoverlay.js';

import { dailiesCommentary } from '../src/commentary.js';

const SITE = 'https://acrdaily.com';
const MEM = new Map();
const CACHE = { match: async (r) => (MEM.has(r.url) ? new Response(MEM.get(r.url)) : undefined), put: async (r, x) => { MEM.set(r.url, await x.text()); } };
const STAND_IN = { beta: { messages: { create: async (body) => {
  const f = JSON.parse(body.messages[0].content), s = f.stages.find((x) => x.board.length) || f.stages[0], b = s && s.board;
  const text = b && b.length > 1 ? `${b[0].name} still the one to beat on ${s.stage}, ${b[0].time}, and ${b[1].name} sits ${b[1].gap.slice(1)} s back.`
    : `${s ? s.stage : 'The stages'} wait for their first time of the day.`;
  return { stop_reason: 'end_turn', content: [{ type: 'text', text }] };
} } } };
http.createServer(async (req, res) => {
  const url = new URL('http://127.0.0.1:8798' + req.url);
  const m = url.pathname.match(/^\/broadcast\/(daily|tt|event|championship|ranked)\/(.+)$/);
  if (m) {
    res.writeHead(200, BROADCAST_HEADERS);
    res.end(broadcastPage(m[1], m[2], url.searchParams, SITE));
    return;
  }
  if (url.pathname === '/broadcast/dailies') {
    res.writeHead(200, BROADCAST_HEADERS);
    res.end(dailiesOverlayPage(url.searchParams, SITE));
    return;
  }
  // HARNESS_CLAUDE=1: Claude's lines (src/commentary.js) on the live boards, written by a stand-in (no key needed)
  if (url.pathname === '/api/broadcast/dailies/commentary') {
    const out = process.env.HARNESS_CLAUDE ? await dailiesCommentary({}, async (p) => {
      const r = await fetch(SITE + p, { headers: { 'User-Agent': 'acr-daily-overlay-check' } });
      return r.ok ? r.json() : null;
    }, { client: STAND_IN, cache: CACHE }) : { on: false };
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(out));
    return;
  }
  if (req.method !== 'GET') { res.writeHead(405); res.end(); return; }
  const r = await fetch(SITE + url.pathname + url.search, { headers: { 'User-Agent': 'acr-daily-overlay-check' } });
  res.writeHead(r.status, { 'Content-Type': r.headers.get('Content-Type') || 'application/octet-stream' });
  res.end(Buffer.from(await r.arrayBuffer()));
}).listen(8798, () => console.log('ready'));
