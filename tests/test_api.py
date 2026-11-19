import time

from fastapi.testclient import TestClient

from app import config, wgconf
from app.main import app

H = {"X-Requested-With": "vpnhost"}


def login(client):
    r = client.post("/api/login", json={"username": "admin", "password": "test-haslo-123"}, headers=H)
    assert r.status_code == 200, r.text


def test_requires_login():
    with TestClient(app) as client:
        assert client.get("/api/status").status_code == 401
        r = client.get("/", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login"
        r = client.post("/api/login", json={"username": "admin", "password": "zle"}, headers=H)
        assert r.status_code == 401


def test_client_lifecycle():
    with TestClient(app) as client:
        login(client)
        # Bez nagłówka zabezpieczającego zmiany są odrzucane.
        assert client.post("/api/clients", json={"name": "x"}).status_code == 403

        r = client.post("/api/clients", json={"name": "Laptop", "mode": "lan"}, headers=H)
        assert r.status_code == 200, r.text
        c = r.json()
        assert c["address"] == "10.8.0.3/32"  # 10.8.0.2 zajmuje istniejący peer
        conf = wgconf.load(config.WG_CONF)
        assert conf.find(c["public_key"]) is not None

        r = client.get(f"/api/clients/{c['id']}/config")
        assert r.status_code == 200
        assert "Endpoint = vpn.example.org:51820" in r.text
        assert "AllowedIPs = 10.8.0.0/24, 192.168.1.0/24" in r.text
        assert client.get(f"/api/clients/{c['id']}/qr.svg").headers["content-type"].startswith("image/svg")

        assert client.post("/api/clients", json={"name": "laptop"}, headers=H).status_code == 400

        r = client.patch(f"/api/clients/{c['id']}", json={"enabled": False}, headers=H)
        assert r.status_code == 200 and r.json()["enabled"] is False
        assert wgconf.load(config.WG_CONF).find(c["public_key"]) is None
        r = client.patch(f"/api/clients/{c['id']}", json={"enabled": True, "name": "Laptop 2"}, headers=H)
        assert r.json()["enabled"] is True and r.json()["name"] == "Laptop 2"
        assert wgconf.load(config.WG_CONF).find(c["public_key"]).name == "Laptop 2"

        r = client.post(f"/api/clients/{c['id']}/regenerate", headers=H)
        new = r.json()
        assert new["public_key"] != c["public_key"]
        assert wgconf.load(config.WG_CONF).find(new["public_key"]) is not None

        time.sleep(1.2)
        st = client.get("/api/status").json()
        assert st["wg"]["up"] is True
        assert any(x["name"] == "Laptop 2" for x in st["clients"])
        assert client.get("/api/history?range=live").status_code == 200
        assert client.get("/api/history?range=24h").status_code == 200
        assert client.get("/api/connections").status_code == 200
        assert client.get("/api/usage?days=7").status_code == 200
        assert client.get("/api/events").status_code == 200

        assert client.delete(f"/api/clients/{new['id']}", headers=H).status_code == 200
        assert wgconf.load(config.WG_CONF).find(new["public_key"]) is None


def test_settings_validation():
    with TestClient(app) as client:
        login(client)
        assert client.put("/api/settings", json={"endpoint": "zly adres"}, headers=H).status_code == 400
        r = client.put("/api/settings", json={"endpoint": "vpn.example.org:51820", "dns": "1.1.1.1, 9.9.9.9"}, headers=H)
        assert r.status_code == 200 and r.json()["dns"] == "1.1.1.1, 9.9.9.9"
