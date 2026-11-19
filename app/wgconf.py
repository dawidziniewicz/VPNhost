"""Odczyt i zapis pliku konfiguracyjnego WireGuarda (wg0.conf).

Sekcja [Interface] jest zachowywana dokładnie tak, jak jest w pliku
(łącznie z PostUp/PostDown i komentarzami). Sekcje [Peer] są parsowane,
żeby panel mógł je dodawać, zmieniać i usuwać.
"""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

NAME_PREFIX = "# vpnhost:"

# Klucze, których `wg syncconf` nie rozumie (obsługuje je tylko wg-quick).
WG_QUICK_ONLY = {"address", "dns", "mtu", "table", "preup", "postup", "predown", "postdown", "saveconfig"}


# ---------------------------------------------------------------- klucze

def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def genkey() -> str:
    raw = bytearray(os.urandom(32))
    raw[0] &= 248
    raw[31] &= 127
    raw[31] |= 64
    return _b64(bytes(raw))


def pubkey(private_key: str) -> str:
    key = X25519PrivateKey.from_private_bytes(base64.b64decode(private_key))
    return _b64(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))


def genpsk() -> str:
    return _b64(os.urandom(32))


def is_key(value: str) -> bool:
    try:
        return len(base64.b64decode(value, validate=True)) == 32
    except Exception:
        return False


# ---------------------------------------------------------------- model

@dataclass
class Peer:
    public_key: str = ""
    preshared_key: str | None = None
    allowed_ips: str = ""
    extra: list[tuple[str, str]] = field(default_factory=list)
    leading: list[str] = field(default_factory=list)   # komentarze nad [Peer]
    inner: list[str] = field(default_factory=list)     # komentarze wewnątrz sekcji

    @property
    def name(self) -> str | None:
        for line in self.leading:
            if line.startswith(NAME_PREFIX):
                return line[len(NAME_PREFIX):].strip() or None
        return None

    def set_name(self, name: str | None) -> None:
        self.leading = [line for line in self.leading if not line.startswith(NAME_PREFIX)]
        if name:
            clean = " ".join(name.split())
            self.leading.append(f"{NAME_PREFIX} {clean}")

    def addresses(self) -> list[str]:
        return [a.strip() for a in self.allowed_ips.split(",") if a.strip()]


@dataclass
class WgConfig:
    preamble: list[str] = field(default_factory=list)
    interface_lines: list[str] = field(default_factory=list)
    peers: list[Peer] = field(default_factory=list)

    # -- odczyt wartości z [Interface]
    def interface_values(self, key: str) -> list[str]:
        out = []
        for raw in self.interface_lines:
            line = raw.strip()
            if not line or line.startswith(("#", ";", "[")) or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip().lower() == key.lower():
                out.append(v.strip())
        return out

    def interface_value(self, key: str) -> str | None:
        values = self.interface_values(key)
        return values[-1] if values else None

    @property
    def addresses(self) -> list[str]:
        out: list[str] = []
        for value in self.interface_values("Address"):
            out.extend(a.strip() for a in value.split(",") if a.strip())
        return out

    @property
    def listen_port(self) -> int | None:
        value = self.interface_value("ListenPort")
        return int(value) if value and value.isdigit() else None

    @property
    def private_key(self) -> str | None:
        return self.interface_value("PrivateKey")

    @property
    def save_config(self) -> bool:
        return (self.interface_value("SaveConfig") or "").lower() == "true"

    def find(self, public_key: str) -> Peer | None:
        return next((p for p in self.peers if p.public_key == public_key), None)

    def remove(self, public_key: str) -> Peer | None:
        peer = self.find(public_key)
        if peer:
            self.peers.remove(peer)
        return peer


# ---------------------------------------------------------------- parser

def parse(text: str) -> WgConfig:
    conf = WgConfig()
    section: str | Peer | None = None
    pending: list[str] = []  # komentarze, które jeszcze nie wiadomo do czego należą

    def flush_pending() -> None:
        if not pending:
            return
        if section == "interface":
            conf.interface_lines.extend(pending)
        elif isinstance(section, Peer):
            section.inner.extend(pending)
        else:
            conf.preamble.extend(pending)
        pending.clear()

    for raw in text.splitlines():
        line = raw.strip()
        lower = line.lower()
        if lower == "[interface]":
            flush_pending()
            section = "interface"
            conf.interface_lines.append(raw)
            continue
        if lower == "[peer]":
            peer = Peer(leading=[p.strip() for p in pending if p.strip()])
            pending.clear()
            conf.peers.append(peer)
            section = peer
            continue
        if line.startswith(("#", ";")):
            pending.append(raw)
            continue
        if not line:
            if section == "interface" and not pending:
                conf.interface_lines.append(raw)
            elif section is None:
                conf.preamble.append(raw)
            continue
        flush_pending()
        if section == "interface":
            conf.interface_lines.append(raw)
        elif isinstance(section, Peer):
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            k = key.lower()
            if k == "publickey":
                section.public_key = value
            elif k == "presharedkey":
                section.preshared_key = value
            elif k == "allowedips":
                section.allowed_ips = f"{section.allowed_ips}, {value}" if section.allowed_ips else value
            else:
                section.extra.append((key, value))
        else:
            conf.preamble.append(raw)
    flush_pending()
    # Komentarze w sekcji peera zostawiamy, ale bez pustych linii.
    for peer in conf.peers:
        peer.inner = [c.strip() for c in peer.inner if c.strip()]
    return conf


def _trim(lines: list[str]) -> list[str]:
    out = list(lines)
    while out and not out[-1].strip():
        out.pop()
    return out


def _render_peer(peer: Peer) -> list[str]:
    lines = list(peer.leading)
    lines.append("[Peer]")
    lines.extend(peer.inner)
    lines.append(f"PublicKey = {peer.public_key}")
    if peer.preshared_key:
        lines.append(f"PresharedKey = {peer.preshared_key}")
    if peer.allowed_ips:
        lines.append(f"AllowedIPs = {peer.allowed_ips}")
    lines.extend(f"{k} = {v}" for k, v in peer.extra)
    return lines


def render(conf: WgConfig) -> str:
    blocks: list[list[str]] = []
    pre = _trim(conf.preamble)
    if pre:
        blocks.append(pre)
    blocks.append(_trim(conf.interface_lines))
    blocks.extend(_render_peer(p) for p in conf.peers)
    return "\n\n".join("\n".join(b) for b in blocks) + "\n"


def render_stripped(conf: WgConfig) -> str:
    """Odpowiednik `wg-quick strip`: tylko to, co rozumie `wg syncconf`."""
    lines = []
    for raw in conf.interface_lines:
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if "=" in line and line.partition("=")[0].strip().lower() in WG_QUICK_ONLY:
            continue
        lines.append(line)
    out = "\n".join(lines) + "\n"
    for peer in conf.peers:
        out += "\n" + "\n".join(_render_peer(Peer(
            public_key=peer.public_key,
            preshared_key=peer.preshared_key,
            allowed_ips=peer.allowed_ips,
            extra=peer.extra,
        ))) + "\n"
    return out


def load(path: Path) -> WgConfig:
    return parse(path.read_text())


def save(path: Path, conf: WgConfig) -> None:
    """Zapis atomowy z kopią zapasową poprzedniej wersji."""
    text = render(conf)
    if path.exists():
        backup = path.with_suffix(path.suffix + ".bak")
        backup.write_text(path.read_text())
        os.chmod(backup, 0o600)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
