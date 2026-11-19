"""Urządzenia w sieci domowej: wykrywanie (ARP), nazwy (DNS, mDNS, NetBIOS), producent po MAC i typ."""
from __future__ import annotations

import ipaddress
import json
import logging
import random
import re
import socket
import struct
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from . import config
from .store import Store

log = logging.getLogger("vpnhost.lan")
MAC_RE = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")
MAX_HOSTS = 1024
NAMES_TTL = 1800          # co ile odświeżać nazwy urządzenia (s)
ARP_SETTLE = 10           # ile czekać po wysłaniu zapytań, aż jądro potwierdzi lub odrzuci wpisy ARP

# Porty sprawdzane na żądanie: pomagają rozpoznać, czym jest urządzenie.
PORTS = {
    21: "FTP", 22: "SSH", 23: "Telnet", 53: "DNS", 80: "WWW", 139: "NetBIOS", 443: "WWW (HTTPS)",
    445: "Udostępnianie plików (SMB)", 515: "Drukarka (LPD)", 548: "Udostępnianie plików Apple (AFP)",
    554: "Strumień wideo (RTSP)", 631: "Drukarka (IPP)", 1400: "Sonos", 1883: "MQTT (smart home)",
    3389: "Pulpit zdalny Windows", 5000: "WWW (5000)", 5001: "WWW (5001)", 5353: "mDNS",
    5900: "VNC / udostępnianie ekranu", 7000: "AirPlay", 8008: "Google Cast", 8009: "Google Cast",
    8080: "WWW (8080)", 8443: "WWW (8443)", 9100: "Drukarka (RAW)", 32400: "Plex", 62078: "iPhone / iPad (synchronizacja)",
}

TYPE_LABELS = {
    "router": "Router", "server": "Serwer", "computer": "Komputer", "phone": "Telefon", "tablet": "Tablet",
    "tv": "Telewizor / odtwarzacz", "speaker": "Głośnik", "printer": "Drukarka", "camera": "Kamera",
    "iot": "Urządzenie smart home", "console": "Konsola", "nas": "Dysk sieciowy (NAS)",
    "network": "Urządzenie sieciowe", "unknown": "Nieznane urządzenie",
}


# ---------------------------------------------------------------- producent po adresie MAC

