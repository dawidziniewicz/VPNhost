"""Aktywne połączenia klientów VPN z tablicy conntrack jądra."""
from __future__ import annotations

import ipaddress
import random
import socket
import time
from concurrent.futures import ThreadPoolExecutor

from . import config

PORT_NAMES = {
    20: "FTP", 21: "FTP", 22: "SSH", 25: "SMTP", 53: "DNS", 80: "HTTP", 110: "POP3", 123: "NTP",
    143: "IMAP", 443: "HTTPS", 465: "SMTPS", 587: "SMTP", 853: "DNS-TLS", 993: "IMAPS", 995: "POP3S",
    1194: "OpenVPN", 3478: "STUN", 5222: "XMPP", 5223: "Apple Push", 5228: "Google Push",
    8080: "HTTP", 8443: "HTTPS", 19302: "STUN", 51820: "WireGuard",
}


class ReverseDns:
    def __init__(self):
        self.cache: dict[str, tuple[str | None, float]] = {}
        self.pending: set[str] = set()
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="rdns")

    def _resolve(self, ip: str) -> None:
        try:
            name = socket.gethostbyaddr(ip)[0]
        except Exception:
            name = None
        self.cache[ip] = (name, time.time())
        self.pending.discard(ip)

    def get(self, ip: str) -> str | None:
        hit = self.cache.get(ip)
        if hit and time.time() - hit[1] < 3600:
            return hit[0]
        if ip not in self.pending and len(self.pending) < 64:
            self.pending.add(ip)
            self.pool.submit(self._resolve, ip)
        return hit[0] if hit else None


def _parse_line(line: str) -> dict | None:
    parts = line.split()
    if len(parts) < 6 or parts[0] != "ipv4":
        return None
    proto = parts[2]
    try:
        timeout = int(parts[4])
    except ValueError:
        timeout = None
    state = None
    if proto == "tcp" and "=" not in parts[5]:
        state = parts[5]
    seen: dict[str, list[str]] = {}
    flags = []
    for token in parts[5:]:
        if "=" in token:
            key, _, value = token.partition("=")
            seen.setdefault(key, []).append(value)
        elif token.startswith("["):
            flags.append(token.strip("[]"))

    def get(key: str, idx: int) -> str | None:
        values = seen.get(key, [])
        return values[idx] if len(values) > idx else None

    def num(key: str, idx: int) -> int:
        value = get(key, idx)
        return int(value) if value and value.isdigit() else 0

    return {
        "proto": proto,
        "state": state,
        "timeout": timeout,
        "src": get("src", 0),
        "dst": get("dst", 0),
        "sport": num("sport", 0),
        "dport": num("dport", 0),
        "bytes_out": num("bytes", 0),
        "bytes_in": num("bytes", 1),
        "packets_out": num("packets", 0),
        "packets_in": num("packets", 1),
        "flags": flags,
    }


class ConntrackReader:
    def __init__(self):
        self.rdns = ReverseDns()
        self.error: str | None = None
        self.mock_conns: list[dict] = []

    def read(self, vpn_net: ipaddress.IPv4Network | None) -> list[dict]:
        if config.MOCK:
            return self._mock(vpn_net)
        if vpn_net is None:
            return []
        try:
            text = config.CONNTRACK_PATH.read_text()
        except FileNotFoundError:
            self.error = "Brak /proc/net/nf_conntrack (moduł nf_conntrack niezaładowany)"
            return []
        except PermissionError:
            self.error = "Brak uprawnień do /proc/net/nf_conntrack (kontener musi działać jako root w sieci hosta)"
            return []
        self.error = None
        out = []
        for line in text.splitlines():
            entry = _parse_line(line)
            if not entry or not entry["src"]:
                continue
            try:
                src = ipaddress.ip_address(entry["src"])
                dst = ipaddress.ip_address(entry["dst"])
            except ValueError:
                continue
            if src not in vpn_net or dst in vpn_net:
                continue
            entry["host"] = self.rdns.get(entry["dst"]) if not dst.is_private else None
            entry["service"] = PORT_NAMES.get(entry["dport"])
            entry["local"] = dst.is_private
            out.append(entry)
        return out

    def _mock(self, vpn_net) -> list[dict]:
        hosts = [
            ("142.250.186.206", "waw02s22-in-f14.1e100.net", 443, "tcp"),
            ("157.240.201.35", "edge-star-mini-shv-01-waw2.facebook.com", 443, "tcp"),
            ("17.253.53.207", "get-bx.g.aaplimg.com", 443, "tcp"),
            ("1.1.1.1", "one.one.one.one", 53, "udp"),
            ("104.16.249.249", None, 443, "udp"),
            ("192.168.1.10", None, 445, "tcp"),
            ("185.199.108.133", "cdn-185-199-108-133.github.com", 443, "tcp"),
            ("162.159.136.234", None, 443, "tcp"),
        ]
        if not self.mock_conns or random.random() < 0.3:
            clients = [f"10.8.0.{i}" for i in (2, 3)]
            self.mock_conns = []
            for _ in range(random.randint(6, 14)):
                ip, host, port, proto = random.choice(hosts)
                self.mock_conns.append({
                    "proto": proto, "state": "ESTABLISHED" if proto == "tcp" else None,
                    "timeout": random.randint(10, 430000), "src": random.choice(clients), "dst": ip,
                    "sport": random.randint(40000, 65000), "dport": port,
                    "bytes_out": random.randint(1000, 900_000), "bytes_in": random.randint(5000, 40_000_000),
                    "packets_out": random.randint(10, 900), "packets_in": random.randint(10, 30000),
                    "flags": ["ASSURED"], "host": host, "service": PORT_NAMES.get(port),
                    "local": ip.startswith("192.168."),
                })
        return [dict(c) for c in self.mock_conns]
