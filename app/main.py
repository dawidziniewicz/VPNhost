"""Panel WWW do zarządzania serwerem WireGuard."""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import qrcode
import qrcode.image.svg
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from . import config
from .auth import COOKIE, Auth
from .lan import MAC_RE, LanScanner
from .monitor import Monitor
from .service import MODES, ClientService, ServiceError
from .store import Store
from .wg import WgError, make_backend

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("vpnhost")
STATIC = Path(__file__).parent / "static"


class Ctx:
    store: Store
    service: ClientService
    auth: Auth
    monitor: Monitor
    lan: LanScanner


ctx = Ctx()


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    ctx.store = Store(config.DB_PATH)
    ctx.service = ClientService(ctx.store, make_backend())
    ctx.auth = Auth(ctx.store)
    ctx.monitor = Monitor(ctx.store, ctx.service)
    ctx.lan = LanScanner(ctx.store, lambda: ctx.service.settings()["lan_subnet"])
    ctx.store.event("system", f"Uruchomiono panel (wersja {config.APP_VERSION})")
    log.info("Panel VPN %s: http://%s:%s (tryb symulacji: %s)",
             config.APP_VERSION, config.PANEL_HOST, config.PANEL_PORT, config.MOCK)
    tasks = [asyncio.create_task(ctx.monitor.run()), asyncio.create_task(lan_loop())]
    yield
    for task in tasks:
        task.cancel()


async def lan_loop() -> None:
    """Skanowanie sieci domowej w tle (pierwsze zaraz po starcie)."""
    await asyncio.sleep(3)
    while True:
        await asyncio.to_thread(ctx.lan.scan)
        await asyncio.sleep(config.LAN_SCAN_INTERVAL)


app = FastAPI(title="VPNhost", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(ServiceError)
async def service_error(_: Request, exc: ServiceError):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.exception_handler(WgError)
async def wg_error(_: Request, exc: WgError):
    return JSONResponse({"detail": f"WireGuard: {exc}"}, status_code=500)


# ---------------------------------------------------------------- pomocnicze

def client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


def require_auth(request: Request) -> str:
    user = ctx.auth.check(request.cookies.get(COOKIE))
    if not user:
        raise HTTPException(401, "Zaloguj się ponownie")
    if request.method not in ("GET", "HEAD") and request.headers.get("x-requested-with") != "vpnhost":
        raise HTTPException(403, "Brak nagłówka zabezpieczającego")
    return user


def pk_from_id(client_id: str) -> str:
    return client_id.replace("-", "+").replace("_", "/")


def id_from_pk(public_key: str) -> str:
    return public_key.replace("+", "-").replace("/", "_")


def page(name: str) -> HTMLResponse:
    html = (STATIC / name).read_text().replace("{{VERSION}}", config.APP_VERSION)
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


def client_out(row: dict[str, Any], now: float, totals: dict[str, tuple[int, int]]) -> dict[str, Any]:
    pk = row["public_key"]
    view = ctx.monitor.peer_view(pk, now) if row["enabled"] else {"active": False, "online": False,
                                                                     "rx_rate": 0, "tx_rate": 0}
    rx, tx = totals.get(pk, (0, 0))
    return {
        "id": id_from_pk(pk),
        "public_key": pk,
        "name": row["name"],
        "note": row["note"],
        "address": row["address"],
        "mode": row["mode"],
        "mode_label": MODES.get(row["mode"], row["mode"]),
        "dns": row["dns"],
        "enabled": bool(row["enabled"]),
        "imported": bool(row["imported"]),
        "has_config": bool(row["private_key"]),
        "created_at": row["created_at"],
        "total_rx": rx,
        "total_tx": tx,
        **view,
    }


# ---------------------------------------------------------------- strony

@app.get("/", include_in_schema=False)
def index(request: Request):
    if not ctx.auth.check(request.cookies.get(COOKIE)):
        return RedirectResponse("/login", status_code=303)
    return page("index.html")


@app.get("/login", include_in_schema=False)
def login_page(request: Request):
    if ctx.auth.check(request.cookies.get(COOKIE)):
        return RedirectResponse("/", status_code=303)
    return page("login.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(STATIC / "favicon.svg", media_type="image/svg+xml")


@app.get("/api/health")
def health():
    state = ctx.monitor.state
    return {"ok": True, "version": config.APP_VERSION, "wg_up": bool(state and state.up)}


# ---------------------------------------------------------------- logowanie

@app.post("/api/login")
async def login(request: Request):
    data = await request.json()
    ip = client_ip(request)
    wait = ctx.auth.blocked(ip)
    if wait:
        raise HTTPException(429, f"Zbyt wiele nieudanych prób. Spróbuj za {wait} s.")
    token = await asyncio.to_thread(ctx.auth.login, str(data.get("username", "")), str(data.get("password", "")),
                                    ip, request.headers.get("user-agent", ""))
    if not token:
        await asyncio.sleep(1)
        raise HTTPException(401, "Nieprawidłowy login lub hasło")
    response = JSONResponse({"ok": True})
    response.set_cookie(COOKIE, token, max_age=config.SESSION_HOURS * 3600, httponly=True,
                        samesite="strict", secure=config.COOKIE_SECURE)
    return response


@app.post("/api/logout")
def logout(request: Request):
    ctx.auth.logout(request.cookies.get(COOKIE))
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE)
    return response


@app.post("/api/password")
async def change_password(request: Request, _: str = Depends(require_auth)):
    data = await request.json()
    try:
        await asyncio.to_thread(ctx.auth.change_password, str(data.get("current", "")), str(data.get("new", "")),
                                request.cookies.get(COOKIE))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True}


