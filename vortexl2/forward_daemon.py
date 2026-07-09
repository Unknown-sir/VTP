"""VortexL2 forwarding daemon."""
from __future__ import annotations

import subprocess
import time

from vortexl2.config import GlobalConfig
from vortexl2.haproxy_manager import HAProxyManager


def run(cmd: str) -> None:
    subprocess.run(cmd, shell=True, capture_output=True, text=True)


def main() -> int:
    last_mode = None
    last_hash = None
    while True:
        cfg = GlobalConfig()
        mode = cfg.forward_mode
        if mode == "haproxy":
            text = HAProxyManager().generate_config()
            current_hash = hash(text)
            if mode != last_mode or current_hash != last_hash:
                HAProxyManager().apply()
                last_hash = current_hash
        else:
            if last_mode != mode:
                run("systemctl stop haproxy")
        last_mode = mode
        time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(main())
