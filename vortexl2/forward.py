"""Forwarding mode helpers.

The original project imported ForwardManager from this module.  This compatibility
class now maps to the configured forwarding backend and prevents ImportError.
"""
from __future__ import annotations

from typing import Any

from vortexl2.config import GlobalConfig
from vortexl2.haproxy_manager import HAProxyManager


def get_forward_mode() -> str:
    return GlobalConfig().forward_mode


def set_forward_mode(mode: str) -> None:
    GlobalConfig().forward_mode = mode


def get_forward_manager(config: Any = None) -> Any:
    mode = get_forward_mode()
    if mode == "haproxy":
        return HAProxyManager(config)
    if mode == "socat":
        try:
            from vortexl2.socat_manager import SocatManager
            return SocatManager(config)
        except Exception:
            return NullForwardManager(config, reason="Socat manager is unavailable")
    return NullForwardManager(config)


class NullForwardManager:
    def __init__(self, config: Any = None, reason: str = "Forwarding is disabled") -> None:
        self.config = config
        self.reason = reason

    def add_forward(self, port: int):
        if self.config and hasattr(self.config, "add_port"):
            self.config.add_port(int(port))
            return True, "Port saved, but forwarding is disabled"
        return False, self.reason

    def remove_forward(self, port: int):
        if self.config and hasattr(self.config, "remove_port"):
            self.config.remove_port(int(port))
            return True, "Port removed"
        return False, self.reason

    def apply(self):
        return True, self.reason


class ForwardManager:
    """Backward-compatible facade used by the older CLI code."""

    def __init__(self, config: Any = None) -> None:
        self.impl = get_forward_manager(config)

    def add_forward(self, port: int):
        return self.impl.add_forward(port)

    def remove_forward(self, port: int):
        return self.impl.remove_forward(port)

    def apply(self):
        return self.impl.apply()
