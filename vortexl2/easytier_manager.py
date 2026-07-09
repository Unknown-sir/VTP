"""EasyTier tunnel manager with proper multi-tunnel and multi-peer support.

Fixes included in this edition:
- each EasyTier service receives unique listener port, RPC port, device name and IP;
- legacy `peer_ip` configs still work, but new configs use `peers: []`;
- a single hub/listener node can run without peers, which is useful for Kharej -> many Iran;
- conflict checks prevent the second tunnel from failing because of duplicated resources.
"""
from __future__ import annotations

import ipaddress
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

CONFIG_DIR = Path(os.environ.get("VORTEXL2_CONFIG_DIR", "/etc/vortexl2"))
TUNNELS_DIR = CONFIG_DIR / "tunnels"


def _find_executable(name: str, env_name: str, default: str) -> Path:
    explicit = os.environ.get(env_name)
    if explicit:
        return Path(explicit)
    found = shutil.which(name)
    if found:
        return Path(found)
    for candidate in (f"/usr/local/bin/{name}", f"/usr/bin/{name}", f"/opt/easytier/{name}"):
        if Path(candidate).exists():
            return Path(candidate)
    return Path(default)


def easytier_binary() -> Path:
    return _find_executable("easytier-core", "VORTEXL2_EASYTIER_BIN", "/usr/local/bin/easytier-core")


def easytier_cli_binary() -> Path:
    return _find_executable("easytier-cli", "VORTEXL2_EASYTIER_CLI", "/usr/local/bin/easytier-cli")


def easytier_install_state() -> Dict[str, Any]:
    core = easytier_binary()
    cli = easytier_cli_binary()
    return {
        "installed": core.exists() and os.access(core, os.X_OK),
        "core": str(core),
        "cli": str(cli) if cli.exists() else None,
    }



def _safe_name(name: str) -> str:
    name = (name or "").strip().lower()
    name = re.sub(r"[^a-z0-9_.-]+", "-", name).strip(".-_")
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