# ---------------------------------------------------------------- stan

@app.get("/api/status")
def status(_: str = Depends(require_auth)):
    now = time.time()
    mon = ctx.monitor
    state = mon.state
    totals = mon.client_totals()
    clients = [client_out(row, now, totals) for row in ctx.store.clients()]
    settings = ctx.service.settings()
    try:
        conf = ctx.service.load()
        address = ", ".join(conf.addresses)
    except ServiceError:
        address = None
    live = mon.live_total[-1] if mon.live_total else (now, 0, 0)
    return {
        "version": config.APP_VERSION,
        "build_date": config.BUILD_DATE,
        "mock": config.MOCK,
        "time": now,
        "panel_uptime": int(now - mon.started),
        "server": mon.server,
        "wg": {
            "interface": config.WG_INTERFACE,
            "up": bool(state and state.up),
            "error": state.error if state else None,
            "public_key": state.public_key if state else None,
            "listen_port": state.listen_port if state else None,
            "address": address,
            "endpoint": settings["endpoint"],
            "clients": len(clients),
            "enabled": sum(1 for c in clients if c["enabled"]),
            "online": sum(1 for c in clients if c["online"]),
            "rx_rate": live[1],
            "tx_rate": live[2],
            "connections": len(mon.connections),
        },
        "lan": ctx.lan.counts(),
        "clients": clients,
    }


RANGES = {"1h": (3600, 60), "6h": (21600, 300), "24h": (86400, 900), "7d": (604800, 3600), "30d": (2592000, 21600)}


@app.get("/api/history")
def history(period: str = Query("live", alias="range"), client: str | None = None,
            _: str = Depends(require_auth)):
    mon = ctx.monitor
    pk = pk_from_id(client) if client else None
    if period == "live":
        source = mon.live_peer.get(pk, []) if pk else mon.live_total
        return {"range": "live", "step": config.SAMPLE_INTERVAL, "points": [list(p) for p in source]}
    if period not in RANGES:
        raise HTTPException(400, "Nieznany zakres")
    span, step = RANGES[period]
    now = int(time.time())
    start = (now - span) // step * step
    sql = "SELECT (ts/?)*? AS b, SUM(rx) rx, SUM(tx) tx FROM traffic WHERE ts>=?"
    args: list[Any] = [step, step, start]
    if pk:
        sql += " AND public_key=?"
        args.append(pk)
    sql += " GROUP BY b"
    rows = {r["b"]: r for r in ctx.store.all(sql, tuple(args))}
    points = []
    for b in range(start, now + 1, step):
        r = rows.get(b)
        points.append([b, round(r["rx"] / step) if r else 0, round(r["tx"] / step) if r else 0])
    total_rx = sum(r["rx"] for r in rows.values())
    total_tx = sum(r["tx"] for r in rows.values())
    return {"range": period, "step": step, "points": points, "total_rx": total_rx, "total_tx": total_tx}


