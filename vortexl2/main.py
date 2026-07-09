#!/usr/bin/env python3
"""VortexL2 command line entry point."""
from __future__ import annotations

import argparse
import os
import sys

from vortexl2 import __version__
from vortexl2.config import ConfigManager, GlobalConfig
from vortexl2.easytier_manager import EasyTierConfigManager, EasyTierManager, easytier_install_state
from vortexl2.forward import get_forward_mode, set_forward_mode
from vortexl2.haproxy_manager import HAProxyManager
from vortexl2.tunnel import TunnelManager


def check_root() -> None:
    if os.name == "posix" and os.geteuid() != 0:
        print("VortexL2 must be run as root. Use sudo.", file=sys.stderr)
        raise SystemExit(1)


def cmd_apply() -> int:
    cfg = GlobalConfig()
    errors = 0
    if cfg.tunnel_mode == "easytier":
        manager = EasyTierConfigManager()
        tunnels = manager.get_all_tunnels()
        if not tunnels:
            print("No EasyTier tunnels configured")
            return 0
        for tunnel_cfg in tunnels:
            ok, msg = EasyTierManager(tunnel_cfg).start_tunnel()
            print(f"{tunnel_cfg.name}: {msg}")
            if not ok:
                errors += 1
    else:
        manager = ConfigManager()
        tunnels = manager.get_all_tunnels()
        if not tunnels:
            print("No L2TPv3 tunnels configured")
            return 0
        for tunnel_cfg in tunnels:
            ok, msg = TunnelManager(tunnel_cfg).full_setup()
            print(f"{tunnel_cfg.name}: {msg}")
            if not ok:
                errors += 1
    if get_forward_mode() == "haproxy":
        ok, msg = HAProxyManager().apply()
        print(f"HAProxy: {msg}")
        if not ok:
            errors += 1
    return 1 if errors else 0


def cmd_status() -> int:
    print(f"VTP {__version__}")
    print(f"tunnel_mode={GlobalConfig().tunnel_mode} forward_mode={get_forward_mode()}")
    state = easytier_install_state()
    print(f"easytier_installed={state.get('installed')} core={state.get('core')}")
    manager = EasyTierConfigManager()
    for cfg in manager.get_all_tunnels():
        active, status = EasyTierManager(cfg).get_status()
        print(f"- {cfg.name}: {status} ip={cfg.local_ip} if={cfg.interface_name} port={cfg.port} rpc={cfg.rpc_port} peers={len(cfg.peers)}")
    return 0


def cmd_panel(args: argparse.Namespace) -> int:
    from vortexl2.panel import main as panel_main
    argv = []
    if args.host:
        argv.extend(["--host", args.host])
    if args.port:
        argv.extend(["--port", str(args.port)])
    if args.no_auth:
        argv.append("--no-auth")
    return panel_main(argv)


def cmd_create_easytier(args: argparse.Namespace) -> int:
    manager = EasyTierConfigManager()
    peers = []
    for peer in args.peer or []:
        peers.append(peer)
    cfg = manager.create_mesh_profile(
        name=args.name,
        role=args.role,
        local_ip=args.local_ip,
        peers=peers,
        network_secret=args.secret,
        port=args.port,
        rpc_port=args.rpc_port,
        remote_forward_ip=args.remote_forward_ip,
    )
    for port in args.forward_port or []:
        cfg.add_port(int(port))
    if args.start:
        ok, msg = EasyTierManager(cfg).start_tunnel()
        print(msg)
        return 0 if ok else 1
    print(f"Created EasyTier tunnel: {cfg.name}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vtp", description="VTP Tunnel Manager with Web Panel")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("apply", help="Apply all configured tunnels")
    sub.add_parser("status", help="Show service status")

    panel = sub.add_parser("panel", help="Run the web panel")
    panel.add_argument("--host")
    panel.add_argument("--port", type=int)
    panel.add_argument("--no-auth", action="store_true")

    fwd = sub.add_parser("forward-mode", help="Set forwarding mode")
    fwd.add_argument("mode", choices=["none", "haproxy", "socat"])

    create = sub.add_parser("create-easytier", help="Create an EasyTier tunnel from CLI")
    create.add_argument("name")
    create.add_argument("--role", default="node")
    create.add_argument("--local-ip")
    create.add_argument("--peer", action="append")
    create.add_argument("--secret", default="vortexl2")
    create.add_argument("--port", type=int)
    create.add_argument("--rpc-port", type=int)
    create.add_argument("--remote-forward-ip")
    create.add_argument("--forward-port", action="append", type=int)
    create.add_argument("--start", action="store_true")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        args.command = "panel"
    if args.command in {"apply", "create-easytier", "forward-mode"}:
        check_root()
    if args.command == "apply":
        return cmd_apply()
    if args.command == "status":
        return cmd_status()
    if args.command == "panel":
        return cmd_panel(args)
    if args.command == "forward-mode":
        set_forward_mode(args.mode)
        if args.mode == "haproxy":
            ok, msg = HAProxyManager().apply()
            print(msg)
            return 0 if ok else 1
        print(f"Forward mode set to {args.mode}")
        return 0
    if args.command == "create-easytier":
        return cmd_create_easytier(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
