"""Pętla pomiarowa: prędkości klientów, sesje, historia ruchu, zasoby serwera."""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import time
from collections import defaultdict, deque
from typing import Any

from . import config
from .conntrack import ConntrackReader
from .service import ClientService, ServiceError
from .store import Store
from .system import SystemSampler
from .wg import InterfaceState

log = logging.getLogger("vpnhost.monitor")
LIVE_POINTS = int(config.LIVE_SECONDS / config.SAMPLE_INTERVAL)


def _day(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts))


class Monitor:
    def __init__(self, store: Store, service: ClientService):
        self.store = store
        self.service = service
        self.backend = service.backend
        self.system = SystemSampler()
        self.conntrack = ConntrackReader()

        self.prev: dict[str, tuple[int, int, float]] = {}
        self.rates: dict[str, tuple[float, float]] = {}
        self.live_total: deque = deque(maxlen=LIVE_POINTS)
        self.live_peer: dict[str, deque] = defaultdict(lambda: deque(maxlen=LIVE_POINTS))
        self.minute: int | None = None
        self.minute_acc: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        self.session_acc: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        self.sessions: dict[str, int] = {}   # public_key -> id otwartej sesji
        self.endpoints: dict[str, str | None] = {}
        self.totals: dict[str, tuple[int, int]] = {}
        self.totals_at = 0.0

        self.state: InterfaceState | None = None
        self.server: dict[str, Any] = {}
        self.connections: list[dict] = []
        self.connections_at = 0.0
        self.last_reconcile = 0.0
        self.last_cleanup = 0.0
        self.vpn_net: ipaddress.IPv4Network | None = None
        self.started = time.time()

    # ------------------------------------------------------------ pętla
    async def run(self) -> None:
        await asyncio.to_thread(self._startup)
        while True:
            started = time.monotonic()
            try:
                await asyncio.to_thread(self.tick)
            except Exception:  # pomiar nie może zatrzymać panelu
                log.exception("Błąd pomiaru")
            await asyncio.sleep(max(0.2, config.SAMPLE_INTERVAL - (time.monotonic() - started)))

    def _startup(self) -> None:
        self.service.reconcile()
        # Sesje, które zostały otwarte przed restartem panelu, przejmujemy albo zamykamy w ticku.
        for row in self.store.all("SELECT id, public_key, endpoint FROM sessions WHERE ended_at IS NULL"):
            self.sessions[row["public_key"]] = row["id"]
            self.endpoints[row["public_key"]] = row["endpoint"]

    def tick(self) -> None:
        now = time.time()
        state = self.backend.dump()
        self.state = state

        if now - self.last_reconcile > 60:
            self.last_reconcile = now
            self.service.reconcile()
            try:
                self.vpn_net = self.service.vpn_network(self.service.load()).network
            except ServiceError:
                self.vpn_net = None

        minute = int(now // 60) * 60
        if self.minute is None:
            self.minute = minute
        elif minute != self.minute:
            self._flush_minute(self.minute)
            self.minute = minute

        total_rx = total_tx = 0.0
        present = set()
        for peer in state.peers:
            pk = peer.public_key
            present.add(pk)
            prev = self.prev.get(pk)
            d_rx = d_tx = 0
            rx_rate = tx_rate = 0.0
            if prev:
                d_rx = peer.rx - prev[0] if peer.rx >= prev[0] else peer.rx
                d_tx = peer.tx - prev[1] if peer.tx >= prev[1] else peer.tx
                dt = max(0.001, now - prev[2])
                rx_rate, tx_rate = d_rx / dt, d_tx / dt
            self.prev[pk] = (peer.rx, peer.tx, now)
            self.rates[pk] = (rx_rate, tx_rate)
            self.live_peer[pk].append((round(now, 1), round(rx_rate), round(tx_rate)))
            total_rx += rx_rate
            total_tx += tx_rate
            if d_rx or d_tx:
                acc = self.minute_acc[pk]
                acc[0] += d_rx
                acc[1] += d_tx
                sacc = self.session_acc[pk]
                sacc[0] += d_rx
                sacc[1] += d_tx
            self._track_session(pk, peer.latest_handshake, peer.endpoint, now)
        for pk in list(self.rates):
            if pk not in present:
                self.rates.pop(pk, None)
                self.prev.pop(pk, None)
                if pk in self.sessions:
                    self._close_session(pk, int(now))
        self.live_total.append((round(now, 1), round(total_rx), round(total_tx)))

        self.server = self.system.sample(total_rx, total_tx)

        if now - self.connections_at >= config.CONNTRACK_INTERVAL:
            self.connections_at = now
            self.connections = self.conntrack.read(self.vpn_net)

        if now - self.last_cleanup > 3600:
            self.last_cleanup = now
            self.store.cleanup(config.HISTORY_DAYS)

    # ------------------------------------------------------------ sesje
    def _online(self, handshake: int, now: float) -> bool:
        return handshake > 0 and now - handshake < config.ONLINE_TIMEOUT

    def _track_session(self, pk: str, handshake: int, endpoint: str | None, now: float) -> None:
        online = self._online(handshake, now)
        sid = self.sessions.get(pk)
        if online and sid is None:
            started = handshake if now - handshake < 10 else int(now)
            sid = self.store.run(
                "INSERT INTO sessions(public_key,endpoint,started_at,last_seen) VALUES(?,?,?,?)",
                (pk, endpoint, started, handshake))
            self.sessions[pk] = sid
            self.endpoints[pk] = endpoint
            self.session_acc.pop(pk, None)
            name = self._name(pk)
            self.store.event("connect", f"„{name}” połączył się z {_host(endpoint)}", pk)
        elif online and sid is not None:
            if endpoint and endpoint != self.endpoints.get(pk):
                old = self.endpoints.get(pk)
                self.endpoints[pk] = endpoint
                if old and _host(old) != _host(endpoint):
                    self.store.event("roam", f"„{self._name(pk)}” zmienił adres: {_host(old)} → {_host(endpoint)}", pk)
                self.store.run("UPDATE sessions SET endpoint=? WHERE id=?", (endpoint, sid))
        elif not online and sid is not None:
            self._close_session(pk, handshake or int(now))

    def _close_session(self, pk: str, ended: int) -> None:
        sid = self.sessions.pop(pk, None)
        if sid is None:
            return
        acc = self.session_acc.pop(pk, [0, 0])
        self.store.run("UPDATE sessions SET ended_at=?, last_seen=?, rx=rx+?, tx=tx+? WHERE id=?",
                       (ended, ended, acc[0], acc[1], sid))
        self.store.event("disconnect", f"„{self._name(pk)}” rozłączył się", pk)
        self.endpoints.pop(pk, None)

    def _name(self, pk: str) -> str:
        row = self.store.client(pk)
        return row["name"] if row else pk[:8] + "…"

    # ------------------------------------------------------------ zapis minutowy
    def _flush_minute(self, minute: int) -> None:
        day = _day(minute)
        rows = [(pk, acc[0], acc[1]) for pk, acc in self.minute_acc.items() if acc[0] or acc[1]]
        self.minute_acc.clear()
        with self.store.tx() as c:
            for pk, rx, tx in rows:
                c.execute("INSERT INTO traffic(ts,public_key,rx,tx) VALUES(?,?,?,?) "
                          "ON CONFLICT(ts,public_key) DO UPDATE SET rx=rx+excluded.rx, tx=tx+excluded.tx",
                          (minute, pk, rx, tx))
                c.execute("INSERT INTO usage_daily(day,public_key,rx,tx) VALUES(?,?,?,?) "
                          "ON CONFLICT(day,public_key) DO UPDATE SET rx=rx+excluded.rx, tx=tx+excluded.tx",
                          (day, pk, rx, tx))
            for pk, sid in self.sessions.items():
                acc = self.session_acc.pop(pk, None)
                last = self.state.peers if self.state else []
                hs = next((p.latest_handshake for p in last if p.public_key == pk), 0)
                if acc:
                    c.execute("UPDATE sessions SET rx=rx+?, tx=tx+?, last_seen=MAX(last_seen,?) WHERE id=?",
                              (acc[0], acc[1], hs, sid))
                else:
                    c.execute("UPDATE sessions SET last_seen=MAX(last_seen,?) WHERE id=?", (hs, sid))
        self.totals_at = 0

    # ------------------------------------------------------------ odczyt
    def client_totals(self) -> dict[str, tuple[int, int]]:
        now = time.time()
        if now - self.totals_at > 30:
            self.totals = {r["public_key"]: (r["rx"], r["tx"]) for r in self.store.all(
                "SELECT public_key, SUM(rx) rx, SUM(tx) tx FROM usage_daily GROUP BY public_key")}
            self.totals_at = now
        out = dict(self.totals)
        for pk, acc in self.minute_acc.items():
            rx, tx = out.get(pk, (0, 0))
            out[pk] = (rx + acc[0], tx + acc[1])
        return out

    def peer_view(self, pk: str, now: float) -> dict[str, Any]:
        peer = next((p for p in (self.state.peers if self.state else []) if p.public_key == pk), None)
        rx_rate, tx_rate = self.rates.get(pk, (0.0, 0.0))
        if not peer:
            return {"active": False, "online": False, "rx_rate": 0, "tx_rate": 0}
        sid = self.sessions.get(pk)
        session_start = None
        if sid:
            row = self.store.one("SELECT started_at FROM sessions WHERE id=?", (sid,))
            session_start = row["started_at"] if row else None
        return {
            "active": True,
            "online": self._online(peer.latest_handshake, now),
            "endpoint": peer.endpoint,
            "latest_handshake": peer.latest_handshake or None,
            "rx_rate": rx_rate,
            "tx_rate": tx_rate,
            "rx_session": peer.rx,
            "tx_session": peer.tx,
            "session_start": session_start,
        }


def _host(endpoint: str | None) -> str:
    if not endpoint:
        return "?"
    if endpoint.startswith("["):
        return endpoint.split("]")[0].lstrip("[")
    return endpoint.rsplit(":", 1)[0]