@app.get("/api/connections")
def connections(client: str | None = None, _: str = Depends(require_auth)):
    mon = ctx.monitor
    by_ip = {}
    for row in ctx.store.clients():
        ip = (row["address"] or "").split("/")[0]
        by_ip[ip] = {"id": id_from_pk(row["public_key"]), "name": row["name"]}
    items = []
    for c in mon.connections:
        owner = by_ip.get(c["src"], {"id": None, "name": c["src"]})
        if client and owner["id"] != client:
            continue
        items.append({**c, "client_id": owner["id"], "client": owner["name"]})
    dest: dict[str, dict[str, Any]] = {}
    for c in items:
        key = c["host"] or c["dst"]
        d = dest.setdefault(key, {"dest": key, "ip": c["dst"], "count": 0, "bytes_in": 0, "bytes_out": 0,
                                  "clients": set(), "services": set()})
        d["count"] += 1
        d["bytes_in"] += c["bytes_in"]
        d["bytes_out"] += c["bytes_out"]
        d["clients"].add(c["client"])
        if c["service"]:
            d["services"].add(c["service"])
    top = sorted(dest.values(), key=lambda d: (d["bytes_in"] + d["bytes_out"], d["count"]), reverse=True)[:30]
    for d in top:
        d["clients"] = sorted(d["clients"])
        d["services"] = sorted(d["services"])
    items.sort(key=lambda c: c["bytes_in"] + c["bytes_out"], reverse=True)
    return {"error": mon.conntrack.error, "items": items[:500], "total": len(items), "top": top,
            "accounting": any(c["bytes_in"] or c["bytes_out"] for c in items)}


@app.get("/api/sessions")
def sessions(client: str | None = None, limit: int = 200, _: str = Depends(require_auth)):
    sql = ("SELECT s.*, c.name FROM sessions s LEFT JOIN clients c ON c.public_key=s.public_key ")
    args: list[Any] = []
    if client:
        sql += "WHERE s.public_key=? "
        args.append(pk_from_id(client))
    sql += "ORDER BY s.started_at DESC LIMIT ?"
    args.append(max(1, min(limit, 1000)))
    rows = ctx.store.all(sql, tuple(args))
    mon = ctx.monitor
    for r in rows:
        r["client_id"] = id_from_pk(r.pop("public_key"))
        r["active"] = r["ended_at"] is None
        if r["active"]:
            acc = mon.session_acc.get(pk_from_id(r["client_id"]), [0, 0])
            r["rx"] += acc[0]
            r["tx"] += acc[1]
    return {"items": rows}


@app.get("/api/usage")
def usage(days: int = 30, _: str = Depends(require_auth)):
    days = max(1, min(days, 365))
    since = time.strftime("%Y-%m-%d", time.localtime(time.time() - (days - 1) * 86400))
    rows = ctx.store.all("SELECT u.day, u.public_key, u.rx, u.tx, c.name FROM usage_daily u "
                         "LEFT JOIN clients c ON c.public_key=u.public_key WHERE u.day>=? ORDER BY u.day", (since,))
    per_day: dict[str, dict[str, int]] = {}
    per_client: dict[str, dict[str, Any]] = {}
    for r in rows:
        d = per_day.setdefault(r["day"], {"rx": 0, "tx": 0})
        d["rx"] += r["rx"]
        d["tx"] += r["tx"]
        cid = id_from_pk(r["public_key"])
        c = per_client.setdefault(cid, {"id": cid, "name": r["name"] or "(usunięty)", "rx": 0, "tx": 0})
        c["rx"] += r["rx"]
        c["tx"] += r["tx"]
    days_list = []
    for i in range(days - 1, -1, -1):
        day = time.strftime("%Y-%m-%d", time.localtime(time.time() - i * 86400))
        days_list.append({"day": day, **per_day.get(day, {"rx": 0, "tx": 0})})
    return {"days": days_list,
            "clients": sorted(per_client.values(), key=lambda c: c["rx"] + c["tx"], reverse=True)}


@app.get("/api/events")
def events(limit: int = 300, kind: str | None = None, _: str = Depends(require_auth)):
    sql = "SELECT e.*, c.name FROM events e LEFT JOIN clients c ON c.public_key=e.public_key "
    args: list[Any] = []
    if kind:
        sql += "WHERE e.kind=? "
        args.append(kind)
    sql += "ORDER BY e.id DESC LIMIT ?"
    args.append(max(1, min(limit, 2000)))
    return {"items": ctx.store.all(sql, tuple(args))}


# ---------------------------------------------------------------- klienci

@app.post("/api/clients")
async def create_client(request: Request, _: str = Depends(require_auth)):
    data = await request.json()
    row = await asyncio.to_thread(ctx.service.create, data.get("name", ""), data.get("note", ""),
                                  data.get("mode"), data.get("dns"))
    return client_out(row, time.time(), {})


