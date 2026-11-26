FROM node:24-bookworm-slim

RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 ca-certificates curl gosu \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY server/package.json server/wrangler.toml server/schema.sql server/vm-server.mjs ./server/
COPY server/migrations ./server/migrations
COPY server/src ./server/src
COPY live/relay.py live/standby_receiver.py ./live/
COPY tools/auto_rollout_watcher.py ./tools/
COPY routes ./routes

RUN printf '#!/bin/sh\nset -e\nif [ "$(id -u)" = "0" ]; then\n  mkdir -p /data\n  [ "$(stat -c %%u /data)" = "1000" ] || chown node:node /data\n  exec gosu node "$@"\nfi\nexec "$@"\n' > /usr/local/bin/docker-entrypoint.sh \
  && chmod +x /usr/local/bin/docker-entrypoint.sh \
  && mkdir -p /data && chown -R node:node /app /data

USER node
WORKDIR /app/server

ENV NODE_ENV=production \
    PORT=8080 \
    RELAY_BIND_HOST=0.0.0.0 \
    RELAY_PORT=8765 \
    RELAY_PEER_BIND_HOST=0.0.0.0 \
    RELAY_PEER_PORT=8766 \
    DATA_DIR=/data

EXPOSE 8080 8765 8766

HEALTHCHECK --interval=15s --timeout=4s --start-period=10s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8080/healthz >/dev/null && curl -fsS http://127.0.0.1:8765/ >/dev/null || exit 1

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["node", "vm-server.mjs"]
