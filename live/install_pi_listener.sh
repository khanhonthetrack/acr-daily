#!/usr/bin/env bash
# Installs & starts the ACR Daily passive backup listener on the Raspberry Pi (auto-detecting the real Linux user/home),
# preserves any existing ~/acr-standby/standby.key, keeps existing port 8095 on Tailscale Funnel :8443/, and mounts
# the standby listener exclusively under :8443/internal/standby so ports :443 (Immich), :8443/ (8095), and :10000 (relay)
# all continue working side by side!
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_USER="${SUDO_USER:-$(id -un)}"
RUN_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"
STANDBY_DIR="${RUN_HOME}/acr-standby"
DATA_DIR="${STANDBY_DIR}/data"
KEY_FILE="${STANDBY_DIR}/standby.key"

sudo -u "$RUN_USER" mkdir -p "$DATA_DIR"
sudo -u "$RUN_USER" cp "${HERE}/standby_receiver.py" "${STANDBY_DIR}/standby_receiver.py"

echo -n "STANDBY_KEY: "
sudo -u "$RUN_USER" python3 "${STANDBY_DIR}/standby_receiver.py" \
  --data-dir "$DATA_DIR" \
  --key-file "$KEY_FILE" \
  --init-key-only

sudo tee /etc/systemd/system/acr-standby.service >/dev/null <<EOF
[Unit]
Description=ACR Daily passive standby backup listener
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${RUN_USER}
ExecStart=/usr/bin/python3 ${STANDBY_DIR}/standby_receiver.py --host 127.0.0.1 --port 9876 --data-dir ${DATA_DIR} --key-file ${KEY_FILE} --auto-create-key
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable acr-standby
sudo systemctl restart acr-standby

for _i in $(seq 1 15); do
  if curl -fsS http://127.0.0.1:9876/healthz >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done
echo "Local listener health: $(curl -fsS http://127.0.0.1:9876/healthz)"

# Keep existing local service on 8095 at :8443/ if present, and route ONLY /internal/standby on :8443 to :9876!
if ss -tln 2>/dev/null | grep -q ':8095 '; then
  echo "Restoring existing 127.0.0.1:8095 mapping on Funnel :8443/ ..."
  sudo tailscale funnel --bg --https=8443 http://127.0.0.1:8095
fi
echo "Mounting /internal/standby on Funnel :8443 -> 127.0.0.1:9876 ..."
sudo tailscale funnel --bg --https=8443 --set-path=/internal/standby http://127.0.0.1:9876/internal/standby

sudo tailscale funnel status
