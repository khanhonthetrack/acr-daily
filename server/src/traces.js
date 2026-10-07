// Run traces in R2 (binding TRACES), not in the database: a finished run's trace is ~16 KB of JSON per minute of
// stage, gzipped about 2.5 times smaller, kept under traces/<run id>.json.gz. Runs from before R2 still have it in
// runs.trace until it is moved (POST /api/admin/move-traces, `python admin.py move-traces`); reading takes either.

export const traceKey = (id) => `traces/${id}.json.gz`;

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

/** Store a run's trace (its JSON text). */
export async function putTrace(env, id, text) {
  await env.TRACES.put(traceKey(id), await gzip(text), { httpMetadata: { contentType: 'application/gzip' } });
}

/** A run's trace as JSON text, or null. row: {id, trace} (trace: the old column, null once moved to R2) */
export async function traceText(env, row) {
  if (row.trace) return row.trace;
  if (!env.TRACES) return null;                       // no bucket bound (a server without R2: traces stay in rows)
  const obj = await env.TRACES.get(traceKey(row.id));
  return obj ? gunzip(obj.body) : null;
}

/** A run's trace (array of samples), or null. */
export async function getTrace(env, row) {
  const text = await traceText(env, row);
  return text ? JSON.parse(text) : null;
}
