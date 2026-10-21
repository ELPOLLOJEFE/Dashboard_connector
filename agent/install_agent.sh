#!/usr/bin/env bash
# Instalador del agente en Linux. Idempotente: puedes relanzarlo.
#
#   sudo DC_HUB_URL=http://IP-DEL-HUB:8700 DC_AGENT_TOKEN=xxxx ./install_agent.sh
#
set -euo pipefail

HUB_URL="${DC_HUB_URL:-}"
TOKEN="${DC_AGENT_TOKEN:-}"
NODE_ID="${DC_NODE_ID:-$(hostname | tr '[:upper:]' '[:lower:]')}"
INTERVAL="${DC_INTERVAL:-20}"
SHARE_CPU_PCT="${DC_SHARE_CPU_PCT:-50}"
SHARE_RAM_MB="${DC_SHARE_RAM_MB:-2048}"
SHARE_FREE_PCT="${DC_SHARE_FREE_PCT:-0}"
WORKER_UNIT="${DC_WORKER_UNIT:-}"

[[ $EUID -eq 0 ]] || { echo "Ejecutalo con sudo."; exit 1; }
[[ -n "$HUB_URL" ]] || { echo "Falta DC_HUB_URL."; exit 1; }
[[ -n "$TOKEN"   ]] || { echo "Falta DC_AGENT_TOKEN."; exit 1; }
command -v python3 >/dev/null || { echo "Falta python3. Instalalo y repite."; exit 1; }

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/dc_agent.py"
[[ -f "$SRC" ]] || { echo "No encuentro dc_agent.py junto a este script."; exit 1; }

install -d -m 755 /opt/dashboard-connector
install -m 755 "$SRC" /opt/dashboard-connector/dc_agent.py
install -d -m 755 /var/lib/dashboard-connector

umask 077
cat > /etc/dashboard-connector.env <<EOF
DC_HUB_URL=$HUB_URL
DC_AGENT_TOKEN=$TOKEN
DC_NODE_ID=$NODE_ID
DC_INTERVAL=$INTERVAL
DC_SHARE_CPU_PCT=$SHARE_CPU_PCT
DC_SHARE_RAM_MB=$SHARE_RAM_MB
DC_SHARE_FREE_PCT=$SHARE_FREE_PCT
DC_WORKER_UNIT=$WORKER_UNIT
DC_STATE_DIR=/var/lib/dashboard-connector
EOF
chmod 600 /etc/dashboard-connector.env

cat > /etc/systemd/system/dashboard-connector-agent.service <<'EOF'
[Unit]
Description=Dashboard Connector - agente
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=/etc/dashboard-connector.env
ExecStart=/usr/bin/python3 /opt/dashboard-connector/dc_agent.py
Restart=always
RestartSec=15
# El agente solo necesita leer metricas y escribir su estado.
NoNewPrivileges=true
ProtectSystem=full
ReadWritePaths=/var/lib/dashboard-connector
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now dashboard-connector-agent.service
sleep 3
systemctl --no-pager --lines=12 status dashboard-connector-agent.service || true

echo
echo "Listo. Este equipo (${NODE_ID}) ya aparece en el panel, en modo 'Fuera'."
echo "Cambiale el modo desde el panel cuando quieras que comparta."
