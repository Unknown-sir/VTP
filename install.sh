#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="/opt/vortexl2"
CONFIG_DIR="/etc/vortexl2"
SERVICE_DIR="/etc/systemd/system"
PANEL_PORT="${VORTEXL2_PANEL_PORT:-8088}"
PANEL_HOST="${VORTEXL2_PANEL_HOST:-0.0.0.0}"
GH_PROXY="${VORTEXL2_GH_PROXY:-}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log(){ echo -e "${BLUE}[VTP]${NC} $*"; }
ok(){ echo -e "${GREEN}[OK]${NC} $*"; }
warn(){ echo -e "${YELLOW}[WARN]${NC} $*"; }
fail(){ echo -e "${RED}[ERR]${NC} $*"; exit 1; }

[[ $EUID -eq 0 ]] || fail "Please run as root: sudo bash install.sh"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$SCRIPT_DIR"

install_packages(){
  log "Installing system packages..."
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y python3 python3-pip python3-venv python3-yaml iproute2 iputils-ping curl wget ca-certificates haproxy socat lsof net-tools unzip tar gzip
  ok "System packages installed"
}

link_easytier_bins(){
  if command -v easytier-core >/dev/null 2>&1; then
    local core
    core="$(command -v easytier-core)"
    [[ "$core" == "/usr/local/bin/easytier-core" ]] || ln -sf "$core" /usr/local/bin/easytier-core
  fi
  if command -v easytier-cli >/dev/null 2>&1; then
    local cli
    cli="$(command -v easytier-cli)"
    [[ "$cli" == "/usr/local/bin/easytier-cli" ]] || ln -sf "$cli" /usr/local/bin/easytier-cli
  fi
}

install_easytier_if_missing(){
  link_easytier_bins || true
  if [[ -x /usr/local/bin/easytier-core ]] || command -v easytier-core >/dev/null 2>&1; then
    ok "EasyTier is already installed: $(command -v easytier-core 2>/dev/null || echo /usr/local/bin/easytier-core)"
    return 0
  fi
  if [[ "${VORTEXL2_SKIP_EASYTIER_INSTALL:-0}" == "1" ]]; then
    warn "Skipping EasyTier install because VORTEXL2_SKIP_EASYTIER_INSTALL=1"
    return 0
  fi
  warn "EasyTier binary was not found. Trying automatic EasyTier install..."
  local installer="/tmp/vtp-easytier-install.sh"
  local raw1="https://github.com/EasyTier/EasyTier/blob/main/script/install.sh?raw=true"
  local raw2="https://raw.githubusercontent.com/EasyTier/EasyTier/main/script/install.sh"
  if [[ -n "$GH_PROXY" ]]; then
    raw1="${GH_PROXY}${raw1}"
    raw2="${GH_PROXY}${raw2}"
  fi
  if curl -fsSL "$raw1" -o "$installer" || curl -fsSL "$raw2" -o "$installer"; then
    bash "$installer" install || warn "EasyTier install script failed; you can install EasyTier from inside the panel later."
  else
    warn "Could not download EasyTier installer. You can install EasyTier from inside the panel later."
  fi
  link_easytier_bins || true
  if [[ -x /usr/local/bin/easytier-core ]] || command -v easytier-core >/dev/null 2>&1; then
    ok "EasyTier installed: $(command -v easytier-core 2>/dev/null || echo /usr/local/bin/easytier-core)"
  else
    warn "EasyTier is still missing. The panel will show an Install EasyTier button."
  fi
}

copy_files(){
  log "Copying VTP files to $APP_DIR..."
  rm -rf "$APP_DIR"
  mkdir -p "$APP_DIR"
  cp -a vortexl2 "$APP_DIR/"
  cp -a scripts "$APP_DIR/" 2>/dev/null || true
  cp -a requirements.txt README.md CHANGELOG_PANEL.md HAPROXY_SETUP.md "$APP_DIR/" 2>/dev/null || true
  mkdir -p "$CONFIG_DIR/tunnels"
  chmod 700 "$CONFIG_DIR"
  chmod 700 "$CONFIG_DIR/tunnels"
  ok "Files copied"
}

