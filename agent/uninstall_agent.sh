#!/usr/bin/env bash
# Desinstala el agente en Linux. Deja el equipo como estaba.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Ejecutalo con sudo."; exit 1; }

systemctl disable --now dashboard-connector-agent.service 2>/dev/null || true
rm -f /etc/systemd/system/dashboard-connector-agent.service
systemctl daemon-reload
rm -rf /opt/dashboard-connector /var/lib/dashboard-connector
rm -f /etc/dashboard-connector.env
echo "Agente desinstalado. Acuerdate de borrarlo tambien en el panel."
