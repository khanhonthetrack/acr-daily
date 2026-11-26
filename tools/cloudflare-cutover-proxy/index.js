// Transparent cutover forwarder for acr-daily.acr-daily-server.workers.dev -> GKE Primary.
// Ensures all existing v0.2.1 desktop apps (compiled against workers.dev before v0.2.2) read & write directly to GKE
// with zero split-brain, preserving POST bodies, Bearer tokens, cookies, and OAuth redirects.

export default {
  async fetch(request, env) {
    if (String(env.MAINTENANCE || '0') === '1') {
      return new Response(
        JSON.stringify({ error: 'Server cutover in progress — please retry in 30 seconds.' }),
        {
          status: 503,
          headers: {
            'Content-Type': 'application/json',
            'Retry-After': '15',
            'Cache-Control': 'no-store',
          },
        },
      );
    }

    const upstream = new URL(env.UPSTREAM_ORIGIN || 'https://acrdaily-eu.34-49-33-253.sslip.io');
    const inUrl = new URL(request.url);
    const targetUrl = new URL(inUrl.pathname + inUrl.search, upstream.origin);

    const headers = new Headers(request.headers);
    headers.delete('host');
    if (headers.has('origin')) {
      const orig = headers.get('origin') || '';
      if (orig === inUrl.origin) {
        headers.set('origin', upstream.origin);
      }
    }
    const clientIp = request.headers.get('cf-connecting-ip');
    if (clientIp) {
      headers.set('x-forwarded-for', clientIp);
    }
    headers.set('x-forwarded-host', inUrl.host);
    headers.set('x-forwarded-proto', inUrl.protocol.replace(':', ''));

    const hasBody = request.method !== 'GET' && request.method !== 'HEAD';
    return fetch(targetUrl.toString(), {
      method: request.method,
      headers,
      body: hasBody ? request.body : undefined,
      redirect: 'manual',
    });
  },
};