class Vendors:
    """Baza producentów kart sieciowych (plik `manuf` z Wiresharka, pobierany przy budowie obrazu)."""

    def __init__(self, path: Path):
        self.path = path
        self.blocks: dict[int, dict[str, str]] = {}
        self.loaded = False
        self._lock = threading.Lock()

    def _load(self) -> None:
        with self._lock:
            if self.loaded:
                return
            self.loaded = True
            try:
                text = self.path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                log.warning("Brak bazy producentów MAC (%s): producent nie będzie pokazywany", self.path)
                return
            for line in text.splitlines():
                if not line or line.startswith("#"):
                    continue
                parts = [p.strip() for p in line.split("\t")]
                if len(parts) < 2:
                    continue
                prefix, _, bits = parts[0].partition("/")
                hexes = prefix.replace(":", "").replace("-", "").lower()
                size = int(bits) if bits.isdigit() else 24
                name = parts[2] if len(parts) > 2 and parts[2] else parts[1]
                self.blocks.setdefault(size, {})[hexes[: size // 4]] = name

    def lookup(self, mac: str) -> str | None:
        self._load()
        hexes = mac.replace(":", "").lower()
        for size in sorted(self.blocks, reverse=True):
            hit = self.blocks[size].get(hexes[: size // 4])
            if hit:
                return clean_vendor(hit)
        return None


_SUFFIX = re.compile(r"[\s,.]+(inc|incorporated|corp|corporation|co|ltd|limited|llc|gmbh|ag|sa|sas|s\.a|bv|b\.v|ab|oy|plc|"
                     r"technologies|technology|electronics|international|company|communication|communications)\.?$",
                     re.IGNORECASE)


def clean_vendor(name: str) -> str:
    name = name.strip()
    for _ in range(4):
        new = _SUFFIX.sub("", name).strip(" ,.")
        if new == name or len(new) < 2:
            break
        name = new
    return name


def is_random_mac(mac: str) -> bool:
    """Adres „lokalnie administrowany”: telefony i komputery używają go jako prywatnego adresu Wi‑Fi."""
    try:
        return bool(int(mac[:2], 16) & 0x02)
    except ValueError:
        return False


# ---------------------------------------------------------------- tablice jądra

def parse_arp(text: str) -> list[dict[str, str]]:
    """Wiersze /proc/net/arp. Flaga 0x2 = adres potwierdzony, 0x0 = urządzenie nie odpowiedziało."""
    out = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 6:
            continue
        ip, _hw, flags, mac, _mask, dev = parts[:6]
        try:
            complete = int(flags, 16) & 0x2
        except ValueError:
            continue
        mac = mac.lower()
        if not complete or mac == "00:00:00:00:00:00" or not MAC_RE.match(mac):
            continue
        out.append({"ip": ip, "mac": mac, "dev": dev})
    return out


def _hex_ip(value: str) -> str:
    return socket.inet_ntoa(struct.pack("<I", int(value, 16)))


def parse_routes(text: str, subnet: ipaddress.IPv4Network) -> tuple[str | None, str | None]:
    """Z /proc/net/route: interfejs sieci domowej i adres bramy (routera)."""
    iface = gateway = None
    default_iface = None
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 8:
            continue
        dev, dest, gw, _flags, *_rest = parts
        mask = parts[7]
        try:
            net = ipaddress.ip_network(f"{_hex_ip(dest)}/{_hex_ip(mask)}", strict=False)
        except ValueError:
            continue
        if net.prefixlen == 0:
            gw_ip = _hex_ip(gw)
            if ipaddress.ip_address(gw_ip) in subnet:
                gateway, default_iface = gw_ip, dev
        elif net.overlaps(subnet) and iface is None:
            iface = dev
    return iface or default_iface, gateway


# ---------------------------------------------------------------- nazwy: DNS, mDNS, NetBIOS

def _encode_name(name: str) -> bytes:
    out = b""
    for label in name.strip(".").split("."):
        raw = label.encode()[:63]
        out += bytes([len(raw)]) + raw
    return out + b"\x00"


def _read_name(data: bytes, pos: int) -> tuple[str, int]:
    labels: list[str] = []
    end = None
    for _ in range(64):
        length = data[pos]
        if length & 0xC0 == 0xC0:
            if end is None:
                end = pos + 2
            pos = ((length & 0x3F) << 8) | data[pos + 1]
            continue
        if length == 0:
            pos += 1
            break
        labels.append(data[pos + 1: pos + 1 + length].decode("utf-8", "replace"))
        pos += 1 + length
    return ".".join(labels), (end if end is not None else pos)


def dns_query(qname: str, qtype: int) -> bytes:
    header = struct.pack(">HHHHHH", random.randint(0, 0xFFFF), 0, 1, 0, 0, 0)
    return header + _encode_name(qname) + struct.pack(">HH", qtype, 1)


def dns_answers(data: bytes, qtype: int) -> list[Any]:
    """Odpowiedzi z pakietu DNS: dla PTR nazwy, dla TXT listy napisów."""
    if len(data) < 12:
        return []
    qd, an, ns, ar = struct.unpack(">HHHH", data[4:12])
    pos = 12
    for _ in range(qd):
        _, pos = _read_name(data, pos)
        pos += 4
    out: list[Any] = []
    for _ in range(an + ns + ar):
        _, pos = _read_name(data, pos)
        rtype, _cls, _ttl, rdlen = struct.unpack(">HHIH", data[pos: pos + 10])
        pos += 10
        rdata_pos = pos
        pos += rdlen
        if rtype != qtype:
            continue
        if rtype == 12:
            out.append(_read_name(data, rdata_pos)[0])
        elif rtype == 16:
            strings, p = [], rdata_pos
            while p < pos:
                n = data[p]
                strings.append(data[p + 1: p + 1 + n].decode("utf-8", "replace"))
                p += 1 + n
            out.append(strings)
    return out


def _udp(ip: str, port: int, payload: bytes, timeout: float) -> bytes | None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        try:
            s.sendto(payload, (ip, port))
            data, _ = s.recvfrom(4096)
            return data
        except OSError:
            return None


def mdns_name(ip: str, timeout: float = 1.0) -> str | None:
    """Zapytanie mDNS wysłane wprost do urządzenia (odpowiadają m.in. iPhone, Mac, drukarki, Chromecast)."""
    rev = ".".join(reversed(ip.split("."))) + ".in-addr.arpa"
    data = _udp(ip, 5353, dns_query(rev, 12), timeout)
    try:
        names = dns_answers(data, 12) if data else []
    except (IndexError, struct.error):
        return None
    return names[0].rstrip(".") if names else None


def mdns_model(hostname: str, ip: str, timeout: float = 1.0) -> str | None:
    """Model urządzenia Apple z rekordu _device-info (np. iPhone15,2, MacBookAir10,1)."""
    short = hostname.removesuffix(".local")
    data = _udp(ip, 5353, dns_query(f"{short}._device-info._tcp.local", 16), timeout)
    try:
        for strings in (dns_answers(data, 16) if data else []):
            for s in strings:
                if s.lower().startswith("model="):
                    return s[6:]
    except (IndexError, struct.error):
        return None
    return None


def nbstat_query() -> bytes:
    name = b"*" + b"\x00" * 15
    encoded = bytes(c for b in name for c in (0x41 + (b >> 4), 0x41 + (b & 0x0F)))
    return struct.pack(">HHHHHH", random.randint(0, 0xFFFF), 0, 1, 0, 0, 0) + b"\x20" + encoded + b"\x00" + struct.pack(">HH", 0x21, 1)


def parse_nbstat(data: bytes) -> str | None:
    """Nazwa komputera z odpowiedzi NetBIOS (Windows, Samba)."""
    try:
        pos = 12
        _, pos = _read_name(data, pos)
        pos += 10                      # typ, klasa, TTL, długość
        count = data[pos]
        pos += 1
        for i in range(count):
            entry = data[pos + i * 18: pos + i * 18 + 18]
            name = entry[:15].decode("ascii", "replace").strip()
            suffix, flags = entry[15], struct.unpack(">H", entry[16:18])[0]
            if suffix == 0x00 and not flags & 0x8000 and name:
                return name
    except (IndexError, struct.error):
        return None
    return None


def netbios_name(ip: str, timeout: float = 1.0) -> str | None:
    data = _udp(ip, 137, nbstat_query(), timeout)
    return parse_nbstat(data) if data else None


def reverse_dns(ip: str) -> str | None:
    try:
        name = socket.gethostbyaddr(ip)[0]
    except (OSError, UnicodeError):
        return None
    return None if name == ip else name


# ---------------------------------------------------------------- rozpoznawanie typu

def _has(text: str, *words: str) -> bool:
    """Długie słowa i słowa z myślnikiem szukamy w całym tekście, krótkie tylko na początku członu nazwy,
    żeby np. „nas” nie pasowało do „jonas-laptop”."""
    tokens = re.split(r"[^a-z0-9]+", text)
    for w in words:
        if len(w) >= 5 or not w.isalnum():
            if w in text:
                return True
        elif any(t.startswith(w) for t in tokens):
            return True
    return False


def classify(dev: dict[str, Any]) -> tuple[str, str]:
    """Zgadywanie typu urządzenia: (klucz typu, opis po polsku)."""
    if dev.get("is_gateway"):
        return "router", "Router (brama do internetu)"
    if dev.get("is_self"):
        return "server", "Ten serwer (VPN i panel)"
    model = (dev.get("model") or "").lower()
    names = " ".join(filter(None, [dev.get("hostname"), dev.get("mdns"), dev.get("netbios")])).lower()
    vendor = (dev.get("vendor") or "").lower()
    ports = set(dev.get("ports") or [])

    if model:
        for key, typ, label in (("iphone", "phone", "iPhone"), ("ipad", "tablet", "iPad"),
                                ("macbook", "computer", "MacBook"), ("imac", "computer", "iMac"),
                                ("macmini", "computer", "Mac mini"), ("mac", "computer", "Mac"),
                                ("appletv", "tv", "Apple TV"), ("audioaccessory", "speaker", "HomePod"),
                                ("watch", "phone", "Apple Watch")):
            if model.startswith(key):
                return typ, label
    rules = (
        (("iphone",), "phone", "iPhone"), (("ipad",), "tablet", "iPad"),
        (("macbook",), "computer", "MacBook"), (("imac",), "computer", "iMac"),
        (("apple-tv", "appletv"), "tv", "Apple TV"), (("homepod",), "speaker", "HomePod"),
        (("galaxy-tab", "tab-s", "-tab"), "tablet", "Tablet z Androidem"),
        (("android", "galaxy", "pixel", "redmi", "oneplus", "huawei-p", "poco", "moto"), "phone", "Telefon z Androidem"),
        (("chromecast", "google-home", "nest"), "tv", "Google Chromecast / Nest"),
        (("firetv", "fire-tv"), "tv", "Amazon Fire TV"), (("echo",), "speaker", "Amazon Echo"),
        (("bravia", "webos", "tizen", "lgwebostv", "smart-tv", "smarttv", "android-tv", "-tv"), "tv", "Telewizor"),
        (("sonos",), "speaker", "Głośnik Sonos"),
        (("printer", "drukar", "epson", "brother", "canon", "laserjet", "officejet", "deskjet", "hp-"), "printer", "Drukarka"),
        (("camera", "kamera", "ipcam", "hikvision", "dahua", "reolink", "tapo-c", "imou"), "camera", "Kamera"),
        (("playstation", "ps4", "ps5", "xbox", "nintendo"), "console", "Konsola do gier"),
        (("synology", "diskstation", "qnap", "nas"), "nas", "Dysk sieciowy (NAS)"),
        (("raspberrypi", "raspberry"), "computer", "Raspberry Pi"),
        (("esp", "tasmota", "shelly", "tuya", "sonoff", "yeelight", "tapo", "smartplug",
          "wled", "zigbee", "hue", "tado", "roborock", "roomba", "vacuum"), "iot", "Urządzenie smart home"),
        (("desktop-", "laptop-", "-pc", "workstation"), "computer", "Komputer z Windows"),
        (("macbook", "mbp", "-mac"), "computer", "Mac"),
    )
    for words, typ, label in rules:
        if _has(names, *words):
            return typ, label

    if 62078 in ports:
        return ("tablet", "iPad") if "ipad" in names else ("phone", "iPhone lub iPad")
    if ports & {9100, 631, 515}:
        return "printer", "Drukarka"
    if 554 in ports:
        return "camera", "Kamera (strumień RTSP)"
    if ports & {8008, 8009}:
        return "tv", "Urządzenie Google Cast (TV / Chromecast)"
    if 1400 in ports:
        return "speaker", "Głośnik Sonos"
    if 3389 in ports or (ports & {139, 445} and dev.get("netbios")):
        return "computer", "Komputer z Windows"
    if 548 in ports or (5900 in ports and "apple" in vendor):
        return "computer", "Mac"

    vendor_rules = (
        (("raspberry",), "computer", "Raspberry Pi"),
        (("espressif", "tuya", "shelly", "itead", "sonoff", "yeelink", "lumi", "signify",
          "philips lighting", "ezviz", "broadlink", "roborock", "irobot", "tado", "wiz connected"), "iot", "Urządzenie smart home"),
        (("hikvision", "dahua", "reolink", "axis comm", "hangzhou"), "camera", "Kamera"),
        (("sonos",), "speaker", "Głośnik Sonos"),
        (("nintendo", "sony interactive", "microsoft xbox"), "console", "Konsola do gier"),
        (("synology", "qnap", "western digital"), "nas", "Dysk sieciowy (NAS)"),
        (("seiko epson", "brother", "canon", "hewlett", "hp inc", "kyocera", "lexmark", "xerox", "ricoh"), "printer", "Drukarka"),
        (("roku", "tcl", "hisense", "vestel", "lg electronics", "vizio", "skyworth", "funai"), "tv", "Telewizor"),
        (("amazon",), "speaker", "Urządzenie Amazon (Echo / Fire TV)"),
        (("google",), "tv", "Urządzenie Google (Chromecast / Nest)"),
        (("sagemcom", "arcadyan", "zte", "technicolor", "zyxel", "ubiquiti", "mikrotik", "netgear", "tenda",
          "mercusys", "cisco", "d-link", "tp-link"), "network", "Urządzenie sieciowe (router / wzmacniacz / AP)"),
        (("intel", "realtek", "liteon", "lite-on", "azurewave", "hon hai", "foxconn", "rivet", "killer",
          "dell", "lenovo", "asustek", "micro-star", "gigabyte", "acer", "pegatron", "chicony", "wistron", "quanta"), "computer", "Komputer"),
        (("apple",), "phone", "Urządzenie Apple"),
        (("samsung",), "phone", "Urządzenie Samsung"),
        (("xiaomi", "oneplus", "oppo", "vivo", "realme", "motorola", "huawei", "honor", "nokia", "hmd global"), "phone", "Telefon"),
    )
    for words, typ, label in vendor_rules:
        if _has(vendor, *words):
            return typ, label
    if dev.get("random_mac"):
        return "phone", "Telefon, tablet lub laptop (prywatny adres Wi‑Fi)"
    if 22 in ports:
        return "computer", "Komputer z Linuksem"
    return "unknown", "Nieznane urządzenie"


# ---------------------------------------------------------------- skaner

def scan_ports(ip: str, timeout: float = 0.6) -> list[int]:
    def probe(port: int) -> int | None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return port if s.connect_ex((ip, port)) == 0 else None
    with ThreadPoolExecutor(max_workers=16) as pool:
        return sorted(p for p in pool.map(probe, [p for p in PORTS if p != 5353]) if p)


class LanScanner:
    def __init__(self, store: Store, subnet_fn):
        self.store = store
        self.subnet_fn = subnet_fn
        self.vendors = Vendors(config.OUI_PATH)
        self.lock = threading.Lock()
        self.scanning = False
        self.scanned_at: float | None = None
        self.error: str | None = None
        self.iface: str | None = None
        self.gateway: str | None = None
        self.self_ip: str | None = None
        self.names_at: dict[str, float] = {}
        self.online: set[str] = set()

    # ------------------------------------------------------------ dane
    def devices(self) -> list[dict[str, Any]]:
        rows = self.store.all("SELECT * FROM lan_devices")
        out = []
        for r in rows:
            r["ports"] = json.loads(r["ports"]) if r["ports"] else None
            r["random_mac"] = is_random_mac(r["mac"])
            r["is_gateway"] = bool(self.gateway and r["ip"] == self.gateway)
            r["is_self"] = bool(self.self_ip and r["ip"] == self.self_ip)
            r["online"] = r["mac"] in self.online
            r["type"], r["type_label"] = classify(r)
            r["port_names"] = {str(p): PORTS.get(p, str(p)) for p in (r["ports"] or [])}
            out.append(r)
        out.sort(key=lambda d: (not d["online"], tuple(int(x) for x in d["ip"].split("."))))
        return out

    def counts(self) -> dict[str, int]:
        total = self.store.one("SELECT COUNT(*) n FROM lan_devices") or {"n": 0}
        return {"online": len(self.online), "total": total["n"]}

    def update(self, mac: str, data: dict[str, Any]) -> dict[str, Any]:
        if not self.store.one("SELECT 1 FROM lan_devices WHERE mac=?", (mac,)):
            raise KeyError(mac)
        fields = {}
        if "name" in data:
            fields["name"] = str(data["name"] or "").strip()[:60]
        if "note" in data:
            fields["note"] = str(data["note"] or "").strip()[:300]
        if fields:
            sets = ",".join(f"{k}=?" for k in fields)
            self.store.run(f"UPDATE lan_devices SET {sets} WHERE mac=?", (*fields.values(), mac))
        return self.device(mac)

    def device(self, mac: str) -> dict[str, Any]:
        for d in self.devices():
            if d["mac"] == mac:
                return d
        raise KeyError(mac)

    def forget(self, mac: str) -> None:
        if mac in self.online:
            raise ValueError("Urządzenie jest teraz w sieci. Można usunąć tylko nieaktywne urządzenia.")
        self.store.run("DELETE FROM lan_devices WHERE mac=?", (mac,))

    def probe_ports(self, mac: str) -> dict[str, Any]:
        dev = self.store.one("SELECT ip FROM lan_devices WHERE mac=?", (mac,))
        if not dev:
            raise KeyError(mac)
        ports = self._mock_ports(mac) if config.MOCK else scan_ports(dev["ip"])
        self.store.run("UPDATE lan_devices SET ports=?, ports_at=? WHERE mac=?", (json.dumps(ports), int(time.time()), mac))
        return self.device(mac)

    # ------------------------------------------------------------ skanowanie
    def scan(self) -> None:
        if not self.lock.acquire(blocking=False):
            with self.lock:       # ktoś już skanuje: poczekaj na wynik
                return
        self.scanning = True
        try:
            found = self._mock_scan() if config.MOCK else self._scan()
            self._save(found)
            self.scanned_at = time.time()
        except Exception as exc:  # skanowanie nie może zatrzymać panelu
            log.exception("Błąd skanowania sieci")
            self.error = str(exc)
        finally:
            self.scanning = False
            self.lock.release()

    def _scan(self) -> list[dict[str, Any]]:
        subnet = ipaddress.ip_network(self.subnet_fn(), strict=False)
        try:
            routes = Path("/proc/net/route").read_text()
        except OSError:
            routes = ""
        self.iface, self.gateway = parse_routes(routes, subnet)
        self.self_ip = self._own_ip(subnet)

        hosts = [str(h) for h in subnet.hosts()][:MAX_HOSTS]
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            for ip in hosts:
                if ip == self.self_ip:
                    continue
                try:
                    s.sendto(b"", (ip, 9))   # wymusza zapytanie ARP; port 9 to „discard”
                except OSError:
                    pass
        time.sleep(ARP_SETTLE)
        try:
            arp = parse_arp(Path("/proc/net/arp").read_text())
        except OSError as exc:
            self.error = f"Nie można odczytać tablicy ARP: {exc}"
            return []
        self.error = None
        found = [a for a in arp if ipaddress.ip_address(a["ip"]) in subnet]
        if self.self_ip and self.iface:
            try:
                mac = Path(f"/sys/class/net/{self.iface}/address").read_text().strip().lower()
                if MAC_RE.match(mac):
                    found.append({"ip": self.self_ip, "mac": mac})
            except OSError:
                pass
        self._resolve_names(found)
        return found

    @staticmethod
    def _own_ip(subnet: ipaddress.IPv4Network) -> str | None:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect((str(next(subnet.hosts())), 9))
                ip = s.getsockname()[0]
            return ip if ipaddress.ip_address(ip) in subnet else None
        except (OSError, StopIteration):
            return None

    def _resolve_names(self, found: list[dict[str, Any]]) -> None:
        now = time.time()
        todo = [d for d in found if now - self.names_at.get(d["mac"], 0) > NAMES_TTL]

        def resolve(d: dict[str, Any]) -> None:
            ip = d["ip"]
            d["hostname"] = reverse_dns(ip)
            d["mdns"] = mdns_name(ip)
            d["netbios"] = netbios_name(ip)
            d["model"] = mdns_model(d["mdns"], ip) if d["mdns"] else None
            self.names_at[d["mac"]] = time.time()

        with ThreadPoolExecutor(max_workers=16, thread_name_prefix="lan-names") as pool:
            list(pool.map(resolve, todo))

    def _save(self, found: list[dict[str, Any]]) -> None:
        now = int(time.time())
        first_scan = not self.store.one("SELECT 1 FROM lan_devices LIMIT 1")
        new = []
        for d in found:
            row = self.store.one("SELECT mac FROM lan_devices WHERE mac=?", (d["mac"],))
            vendor = None if is_random_mac(d["mac"]) else self.vendors.lookup(d["mac"])
            if row:
                sets = {"ip": d["ip"], "last_seen": now, "vendor": vendor}
                for key in ("hostname", "mdns", "netbios", "model"):
                    if key in d and d[key]:
                        sets[key] = d[key]
                cols = ",".join(f"{k}=?" for k in sets)
                self.store.run(f"UPDATE lan_devices SET {cols} WHERE mac=?", (*sets.values(), d["mac"]))
            else:
                self.store.run(
                    "INSERT INTO lan_devices(mac, ip, vendor, hostname, mdns, netbios, model, first_seen, last_seen) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    (d["mac"], d["ip"], vendor, d.get("hostname"), d.get("mdns"), d.get("netbios"), d.get("model"), now, now))
                new.append(d)
        self.online = {d["mac"] for d in found}
        if first_scan and new:
            self.store.event("lan", f"Wykryto {len(new)} urządzeń w sieci domowej")
        else:
            for d in new:
                name = d.get("mdns") or d.get("hostname") or d.get("netbios") or (
                    "prywatny adres Wi‑Fi" if is_random_mac(d["mac"]) else self.vendors.lookup(d["mac"])) or "nieznane"
                self.store.event("lan", f"Nowe urządzenie w sieci: {d['ip']} ({name}, {d['mac']})")

    # ------------------------------------------------------------ symulacja
    _MOCK = [
        ("192.168.1.1", "e8:ad:a6:12:34:01", "funbox.home", None, None, None),
        ("192.168.1.10", "00:11:32:aa:bb:02", "diskstation.home", "DiskStation.local", "DISKSTATION", None),
        ("192.168.1.14", "3c:22:fb:55:66:03", "iPhone-Dawida.home", "iPhone-Dawida.local", None, "iPhone15,2"),
        ("192.168.1.15", "f0:18:98:44:55:04", "MacBook-Air.home", "MacBook-Air.local", None, "MacBookAir10,1"),
        ("192.168.1.21", "ba:7c:1e:90:12:05", None, None, None, None),
        ("192.168.1.30", "24:6f:28:01:02:06", "ESP_0A1B2C.home", None, None, None),
        ("192.168.1.31", "c8:2b:96:11:22:07", "shelly1-AABB.home", None, None, None),
        ("192.168.1.40", "a8:23:fe:33:44:08", "LGwebOSTV.home", "LGwebOSTV.local", None, None),
        ("192.168.1.45", "64:eb:8c:77:88:09", "EPSON-ET2810.home", "EPSON-ET2810.local", None, None),
        ("192.168.1.50", "c4:65:16:99:00:0a", "DESKTOP-K7H2.home", None, "DESKTOP-K7H2", None),
        ("192.168.1.76", "dc:a6:32:12:ab:0b", "vpn.home", None, None, None),
        ("192.168.1.88", "f4:f5:d8:21:43:0c", None, "Chromecast.local", None, None),
    ]

    def _mock_scan(self) -> list[dict[str, Any]]:
        self.iface, self.gateway, self.self_ip = "eno1", "192.168.1.1", "192.168.1.76"
        out = []
        for ip, mac, host, mdns, nb, model in self._MOCK:
            if mac.endswith("05") and random.random() < 0.4:
                continue          # ten telefon czasem jest poza domem
            out.append({"ip": ip, "mac": mac, "hostname": host, "mdns": mdns, "netbios": nb, "model": model})
        return out

    @staticmethod
    def _mock_ports(mac: str) -> list[int]:
        return {"e8:ad:a6:12:34:01": [53, 80, 443], "00:11:32:aa:bb:02": [22, 80, 139, 445, 5000, 5001],
                "64:eb:8c:77:88:09": [80, 443, 631, 9100], "3c:22:fb:55:66:03": [62078],
                "f4:f5:d8:21:43:0c": [8008, 8009], "c4:65:16:99:00:0a": [139, 445, 3389]}.get(mac, [])
