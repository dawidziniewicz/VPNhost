"""Logowanie do panelu: hasło (scrypt), sesje w bazie, ograniczenie prób."""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from collections import defaultdict, deque

from . import config
from .store import Store

log = logging.getLogger("vpnhost.auth")
COOKIE = "vpnhost_session"
MAX_FAILS = 5
FAIL_WINDOW = 300


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_hex, digest_hex = stored.split("$")
        if algo != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


class Auth:
    def __init__(self, store: Store):
        self.store = store
        self.fails: dict[str, deque] = defaultdict(deque)
        self._ensure_password()

    def _ensure_password(self) -> None:
        if self.store.get_setting("admin_password"):
            return
        password = config.ADMIN_PASSWORD
        if not password:
            password = secrets.token_urlsafe(12)
            log.warning("Nie ustawiono ADMIN_PASSWORD. Wygenerowane hasło do panelu (użytkownik %s): %s",
                        config.ADMIN_USER, password)
        self.store.set_setting("admin_password", hash_password(password))
        self.store.set_setting("admin_user", config.ADMIN_USER)

    @property
    def username(self) -> str:
        return self.store.get_setting("admin_user", config.ADMIN_USER) or config.ADMIN_USER

    def blocked(self, ip: str) -> int:
        q = self.fails[ip]
        now = time.time()
        while q and now - q[0] > FAIL_WINDOW:
            q.popleft()
        if len(q) >= MAX_FAILS:
            return int(FAIL_WINDOW - (now - q[0])) + 1
        return 0

    def login(self, username: str, password: str, ip: str, user_agent: str) -> str | None:
        stored = self.store.get_setting("admin_password") or ""
        ok = hmac.compare_digest(username.strip().lower(), self.username.lower()) & verify_password(password, stored)
        if not ok:
            self.fails[ip].append(time.time())
            self.store.event("auth", f"Nieudane logowanie z {ip}")
            return None
        self.fails.pop(ip, None)
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        self.store.run("INSERT INTO auth_sessions(token,username,created_at,expires_at,ip,user_agent) VALUES(?,?,?,?,?,?)",
                       (token, self.username, now, now + config.SESSION_HOURS * 3600, ip, user_agent[:200]))
        self.store.event("auth", f"Zalogowano z {ip}")
        return token

    def check(self, token: str | None) -> str | None:
        if not token:
            return None
        row = self.store.one("SELECT username, expires_at FROM auth_sessions WHERE token=?", (token,))
        if not row or row["expires_at"] < time.time():
            return None
        return row["username"]

    def logout(self, token: str | None) -> None:
        if token:
            self.store.run("DELETE FROM auth_sessions WHERE token=?", (token,))

    def change_password(self, current: str, new: str, keep_token: str | None) -> None:
        if not verify_password(current, self.store.get_setting("admin_password") or ""):
            raise ValueError("Obecne hasło jest nieprawidłowe")
        if len(new) < 8:
            raise ValueError("Nowe hasło musi mieć co najmniej 8 znaków")
        self.store.set_setting("admin_password", hash_password(new))
        # Wylogowanie wszystkich innych sesji.
        self.store.run("DELETE FROM auth_sessions WHERE token<>?", (keep_token or "",))
        self.store.event("auth", "Zmieniono hasło do panelu")