install_python_requirements(){
  log "Installing Python requirements..."
  python3 -m pip install --break-system-packages -r "$APP_DIR/requirements.txt" >/dev/null 2>&1 || \
  python3 -m pip install -r "$APP_DIR/requirements.txt" >/dev/null 2>&1 || \
  warn "pip install failed. If PyYAML/rich are missing, install them manually."
}

write_config(){
  log "Writing default config..."
  if [[ ! -f "$CONFIG_DIR/config.yaml" ]]; then
    cat > "$CONFIG_DIR/config.yaml" <<CFG
# VTP / VortexL2 global config
tunnel_mode: easytier
forward_mode: none
panel_host: "$PANEL_HOST"
panel_port: $PANEL_PORT
panel_auth: true
CFG
    chmod 600 "$CONFIG_DIR/config.yaml"
  else
    python3 - <<PY
from pathlib import Path
import yaml
p=Path('$CONFIG_DIR/config.yaml')
data=yaml.safe_load(p.read_text()) if p.exists() else {}
data=data or {}
data.setdefault('tunnel_mode','easytier')
data.setdefault('forward_mode','none')
data.setdefault('panel_host','$PANEL_HOST')
data.setdefault('panel_port',int('$PANEL_PORT'))
data.setdefault('panel_auth',True)
p.write_text(yaml.safe_dump(data, sort_keys=False))
p.chmod(0o600)
PY
  fi
  if [[ ! -s "$CONFIG_DIR/panel_token" ]]; then
    python3 - <<PY
from pathlib import Path
import secrets, os
p=Path('$CONFIG_DIR/panel_token')
p.write_text(secrets.token_urlsafe(24)+'\n')
os.chmod(p,0o600)
PY
  fi
  ok "Config ready"
}

install_launchers(){
  log "Installing launchers..."
  cat > /usr/local/bin/vortexl2 <<'LAUNCH'
#!/usr/bin/env bash
export PYTHONPATH=/opt/vortexl2
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
exec /usr/bin/python3 -m vortexl2.main "$@"
LAUNCH
  chmod +x /usr/local/bin/vortexl2
  ln -sf /usr/local/bin/vortexl2 /usr/local/bin/vtp
  install -m 0755 "$APP_DIR/scripts/vortexl2-doctor" /usr/local/bin/vortexl2-doctor 2>/dev/null || true
  ln -sf /usr/local/bin/vortexl2-doctor /usr/local/bin/vtp-doctor 2>/dev/null || true
  ok "Launchers installed"
}

install_services(){
  log "Installing systemd services..."
  cp -f systemd/vortexl2-panel.service "$SERVICE_DIR/vortexl2-panel.service"
  cp -f systemd/vortexl2-forward-daemon.service "$SERVICE_DIR/vortexl2-forward-daemon.service"
  cp -f systemd/vortexl2-tunnel.service "$SERVICE_DIR/vortexl2-tunnel.service" 2>/dev/null || true
  sed -i "s/--host 0.0.0.0 --port 8088/--host ${PANEL_HOST} --port ${PANEL_PORT}/" "$SERVICE_DIR/vortexl2-panel.service"
  systemctl daemon-reload
  systemctl enable vortexl2-panel.service vortexl2-forward-daemon.service >/dev/null 2>&1 || true
  systemctl restart vortexl2-panel.service
  systemctl restart vortexl2-forward-daemon.service || true
  ok "Panel service started"
}

print_finish(){
  TOKEN="$(cat "$CONFIG_DIR/panel_token" 2>/dev/null || true)"
  PUBLIC_IP="$(curl -fsS --max-time 4 https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}')"
  echo
  ok "VTP Panel Edition installed."
  echo "------------------------------------------------------------"
  echo "Panel URL:  http://${PUBLIC_IP}:${PANEL_PORT}"
  echo "Local URL:  http://127.0.0.1:${PANEL_PORT}"
  echo "Token:      ${TOKEN}"
  echo "Status:     sudo systemctl status vortexl2-panel"
  echo "Doctor:     sudo vtp-doctor"
  echo "CLI:        sudo vtp status"
  echo "------------------------------------------------------------"
  warn "Firewall note: open TCP ${PANEL_PORT} only for trusted IPs. The panel is token-protected but should not be exposed publicly without firewall rules."
}

install_packages
install_easytier_if_missing
copy_files
install_python_requirements
write_config
install_launchers
install_services
print_finish
