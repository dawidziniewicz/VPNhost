"""Ustawienia panelu czytane ze zmiennych środowiskowych."""
from __future__ import annotations

import os
from pathlib import Path


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _flag(name: str, default: str = "0") -> bool:
    return (_env(name, default) or "").lower() in ("1", "true", "yes", "on")


# Tryb symulacji: bez prawdziwego WireGuarda (do pracy nad panelem lokalnie).
MOCK = _flag("WG_MOCK")

_dev_root = Path(__file__).resolve().parent.parent / "dev-data"

WG_INTERFACE = _env("WG_INTERFACE", "wg0")
WG_CONF_DIR = Path(_env("WG_CONF_DIR", str(_dev_root / "wireguard") if MOCK else "/etc/wireguard"))
WG_CONF = WG_CONF_DIR / f"{WG_INTERFACE}.conf"
DATA_DIR = Path(_env("DATA_DIR", str(_dev_root) if MOCK else "/data"))
DB_PATH = DATA_DIR / "vpnhost.db"

PANEL_HOST = _env("PANEL_HOST", "0.0.0.0")
PANEL_PORT = int(_env("PANEL_PORT", "8090"))

ADMIN_USER = _env("ADMIN_USER", "admin")
ADMIN_PASSWORD = _env("ADMIN_PASSWORD")
SESSION_HOURS = int(_env("SESSION_HOURS", "12"))
COOKIE_SECURE = _flag("COOKIE_SECURE")

# Wartości domyślne dla nowych klientów (można je zmienić w panelu).
DEFAULT_ENDPOINT = _env("WG_ENDPOINT")
DEFAULT_DNS = _env("WG_DNS", "1.1.1.1")
LAN_SUBNET = _env("LAN_SUBNET", "192.168.1.0/24")
DEFAULT_KEEPALIVE = int(_env("WG_KEEPALIVE", "25"))

SAMPLE_INTERVAL = float(_env("SAMPLE_INTERVAL", "2"))
CONNTRACK_INTERVAL = float(_env("CONNTRACK_INTERVAL", "4"))
ONLINE_TIMEOUT = int(_env("ONLINE_TIMEOUT", "180"))
HISTORY_DAYS = int(_env("HISTORY_DAYS", "30"))
LIVE_SECONDS = 600

CONNTRACK_PATH = Path(_env("CONNTRACK_PATH", "/proc/net/nf_conntrack"))
OS_RELEASE_PATH = Path(_env("OS_RELEASE_PATH", "/host/os-release"))
DISK_PATH = Path(_env("DISK_PATH", str(WG_CONF_DIR)))

APP_VERSION = _env("APP_VERSION", "dev")
BUILD_DATE = _env("BUILD_DATE", "")
