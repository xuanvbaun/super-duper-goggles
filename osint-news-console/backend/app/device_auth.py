"""Device authorization and persistent login throttling for the local launcher."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import threading
import time
from pathlib import Path

DEVICE_TTL_SECONDS = 30 * 24 * 60 * 60
PERMANENT_COOKIE_SECONDS = 400 * 24 * 60 * 60
MAX_AUTHORIZED_DEVICES = 20
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 10 * 60
LOGIN_BLOCK_SECONDS = 24 * 60 * 60


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def safe_next(value: str | None) -> str:
    value = value or "/"
    if not value.startswith("/") or value.startswith("//"):
        return "/"
    return value[:2048]


def _atomic_json_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _masked_client(value: str) -> str:
    try:
        address = ipaddress.ip_address(value)
        if address.version == 4:
            parts = value.split(".")
            return ".".join(parts[:3] + ["*"])
        return ":".join(address.exploded.split(":")[:4]) + ":*"
    except ValueError:
        return "未知地址"


class DeviceAuthStore:
    """Store token hashes and device metadata; never persist raw device tokens."""

    def __init__(self, path: Path, ttl_seconds: int = DEVICE_TTL_SECONDS):
        self.path = path
        self.ttl_seconds = ttl_seconds
        self._lock = threading.RLock()
        self._devices = self._load()

    def _load(self) -> dict[str, dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            devices = data.get("devices", {})
            if isinstance(devices, dict):
                result = {}
                for key, value in devices.items():
                    if not isinstance(value, dict):
                        continue
                    result[str(key)] = {
                        "name": str(value.get("name") or "未命名设备")[:40],
                        "created_at": float(value.get("created_at", 0)),
                        "last_seen": float(value.get("last_seen", 0)),
                        "last_ip": str(value.get("last_ip") or ""),
                        "permanent": bool(value.get("permanent", False)),
                    }
                return result
        except (OSError, ValueError, TypeError):
            pass
        return {}

    def _prune_locked(self, now: float) -> bool:
        before = len(self._devices)
        self._devices = {
            key: value
            for key, value in self._devices.items()
            if value.get("permanent", False)
            or now - value.get("last_seen", 0) <= self.ttl_seconds
        }
        return len(self._devices) != before

    def _save_locked(self) -> None:
        _atomic_json_write(self.path, {"devices": self._devices})

    def authorize(self, token: str, name: str = "未命名设备", ip: str = "") -> None:
        now = time.time()
        with self._lock:
            self._prune_locked(now)
            self._devices[token_hash(token)] = {
                "name": (name.strip() or "未命名设备")[:40],
                "created_at": now,
                "last_seen": now,
                "last_ip": _masked_client(ip) if ip else "",
                "permanent": False,
            }
            if len(self._devices) > MAX_AUTHORIZED_DEVICES:
                removable = sorted(
                    (
                        item
                        for item in self._devices.items()
                        if not item[1].get("permanent", False)
                    ),
                    key=lambda item: item[1]["last_seen"],
                )
                while len(self._devices) > MAX_AUTHORIZED_DEVICES and removable:
                    key, _ = removable.pop(0)
                    self._devices.pop(key, None)
            self._save_locked()

    def get_authorization(self, token: str | None, ip: str = "") -> dict | None:
        if not token:
            return None
        now = time.time()
        with self._lock:
            changed = self._prune_locked(now)
            key = token_hash(token)
            record = self._devices.get(key)
            if not record:
                if changed:
                    self._save_locked()
                return None
            if now - record["last_seen"] >= 24 * 60 * 60:
                record["last_seen"] = now
                if ip:
                    record["last_ip"] = _masked_client(ip)
                changed = True
            if changed:
                self._save_locked()
            return {"id": key, **record}

    def is_authorized(self, token: str | None) -> bool:
        return self.get_authorization(token) is not None

    def list_devices(self) -> list[dict]:
        now = time.time()
        with self._lock:
            if self._prune_locked(now):
                self._save_locked()
            return sorted(
                ({"id": key, **value} for key, value in self._devices.items()),
                key=lambda item: item["last_seen"],
                reverse=True,
            )

    def set_permanent(self, device_id: str, permanent: bool) -> bool:
        with self._lock:
            record = self._devices.get(device_id)
            if not record:
                return False
            record["permanent"] = permanent
            self._save_locked()
            return True

    def rename(self, device_id: str, name: str) -> bool:
        with self._lock:
            record = self._devices.get(device_id)
            if not record:
                return False
            record["name"] = (name.strip() or "未命名设备")[:40]
            self._save_locked()
            return True

    def revoke(self, device_id: str) -> bool:
        with self._lock:
            removed = self._devices.pop(device_id, None) is not None
            if removed:
                self._save_locked()
            return removed

    def revoke_all(self) -> int:
        with self._lock:
            count = len(self._devices)
            self._devices = {}
            self._save_locked()
            return count

    def count(self) -> int:
        return len(self.list_devices())


class LoginRateLimiter:
    """Persist failed attempts by hashed client address and expose local unblock."""

    def __init__(
        self,
        max_attempts: int = MAX_LOGIN_ATTEMPTS,
        window_seconds: int = LOGIN_WINDOW_SECONDS,
        block_seconds: int = LOGIN_BLOCK_SECONDS,
        path: Path | None = None,
    ):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.block_seconds = block_seconds
        self.path = path
        self._records = self._load()
        self._lock = threading.Lock()

    def _load(self) -> dict[str, dict]:
        if not self.path:
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            records = data.get("clients", {})
            return records if isinstance(records, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _save_locked(self) -> None:
        if self.path:
            _atomic_json_write(self.path, {"clients": self._records})

    def _key(self, client: str) -> str:
        return token_hash(f"login:{client}")

    def _record_locked(self, client: str, now: float) -> tuple[str, dict]:
        key = self._key(client)
        record = self._records.setdefault(
            key,
            {"label": _masked_client(client), "attempts": [], "blocked_until": 0},
        )
        record["attempts"] = [
            float(value)
            for value in record.get("attempts", [])
            if now - float(value) < self.window_seconds
        ]
        if float(record.get("blocked_until", 0)) <= now:
            record["blocked_until"] = 0
        return key, record

    def can_attempt(self, client: str) -> bool:
        now = time.time()
        with self._lock:
            _, record = self._record_locked(client, now)
            self._save_locked()
            return float(record.get("blocked_until", 0)) <= now

    def blocked_until(self, client: str) -> float:
        now = time.time()
        with self._lock:
            _, record = self._record_locked(client, now)
            return float(record.get("blocked_until", 0))

    def record_failure(self, client: str) -> int:
        now = time.time()
        with self._lock:
            _, record = self._record_locked(client, now)
            attempts = record["attempts"]
            attempts.append(now)
            remaining = max(0, self.max_attempts - len(attempts))
            if remaining == 0:
                record["blocked_until"] = now + self.block_seconds
                record["attempts"] = []
            self._save_locked()
            return remaining

    def clear(self, client: str) -> None:
        with self._lock:
            self._records.pop(self._key(client), None)
            self._save_locked()

    def list_blocked(self) -> list[dict]:
        now = time.time()
        with self._lock:
            blocked = []
            changed = False
            for key, record in list(self._records.items()):
                until = float(record.get("blocked_until", 0))
                if until > now:
                    blocked.append(
                        {"id": key, "label": record.get("label", "未知地址"), "until": until}
                    )
                elif not record.get("attempts"):
                    self._records.pop(key, None)
                    changed = True
            if changed:
                self._save_locked()
            return sorted(blocked, key=lambda item: item["until"], reverse=True)

    def unblock(self, block_id: str) -> bool:
        with self._lock:
            removed = self._records.pop(block_id, None) is not None
            if removed:
                self._save_locked()
            return removed
