#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Run as root"; exit 1; }
systemctl stop vortexl2-panel vortexl2-forward-daemon vortexl2-tunnel 2>/dev/null || true
systemctl disable vortexl2-panel vortexl2-forward-daemon vortexl2-tunnel 2>/dev/null || true
systemctl stop 'vortexl2-easytier-*' 2>/dev/null || true
systemctl disable 'vortexl2-easytier-*' 2>/dev/null || true
rm -f /etc/systemd/system/vortexl2-panel.service /etc/systemd/system/vortexl2-forward-daemon.service /etc/systemd/system/vortexl2-tunnel.service
rm -f /etc/systemd/system/vortexl2-easytier-*.service
rm -f /usr/local/bin/vortexl2 /usr/local/bin/vortexl2-doctor /usr/local/bin/vtp /usr/local/bin/vtp-doctor
rm -rf /opt/vortexl2
systemctl daemon-reload
read -r -p "Remove /etc/vortexl2 configs too? [y/N] " ans
if [[ "${ans,,}" == "y" ]]; then rm -rf /etc/vortexl2; fi
echo "VTP Panel Edition removed."
