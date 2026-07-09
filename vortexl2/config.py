"""VortexL2 configuration management.

The project stores global settings in /etc/vortexl2/config.yaml and each tunnel in
/etc/vortexl2/tunnels/<name>.yaml.  This file keeps the original L2TPv3 model and
adds safer helpers that are useful for the web panel.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml

CONFIG_DIR = Path(os.environ.get("VORTEXL2_CONFIG_DIR", "/etc/vortexl2"))
TUNNELS_DIR = CONFIG_DIR / "tunnels"
GLOBAL_CONFIG_FILE = CONFIG_DIR / "config.yaml"


def _safe_name(name: str) -> str:
    name = (name or "").strip().lower()
    name = re.sub(r"[^a-z0-9_.-]+", "-", name)
    name = name.strip(".-_")
    if not name:
        raise ValueError("Tunnel name is required")
    if len(name) > 40:
        raise ValueError("Tunnel name must be 40 characters or less")
    return name


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_yaml(path: Path, data: Dict[str, Any], mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
    os.chmod(path, mode)


class GlobalConfig:
    """Global configuration for VortexL2."""

    VALID_FORWARD_MODES = ["none", "haproxy", "socat"]
    VALID_TUNNEL_MODES = ["l2tpv3", "easytier"]

    DEFAULTS: Dict[str, Any] = {
        "forward_mode": "none",
        "tunnel_mode": "easytier",
        "panel_host": "0.0.0.0",
        "panel_port": 8088,
        "panel_auth": True,
    }

    def __init__(self) -> None:
        self._config: Dict[str, Any] = {}
        self._load()
        changed = False
        for key, value in self.DEFAULTS.items():
            if key not in self._config:
                self._config[key] = value
                changed = True
        if changed:
            self._save()

    def _load(self) -> None:
        self._config = _read_yaml(GLOBAL_CONFIG_FILE)

    def _save(self) -> None:
        _write_yaml(GLOBAL_CONFIG_FILE, self._config)

    @property
    def forward_mode(self) -> str:
        mode = self._config.get("forward_mode", "none")
        return mode if mode in self.VALID_FORWARD_MODES else "none"

    @forward_mode.setter
    def forward_mode(self, value: str) -> None:
        if value not in self.VALID_FORWARD_MODES:
            raise ValueError(f"Invalid forward mode: {value}")
        self._config["forward_mode"] = value
        self._save()

    @property
    def tunnel_mode(self) -> str:
        mode = self._config.get("tunnel_mode", "easytier")
        return mode if mode in self.VALID_TUNNEL_MODES else "easytier"

    @tunnel_mode.setter
    def tunnel_mode(self, value: str) -> None:
        if value not in self.VALID_TUNNEL_MODES:
            raise ValueError(f"Invalid tunnel mode: {value}")
        self._config["tunnel_mode"] = value
        self._save()

    @property
    def panel_host(self) -> str:
        return str(self._config.get("panel_host", "0.0.0.0"))

    @panel_host.setter
    def panel_host(self, value: str) -> None:
        self._config["panel_host"] = value or "0.0.0.0"
        self._save()

    @property
    def panel_port(self) -> int:
        try:
            return int(self._config.get("panel_port", 8088))
        except Exception:
            return 8088

    @panel_port.setter
    def panel_port(self, value: int) -> None:
        value = int(value)
        if not 1 <= value <= 65535:
            raise ValueError("Panel port must be between 1 and 65535")
        self._config["panel_port"] = value
        self._save()

    @property
    def panel_auth(self) -> bool:
        return bool(self._config.get("panel_auth", True))

    @panel_auth.setter
    def panel_auth(self, value: bool) -> None:
        self._config["panel_auth"] = bool(value)
        self._save()

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._config)


class TunnelConfig:
    """Configuration for a single L2TPv3 tunnel."""

    DEFAULTS: Dict[str, Any] = {
        "name": "tunnel1",
        "tunnel_type": "l2tpv3",
        "local_ip": None,
        "remote_ip": None,
        "interface_ip": "10.30.30.1/30",
        "remote_forward_ip": "10.30.30.2",
        "tunnel_id": 1000,
        "peer_tunnel_id": 2000,
        "session_id": 10,
        "peer_session_id": 20,
        "interface_index": 0,
        "forwarded_ports": [],
        "encap_type": "ip",
        "udp_port": 55555,
    }

    def __init__(self, name: str, config_data: Optional[Dict[str, Any]] = None, auto_save: bool = True) -> None:
        self._name = _safe_name(name)
        self._file_path = TUNNELS_DIR / f"{self._name}.yaml"
        self._auto_save = auto_save
        self._config: Dict[str, Any] = dict(config_data or _read_yaml(self._file_path))
        for key, default in self.DEFAULTS.items():
            self._config.setdefault(key, default)
        self._config["name"] = self._name
        self._config["tunnel_type"] = "l2tpv3"

    def _save(self) -> None:
        if self._auto_save:
            self.save()

    def save(self) -> None:
        _write_yaml(self._file_path, self._config)
        self._auto_save = True

    def delete(self) -> bool:
        if self._file_path.exists():
            self._file_path.unlink()
            return True
        return False

    @property
    def name(self) -> str:
        return self._name

    @property
    def tunnel_type(self) -> str:
        return "l2tpv3"

    @property
    def local_ip(self) -> Optional[str]:
        return self._config.get("local_ip")

    @local_ip.setter
    def local_ip(self, value: Optional[str]) -> None:
        self._config["local_ip"] = value
        self._save()

    @property
    def remote_ip(self) -> Optional[str]:
        return self._config.get("remote_ip")

    @remote_ip.setter
    def remote_ip(self, value: Optional[str]) -> None:
        self._config["remote_ip"] = value
        self._save()

    @property
    def interface_ip(self) -> str:
        return str(self._config.get("interface_ip", "10.30.30.1/30"))

    @interface_ip.setter
    def interface_ip(self, value: str) -> None:
        self._config["interface_ip"] = value
        self._save()

    @property
    def remote_forward_ip(self) -> str:
        return str(self._config.get("remote_forward_ip", "10.30.30.2"))

    @remote_forward_ip.setter
    def remote_forward_ip(self, value: str) -> None:
        self._config["remote_forward_ip"] = value
        self._save()

    @property
    def tunnel_id(self) -> int:
        return int(self._config.get("tunnel_id", 1000))

    @tunnel_id.setter
    def tunnel_id(self, value: int) -> None:
        self._config["tunnel_id"] = int(value)
        self._save()

    @property
    def peer_tunnel_id(self) -> int:
        return int(self._config.get("peer_tunnel_id", 2000))

    @peer_tunnel_id.setter
    def peer_tunnel_id(self, value: int) -> None:
        self._config["peer_tunnel_id"] = int(value)
        self._save()

    @property
    def session_id(self) -> int:
        return int(self._config.get("session_id", 10))

    @session_id.setter
    def session_id(self, value: int) -> None:
        self._config["session_id"] = int(value)
        self._save()

    @property
    def peer_session_id(self) -> int:
        return int(self._config.get("peer_session_id", 20))

    @peer_session_id.setter
    def peer_session_id(self, value: int) -> None:
        self._config["peer_session_id"] = int(value)
        self._save()

    @property
    def interface_index(self) -> int:
        return int(self._config.get("interface_index", 0))

    @interface_index.setter
    def interface_index(self, value: int) -> None:
        self._config["interface_index"] = int(value)
        self._save()

    @property
    def interface_name(self) -> str:
        return f"l2tpeth{self.interface_index}"

    @property
    def forwarded_ports(self) -> List[int]:
        return [int(p) for p in self._config.get("forwarded_ports", [])]

    @forwarded_ports.setter
    def forwarded_ports(self, value: List[int]) -> None:
        self._config["forwarded_ports"] = sorted({int(p) for p in value if 1 <= int(p) <= 65535})
        self._save()

    @property
    def encap_type(self) -> str:
        value = self._config.get("encap_type", "ip")
        return value if value in {"ip", "udp"} else "ip"

    @encap_type.setter
    def encap_type(self, value: str) -> None:
        if value not in {"ip", "udp"}:
            raise ValueError("encap_type must be 'ip' or 'udp'")
        self._config["encap_type"] = value
        self._save()

    @property
    def udp_port(self) -> int:
        return int(self._config.get("udp_port", 55555))

    @udp_port.setter
    def udp_port(self, value: int) -> None:
        value = int(value)
        if not 1 <= value <= 65535:
            raise ValueError("UDP port must be between 1 and 65535")
        self._config["udp_port"] = value
        self._save()

    def add_port(self, port: int) -> None:
        ports = self.forwarded_ports
        if int(port) not in ports:
            ports.append(int(port))
        self.forwarded_ports = ports

    def remove_port(self, port: int) -> None:
        self.forwarded_ports = [p for p in self.forwarded_ports if p != int(port)]

    def is_configured(self) -> bool:
        return bool(self.local_ip and self.remote_ip)

    def to_dict(self) -> Dict[str, Any]:
        data = dict(self._config)
        data["interface_name"] = self.interface_name
        return data


class ConfigManager:
    """Manages multiple L2TPv3 tunnel configurations."""

    def __init__(self) -> None:
        TUNNELS_DIR.mkdir(parents=True, exist_ok=True)

    def list_tunnels(self) -> List[str]:
        tunnels: List[str] = []
        for f in TUNNELS_DIR.glob("*.yaml"):
            data = _read_yaml(f)
            if data.get("tunnel_type", "l2tpv3") == "l2tpv3":
                tunnels.append(f.stem)
        return sorted(tunnels)

    def get_tunnel(self, name: str) -> Optional[TunnelConfig]:
        try:
            safe = _safe_name(name)
        except ValueError:
            return None
        if (TUNNELS_DIR / f"{safe}.yaml").exists():
            return TunnelConfig(safe)
        return None

    def get_all_tunnels(self) -> List[TunnelConfig]:
        return [TunnelConfig(name) for name in self.list_tunnels()]

    def tunnel_exists(self, name: str) -> bool:
        try:
            return (TUNNELS_DIR / f"{_safe_name(name)}.yaml").exists()
        except ValueError:
            return False

    def create_tunnel(self, name: str) -> TunnelConfig:
        safe = _safe_name(name)
        used_indices: Set[int] = {t.interface_index for t in self.get_all_tunnels()}
        new_index = 0
        while new_index in used_indices:
            new_index += 1
        tunnel = TunnelConfig(safe, auto_save=False)
        tunnel._config["interface_index"] = new_index
        base = 1000 + new_index * 100
        tunnel._config.update({
            "tunnel_id": base,
            "peer_tunnel_id": base + 1000,
            "session_id": 10 + new_index,
            "peer_session_id": 20 + new_index,
            "udp_port": 55555 + new_index,
        })
        return tunnel

    def delete_tunnel(self, name: str) -> bool:
        tunnel = self.get_tunnel(name)
        return tunnel.delete() if tunnel else False

    def get_used_values(self, exclude_tunnel: Optional[str] = None) -> Dict[str, Set[Any]]:
        used: Dict[str, Set[Any]] = {
            "tunnel_ids": set(),
            "peer_tunnel_ids": set(),
            "session_ids": set(),
            "peer_session_ids": set(),
            "interface_ips": set(),
            "local_ips": set(),
            "remote_ips": set(),
        }
        for tunnel in self.get_all_tunnels():
            if exclude_tunnel and tunnel.name == exclude_tunnel:
                continue
            used["tunnel_ids"].add(tunnel.tunnel_id)
            used["peer_tunnel_ids"].add(tunnel.peer_tunnel_id)
            used["session_ids"].add(tunnel.session_id)
            used["peer_session_ids"].add(tunnel.peer_session_id)
            used["interface_ips"].add(tunnel.interface_ip.split("/")[0])
            if tunnel.local_ip:
                used["local_ips"].add(tunnel.local_ip)
            if tunnel.remote_ip:
                used["remote_ips"].add(tunnel.remote_ip)
        return used
