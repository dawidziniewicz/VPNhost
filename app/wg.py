"""Komunikacja z działającym interfejsem WireGuard (lub jego symulacja)."""
from __future__ import annotations

import os
import random
import subprocess
import tempfile
import time
from dataclasses import dataclass

from . import config, wgconf


@dataclass
class PeerState:
    public_key: str
    endpoint: str | None
    allowed_ips: str
    latest_handshake: int
    rx: int  # bajty odebrane od klienta
    tx: int  # bajty wysłane do klienta
    keepalive: int | None


@dataclass
class InterfaceState:
    up: bool
    public_key: str | None
    listen_port: int | None
    peers: list[PeerState]
    error: str | None = None


class WgError(RuntimeError):
    pass


def _none(value: str) -> str | None:
    return None if value in ("(none)", "off", "") else value


class RealBackend:
    def __init__(self, interface: str):
        self.interface = interface

    def _run(self, *args: str) -> str:
        try:
            result = subprocess.run(["wg", *args], capture_output=True, text=True, timeout=10)
        except FileNotFoundError as exc:
            raise WgError("Brak programu `wg` w kontenerze") from exc
        if result.returncode != 0:
            raise WgError(result.stderr.strip() or f"wg {' '.join(args)} zakończył się błędem")
        return result.stdout

    def dump(self) -> InterfaceState:
        try:
            out = self._run("show", self.interface, "dump")
        except WgError as exc:
            return InterfaceState(up=False, public_key=None, listen_port=None, peers=[], error=str(exc))
        lines = [line for line in out.splitlines() if line.strip()]
        if not lines:
            return InterfaceState(up=False, public_key=None, listen_port=None, peers=[])
        head = lines[0].split("\t")
        peers = []
        for line in lines[1:]:
            f = line.split("\t")
            if len(f) < 8:
                continue
            peers.append(PeerState(
                public_key=f[0],
                endpoint=_none(f[2]),
                allowed_ips=f[3] if f[3] != "(none)" else "",
                latest_handshake=int(f[4] or 0),
                rx=int(f[5] or 0),
                tx=int(f[6] or 0),
                keepalive=int(f[7]) if f[7].isdigit() else None,
            ))
        return InterfaceState(
            up=True,
            public_key=_none(head[1]) if len(head) > 1 else None,
            listen_port=int(head[2]) if len(head) > 2 and head[2].isdigit() else None,
            peers=peers,
        )

    def sync(self, conf: wgconf.WgConfig) -> None:
        stripped = wgconf.render_stripped(conf)
        fd, path = tempfile.mkstemp(prefix="wg-sync-", suffix=".conf")
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(stripped)
            os.chmod(path, 0o600)
            self._run("syncconf", self.interface, path)
        finally:
            os.unlink(path)


class MockBackend:
    """Udaje działający WireGuard: czyta peerów z pliku i generuje ruch."""

    def __init__(self, interface: str):
        self.interface = interface
        self.counters: dict[str, list[int]] = {}
        self.handshakes: dict[str, int] = {}
        self.endpoints: dict[str, str] = {}
        self.profile: dict[str, float] = {}
        self._ensure_conf()

    def _ensure_conf(self) -> None:
        if config.WG_CONF.exists():
            return
        config.WG_CONF_DIR.mkdir(parents=True, exist_ok=True)
        server_key = wgconf.genkey()
        demo_key = wgconf.genkey()
        text = (
            "[Interface]\n"
            "Address = 10.8.0.1/24\n"
            "ListenPort = 51820\n"
            f"PrivateKey = {server_key}\n"
            "PostUp = nft add table ip wgnat; nft add chain ip wgnat post '{ type nat hook postrouting priority srcnat; }'; "
            "nft add rule ip wgnat post ip saddr 10.8.0.0/24 oifname \"eno1\" masquerade\n"
            "PostDown = nft delete table ip wgnat\n\n"
            "[Peer]\n"
            f"PublicKey = {wgconf.pubkey(demo_key)}\n"
            f"PresharedKey = {wgconf.genpsk()}\n"
            "AllowedIPs = 10.8.0.2/32\n"
        )
        config.WG_CONF.write_text(text)

    def dump(self) -> InterfaceState:
        conf = wgconf.load(config.WG_CONF)
        now = int(time.time())
        peers = []
        for peer in conf.peers:
            pk = peer.public_key
            if pk not in self.counters:
                self.profile.setdefault(pk, random.choice([0.0, 0.3, 1.0, 2.5]))
                self.counters[pk] = [random.randint(1, 50) * 10**6, random.randint(5, 900) * 10**6]
                self.endpoints[pk] = f"37.47.{random.randint(1, 254)}.{random.randint(1, 254)}:{random.randint(1024, 65000)}"
                self.handshakes[pk] = now - random.randint(5, 100) if self.profile[pk] > 0 else 0
            level = self.profile[pk]
            if level > 0:
                burst = random.random() ** 3
                self.counters[pk][0] += int(level * (20_000 + burst * 400_000) * config.SAMPLE_INTERVAL)
                self.counters[pk][1] += int(level * (80_000 + burst * 3_000_000) * config.SAMPLE_INTERVAL)
                if now - self.handshakes[pk] > 110:
                    self.handshakes[pk] = now
            peers.append(PeerState(
                public_key=pk,
                endpoint=self.endpoints[pk] if level > 0 else None,
                allowed_ips=peer.allowed_ips,
                latest_handshake=self.handshakes[pk],
                rx=self.counters[pk][0],
                tx=self.counters[pk][1],
                keepalive=25,
            ))
        server_pub = wgconf.pubkey(conf.private_key) if conf.private_key else None
        return InterfaceState(up=True, public_key=server_pub, listen_port=conf.listen_port, peers=peers)

    def sync(self, conf: wgconf.WgConfig) -> None:
        # Nowi klienci w symulacji od razu "się łączą".
        for peer in conf.peers:
            if peer.public_key not in self.profile:
                self.profile[peer.public_key] = 1.0


def make_backend():
    return MockBackend(config.WG_INTERFACE) if config.MOCK else RealBackend(config.WG_INTERFACE)
