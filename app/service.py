"""Zarządzanie klientami VPN: dodawanie, usuwanie, wyłączanie, konfiguracje."""
from __future__ import annotations

import ipaddress
import json
import re
import threading
from typing import Any

from . import config, wgconf
from .store import Store

MODES = {
    "full": "Cały ruch przez dom",
    "lan": "Tylko sieć domowa",
}


class ServiceError(ValueError):
    pass


def _clean_name(name: str) -> str:
    name = " ".join((name or "").split())
    if not name:
        raise ServiceError("Podaj nazwę klienta")
    if len(name) > 60:
        raise ServiceError("Nazwa może mieć najwyżej 60 znaków")
    return name


def _slug(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip("-")
    return (slug or "klient")[:40]


def _peer_to_json(peer: wgconf.Peer) -> dict[str, Any]:
    return {
        "public_key": peer.public_key,
        "preshared_key": peer.preshared_key,
        "allowed_ips": peer.allowed_ips,
        "extra": peer.extra,
        "leading": peer.leading,
        "inner": peer.inner,
    }


def _peer_from_json(data: dict[str, Any]) -> wgconf.Peer:
    return wgconf.Peer(
        public_key=data["public_key"],
        preshared_key=data.get("preshared_key"),
        allowed_ips=data.get("allowed_ips", ""),
        extra=[tuple(x) for x in data.get("extra", [])],
        leading=list(data.get("leading", [])),
        inner=list(data.get("inner", [])),
    )


class ClientService:
    def __init__(self, store: Store, backend):
        self.store = store
        self.backend = backend
        self.lock = threading.RLock()

    # ------------------------------------------------------------ ustawienia
    def settings(self) -> dict[str, Any]:
        s = self.store
        return {
            "endpoint": s.get_setting("endpoint", config.DEFAULT_ENDPOINT or ""),
            "dns": s.get_setting("dns", config.DEFAULT_DNS),
            "lan_subnet": s.get_setting("lan_subnet", config.LAN_SUBNET),
            "keepalive": int(s.get_setting("keepalive", str(config.DEFAULT_KEEPALIVE)) or 0),
            "default_mode": s.get_setting("default_mode", "full"),
            "mtu": s.get_setting("mtu", ""),
        }

    def update_settings(self, data: dict[str, Any]) -> dict[str, Any]:
        current = self.settings()
        if "endpoint" in data:
            endpoint = (data["endpoint"] or "").strip()
            if endpoint and not re.fullmatch(r"(\[[0-9a-fA-F:]+\]|[A-Za-z0-9.-]+):\d{1,5}", endpoint):
                raise ServiceError("Adres serwera wpisz jako host:port, np. vpn.duckdns.org:51820")
            current["endpoint"] = endpoint
        if "dns" in data:
            dns = ", ".join(x.strip() for x in str(data["dns"] or "").split(",") if x.strip())
            for item in dns.split(", ") if dns else []:
                try:
                    ipaddress.ip_address(item)
                except ValueError as exc:
                    raise ServiceError(f"Niepoprawny adres DNS: {item}") from exc
            current["dns"] = dns
        if "lan_subnet" in data:
            try:
                current["lan_subnet"] = str(ipaddress.ip_network(str(data["lan_subnet"]).strip(), strict=False))
            except ValueError as exc:
                raise ServiceError("Niepoprawna sieć domowa, np. 192.168.1.0/24") from exc
        if "keepalive" in data:
            try:
                keepalive = int(data["keepalive"] or 0)
            except (TypeError, ValueError) as exc:
                raise ServiceError("Keepalive musi być liczbą") from exc
            if not 0 <= keepalive <= 600:
                raise ServiceError("Keepalive musi być między 0 a 600 sekund")
            current["keepalive"] = keepalive
        if "default_mode" in data:
            if data["default_mode"] not in MODES:
                raise ServiceError("Nieznany tryb")
            current["default_mode"] = data["default_mode"]
        if "mtu" in data:
            mtu = str(data["mtu"] or "").strip()
            if mtu and (not mtu.isdigit() or not 1280 <= int(mtu) <= 1500):
                raise ServiceError("MTU musi być liczbą od 1280 do 1500 (albo puste)")
            current["mtu"] = mtu
        for key, value in current.items():
            self.store.set_setting(key, str(value))
        self.store.event("settings", "Zmieniono ustawienia serwera")
        return current

    # ------------------------------------------------------------ konfiguracja
    def load(self) -> wgconf.WgConfig:
        if not config.WG_CONF.exists():
            raise ServiceError(f"Nie znaleziono pliku {config.WG_CONF}")
        return wgconf.load(config.WG_CONF)

    def apply(self, conf: wgconf.WgConfig) -> None:
        wgconf.save(config.WG_CONF, conf)
        self.backend.sync(conf)

    def vpn_network(self, conf: wgconf.WgConfig) -> ipaddress.IPv4Interface:
        for addr in conf.addresses:
            try:
                iface = ipaddress.ip_interface(addr)
            except ValueError:
                continue
            if iface.version == 4:
                return iface
        raise ServiceError("W [Interface] brakuje adresu IPv4 (Address)")

    def server_public_key(self, conf: wgconf.WgConfig | None = None) -> str | None:
        state = self.backend.dump()
        if state.public_key:
            return state.public_key
        conf = conf or self.load()
        return wgconf.pubkey(conf.private_key) if conf.private_key else None

    def _used_addresses(self, conf: wgconf.WgConfig) -> set[ipaddress.IPv4Address]:
        used: set[ipaddress.IPv4Address] = set()
        for addr in conf.addresses:
            try:
                used.add(ipaddress.ip_interface(addr).ip)
            except ValueError:
                pass
        for peer in conf.peers:
            for a in peer.addresses():
                try:
                    net = ipaddress.ip_network(a, strict=False)
                except ValueError:
                    continue
                if net.version == 4 and net.num_addresses <= 256:
                    used.update(net)
        for row in self.store.clients():
            try:
                used.add(ipaddress.ip_interface(row["address"]).ip)
            except ValueError:
                pass
        return used

    def _allocate(self, conf: wgconf.WgConfig) -> ipaddress.IPv4Address:
        iface = self.vpn_network(conf)
        used = self._used_addresses(conf)
        for host in iface.network.hosts():
            if host not in used:
                return host
        raise ServiceError("Brak wolnych adresów w sieci VPN")

    # ------------------------------------------------------------ synchronizacja
    def reconcile(self) -> None:
        """Dopasowuje bazę do pliku wg0.conf (np. po ręcznej edycji pliku)."""
        with self.lock:
            try:
                conf = self.load()
            except ServiceError:
                return
            known = {row["public_key"]: row for row in self.store.clients()}
            for peer in conf.peers:
                if peer.public_key in known:
                    row = known[peer.public_key]
                    if not row["enabled"]:
                        self.store.update_client(peer.public_key, enabled=1, peer_json=None)
                    continue
                name = peer.name
                if not name:
                    for line in peer.leading:
                        text = line.lstrip("#; ").strip()
                        if text:
                            name = text[:60]
                            break
                address = next((a for a in peer.addresses() if a.endswith("/32")), peer.addresses()[0] if peer.addresses() else "")
                self.store.insert_client({
                    "public_key": peer.public_key,
                    "name": name or f"Klient {address.split('/')[0]}",
                    "preshared_key": peer.preshared_key,
                    "address": address,
                    "imported": 1,
                    "mode": "full",
                })
                self.store.event("client", f"Wykryto istniejącego klienta {address}", peer.public_key)
            in_conf = {p.public_key for p in conf.peers}
            for pk, row in known.items():
                if row["enabled"] and pk not in in_conf:
                    # Ktoś usunął peera ręcznie z pliku: zachowujemy go jako wyłączonego.
                    peer = wgconf.Peer(public_key=pk, preshared_key=row["preshared_key"], allowed_ips=row["address"])
                    peer.set_name(row["name"])
                    self.store.update_client(pk, enabled=0, peer_json=_peer_to_json(peer))

    # ------------------------------------------------------------ operacje
    def create(self, name: str, note: str = "", mode: str | None = None, dns: str | None = None) -> dict[str, Any]:
        name = _clean_name(name)
        mode = mode or self.settings()["default_mode"]
        if mode not in MODES:
            raise ServiceError("Nieznany tryb ruchu")
        with self.lock:
            conf = self.load()
            if any(row["name"].lower() == name.lower() for row in self.store.clients()):
                raise ServiceError("Klient o tej nazwie już istnieje")
            address = f"{self._allocate(conf)}/32"
            private_key = wgconf.genkey()
            public_key = wgconf.pubkey(private_key)
            psk = wgconf.genpsk()
            peer = wgconf.Peer(public_key=public_key, preshared_key=psk, allowed_ips=address)
            peer.set_name(name)
            conf.peers.append(peer)
            self.apply(conf)
            self.store.insert_client({
                "public_key": public_key,
                "name": name,
                "note": (note or "").strip()[:300],
                "private_key": private_key,
                "preshared_key": psk,
                "address": address,
                "mode": mode,
                "dns": (dns or "").strip() or None,
            })
            self.store.event("client", f"Dodano klienta „{name}” ({address})", public_key)
            return self.store.client(public_key)

    def get(self, public_key: str) -> dict[str, Any]:
        row = self.store.client(public_key)
        if not row:
            raise ServiceError("Nie ma takiego klienta")
        return row

    def update(self, public_key: str, data: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            row = self.get(public_key)
            fields: dict[str, Any] = {}
            if "name" in data and data["name"] is not None:
                name = _clean_name(data["name"])
                if any(r["name"].lower() == name.lower() and r["public_key"] != public_key for r in self.store.clients()):
                    raise ServiceError("Klient o tej nazwie już istnieje")
                fields["name"] = name
            if "note" in data and data["note"] is not None:
                fields["note"] = str(data["note"]).strip()[:300]
            if "mode" in data and data["mode"] is not None:
                if data["mode"] not in MODES:
                    raise ServiceError("Nieznany tryb ruchu")
                fields["mode"] = data["mode"]
            if "dns" in data:
                fields["dns"] = (data["dns"] or "").strip() or None
            enabled = data.get("enabled")
            conf = self.load()
            changed_conf = False
            if "name" in fields and row["enabled"]:
                peer = conf.find(public_key)
                if peer:
                    peer.set_name(fields["name"])
                    changed_conf = True
            if enabled is not None and bool(enabled) != bool(row["enabled"]):
                if enabled:
                    peer = _peer_from_json(json.loads(row["peer_json"])) if row["peer_json"] else wgconf.Peer(
                        public_key=public_key, preshared_key=row["preshared_key"], allowed_ips=row["address"])
                    peer.set_name(fields.get("name", row["name"]))
                    if not conf.find(public_key):
                        conf.peers.append(peer)
                    fields.update(enabled=1, peer_json=None)
                    self.store.event("client", f"Włączono klienta „{row['name']}”", public_key)
                else:
                    peer = conf.remove(public_key)
                    if peer is None:
                        peer = wgconf.Peer(public_key=public_key, preshared_key=row["preshared_key"], allowed_ips=row["address"])
                    fields.update(enabled=0, peer_json=_peer_to_json(peer))
                    self.store.event("client", f"Wyłączono klienta „{row['name']}”", public_key)
                changed_conf = True
            if changed_conf:
                self.apply(conf)
            if "name" in fields and fields["name"] != row["name"]:
                self.store.event("client", f"Zmieniono nazwę „{row['name']}” → „{fields['name']}”", public_key)
            self.store.update_client(public_key, **fields)
            return self.get(public_key)

    def delete(self, public_key: str) -> None:
        with self.lock:
            row = self.get(public_key)
            conf = self.load()
            if conf.remove(public_key):
                self.apply(conf)
            self.store.delete_client(public_key)
            self.store.event("client", f"Usunięto klienta „{row['name']}” ({row['address']})", public_key)

    def regenerate(self, public_key: str) -> dict[str, Any]:
        """Nowe klucze dla klienta (stara konfiguracja przestaje działać)."""
        with self.lock:
            row = self.get(public_key)
            conf = self.load()
            private_key = wgconf.genkey()
            new_pub = wgconf.pubkey(private_key)
            psk = wgconf.genpsk()
            peer = conf.find(public_key)
            if peer:
                peer.public_key = new_pub
                peer.preshared_key = psk
                self.apply(conf)
            peer_json = None
            if not row["enabled"]:
                old = _peer_from_json(json.loads(row["peer_json"])) if row["peer_json"] else wgconf.Peer(allowed_ips=row["address"])
                old.public_key, old.preshared_key = new_pub, psk
                peer_json = _peer_to_json(old)
            self.store.replace_client_key(public_key, new_pub)
            self.store.update_client(new_pub, private_key=private_key, preshared_key=psk, imported=0, peer_json=peer_json)
            self.store.event("client", f"Wygenerowano nowe klucze dla „{row['name']}”", new_pub)
            return self.get(new_pub)

    def client_config(self, public_key: str) -> tuple[str, str]:
        row = self.get(public_key)
        if not row["private_key"]:
            raise ServiceError("Ten klient został dodany poza panelem i panel nie zna jego klucza prywatnego. "
                               "Użyj „Nowe klucze”, żeby wygenerować dla niego nową konfigurację.")
        settings = self.settings()
        if not settings["endpoint"]:
            raise ServiceError("Najpierw ustaw adres serwera (Ustawienia → Adres serwera)")
        conf = self.load()
        server_pub = self.server_public_key(conf)
        if not server_pub:
            raise ServiceError("Nie udało się odczytać klucza publicznego serwera")
        vpn = self.vpn_network(conf)
        if row["mode"] == "lan":
            allowed = f"{vpn.network}, {settings['lan_subnet']}"
        else:
            allowed = "0.0.0.0/0, ::/0"
        dns = row["dns"] or settings["dns"]
        lines = [
            "[Interface]",
            f"# {row['name']}",
            f"PrivateKey = {row['private_key']}",
            f"Address = {row['address']}",
        ]
        if dns:
            lines.append(f"DNS = {dns}")
        if settings["mtu"]:
            lines.append(f"MTU = {settings['mtu']}")
        lines += [
            "",
            "[Peer]",
            f"PublicKey = {server_pub}",
        ]
        if row["preshared_key"]:
            lines.append(f"PresharedKey = {row['preshared_key']}")
        lines += [
            f"Endpoint = {settings['endpoint']}",
            f"AllowedIPs = {allowed}",
        ]
        if settings["keepalive"]:
            lines.append(f"PersistentKeepalive = {settings['keepalive']}")
        return "\n".join(lines) + "\n", f"{_slug(row['name'])}.conf"
