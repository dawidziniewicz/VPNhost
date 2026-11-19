from app import wgconf

REAL = """[Interface]
Address = 10.8.0.1/24
ListenPort = 51820
PrivateKey = yAnz5TF+lXXJte14tji3zlMNq+hd2rYUIgJBgB3fBmk=
PostUp = nft add table ip wgnat; nft add rule ip wgnat post ip saddr 10.8.0.0/24 oifname "eno1" masquerade
PostDown = nft delete table ip wgnat

### telefon
[Peer]
PublicKey = kmoqvuyWg9RGijfJGmNMj2HhH2o3fQWd09LXgp3zFl4=
PresharedKey = FpCyhws9cxwWoV4xELtfJvjJN+zQVRPISllRWgeopVE=
AllowedIPs = 10.8.0.2/32
"""


def test_parse_keeps_interface_and_peer():
    conf = wgconf.parse(REAL)
    assert conf.addresses == ["10.8.0.1/24"]
    assert conf.listen_port == 51820
    assert len(conf.interface_values("PostUp")) == 1
    assert len(conf.peers) == 1
    peer = conf.peers[0]
    assert peer.public_key.startswith("kmoq")
    assert peer.allowed_ips == "10.8.0.2/32"
    assert peer.leading == ["### telefon"]


def test_roundtrip_is_stable():
    once = wgconf.render(wgconf.parse(REAL))
    twice = wgconf.render(wgconf.parse(once))
    assert once == twice
    assert "PostUp = nft add table" in once
    assert "### telefon\n[Peer]" in once


def test_stripped_has_no_wg_quick_keys():
    out = wgconf.render_stripped(wgconf.parse(REAL))
    assert "Address" not in out and "PostUp" not in out and "PostDown" not in out
    assert "PrivateKey" in out and "ListenPort" in out and "PublicKey" in out


def test_names_and_keys():
    conf = wgconf.parse(REAL)
    peer = conf.peers[0]
    peer.set_name("Telefon Dawida")
    assert peer.name == "Telefon Dawida"
    assert "# vpnhost: Telefon Dawida" in wgconf.render(conf)
    priv = wgconf.genkey()
    pub = wgconf.pubkey(priv)
    assert wgconf.is_key(priv) and wgconf.is_key(pub) and priv != pub
