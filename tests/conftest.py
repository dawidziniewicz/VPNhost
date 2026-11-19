import os
import sys
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="vpnhost-test-"))
os.environ.update({
    "WG_MOCK": "1",
    "DATA_DIR": str(_tmp / "data"),
    "WG_CONF_DIR": str(_tmp / "wireguard"),
    "ADMIN_PASSWORD": "test-haslo-123",
    "WG_ENDPOINT": "vpn.example.org:51820",
    "SAMPLE_INTERVAL": "0.5",
})
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
