"""VTP / VortexL2 Web Panel.

Dependency-light web UI implemented with Python standard library. This edition
uses a sectioned panel and a step-by-step tunnel wizard instead of showing all
features on one crowded page.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import parse_qs, urlparse

from vortexl2 import __version__
from vortexl2.config import CONFIG_DIR, GlobalConfig
from vortexl2.easytier_manager import (
    EasyTierConfigManager,
    EasyTierManager,
    easytier_binary,
    easytier_install_state,
)
from vortexl2.forward import get_forward_mode, set_forward_mode
from vortexl2.haproxy_manager import HAProxyManager

TOKEN_FILE = CONFIG_DIR / "panel_token"


def run(cmd: str, timeout: int = 15) -> Tuple[bool, str]:
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0, (result.stdout.strip() or result.stderr.strip())
    except Exception as exc:
        return False, str(exc)


def get_or_create_token() -> str:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(24)
    TOKEN_FILE.write_text(token + "\n", encoding="utf-8")
    os.chmod(TOKEN_FILE, 0o600)
    return token


def parse_peers(text: str, default_port: int) -> List[Dict[str, Any]]:
    peers = []
    for raw in (text or "").replace(",", "\n").splitlines():
        line = raw.strip()
        if not line:
            continue
        name = None
        if "#" in line:
            line, name = line.split("#", 1)
            line = line.strip()
            name = name.strip() or None
        protocol = "tcp"
        if "://" in line:
            protocol, line = line.split("://", 1)
        host = line
        port = default_port
        if line.count(":") == 1 and not line.startswith("["):
            host, maybe_port = line.rsplit(":", 1)
            if maybe_port.isdigit():
                port = int(maybe_port)
        peers.append({"host": host.strip("[]"), "port": port, "protocol": protocol or "tcp", "name": name})
    return peers


def parse_ports(text: str) -> List[int]:
    ports: List[int] = []
    for port_s in str(text or "").replace(",", "\n").splitlines():
        port_s = port_s.strip()
        if not port_s:
            continue
        port = int(port_s)
        if not 1 <= port <= 65535:
            raise ValueError(f"Port out of range: {port}")
        ports.append(port)
    return sorted(set(ports))


def tunnel_to_payload(name: str) -> Dict[str, Any]:
    cfg = EasyTierConfigManager().get_tunnel(name)
    if not cfg:
        return {}
    active, status = EasyTierManager(cfg).get_status()
    data = cfg.to_dict()
    data.update({"active": active, "status": status})
    return data


def install_easytier_now() -> Tuple[bool, str]:
    state = easytier_install_state()
    if state.get("installed"):
        return True, f"EasyTier already installed: {state.get('core')}"
    installer = "/tmp/vtp-easytier-install.sh"
    commands = [
        f'curl -fsSL "https://github.com/EasyTier/EasyTier/blob/main/script/install.sh?raw=true" -o {installer}',
        f'curl -fsSL "https://raw.githubusercontent.com/EasyTier/EasyTier/main/script/install.sh" -o {installer}',
    ]
    downloaded = False
    last_msg = ""
    for command in commands:
        ok, msg = run(command, timeout=45)
        last_msg = msg
        if ok and Path(installer).exists():
            downloaded = True
            break
    if not downloaded:
        return False, "EasyTier installer download failed: " + last_msg
    ok, msg = run(f"bash {installer} install", timeout=180)
    if not ok:
        return False, "EasyTier installer failed: " + msg
    found = shutil.which("easytier-core")
    if found and found != "/usr/local/bin/easytier-core":
        run(f"ln -sf {found} /usr/local/bin/easytier-core")
    cli = shutil.which("easytier-cli")
    if cli and cli != "/usr/local/bin/easytier-cli":
        run(f"ln -sf {cli} /usr/local/bin/easytier-cli")
    state = easytier_install_state()
    if state.get("installed"):
        return True, f"EasyTier installed: {state.get('core')}"
    return False, f"Installer completed but easytier-core was still not found. Expected: {easytier_binary()}"


class PanelHandler(BaseHTTPRequestHandler):
    server_version = "VTPPanel/4.4"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), fmt % args))

    @property
    def token(self) -> str:
        return self.server.token  # type: ignore[attr-defined]

    @property
    def auth_enabled(self) -> bool:
        return self.server.auth_enabled  # type: ignore[attr-defined]

    def _is_authorized(self) -> bool:
        if not self.auth_enabled:
            return True
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        supplied = self.headers.get("X-Vortex-Token") or self.headers.get("Authorization", "").replace("Bearer ", "")
        if not supplied:
            supplied = qs.get("token", [""])[0]
        cookie = self.headers.get("Cookie", "")
        if not supplied and "vortex_token=" in cookie:
            supplied = cookie.split("vortex_token=", 1)[1].split(";", 1)[0]
        return secrets.compare_digest(str(supplied), self.token)

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            data = json.loads(body)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {k: v[0] if len(v) == 1 else v for k, v in parse_qs(body).items()}

    def _send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_html(self, html: str, status: int = 200) -> None:
        raw = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _require_auth(self) -> bool:
        if self._is_authorized():
            return True
        self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
        return False

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path == "/":
            self._send_html(INDEX_HTML.replace("__VERSION__", __version__))
            return
        if path == "/api/auth/check":
            self._send_json({"ok": self._is_authorized(), "auth_enabled": self.auth_enabled})
            return
        if not self._require_auth():
            return
        if path == "/api/status":
            self.api_status()
        elif path == "/api/tunnels":
            self.api_tunnels()
        elif path.startswith("/api/tunnel/") and path.endswith("/logs"):
            name = path.split("/")[3]
            cfg = EasyTierConfigManager().get_tunnel(name)
            if not cfg:
                self._send_json({"ok": False, "error": "Tunnel not found"}, 404)
                return
            self._send_json({"ok": True, "logs": EasyTierManager(cfg).get_logs()})
        elif path.startswith("/api/tunnel/") and path.endswith("/peers"):
            name = path.split("/")[3]
            cfg = EasyTierConfigManager().get_tunnel(name)
            if not cfg:
                self._send_json({"ok": False, "error": "Tunnel not found"}, 404)
                return
            self._send_json({"ok": True, "peers": EasyTierManager(cfg).get_peer_info()})
        else:
            self._send_json({"ok": False, "error": "Not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path == "/api/login":
            data = self._read_json()
            if (not self.auth_enabled) or secrets.compare_digest(str(data.get("token", "")), self.token):
                raw = json.dumps({"ok": True}, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Set-Cookie", f"vortex_token={self.token}; Path=/; SameSite=Lax")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            else:
                self._send_json({"ok": False, "error": "Token اشتباه است"}, 403)
            return
        if not self._require_auth():
            return
        data = self._read_json()
        try:
            if path == "/api/tunnel/create":
                self.api_create_tunnel(data)
            elif path == "/api/easytier/install":
                ok, msg = install_easytier_now()
                self._send_json({"ok": ok, "message": msg, "state": easytier_install_state()})
            elif path.startswith("/api/tunnel/"):
                parts = path.split("/")
                name = parts[3] if len(parts) > 3 else ""
                action = parts[4] if len(parts) > 4 else ""
                self.api_tunnel_action(name, action, data)
            elif path == "/api/forward-mode":
                mode = str(data.get("mode", "none"))
                set_forward_mode(mode)
                if mode == "haproxy":
                    ok, msg = HAProxyManager().apply()
                    self._send_json({"ok": ok, "message": msg, "mode": mode})
                    return
                run("systemctl stop haproxy")
                self._send_json({"ok": True, "message": "Forwarding خاموش شد", "mode": mode})
            else:
                self._send_json({"ok": False, "error": "Not found"}, 404)
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, 400)

    def api_status(self) -> None:
        cfg = GlobalConfig()
        ok_panel, panel_status = run("systemctl is-active vortexl2-panel")
        ok_forward, forward_status = run("systemctl is-active vortexl2-forward-daemon")
        ok_haproxy, haproxy_status = run("systemctl is-active haproxy")
        easy_state = easytier_install_state()
        easy_ver = "not found"
        if easy_state.get("installed"):
            ok_easy, easy_msg = run(f"{easytier_binary()} --version", timeout=5)
            easy_ver = easy_msg if ok_easy and easy_msg else str(easy_state.get("core"))
        hap = HAProxyManager()
        forward_plan = hap.forwarding_plan()
        if not forward_plan and get_forward_mode() == "haproxy":
            haproxy_label = "ready / no forwarded ports"
        else:
            haproxy_label = haproxy_status if ok_haproxy else "stopped"
        self._send_json({
            "ok": True,
            "version": __version__,
            "global": cfg.to_dict(),
            "forward_mode": get_forward_mode(),
            "forward_plan": forward_plan,
            "services": {
                "panel": panel_status if ok_panel else "unknown/stopped",
                "forward_daemon": forward_status if ok_forward else "unknown/stopped",
                "haproxy": haproxy_label,
                "easytier": easy_ver,
            },
            "easytier": easy_state,
        })

    def api_tunnels(self) -> None:
        manager = EasyTierConfigManager()
        tunnels = [tunnel_to_payload(name) for name in manager.list_tunnels()]
        defaults = manager.next_defaults()
        role_defaults = {
            "IRAN": manager.next_defaults("IRAN"),
            "KHAREJ": manager.next_defaults("KHAREJ"),
            "NODE": manager.next_defaults("NODE"),
        }
        self._send_json({"ok": True, "tunnels": tunnels, "defaults": defaults, "role_defaults": role_defaults})

    def api_create_tunnel(self, data: Dict[str, Any]) -> None:
        """Create, persist, and then try to start an EasyTier tunnel.

        The important behavior for the web panel is that configuration saving is
        independent from service startup. On real servers EasyTier/systemd/HAProxy
        can fail for environmental reasons, but the newly created tunnel must
        still appear in the management page so the user can edit it, view the
        generated command, install EasyTier, or retry Start.
        """
        manager = EasyTierConfigManager()
        name = str(data.get("name") or "").strip()
        if not name:
            raise ValueError("نام تونل الزامی است")
        if manager.tunnel_exists(name):
            raise ValueError("این نام تونل قبلاً وجود دارد")
        role = str(data.get("role") or "NODE").upper()
        if role in {"HUB", "OUTSIDE", "KH"}:
            role = "KHAREJ"
        elif role in {"IR", "NODE_IRAN"}:
            role = "IRAN"
        defaults = manager.next_defaults(role)
        port = int(data.get("port") or defaults["port"])
        peers = data.get("peers")
        if isinstance(peers, str):
            peers = parse_peers(peers, port)
        elif not isinstance(peers, list):
            peers = []

        cfg = manager.create_mesh_profile(
            name=name,
            role=role,
            local_ip=str(data.get("local_ip") or defaults["local_ip"]),
            peers=peers,
            network_secret=str(data.get("network_secret") or "vortexl2"),
            port=port,
            rpc_port=int(data.get("rpc_port") or defaults["rpc_port"]),
            remote_forward_ip=(str(data.get("remote_forward_ip") or "").strip() or defaults.get("remote_forward_ip") or None),
        )

        saved_message = f"Tunnel '{cfg.name}' ذخیره شد"
        forwarded_ports_error = None
        if data.get("forwarded_ports"):
            try:
                cfg.forwarded_ports = parse_ports(str(data.get("forwarded_ports")))
                if not cfg.remote_forward_ip:
                    cfg.remote_forward_ip = defaults.get("remote_forward_ip")
            except Exception as exc:
                forwarded_ports_error = str(exc)

        started = False
        start_message = "Start اجرا نشد"
        if data.get("autostart", True):
            try:
                started, start_message = EasyTierManager(cfg).start_tunnel()
            except Exception as exc:
                start_message = f"خطا هنگام اجرای سرویس: {exc}"

        haproxy_ok = None
        haproxy_message = None
        if get_forward_mode() == "haproxy" and cfg.forwarded_ports:
            try:
                haproxy_ok, haproxy_message = HAProxyManager().apply()
            except Exception as exc:
                haproxy_ok, haproxy_message = False, f"HAProxy apply failed: {exc}"

        parts = [saved_message]
        if started:
            parts.append("EasyTier اجرا شد")
        else:
            parts.append(start_message)
        if forwarded_ports_error:
            parts.append("خطای ذخیره پورت‌ها: " + forwarded_ports_error)
        if haproxy_message:
            parts.append("HAProxy: " + haproxy_message)

        self._send_json({
            "ok": True,
            "saved": True,
            "started": started,
            "start_message": start_message,
            "haproxy_ok": haproxy_ok,
            "haproxy_message": haproxy_message,
            "ports_error": forwarded_ports_error,
            "message": " | ".join(parts),
            "tunnel": tunnel_to_payload(cfg.name),
        })

    def api_tunnel_action(self, name: str, action: str, data: Dict[str, Any]) -> None:
        manager = EasyTierConfigManager()
        cfg = manager.get_tunnel(name)
        if not cfg:
            self._send_json({"ok": False, "error": "Tunnel not found"}, 404)
            return
        et = EasyTierManager(cfg)
        if action == "start":
            ok, msg = et.start_tunnel()
        elif action == "stop":
            ok, msg = et.stop_tunnel()
        elif action == "restart":
            ok, msg = et.restart_tunnel()
        elif action == "delete":
            ok = manager.delete_tunnel(name)
            msg = "Tunnel حذف شد" if ok else "حذف انجام نشد"
            if get_forward_mode() == "haproxy":
                HAProxyManager().apply()
            self._send_json({"ok": ok, "message": msg})
            return
        elif action == "ports":
            cfg.forwarded_ports = parse_ports(str(data.get("forwarded_ports", "")))
            cfg.remote_forward_ip = str(data.get("remote_forward_ip") or cfg.remote_forward_ip or "").strip() or None
            ok, msg = True, "پورت‌ها ذخیره شدند"
            if get_forward_mode() == "haproxy":
                ok, msg = HAProxyManager().apply()
        elif action == "peers":
            cfg.peers = parse_peers(str(data.get("peers", "")), cfg.port)
            ok, msg = et.restart_tunnel() if data.get("restart", True) else (True, "Peerها ذخیره شدند")
        else:
            self._send_json({"ok": False, "error": "Unknown action"}, 404)
            return
        self._send_json({"ok": ok, "message": msg, "tunnel": tunnel_to_payload(name)})


INDEX_HTML = r'''<!doctype html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>VTP Web Panel</title>
  <style>
    :root{--bg:#070b18;--card:#111936;--card2:#0a1126;--muted:#91a2c7;--text:#eef3ff;--primary:#755cff;--ok:#27d17c;--bad:#ff5d6c;--warn:#ffca3a;--line:#263764}
    *{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top,#1d2856 0,#0b1020 42%,#060914 100%);color:var(--text);font-family:Tahoma,Vazirmatn,Arial,sans-serif;min-height:100vh}.wrap{max-width:1260px;margin:0 auto;padding:24px}.top{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:18px}.brand{display:flex;align-items:center;gap:14px}.logo{width:50px;height:50px;border-radius:18px;background:linear-gradient(135deg,#7c5cff,#20d6ff);display:grid;place-items:center;font-weight:900;box-shadow:0 15px 40px #0008}.muted{color:var(--muted)}.layout{display:grid;grid-template-columns:255px 1fr;gap:18px}.side{position:sticky;top:20px;align-self:start}.card{background:linear-gradient(180deg,#121b38,#0e152d);border:1px solid var(--line);border-radius:22px;padding:18px;box-shadow:0 20px 60px #0005}.nav button{display:block;width:100%;text-align:right;margin-bottom:8px;background:transparent;border:1px solid var(--line);color:var(--text);border-radius:14px;padding:13px;cursor:pointer;font-family:inherit}.nav button.active{background:var(--primary);border-color:transparent}.page{display:none}.page.active{display:block}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.grid2{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}.metric{background:var(--card2);border:1px solid var(--line);border-radius:18px;padding:14px}.metric b{display:block;font-size:12px;color:var(--muted);margin-bottom:6px}.metric span{font-size:16px}.row{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}.row3{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.steps{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 18px}.step{border:1px solid var(--line);border-radius:999px;padding:8px 12px;color:var(--muted)}.step.on{background:#222d5b;color:white;border-color:#5867b8}label{display:block;font-size:13px;color:var(--muted);margin-bottom:6px}input,select,textarea{width:100%;border:1px solid #2d3c70;background:#0a1023;color:var(--text);border-radius:14px;padding:12px;font-family:inherit;outline:none}textarea{min-height:98px;resize:vertical}button{border:0;border-radius:14px;padding:11px 14px;background:var(--primary);color:white;font-weight:700;cursor:pointer;font-family:inherit}button.secondary{background:#243058}button.danger{background:#aa2637}button.ok{background:#13794a}button.warn{background:#9d7410}.btns{display:flex;gap:8px;flex-wrap:wrap}.pill{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);background:#0b1228;border-radius:999px;padding:6px 10px;color:var(--muted);font-size:12px}.status-ok{color:var(--ok)}.status-bad{color:var(--bad)}.tunnel{border:1px solid var(--line);border-radius:18px;padding:14px;margin-bottom:12px;background:#0a1023}.tunnel-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.code{direction:ltr;text-align:left;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;background:#060a16;border:1px solid #202b52;border-radius:14px;padding:10px;white-space:pre-wrap;overflow:auto;color:#c6d3ff}.toast{position:fixed;bottom:20px;left:20px;background:#111934;border:1px solid var(--line);padding:14px 16px;border-radius:16px;max-width:520px;display:none;box-shadow:0 16px 60px #0008}.login{max-width:460px;margin:11vh auto}.hide{display:none}.hint{border:1px solid #36508e;background:#0d1733;border-radius:16px;padding:12px;color:#c9d6ff}.warnbox{border:1px solid #7a5e20;background:#2a210c;border-radius:16px;padding:12px;color:#ffdf7a}.select-card{background:#0a1023;border:1px solid #31477f;border-radius:18px;padding:16px}.select-card b{font-size:18px}.select-card p{min-height:52px}.mini{font-size:12px;color:#99aad0}.required{color:#ffca3a}@media(max-width:950px){.layout,.grid,.grid2,.row,.row3{grid-template-columns:1fr}.top{align-items:flex-start;flex-direction:column}.side{position:static}}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="top">
      <div class="brand"><div class="logo">VTP</div><div><h1 style="margin:0">پنل گرافیکی VTP</h1><div class="muted">نسخه __VERSION__ — ساخت و مدیریت تونل بدون کامند</div></div></div>
      <div class="btns"><button class="secondary" onclick="loadAll()">بروزرسانی</button><button class="secondary" onclick="logout()">خروج</button></div>
    </div>

    <div id="login" class="card login hide">
      <h2>ورود به پنل</h2>
      <p class="muted">توکن پنل داخل <span dir="ltr">/etc/vortexl2/panel_token</span> ذخیره شده است.</p>
      <label>Token</label><input id="token" dir="ltr" placeholder="VTP token" />
      <div style="height:12px"></div><button onclick="login()">ورود</button>
    </div>

    <div id="app" class="layout hide">
      <aside class="card side nav">
        <button class="active" data-page="dashboard" onclick="showPage('dashboard',this)">۱. وضعیت کلی</button>
        <button data-page="wizard" onclick="showPage('wizard',this)">۲. ساخت تونل مرحله‌ای</button>
        <button data-page="tunnelsPage" onclick="showPage('tunnelsPage',this)">۳. مدیریت تونل‌ها</button>
        <button data-page="forwarding" onclick="showPage('forwarding',this)">۴. Port Forwarding</button>
        <button data-page="diagnostics" onclick="showPage('diagnostics',this)">۵. عیب‌یابی و لاگ</button>
      </aside>

      <main>
        <section id="dashboard" class="page active card">
          <h2>وضعیت کلی سیستم</h2>
          <p class="muted">پنل فقط وضعیت‌های اصلی را نشان می‌دهد. اگر EasyTier نصب نشده باشد از همین بخش نصب خودکار را اجرا کنید.</p>
          <div id="statusCards" class="grid"></div>
          <div id="easyInstallBox" style="margin-top:14px"></div>
        </section>

        <section id="wizard" class="page card">
          <h2>ساخت تونل مرحله‌ای مطابق اسکریپت VortexL2</h2>
          <p class="muted">مراحل این بخش مطابق منوی اصلی اسکریپت است: انتخاب IRAN/KHAREJ، تنظیم IP داخلی و Peer عمومی، سپس Forward و دکمه «ذخیره و اجرا».</p>
          <div class="steps"><span id="s1" class="step on">۱. انتخاب نقش</span><span id="s2" class="step">۲. تنظیمات شبکه</span><span id="s3" class="step">۳. Peer عمومی</span><span id="s4" class="step">۴. ذخیره و اجرا</span></div>

          <div id="w1">
            <h3>مرحله ۱: این سرور IRAN است یا KHAREJ؟</h3>
            <div class="grid2">
              <div class="select-card"><b>IRAN</b><p class="muted">سرور ایران. طبق اسکریپت، IP داخلی پیش‌فرض ایران <span dir="ltr">10.155.155.1</span> است و Peer باید IP عمومی سرور خارج باشد.</p><button onclick="pickScenario('IRAN')">انتخاب IRAN</button></div>
              <div class="select-card"><b>KHAREJ</b><p class="muted">سرور خارج. طبق اسکریپت، IP داخلی پیش‌فرض خارج <span dir="ltr">10.155.155.2</span> است و Peer می‌تواند یک یا چند IP عمومی سرور ایران باشد.</p><button onclick="pickScenario('KHAREJ')">انتخاب KHAREJ</button></div>
            </div>
          </div>

          <div id="w2" class="hide">
            <h3>مرحله ۲: تنظیمات شبکه EasyTier</h3>
            <div class="row3">
              <div><label>نام تونل <span class="required">*</span></label><input id="name" placeholder="iran یا kharej" /></div>
              <div><label>نقش</label><select id="role" onchange="applyRoleDefaults(this.value,true)"><option value="IRAN">IRAN</option><option value="KHAREJ">KHAREJ</option><option value="NODE">NODE معمولی</option></select></div>
              <div><label>Secret شبکه <span class="required">*</span></label><input id="secret" value="vortexl2" /></div>
            </div>
            <div class="row3" style="margin-top:12px">
              <div><label>IP داخلی Tunnel</label><input id="local_ip" dir="ltr" placeholder="10.155.155.1" /></div>
              <div><label>Listen Port</label><input id="port" dir="ltr" type="number" /></div>
              <div><label>RPC Port</label><input id="rpc_port" dir="ltr" type="number" /></div>
            </div>
            <p id="networkHint" class="mini"></p>
            <div class="btns" style="margin-top:14px"><button class="secondary" onclick="wizardStep(1)">قبلی</button><button onclick="wizardStep(3)">بعدی</button></div>
          </div>

          <div id="w3" class="hide">
            <h3>مرحله ۳: Peer عمومی طرف مقابل</h3>
            <p id="peerHint" class="muted"></p>
            <textarea id="peers" dir="ltr" placeholder="KHAREJ_PUBLIC_IP:2070"></textarea>
            <div class="hint" style="margin-top:12px">برای چند سرور ایران، در سمت KHAREJ هر IP عمومی ایران را در یک خط وارد کنید. مثال:<br><span dir="ltr">IRAN1_PUBLIC_IP:2070 # iran1</span><br><span dir="ltr">IRAN2_PUBLIC_IP:2070 # iran2</span></div>
            <div class="btns" style="margin-top:14px"><button class="secondary" onclick="wizardStep(2)">قبلی</button><button onclick="wizardStep(4)">بعدی</button></div>
          </div>

          <div id="w4" class="hide">
            <h3>مرحله ۴: Forward و اجرای نهایی</h3>
            <div class="row">
              <div><label>Remote Forward IP</label><input id="remote_forward_ip" dir="ltr" placeholder="10.155.155.2" /></div>
              <div><label>Forwarded ports</label><input id="forwarded_ports" dir="ltr" placeholder="80,443,2087" /></div>
            </div>
            <p class="muted">اگر Forward نمی‌خواهید، پورت‌ها را خالی بگذارید. دکمه زیر کانفیگ را ذخیره می‌کند، systemd service تونل را می‌سازد و همان لحظه اجرا می‌کند.</p>
            <div id="review" class="code"></div>
            <div class="btns" style="margin-top:14px"><button class="secondary" onclick="wizardStep(3)">قبلی</button><button id="runBtn" class="ok" onclick="createTunnel()">ذخیره و اجرا</button></div><div id="createResult" class="code" style="display:none;margin-top:12px"></div>
          </div>
        </section>

        <section id="tunnelsPage" class="page card">
          <h2>مدیریت تونل‌ها</h2>
          <div id="tunnels"></div>
        </section>

        <section id="forwarding" class="page card">
          <h2>Port Forwarding</h2>
          <p class="muted">اول روی یک Tunnel پورت و Remote Forward IP تعریف کنید، سپس HAProxy را فعال کنید. اگر هیچ listener وجود نداشته باشد، HAProxy به‌صورت امن stop می‌ماند.</p>
          <div id="forwardPlan" class="code">در حال خواندن...</div>
          <div class="btns" style="margin-top:14px"><button onclick="setForward('haproxy')">فعال‌سازی HAProxy</button><button class="secondary" onclick="setForward('none')">خاموش کردن Forwarding</button></div>
        </section>

        <section id="diagnostics" class="page card">
          <h2>عیب‌یابی و لاگ</h2>
          <p class="muted">برای لاگ هر تونل از بخش مدیریت تونل‌ها دکمه «نمایش لاگ» را بزنید.</p>
          <div id="diag" class="code">در حال خواندن...</div>
        </section>
      </main>
    </div>
  </div>
  <div id="toast" class="toast"></div>
<script>
let statusCache=null;
let roleDefaults={};
function qs(id){return document.getElementById(id)}
function toast(msg, ok=true){const t=qs('toast');t.textContent=msg||'';t.style.display='block';t.style.borderColor=ok?'#28d17c':'#ff5d6c';setTimeout(()=>t.style.display='none',6200)}
async function api(path, opts={}){opts.headers=Object.assign({'Content-Type':'application/json','X-Vortex-Token':localStorage.vortexToken||''},opts.headers||{});let r;try{r=await fetch(path,opts)}catch(e){throw new Error('ارتباط با سرویس پنل برقرار نشد')}const text=await r.text();let j={ok:false,error:text||'Invalid response'};try{j=text?JSON.parse(text):j}catch(e){}if(r.status===401){showLogin();throw new Error('Unauthorized')}if(!r.ok && !j.error)j.error='HTTP '+r.status;return j}
function showLogin(){qs('login').classList.remove('hide');qs('app').classList.add('hide')}
function showApp(){qs('login').classList.add('hide');qs('app').classList.remove('hide')}
async function login(){const token=qs('token').value.trim();const j=await api('/api/login',{method:'POST',body:JSON.stringify({token})});if(j.ok){localStorage.vortexToken=token;showApp();loadAll()}else toast(j.error||'ورود ناموفق',false)}
function logout(){localStorage.removeItem('vortexToken');showLogin()}
function showPage(id, btn){document.querySelectorAll('.page').forEach(x=>x.classList.remove('active'));qs(id).classList.add('active');document.querySelectorAll('.nav button').forEach(x=>x.classList.remove('active'));if(btn)btn.classList.add('active')}
async function init(){try{const j=await api('/api/auth/check');if(j.ok || !j.auth_enabled){showApp();loadAll()}else showLogin()}catch(e){showLogin()}}
async function loadAll(){await Promise.allSettled([loadStatus(),loadTunnels()])}
function badgeText(v){return escapeHtml(String(v||''))}
async function loadStatus(){const j=await api('/api/status');if(!j.ok)return;statusCache=j;const e=j.easytier||{};qs('statusCards').innerHTML=`
  <div class="metric"><b>EasyTier</b><span>${e.installed?'نصب شده':'نصب نشده'}</span><div class="muted" dir="ltr">${badgeText(e.core||'')}</div></div>
  <div class="metric"><b>HAProxy</b><span>${badgeText(j.services.haproxy)}</span><div class="muted">Forward mode: ${badgeText(j.forward_mode)}</div></div>
  <div class="metric"><b>Panel</b><span>${badgeText(j.services.panel)}</span><div class="muted">Forward daemon: ${badgeText(j.services.forward_daemon)}</div></div>`;
  qs('easyInstallBox').innerHTML=e.installed?'':`<div class="warnbox"><b>EasyTier نصب نیست.</b><p>بدون EasyTier تونل اجرا نمی‌شود. از همین پنل می‌توانید نصب خودکار را اجرا کنید.</p><button onclick="installEasyTier()">نصب خودکار EasyTier</button></div>`;
  qs('forwardPlan').textContent=JSON.stringify(j.forward_plan||{},null,2)||'{}';
  qs('diag').textContent=JSON.stringify({version:j.version, services:j.services, easytier:j.easytier, forward_mode:j.forward_mode, forward_plan:j.forward_plan},null,2);
}
async function installEasyTier(){toast('نصب EasyTier شروع شد؛ ممکن است کمی طول بکشد...');const j=await api('/api/easytier/install',{method:'POST',body:'{}'});toast(j.message||j.error,j.ok);loadStatus()}
async function loadTunnels(){const j=await api('/api/tunnels');if(!j.ok)return;roleDefaults=j.role_defaults||{};if(!qs('local_ip').value){applyRoleDefaults(qs('role').value||'IRAN',false)}const box=qs('tunnels');if(!j.tunnels.length){box.innerHTML='<p class="muted">هنوز تونلی ساخته نشده. از بخش «ساخت تونل مرحله‌ای» شروع کنید.</p>';return}box.innerHTML=j.tunnels.map(t=>`<div class="tunnel"><div class="tunnel-head"><div><h3>${escapeHtml(t.name)} <span class="${t.active?'status-ok':'status-bad'}">● ${escapeHtml(t.status)}</span></h3><div class="muted">${escapeHtml(t.role||'node')} — ${escapeHtml(t.local_ip)} — ${escapeHtml(t.interface_name)} — listen:${t.port} rpc:${t.rpc_port}</div><div style="margin-top:8px">${(t.peers||[]).map(p=>`<span class="pill" dir="ltr">${escapeHtml(p.protocol||'tcp')}://${escapeHtml(p.host)}:${p.port}</span>`).join(' ')||'<span class="pill">بدون Peer اولیه / Listener</span>'}</div></div><div class="btns"><button class="ok" onclick="act('${t.name}','start')">Start</button><button class="warn" onclick="act('${t.name}','restart')">Restart</button><button class="secondary" onclick="act('${t.name}','stop')">Stop</button><button class="danger" onclick="delTunnel('${t.name}')">Delete</button></div></div><div class="row" style="margin-top:12px"><div><label>Remote Forward IP</label><input id="rfi_${t.name}" dir="ltr" value="${escapeHtml(t.remote_forward_ip||'')}"/><label style="margin-top:8px">Ports</label><input id="ports_${t.name}" dir="ltr" value="${(t.forwarded_ports||[]).join(',')}"/><button class="secondary" style="margin-top:8px" onclick="savePorts('${t.name}')">ذخیره پورت‌ها</button></div><div><label>Peers</label><textarea id="peers_${t.name}" dir="ltr">${(t.peers||[]).map(p=>`${p.protocol||'tcp'}://${p.host}:${p.port}${p.name?' # '+p.name:''}`).join('\n')}</textarea><button class="secondary" style="margin-top:8px" onclick="savePeers('${t.name}')">ذخیره Peerها و ری‌استارت</button></div></div><details style="margin-top:12px"><summary>Command</summary><div class="code">${escapeHtml(t.command||'')}</div></details><div class="btns" style="margin-top:10px"><button class="secondary" onclick="logs('${t.name}')">نمایش لاگ</button><button class="secondary" onclick="peers('${t.name}')">Peer Stats</button></div><div id="out_${t.name}" class="code" style="display:none;margin-top:10px"></div></div>`).join('')}
function escapeHtml(s){return String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function applyRoleDefaults(role, overwrite=false){const r=(role||'IRAN').toUpperCase();const d=roleDefaults[r]||{};if(overwrite||!qs('local_ip').value)qs('local_ip').value=d.local_ip||'';if(overwrite||!qs('port').value)qs('port').value=d.port||2070;if(overwrite||!qs('rpc_port').value)qs('rpc_port').value=d.rpc_port||15888;if(overwrite||!qs('remote_forward_ip').value)qs('remote_forward_ip').value=d.remote_forward_ip||'';if(!qs('name').value||overwrite){qs('name').value=r==='KHAREJ'?'kharej':'iran'}if(r==='IRAN'){qs('peerHint').innerHTML='برای IRAN، IP عمومی سرور KHAREJ را وارد کنید. مثال: <span dir="ltr">KHAREJ_PUBLIC_IP:2070 # kharej</span>';qs('peers').placeholder='KHAREJ_PUBLIC_IP:2070 # kharej';qs('networkHint').innerHTML='پیش‌فرض مطابق اسکریپت: IRAN = <span dir="ltr">10.155.155.1</span> و Remote Forward = <span dir="ltr">10.155.155.2</span>'}else if(r==='KHAREJ'){qs('peerHint').innerHTML='برای KHAREJ، IP عمومی سرور IRAN را وارد کنید. برای چند ایران، هر IP را در یک خط بنویسید.';qs('peers').placeholder='IRAN1_PUBLIC_IP:2070 # iran1\nIRAN2_PUBLIC_IP:2070 # iran2';qs('networkHint').innerHTML='پیش‌فرض مطابق اسکریپت: KHAREJ = <span dir="ltr">10.155.155.2</span> و Remote Forward = <span dir="ltr">10.155.155.1</span>'}else{qs('peerHint').textContent='Peerها را به صورت HOST:PORT وارد کنید.';qs('networkHint').textContent='NODE معمولی برای سناریوهای سفارشی است.'}}
function pickScenario(role){qs('role').value=role;applyRoleDefaults(role,true);wizardStep(2)}
function wizardStep(n){[1,2,3,4].forEach(i=>{qs('w'+i).classList.toggle('hide',i!==n);qs('s'+i).classList.toggle('on',i===n)});if(n===4)reviewWizard()}
function reviewWizard(){const data={name:qs('name').value,role:qs('role').value,local_ip:qs('local_ip').value,port:qs('port').value,rpc_port:qs('rpc_port').value,secret:qs('secret').value?'***':'',peers:qs('peers').value,remote_forward_ip:qs('remote_forward_ip').value,forwarded_ports:qs('forwarded_ports').value,action:'save config + create systemd service + start tunnel'};qs('review').textContent=JSON.stringify(data,null,2)}
async function createTunnel(){
  reviewWizard();
  const btn=qs('runBtn');
  const oldText=btn?btn.textContent:'';
  const body={name:qs('name').value.trim(),role:qs('role').value,network_secret:qs('secret').value,local_ip:qs('local_ip').value.trim(),port:qs('port').value,rpc_port:qs('rpc_port').value,peers:qs('peers').value,remote_forward_ip:qs('remote_forward_ip').value.trim(),forwarded_ports:qs('forwarded_ports').value,autostart:true};
  if(!body.name){toast('نام تونل الزامی است',false);wizardStep(2);return}
  if(btn){btn.disabled=true;btn.textContent='در حال ذخیره و اجرا...'}
  let j={ok:false,error:'درخواست ارسال نشد'};
  try{
    j=await api('/api/tunnel/create',{method:'POST',body:JSON.stringify(body)});
    toast(j.message||j.error,j.ok);
    const out=qs('createResult');if(out){out.style.display='block';out.textContent=JSON.stringify(j,null,2)}
  }catch(e){
    toast(e.message||'خطا در ارتباط با پنل',false);
    const out=qs('createResult');if(out){out.style.display='block';out.textContent=e.message||String(e)}
  }finally{
    if(btn){btn.disabled=false;btn.textContent=oldText||'ذخیره و اجرا'}
    await loadAll().catch(()=>{});
  }
  if(j.ok||j.saved){
    ['name','peers','forwarded_ports'].forEach(i=>qs(i).value='');
    applyRoleDefaults(qs('role').value,true);
    wizardStep(1);
    showPage('tunnelsPage',document.querySelector('[data-page="tunnelsPage"]'));
  }
}
async function act(name,action){const j=await api(`/api/tunnel/${name}/${action}`,{method:'POST',body:'{}'});toast(j.message||j.error,j.ok);loadAll()}
async function delTunnel(name){if(!confirm('حذف شود؟ '+name))return;await act(name,'delete')}
async function savePorts(name){const j=await api(`/api/tunnel/${name}/ports`,{method:'POST',body:JSON.stringify({forwarded_ports:qs('ports_'+name).value,remote_forward_ip:qs('rfi_'+name).value})});toast(j.message||j.error,j.ok);loadAll()}
async function savePeers(name){const j=await api(`/api/tunnel/${name}/peers`,{method:'POST',body:JSON.stringify({peers:qs('peers_'+name).value,restart:true})});toast(j.message||j.error,j.ok);loadAll()}
async function logs(name){const j=await api(`/api/tunnel/${name}/logs`);const o=qs('out_'+name);o.style.display='block';o.textContent=j.logs||j.error||''}
async function peers(name){const j=await api(`/api/tunnel/${name}/peers`);const o=qs('out_'+name);o.style.display='block';o.textContent=JSON.stringify(j.peers||[],null,2)}
async function setForward(mode){const j=await api('/api/forward-mode',{method:'POST',body:JSON.stringify({mode})});toast(j.message||j.error,j.ok);loadStatus()}
init();
</script>
</body>
</html>'''


def main(argv: List[str] | None = None) -> int:
    cfg = GlobalConfig()
    parser = argparse.ArgumentParser(description="VTP Web Panel")
    parser.add_argument("--host", default=cfg.panel_host)
    parser.add_argument("--port", type=int, default=cfg.panel_port)
    parser.add_argument("--no-auth", action="store_true")
    args = parser.parse_args(argv)
    token = get_or_create_token()
    server = ThreadingHTTPServer((args.host, args.port), PanelHandler)
    server.token = token  # type: ignore[attr-defined]
    server.auth_enabled = cfg.panel_auth and not args.no_auth  # type: ignore[attr-defined]
    print(f"VTP panel listening on http://{args.host}:{args.port}")
    print(f"Panel token: {token}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