def _write_yaml(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
    os.chmod(path, 0o600)


def _normalize_peer(peer: Any, default_port: int) -> Optional[Dict[str, Any]]:
    if not peer:
        return None
    if isinstance(peer, str):
        value = peer.strip()
        if not value:
            return None
        protocol = "tcp"
        if "://" in value:
            protocol, value = value.split("://", 1)
        host = value
        port = default_port
        if value.count(":") == 1 and not value.startswith("["):
            host, port_s = value.rsplit(":", 1)
            if port_s.isdigit():
                port = int(port_s)
        return {"host": host.strip("[]"), "port": port, "protocol": protocol or "tcp"}
    if isinstance(peer, dict):
        host = peer.get("host") or peer.get("ip") or peer.get("peer_ip") or peer.get("address")
        if not host:
            return None
        return {
            "host": str(host).strip(),
            "port": int(peer.get("port") or default_port),
            "protocol": str(peer.get("protocol") or "tcp"),
            "name": peer.get("name"),
        }
    return None


def _quote_cmd(args: Iterable[str]) -> str:
    return shlex.join([str(a) for a in args])


class EasyTierConfig:
    DEFAULTS: Dict[str, Any] = {
        "name": "tunnel1",
        "tunnel_type": "easytier",
        "role": "node",  # hub/node/iran/kharej are accepted labels for UI only
        "local_ip": "10.155.155.1",
        "peer_ip": None,  # legacy compatibility
        "peers": [],
        "port": 2070,
        "rpc_port": 15888,
        "network_secret": "vortexl2",
        "interface_name": "tun1",
        "hostname": "node1",
        "forwarded_ports": [],
        "remote_forward_ip": None,
        "default_protocol": "tcp",
        "enable_listeners": True,
    }

    def __init__(self, name: str, config_data: Optional[Dict[str, Any]] = None, auto_save: bool = True) -> None:
        self._name = _safe_name(name)
        self._file_path = TUNNELS_DIR / f"{self._name}.yaml"
        self._auto_save = auto_save
        self._config: Dict[str, Any] = dict(config_data or _read_yaml(self._file_path))
        for key, value in self.DEFAULTS.items():
            self._config.setdefault(key, value)
        self._config["name"] = self._name
        self._config["tunnel_type"] = "easytier"
        self._migrate_legacy_peer()

    def _migrate_legacy_peer(self) -> None:
        peers = list(self._config.get("peers") or [])
        legacy_peer_ip = self._config.get("peer_ip")
        if legacy_peer_ip and not peers:
            peers.append({"host": legacy_peer_ip, "port": int(self._config.get("port", 2070)), "protocol": "tcp"})
        normalized: List[Dict[str, Any]] = []
        seen = set()
        for peer in peers:
            item = _normalize_peer(peer, int(self._config.get("port", 2070)))
            if not item:
                continue
            key = (item["protocol"], item["host"], int(item["port"]))
            if key not in seen:
                normalized.append(item)
                seen.add(key)
        self._config["peers"] = normalized

    def _save(self) -> None:
        if self._auto_save:
            self.save()

    def save(self) -> None:
        self._migrate_legacy_peer()
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
    def role(self) -> str:
        return str(self._config.get("role", "node"))

    @role.setter
    def role(self, value: str) -> None:
        self._config["role"] = value or "node"
        self._save()

    @property
    def local_ip(self) -> str:
        return str(self._config.get("local_ip", "10.155.155.1"))

    @local_ip.setter
    def local_ip(self, value: str) -> None:
        self._config["local_ip"] = value
        self._save()

    @property
    def port(self) -> int:
        return int(self._config.get("port", 2070))

    @port.setter
    def port(self, value: int) -> None:
        value = int(value)
        if not 1 <= value <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        self._config["port"] = value
        self._save()

    @property
    def rpc_port(self) -> int:
        return int(self._config.get("rpc_port", 15888))

    @rpc_port.setter
    def rpc_port(self, value: int) -> None:
        value = int(value)
        if not 1 <= value <= 65535:
            raise ValueError("RPC port must be between 1 and 65535")
        self._config["rpc_port"] = value
        self._save()

    @property
    def network_secret(self) -> str:
        return str(self._config.get("network_secret", "vortexl2"))

    @network_secret.setter
    def network_secret(self, value: str) -> None:
        self._config["network_secret"] = value or "vortexl2"
        self._save()

    @property
    def interface_name(self) -> str:
        return str(self._config.get("interface_name", "tun1"))[:15]

    @interface_name.setter
    def interface_name(self, value: str) -> None:
        clean = re.sub(r"[^a-zA-Z0-9_.-]+", "", value or "tun1")[:15]
        if not clean:
            raise ValueError("Interface name is required")
        self._config["interface_name"] = clean
        self._save()

    @property
    def hostname(self) -> str:
        return str(self._config.get("hostname", self._name))

    @hostname.setter
    def hostname(self, value: str) -> None:
        self._config["hostname"] = value or self._name
        self._save()

    @property
    def default_protocol(self) -> str:
        protocol = str(self._config.get("default_protocol", "tcp"))
        return protocol if protocol in {"tcp", "udp", "wg"} else "tcp"

    @default_protocol.setter
    def default_protocol(self, value: str) -> None:
        self._config["default_protocol"] = value if value in {"tcp", "udp", "wg"} else "tcp"
        self._save()

    @property
    def enable_listeners(self) -> bool:
        return bool(self._config.get("enable_listeners", True))

    @enable_listeners.setter
    def enable_listeners(self, value: bool) -> None:
        self._config["enable_listeners"] = bool(value)
        self._save()

    @property
    def peer_ip(self) -> Optional[str]:
        peers = self.peers
        return peers[0]["host"] if peers else None

    @peer_ip.setter
    def peer_ip(self, value: Optional[str]) -> None:
        if value:
            self.peers = [{"host": value, "port": self.port, "protocol": "tcp"}]
            self._config["peer_ip"] = value
        else:
            self.peers = []
            self._config["peer_ip"] = None
        self._save()

    @property
    def peers(self) -> List[Dict[str, Any]]:
        self._migrate_legacy_peer()
        return list(self._config.get("peers") or [])

    @peers.setter
    def peers(self, value: List[Any]) -> None:
        normalized: List[Dict[str, Any]] = []
        seen = set()
        for peer in value or []:
            item = _normalize_peer(peer, self.port)
            if not item:
                continue
            key = (item["protocol"], item["host"], int(item["port"]))
            if key not in seen:
                normalized.append(item)
                seen.add(key)
        self._config["peers"] = normalized
        self._config["peer_ip"] = normalized[0]["host"] if normalized else None
        self._save()

    @property
    def forwarded_ports(self) -> List[int]:
        return sorted({int(p) for p in self._config.get("forwarded_ports", []) if 1 <= int(p) <= 65535})

    @forwarded_ports.setter
    def forwarded_ports(self, value: List[int]) -> None:
        self._config["forwarded_ports"] = sorted({int(p) for p in value if 1 <= int(p) <= 65535})
        self._save()

    @property
    def remote_forward_ip(self) -> Optional[str]:
        value = self._config.get("remote_forward_ip")
        return str(value) if value else None

    @remote_forward_ip.setter
    def remote_forward_ip(self, value: Optional[str]) -> None:
        self._config["remote_forward_ip"] = value or None
        self._save()

    def add_peer(self, host: str, port: Optional[int] = None, protocol: str = "tcp", name: Optional[str] = None) -> None:
        peers = self.peers
        peers.append({"host": host, "port": int(port or self.port), "protocol": protocol or "tcp", "name": name})
        self.peers = peers

    def remove_peer(self, host: str, port: Optional[int] = None) -> None:
        self.peers = [p for p in self.peers if not (p.get("host") == host and (port is None or int(p.get("port", self.port)) == int(port)))]

    def add_port(self, port: int) -> None:
        ports = self.forwarded_ports
        if int(port) not in ports:
            ports.append(int(port))
        self.forwarded_ports = ports

    def remove_port(self, port: int) -> None:
        self.forwarded_ports = [p for p in self.forwarded_ports if p != int(port)]

    def is_configured(self) -> bool:
        # Listener-only nodes are valid for hub/Kharej scenarios.
        return bool(self.local_ip and self.network_secret and self.port and self.rpc_port and self.interface_name)

    def validate(self, manager: Optional["EasyTierConfigManager"] = None) -> List[str]:
        errors: List[str] = []
        try:
            ipaddress.ip_interface(self.local_ip)
        except Exception:
            # EasyTier often accepts bare IPv4. Validate bare IP too.
            try:
                ipaddress.ip_address(self.local_ip)
            except Exception:
                errors.append("local_ip is not a valid IP address")
        if not re.match(r"^[a-zA-Z0-9_.-]{1,15}$", self.interface_name):
            errors.append("interface_name must be 1-15 chars and contain only letters, digits, dot, dash or underscore")
        if not 1 <= self.port <= 65535:
            errors.append("port must be between 1 and 65535")
        if not 1 <= self.rpc_port <= 65535:
            errors.append("rpc_port must be between 1 and 65535")
        if self.port == self.rpc_port:
            errors.append("port and rpc_port must be different")
        for peer in self.peers:
            if not peer.get("host"):
                errors.append("peer host is empty")
            if not 1 <= int(peer.get("port", self.port)) <= 65535:
                errors.append(f"peer port is invalid for {peer.get('host')}")
        if manager:
            conflicts = manager.find_conflicts(self)
            errors.extend(conflicts)
        return errors

    def peer_urls(self) -> List[str]:
        urls = []
        for peer in self.peers:
            protocol = peer.get("protocol") or self.default_protocol
            host = str(peer.get("host"))
            port = int(peer.get("port") or self.port)
            if ":" in host and not host.startswith("["):
                host = f"[{host}]"
            urls.append(f"{protocol}://{host}:{port}")
        return urls

    def get_command_args(self) -> List[str]:
        args = [
            str(easytier_binary()),
            "-i", self.local_ip,
            "--hostname", self.hostname,
            "--network-secret", self.network_secret,
            "--default-protocol", self.default_protocol,
            "--multi-thread",
            "--dev-name", self.interface_name,
            "--rpc-portal", f"127.0.0.1:{self.rpc_port}",
        ]
        if self.enable_listeners:
            args.extend(["--listeners", f"tcp://[::]:{self.port}", f"tcp://0.0.0.0:{self.port}"])
        peer_urls = self.peer_urls()
        if peer_urls:
            args.append("--peers")
            args.extend(peer_urls)
        return args

    def get_command_string(self) -> str:
        return _quote_cmd(self.get_command_args())

    def to_dict(self) -> Dict[str, Any]:
        data = dict(self._config)
        data["peers"] = self.peers
        data["peer_urls"] = self.peer_urls()
        data["command"] = self.get_command_string()
        return data


class EasyTierManager:
    def __init__(self, config: EasyTierConfig) -> None:
        self.config = config
        self.service_name = f"vortexl2-easytier-{config.name}"

    def _run_command(self, cmd: str, timeout: int = 30) -> Tuple[bool, str, str]:
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            return False, "", "Command timed out"
        except Exception as exc:
            return False, "", str(exc)

    def check_easytier_installed(self) -> bool:
        return easytier_binary().exists() and os.access(easytier_binary(), os.X_OK)

    def check_tunnel_exists(self) -> bool:
        success, _, _ = self._run_command(f"ip link show {shlex.quote(self.config.interface_name)}")
        return success

    def _service_path(self) -> Path:
        return Path(f"/etc/systemd/system/{self.service_name}.service")

    def _create_service_file(self) -> Tuple[bool, str]:
        errors = self.config.validate(EasyTierConfigManager())
        if errors:
            return False, "Config validation failed: " + "; ".join(errors)
        content = f"""[Unit]
Description=VortexL2 EasyTier Tunnel - {self.config.name}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={self.config.get_command_string()}
Restart=on-failure
RestartSec=5
StartLimitIntervalSec=60
StartLimitBurst=5
# EasyTier needs network administration privileges to create tunnel devices.
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_BIND_SERVICE

[Install]
WantedBy=multi-user.target
"""
        try:
            path = self._service_path()
            path.write_text(content, encoding="utf-8")
            os.chmod(path, 0o644)
            self._run_command("systemctl daemon-reload")
            return True, f"Service file created: {self.service_name}"
        except Exception as exc:
            return False, f"Failed to create service: {exc}"

    def start_tunnel(self) -> Tuple[bool, str]:
        if not self.check_easytier_installed():
            return False, f"EasyTier binary not found. Expected: {easytier_binary()}"
        if not self.config.is_configured():
            return False, "Tunnel is not fully configured"
        success, msg = self._create_service_file()
        if not success:
            return False, msg
        self._run_command(f"systemctl enable {shlex.quote(self.service_name)}")
        success, _, stderr = self._run_command(f"systemctl restart {shlex.quote(self.service_name)}")
        if not success:
            return False, f"Failed to start tunnel: {stderr}"
        return True, f"EasyTier tunnel '{self.config.name}' started"

    def stop_tunnel(self) -> Tuple[bool, str]:
        self._run_command(f"systemctl stop {shlex.quote(self.service_name)}")
        self._run_command(f"systemctl disable {shlex.quote(self.service_name)}")
        return True, f"EasyTier tunnel '{self.config.name}' stopped"

    def restart_tunnel(self) -> Tuple[bool, str]:
        success, msg = self._create_service_file()
        if not success:
            return False, msg
        success, _, stderr = self._run_command(f"systemctl restart {shlex.quote(self.service_name)}")
        if not success:
            return False, f"Failed to restart tunnel: {stderr}"
        return True, f"EasyTier tunnel '{self.config.name}' restarted"

    def get_status(self) -> Tuple[bool, str]:
        success, stdout, _ = self._run_command(f"systemctl is-active {shlex.quote(self.service_name)}")
        if success and stdout.strip() == "active":
            return True, "Running"
        return False, "Stopped"

    def get_logs(self, lines: int = 80) -> str:
        _, stdout, stderr = self._run_command(f"journalctl -u {shlex.quote(self.service_name)} -n {int(lines)} --no-pager", timeout=10)
        return stdout or stderr

    def get_peer_info(self) -> List[Dict[str, Any]]:
        cli_bin = easytier_cli_binary()
        if not cli_bin.exists():
            return []
        commands = [
            f"{shlex.quote(str(cli_bin))} --rpc-portal 127.0.0.1:{self.config.rpc_port} peer",
            f"{shlex.quote(str(cli_bin))} peer --rpc-portal 127.0.0.1:{self.config.rpc_port}",
            f"{shlex.quote(str(cli_bin))} peer",
        ]
        stdout = ""
        for command in commands:
            success, stdout, _ = self._run_command(command, timeout=10)
            if success and stdout:
                break
        if not stdout:
            return []
        peers: List[Dict[str, Any]] = []
        for raw in stdout.splitlines():
            line = raw.strip()
            if not line or any(c in line for c in "┌├└─┬┴┼"):
                continue
            if "ipv4" in line.lower() and "hostname" in line.lower():
                continue
            if line.startswith("│"):
                parts = [p.strip() for p in line.split("│") if p.strip()]
                if len(parts) >= 2:
                    peers.append({
                        "ipv4": parts[0],
                        "hostname": parts[1],
                        "cost": parts[2] if len(parts) > 2 else None,
                        "latency": parts[3] if len(parts) > 3 else None,
                        "loss": parts[4] if len(parts) > 4 else None,
                        "rx": parts[5] if len(parts) > 5 else None,
                        "tx": parts[6] if len(parts) > 6 else None,
                        "tunnel": parts[7] if len(parts) > 7 else None,
                        "nat": parts[8] if len(parts) > 8 else None,
                    })
        return peers

    def full_setup(self) -> Tuple[bool, str]:
        return self.start_tunnel()

    def full_teardown(self) -> Tuple[bool, str]:
        self.stop_tunnel()
        path = self._service_path()
        if path.exists():
            path.unlink()
            self._run_command("systemctl daemon-reload")
        return True, f"EasyTier tunnel '{self.config.name}' removed"


class EasyTierConfigManager:
    def __init__(self) -> None:
        TUNNELS_DIR.mkdir(parents=True, exist_ok=True)

    def list_tunnels(self) -> List[str]:
        tunnels: List[str] = []
        for f in TUNNELS_DIR.glob("*.yaml"):
            data = _read_yaml(f)
            if data.get("tunnel_type") == "easytier":
                tunnels.append(f.stem)
        return sorted(tunnels)

    def get_tunnel(self, name: str) -> Optional[EasyTierConfig]:
        try:
            safe = _safe_name(name)
        except ValueError:
            return None
        if (TUNNELS_DIR / f"{safe}.yaml").exists():
            return EasyTierConfig(safe)
        return None

    def get_all_tunnels(self) -> List[EasyTierConfig]:
        return [EasyTierConfig(name) for name in self.list_tunnels()]

    def tunnel_exists(self, name: str) -> bool:
        try:
            return (TUNNELS_DIR / f"{_safe_name(name)}.yaml").exists()
        except ValueError:
            return False

    def _used(self, exclude: Optional[str] = None) -> Dict[str, set]:
        used = {"ports": set(), "rpc_ports": set(), "interfaces": set(), "ips": set(), "hostnames": set()}
        for tunnel in self.get_all_tunnels():
            if exclude and tunnel.name == exclude:
                continue
            used["ports"].add(tunnel.port)
            used["rpc_ports"].add(tunnel.rpc_port)
            used["interfaces"].add(tunnel.interface_name)
            used["ips"].add(tunnel.local_ip.split("/")[0])
            used["hostnames"].add(tunnel.hostname)
        return used

    def next_defaults(self, role: str = "node") -> Dict[str, Any]:
        """Return safe defaults for the next EasyTier profile.

        The upstream VortexL2 script uses these EasyTier side defaults:
        - IRAN:   tunnel IP 10.155.155.1, hostname iran
        - KHAREJ: tunnel IP 10.155.155.2, hostname kharej

        This panel keeps the same role-based defaults, but if a value is
        already used on the same machine it automatically chooses the next
        free port, RPC port, interface and IP so the second tunnel can start.
        """
        role_u = str(role or "node").upper()
        used = self._used()

        index = 1
        while True:
            port = 2070 + index - 1
            rpc_port = 15888 + index - 1
            iface = f"tun{index}"
            if port not in used["ports"] and rpc_port not in used["rpc_ports"] and iface not in used["interfaces"]:
                break
            index += 1

        if role_u in {"IRAN", "IR", "NODE_IRAN"}:
            hostname = "iran" if "iran" not in used["hostnames"] else f"iran{index}"
            # First IRAN matches the original script: 10.155.155.1
            ip_candidates = ["10.155.155.1"] + [f"10.155.155.{n}" for n in range(3, 255, 2)]
            remote_forward_ip = "10.155.155.2"
            role_clean = "IRAN"
        elif role_u in {"KHAREJ", "HUB", "OUTSIDE", "KH"}:
            hostname = "kharej" if "kharej" not in used["hostnames"] else f"kharej{index}"
            # First KHAREJ matches the original script: 10.155.155.2
            ip_candidates = ["10.155.155.2"] + [f"10.155.155.{n}" for n in range(4, 255, 2)]
            remote_forward_ip = "10.155.155.1"
            role_clean = "KHAREJ"
        else:
            hostname = f"node{index}"
            ip_candidates = [f"10.155.{154 + index}.1"] + [f"10.155.{154 + n}.1" for n in range(index + 1, index + 64)]
            remote_forward_ip = None
            role_clean = "NODE"

        local_ip = next((ip for ip in ip_candidates if ip not in used["ips"]), ip_candidates[-1])
        return {
            "index": index,
            "role": role_clean,
            "port": port,
            "rpc_port": rpc_port,
            "interface_name": iface,
            "local_ip": local_ip,
            "hostname": hostname,
            "remote_forward_ip": remote_forward_ip,
        }

    def create_tunnel(self, name: str, role: str = "node") -> EasyTierConfig:
        safe = _safe_name(name)
        defaults = self.next_defaults(role)
        cfg = EasyTierConfig(safe, auto_save=False)
        cfg._config.update({
            "name": safe,
            "role": defaults["role"],
            "hostname": defaults["hostname"],
            "interface_name": defaults["interface_name"],
            "local_ip": defaults["local_ip"],
            "port": defaults["port"],
            "rpc_port": defaults["rpc_port"],
            "remote_forward_ip": defaults["remote_forward_ip"],
        })
        return cfg

    def create_mesh_profile(
        self,
        name: str,
        role: str,
        local_ip: Optional[str] = None,
        peers: Optional[List[Any]] = None,
        network_secret: str = "vortexl2",
        port: Optional[int] = None,
        rpc_port: Optional[int] = None,
        remote_forward_ip: Optional[str] = None,
    ) -> EasyTierConfig:
        cfg = self.create_tunnel(name, role=role)
        role_u = str(role or cfg.role).upper()
        if role_u in {"HUB", "OUTSIDE", "KH"}:
            role_u = "KHAREJ"
        elif role_u in {"IR", "NODE_IRAN"}:
            role_u = "IRAN"
        cfg.role = role_u
        if local_ip:
            cfg.local_ip = local_ip
        cfg.network_secret = network_secret
        if port:
            cfg.port = int(port)
        if rpc_port:
            cfg.rpc_port = int(rpc_port)
        if peers:
            cfg.peers = peers
        if remote_forward_ip:
            cfg.remote_forward_ip = remote_forward_ip
        elif not cfg.remote_forward_ip:
            cfg.remote_forward_ip = self.next_defaults(role_u).get("remote_forward_ip")
        errors = cfg.validate(self)
        if errors:
            raise ValueError("; ".join(errors))
        cfg.save()
        return cfg

    def find_conflicts(self, cfg: EasyTierConfig) -> List[str]:
        used = self._used(exclude=cfg.name)
        errors: List[str] = []
        if cfg.port in used["ports"]:
            errors.append(f"port {cfg.port} is already used by another EasyTier tunnel")
        if cfg.rpc_port in used["rpc_ports"]:
            errors.append(f"rpc_port {cfg.rpc_port} is already used by another EasyTier tunnel")
        if cfg.interface_name in used["interfaces"]:
            errors.append(f"interface {cfg.interface_name} is already used by another EasyTier tunnel")
        if cfg.local_ip.split("/")[0] in used["ips"]:
            errors.append(f"local_ip {cfg.local_ip} is already used by another EasyTier tunnel")
        if cfg.hostname in used["hostnames"]:
            errors.append(f"hostname {cfg.hostname} is already used by another EasyTier tunnel")
        return errors

    def delete_tunnel(self, name: str) -> bool:
        tunnel = self.get_tunnel(name)
        if not tunnel:
            return False
        EasyTierManager(tunnel).full_teardown()
        return tunnel.delete()
