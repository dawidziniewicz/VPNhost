import ipaddress
import struct

from fastapi.testclient import TestClient

from app import lan
from app.main import app
from tests.test_api import H, login

ARP = """IP address       HW type     Flags       HW address            Mask     Device
192.168.1.1      0x1         0x2         E8:AD:A6:12:34:01     *        eno1
192.168.1.14     0x1         0x2         3a:22:fb:55:66:03     *        eno1
192.168.1.99     0x1         0x0         00:00:00:00:00:00     *        eno1
"""

ROUTE = """Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT
eno1\t00000000\t0101A8C0\t0003\t0\t0\t100\t00000000\t0\t0\t0
wg0\t0000080A\t00000000\t0001\t0\t0\t0\t00FFFFFF\t0\t0\t0
eno1\t0001A8C0\t00000000\t0001\t0\t0\t100\t00FFFFFF\t0\t0\t0
"""


def test_parse_arp_skips_incomplete():
    rows = lan.parse_arp(ARP)
    assert [r["ip"] for r in rows] == ["192.168.1.1", "192.168.1.14"]
    assert rows[0]["mac"] == "e8:ad:a6:12:34:01"


def test_parse_routes():
    iface, gw = lan.parse_routes(ROUTE, ipaddress.ip_network("192.168.1.0/24"))
    assert (iface, gw) == ("eno1", "192.168.1.1")


def test_random_mac():
    assert lan.is_random_mac("3a:22:fb:55:66:03")
    assert not lan.is_random_mac("3c:22:fb:55:66:03")


def _answer(qname: str, qtype: int, rdata: bytes) -> bytes:
    name = lan._encode_name(qname)
    head = struct.pack(">HHHHHH", 1, 0x8400, 1, 1, 0, 0)
    question = name + struct.pack(">HH", qtype, 1)
    rr = b"\xc0\x0c" + struct.pack(">HHIH", qtype, 1, 120, len(rdata)) + rdata
    return head + question + rr


def test_dns_ptr_and_txt():
    data = _answer("14.1.168.192.in-addr.arpa", 12, lan._encode_name("iPhone-Dawida.local"))
    assert lan.dns_answers(data, 12) == ["iPhone-Dawida.local"]
    txt = b"".join(bytes([len(s)]) + s for s in (b"model=iPhone15,2", b"osxvers=0"))
    data = _answer("iPhone-Dawida._device-info._tcp.local", 16, txt)
    assert lan.dns_answers(data, 16) == [["model=iPhone15,2", "osxvers=0"]]


def test_nbstat():
    q = lan.nbstat_query()
    name = q[12:12 + 34]
    entries = b"WORKGROUP      \x00\x84\x00" + b"DESKTOP-K7H2   \x00\x04\x00"
    rdata = bytes([2]) + entries + b"\x00" * 6
    data = struct.pack(">HHHHHH", 1, 0x8400, 0, 1, 0, 0) + name + struct.pack(">HHIH", 0x21, 1, 0, len(rdata)) + rdata
    assert lan.parse_nbstat(data) == "DESKTOP-K7H2"


def test_vendors_and_clean(tmp_path):
    f = tmp_path / "manuf"
    f.write_text("# komentarz\n00:03:93         \tApple       \tApple, Inc.\n"
                 "00:55:DA:10/28   \tKoolPOS     \tKoolPOS Inc.\n"
                 "00:11:32         \tSynology    \tSynology Incorporated\n")
    v = lan.Vendors(f)
    assert v.lookup("00:03:93:aa:bb:cc") == "Apple"
    assert v.lookup("00:55:da:1f:00:00") == "KoolPOS"
    assert v.lookup("00:11:32:00:00:01") == "Synology"
    assert v.lookup("aa:bb:cc:00:00:00") is None
    assert lan.clean_vendor("TP-LINK TECHNOLOGIES CO.,LTD.") == "TP-LINK"


def test_classify():
    assert lan.classify({"is_gateway": True})[0] == "router"
    assert lan.classify({"model": "iPhone15,2"}) == ("phone", "iPhone")
    assert lan.classify({"hostname": "jonas-laptop.home"})[0] != "nas"
    assert lan.classify({"hostname": "nas01.home"})[0] == "nas"
    assert lan.classify({"hostname": "DESKTOP-K7H2.home"})[0] == "computer"
    assert lan.classify({"vendor": "Espressif"})[0] == "iot"
    assert lan.classify({"ports": [9100]})[0] == "printer"
    assert lan.classify({"random_mac": True})[0] == "phone"
    assert lan.classify({})[0] == "unknown"


def test_lan_api():
    with TestClient(app) as client:
        login(client)
        r = client.post("/api/lan/scan", headers=H)
        assert r.status_code == 200, r.text
        data = r.json()
        devs = {d["mac"]: d for d in data["devices"]}
        assert devs["e8:ad:a6:12:34:01"]["is_gateway"] and devs["e8:ad:a6:12:34:01"]["online"]
        assert devs["dc:a6:32:12:ab:0b"]["is_self"]

        mac = "3c:22:fb:55:66:03"
        r = client.patch(f"/api/lan/{mac}", json={"name": "Telefon", "note": "salon"}, headers=H)
        assert r.status_code == 200 and r.json()["name"] == "Telefon"
        r = client.post(f"/api/lan/{mac}/ports", headers=H)
        assert r.json()["ports"] == [62078]

        assert client.delete(f"/api/lan/{mac}", headers=H).status_code == 400   # jest w sieci
        assert client.patch("/api/lan/zly-mac", json={}, headers=H).status_code == 400
        assert client.patch("/api/lan/aa:aa:aa:aa:aa:aa", json={}, headers=H).status_code == 404
        assert client.get("/api/status").json()["lan"]["total"] >= 10
