from app.conntrack import _parse_line

TCP = ("ipv4     2 tcp      6 431997 ESTABLISHED src=10.8.0.2 dst=142.250.186.206 sport=51234 dport=443 "
       "packets=12 bytes=3400 src=142.250.186.206 dst=192.168.1.76 sport=443 dport=51234 packets=20 bytes=88000 "
       "[ASSURED] mark=0 zone=0 use=2")
UDP = ("ipv4     2 udp      17 25 src=10.8.0.2 dst=1.1.1.1 sport=40000 dport=53 "
       "src=1.1.1.1 dst=192.168.1.76 sport=53 dport=40000 mark=0 zone=0 use=2")


def test_tcp_with_accounting():
    e = _parse_line(TCP)
    assert e["proto"] == "tcp" and e["state"] == "ESTABLISHED"
    assert (e["src"], e["dst"], e["dport"]) == ("10.8.0.2", "142.250.186.206", 443)
    assert e["bytes_out"] == 3400 and e["bytes_in"] == 88000
    assert "ASSURED" in e["flags"]


def test_udp_without_accounting():
    e = _parse_line(UDP)
    assert e["proto"] == "udp" and e["state"] is None
    assert e["dport"] == 53 and e["bytes_in"] == 0
