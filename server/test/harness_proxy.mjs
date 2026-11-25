// The broadcast overlays (src/broadcast.js) of this checkout on the live site's data (not a test: node
// test/harness_proxy.mjs, then http://127.0.0.1:8798/broadcast/championship/<id>): pages from here, every /api/ GET
// from acrdaily.com (read-only, public).
import http from 'node:http';
import { broadcastPage, BROADCAST_HEADERS } from '../src/broadcast.js';

const SITE = 'https://acrdaily.com';
http.createServer(async (req, res) => {
  const url = new URL('http://127.0.0.1:8798' + req.url);
  const m = url.pathname.match(/^\/broadcast\/(daily|tt|event|championship|ranked)\/(.+)$/);
  if (m) {
    res.writeHead(200, BROADCAST_HEADERS);
    res.end(broadcastPage(m[1], m[2], url.searchParams, SITE));
    return;
  }
  if (req.method !== 'GET') { res.writeHead(405); res.end(); return; }
  const r = await fetch(SITE + url.pathname + url.search, { headers: { 'User-Agent': 'acr-daily-overlay-check' } });
  res.writeHead(r.status, { 'Content-Type': r.headers.get('Content-Type') || 'application/octet-stream' });
  res.end(Buffer.from(await r.arrayBuffer()));
}).listen(8798, () => console.log('ready'));
