"""Basic L2TPv3 manager kept for compatibility with the original project."""
from __future__ import annotations

import shlex
import subprocess
from typing import Tuple

from vortexl2.config import TunnelConfig


class TunnelManager:
    def __init__(self, config: TunnelConfig) -> None:
        self.config = config

    def _run(self, cmd: str) -> Tuple[bool, str, str]:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()

    def install_prerequisites(self) -> Tuple[bool, str]:
        cmds = [
            "modprobe l2tp_core || true",
            "modprobe l2tp_netlink || true",
            "modprobe l2tp_eth || true",
            "sysctl -w net.ipv4.ip_forward=1",
        ]
        out = []
        ok_all = True
        for cmd in cmds:
            ok, stdout, stderr = self._run(cmd)
            ok_all = ok_all and ok
            out.append(stdout or stderr or cmd)
        return ok_all, "\n".join(out)

    def full_setup(self) -> Tuple[bool, str]:
        c = self.config
        if not c.is_configured():
            return False, "L2TPv3 tunnel is not fully configured"
        self.full_teardown(ignore_errors=True)
        encap = f"encap {c.encap_type}"
        udp = f"udp_sport {c.udp_port} udp_dport {c.udp_port}" if c.encap_type == "udp" else ""
        cmds = [
            f"ip l2tp add tunnel tunnel_id {c.tunnel_id} peer_tunnel_id {c.peer_tunnel_id} {encap} local {shlex.quote(c.local_ip)} remote {shlex.quote(c.remote_ip)} {udp}",
            f"ip l2tp add session tunnel_id {c.tunnel_id} session_id {c.session_id} peer_session_id {c.peer_session_id}",
            f"ip link set {shlex.quote(c.interface_name)} up",
            f"ip addr add {shlex.quote(c.interface_ip)} dev {shlex.quote(c.interface_name)} || true",
        ]
        errors = []
        for cmd in cmds:
            ok, _, stderr = self._run(cmd)
            if not ok:
                errors.append(stderr or cmd)
        if errors:
            return False, "\n".join(errors)
        return True, f"L2TPv3 tunnel '{c.name}' is up on {c.interface_name}"

    def full_teardown(self, ignore_errors: bool = False) -> Tuple[bool, str]:
        c = self.config
        cmds = [
            f"ip link set {shlex.quote(c.interface_name)} down || true",
            f"ip l2tp del session tunnel_id {c.tunnel_id} session_id {c.session_id} || true",
            f"ip l2tp del tunnel tunnel_id {c.tunnel_id} || true",
        ]
        for cmd in cmds:
            self._run(cmd)
        return True, f"L2TPv3 tunnel '{c.name}' removed"
