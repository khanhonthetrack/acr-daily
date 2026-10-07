// Run traces. A finished run's trace is ~16 KB of JSON per minute of stage; only counted runs keep one.
// - With an R2 bucket (binding TRACES): gzipped, under traces/<run id>.json.gz.
// - Without (the free plan has no R2): gzipped in the run's row (runs.trace), as text "gz:<base64>", about half the
//   size of the JSON (gzip ~2.5x, base64 +33 %). Older rows hold plain JSON; reading takes all three.
// `python admin.py move-traces` moves the traces in rows to R2 once a bucket is bound.

export const traceKey = (id) => `traces/${id}.json.gz`;
const PACKED = 'gz:';

/** text -> gzipped bytes */
export async function gzip(text) {
  const stream = new Blob([text]).stream().pipeThrough(new CompressionStream('gzip'));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

/** gzipped bytes, or a stream of them -> text */
export async function gunzip(data) {
  const stream = data instanceof ReadableStream ? data : new Blob([data]).stream();
  return new Response(stream.pipeThrough(new DecompressionStream('gzip'))).text();
}

function toBase64(bytes) {
  let s = '';
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

function fromBase64(b64) {
  const s = atob(b64), out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
  return out;
}

/** A trace (JSON text) as kept in its run's row. */
export async function packTrace(text) {
  return PACKED + toBase64(await gzip(text));
}

/** Store a run's trace (its JSON text) in R2. */
export async function putTrace(env, id, text) {
  await env.TRACES.put(traceKey(id), await gzip(text), { httpMetadata: { contentType: 'application/gzip' } });
}

/** A run's trace as JSON text, or null. row: {id, trace} (trace: the row's copy, packed or plain; null if in R2 or none) */
export async function traceText(env, row) {
  if (row.trace) return row.trace.startsWith(PACKED) ? gunzip(fromBase64(row.trace.slice(PACKED.length))) : row.trace;
  if (!env.TRACES) return null;
  const obj = await env.TRACES.get(traceKey(row.id));
  return obj ? gunzip(obj.body) : null;
}

/** A run's trace (array of samples), or null. */
export async function getTrace(env, row) {
  const text = await traceText(env, row);
  return text ? JSON.parse(text) : null;
}

export const TRACE_DAYS = 14, TRACE_TOP = 3;
export const TRIM_TRACES_SQL = `UPDATE runs SET trace = NULL WHERE id IN (
  SELECT id FROM (SELECT id, ROW_NUMBER() OVER (PARTITION BY date, slot ORDER BY status != 'finished', total_ms, id) AS place
                    FROM runs WHERE date BETWEEN ? AND ? AND trace IS NOT NULL)
   WHERE place > ?)`;

/** Once a day (the cron): a daily more than TRACE_DAYS days old keeps the traces of its TRACE_TOP fastest runs only, so
 *  the database stays far below the free plan's 500 MB. The others keep their times, splits, sections and stats
 *  profile; their viewer page says the map and charts are gone. Traces in rows only (R2 has room). */
export function trimTraces(env, now = Date.now()) {
  const day = (ms) => new Date(ms).toISOString().slice(0, 10);
  const to = day(now - (TRACE_DAYS + 1) * 86400000), from = day(now - (TRACE_DAYS + 8) * 86400000);   // a week's margin
  return env.DB.prepare(TRIM_TRACES_SQL).bind(from, to, TRACE_TOP).run();
}