@app.patch("/api/clients/{client_id}")
async def update_client(client_id: str, request: Request, _: str = Depends(require_auth)):
    data = await request.json()
    row = await asyncio.to_thread(ctx.service.update, pk_from_id(client_id), data)
    return client_out(row, time.time(), ctx.monitor.client_totals())


@app.delete("/api/clients/{client_id}")
async def delete_client(client_id: str, _: str = Depends(require_auth)):
    await asyncio.to_thread(ctx.service.delete, pk_from_id(client_id))
    return {"ok": True}


@app.post("/api/clients/{client_id}/regenerate")
async def regenerate_client(client_id: str, _: str = Depends(require_auth)):
    row = await asyncio.to_thread(ctx.service.regenerate, pk_from_id(client_id))
    return client_out(row, time.time(), ctx.monitor.client_totals())


@app.get("/api/clients/{client_id}/config")
def client_config(client_id: str, download: int = 0, _: str = Depends(require_auth)):
    text, filename = ctx.service.client_config(pk_from_id(client_id))
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'} if download else {}
    return Response(text, media_type="text/plain; charset=utf-8", headers=headers)


@app.get("/api/clients/{client_id}/qr.svg")
def client_qr(client_id: str, _: str = Depends(require_auth)):
    text, _name = ctx.service.client_config(pk_from_id(client_id))
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=2, box_size=10)
    qr.add_data(text)
    qr.make(fit=True)
    svg = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage).to_string()
    return Response(svg, media_type="image/svg+xml")


# ---------------------------------------------------------------- ustawienia

@app.get("/api/settings")
def get_settings(_: str = Depends(require_auth)):
    conf = ctx.service.load()
    state = ctx.monitor.state
    return {
        **ctx.service.settings(),
        "modes": MODES,
        "info": {
            "interface": config.WG_INTERFACE,
            "conf_path": str(config.WG_CONF),
            "address": ", ".join(conf.addresses),
            "listen_port": conf.listen_port,
            "public_key": (state.public_key if state and state.public_key else ctx.service.server_public_key(conf)),
            "save_config": conf.save_config,
            "post_up": conf.interface_values("PostUp"),
            "username": ctx.auth.username,
            "version": config.APP_VERSION,
            "build_date": config.BUILD_DATE,
            "mock": config.MOCK,
            "conntrack_error": ctx.monitor.conntrack.error,
        },
    }


@app.put("/api/settings")
async def put_settings(request: Request, _: str = Depends(require_auth)):
    data = await request.json()
    return await asyncio.to_thread(ctx.service.update_settings, data)


# ---------------------------------------------------------------- sieć domowa

def lan_out() -> dict[str, Any]:
    lan = ctx.lan
    return {"subnet": ctx.service.settings()["lan_subnet"], "interface": lan.iface, "gateway": lan.gateway,
            "scanned_at": lan.scanned_at, "scanning": lan.scanning, "error": lan.error,
            "interval": config.LAN_SCAN_INTERVAL, "devices": lan.devices()}


def lan_mac(mac: str) -> str:
    mac = mac.lower().replace("-", ":")
    if not MAC_RE.match(mac):
        raise HTTPException(400, "Nieprawidłowy adres MAC")
    return mac


@app.get("/api/lan")
def lan_devices(_: str = Depends(require_auth)):
    return lan_out()


@app.post("/api/lan/scan")
async def lan_scan(_: str = Depends(require_auth)):
    await asyncio.to_thread(ctx.lan.scan)
    return lan_out()


@app.patch("/api/lan/{mac}")
async def lan_update(mac: str, request: Request, _: str = Depends(require_auth)):
    data = await request.json()
    try:
        return await asyncio.to_thread(ctx.lan.update, lan_mac(mac), data)
    except KeyError as exc:
        raise HTTPException(404, "Nie ma takiego urządzenia") from exc


@app.post("/api/lan/{mac}/ports")
async def lan_ports(mac: str, _: str = Depends(require_auth)):
    try:
        return await asyncio.to_thread(ctx.lan.probe_ports, lan_mac(mac))
    except KeyError as exc:
        raise HTTPException(404, "Nie ma takiego urządzenia") from exc


@app.delete("/api/lan/{mac}")
async def lan_forget(mac: str, _: str = Depends(require_auth)):
    try:
        await asyncio.to_thread(ctx.lan.forget, lan_mac(mac))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True}
