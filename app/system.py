"""Statystyki serwera z /proc i /sys (kontener działa w sieci hosta)."""
from __future__ import annotations

import os
import platform
import random
import socket
import time
from pathlib import Path

from . import config

SKIP_IFACES = ("lo", "docker", "veth", "br-", "virbr")


def _read(path: str | Path) -> str | None:
    try:
        return Path(path).read_text()
    except OSError:
        return None


class SystemSampler:
    def __init__(self):
        self.prev_cpu: tuple[int, int] | None = None
        self.prev_net: dict[str, tuple[int, int, float]] = {}
        self.mock = config.MOCK or not Path("/proc/stat").exists()
        self.static = self._static_info()

    # ------------------------------------------------------------ dane stałe
    def _static_info(self) -> dict:
        cpu_model = None
        cpuinfo = _read("/proc/cpuinfo") or ""
        for line in cpuinfo.splitlines():
            if line.lower().startswith("model name"):
                cpu_model = line.split(":", 1)[1].strip()
                break
        os_name = None
        for path in (config.OS_RELEASE_PATH, Path("/etc/os-release")):
            text = _read(path)
            if text:
                for line in text.splitlines():
                    if line.startswith("PRETTY_NAME="):
                        os_name = line.split("=", 1)[1].strip().strip('"')
                        break
                if path == config.OS_RELEASE_PATH and os_name:
                    break
        if self.mock:
            cpu_model = cpu_model or "Intel(R) Pentium(R) Silver J5005 CPU @ 1.50GHz (symulacja)"
            os_name = "Debian GNU/Linux 13 (trixie) — symulacja"
        return {
            "hostname": _read("/proc/sys/kernel/hostname").strip() if _read("/proc/sys/kernel/hostname") else socket.gethostname(),
            "cpu_model": cpu_model or platform.processor() or "nieznany",
            "cores": os.cpu_count() or 1,
            "os": os_name or platform.platform(),
            "kernel": platform.release(),
        }

    # ------------------------------------------------------------ pomiary
    def _cpu(self) -> float | None:
        text = _read("/proc/stat")
        if not text:
            return None
        parts = [int(x) for x in text.splitlines()[0].split()[1:]]
        idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
        total = sum(parts[:8])
        result = None
        if self.prev_cpu:
            d_total = total - self.prev_cpu[0]
            d_idle = idle - self.prev_cpu[1]
            if d_total > 0:
                result = round(100 * (1 - d_idle / d_total), 1)
        self.prev_cpu = (total, idle)
        return result

    def _mem(self) -> dict | None:
        text = _read("/proc/meminfo")
        if not text:
            return None
        info = {}
        for line in text.splitlines():
            key, _, rest = line.partition(":")
            info[key] = int(rest.split()[0]) * 1024 if rest.split() else 0
        total = info.get("MemTotal", 0)
        available = info.get("MemAvailable", info.get("MemFree", 0))
        swap_total = info.get("SwapTotal", 0)
        swap_free = info.get("SwapFree", 0)
        return {
            "total": total,
            "used": total - available,
            "percent": round(100 * (total - available) / total, 1) if total else 0,
            "swap_total": swap_total,
            "swap_used": swap_total - swap_free,
        }

    def _disk(self) -> dict | None:
        try:
            st = os.statvfs(config.DISK_PATH)
        except OSError:
            return None
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        used = total - st.f_bfree * st.f_frsize
        return {"total": total, "used": used, "free": free,
                "percent": round(100 * used / total, 1) if total else 0}

    def _temp(self) -> float | None:
        temps = []
        base = Path("/sys/class/hwmon")
        if base.exists():
            for hw in base.iterdir():
                name = (_read(hw / "name") or "").strip()
                if name not in ("coretemp", "k10temp", "zenpower", "cpu_thermal", "acpitz", "soc_thermal"):
                    continue
                for f in hw.glob("temp*_input"):
                    value = _read(f)
                    if value and value.strip().lstrip("-").isdigit():
                        temps.append(int(value) / 1000)
        if not temps:
            for zone in Path("/sys/class/thermal").glob("thermal_zone*"):
                value = _read(zone / "temp")
                if value and value.strip().isdigit():
                    temps.append(int(value) / 1000)
        return round(max(temps), 1) if temps else None

    def _net(self, now: float) -> list[dict]:
        text = _read("/proc/net/dev")
        if not text:
            return []
        out = []
        for line in text.splitlines()[2:]:
            name, _, rest = line.partition(":")
            name = name.strip()
            if name.startswith(SKIP_IFACES):
                continue
            f = rest.split()
            rx, tx = int(f[0]), int(f[8])
            rx_rate = tx_rate = 0.0
            prev = self.prev_net.get(name)
            if prev and now > prev[2]:
                dt = now - prev[2]
                rx_rate = max(0.0, (rx - prev[0]) / dt)
                tx_rate = max(0.0, (tx - prev[1]) / dt)
            self.prev_net[name] = (rx, tx, now)
            out.append({"name": name, "rx_total": rx, "tx_total": tx, "rx_rate": rx_rate, "tx_rate": tx_rate})
        return out

    def _mock(self, now: float, wg_rx: float, wg_tx: float) -> dict:
        cpu = round(random.uniform(2, 9) + (wg_rx + wg_tx) / 2_000_000, 1)
        total_mem = 3_869_000_000
        used = int(total_mem * random.uniform(0.13, 0.16))
        return {
            **self.static,
            "uptime": int(now - 418_000),
            "load": [round(random.uniform(0.0, 0.3), 2) for _ in range(3)],
            "cpu": min(cpu, 100),
            "mem": {"total": total_mem, "used": used, "percent": round(100 * used / total_mem, 1),
                    "swap_total": 0, "swap_used": 0},
            "disk": {"total": 28_900_000_000, "used": 5_480_000_000, "free": 22_000_000_000, "percent": 19.0},
            "temp": round(random.uniform(38, 44), 1),
            "interfaces": [
                {"name": "eno1", "rx_total": 0, "tx_total": 0,
                 "rx_rate": wg_rx * 1.05 + random.uniform(500, 5000), "tx_rate": wg_tx * 1.05 + random.uniform(500, 3000)},
                {"name": config.WG_INTERFACE, "rx_total": 0, "tx_total": 0, "rx_rate": wg_rx, "tx_rate": wg_tx},
            ],
        }

    def sample(self, wg_rx: float = 0, wg_tx: float = 0) -> dict:
        now = time.time()
        if self.mock:
            return self._mock(now, wg_rx, wg_tx)
        uptime_text = _read("/proc/uptime")
        load_text = _read("/proc/loadavg")
        return {
            **self.static,
            "uptime": int(float(uptime_text.split()[0])) if uptime_text else None,
            "load": [float(x) for x in load_text.split()[:3]] if load_text else None,
            "cpu": self._cpu(),
            "mem": self._mem(),
            "disk": self._disk(),
            "temp": self._temp(),
            "interfaces": self._net(now),
        }
