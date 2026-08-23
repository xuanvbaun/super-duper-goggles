import json
import http.client
import importlib.util
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

from app.device_auth import DeviceAuthStore, LoginRateLimiter, safe_next


def test_device_token_is_hashed_on_disk(tmp_path):
    path = tmp_path / "authorized_devices.json"
    store = DeviceAuthStore(path)
    token = "secret-device-token"
    store.authorize(token)

    assert store.is_authorized(token)
    content = path.read_text(encoding="utf-8")
    assert token not in content
    assert len(json.loads(content)["devices"]) == 1


def test_expired_device_is_rejected(tmp_path):
    store = DeviceAuthStore(tmp_path / "authorized_devices.json", ttl_seconds=1)
    store.authorize("old-token")
    for record in store._devices.values():
        record["last_seen"] = time.time() - 2
    assert not store.is_authorized("old-token")


def test_permanent_device_does_not_expire(tmp_path):
    store = DeviceAuthStore(tmp_path / "authorized_devices.json", ttl_seconds=1)
    store.authorize("permanent-token", "我的手机")
    device_id = store.list_devices()[0]["id"]
    assert store.set_permanent(device_id, True)
    store._devices[device_id]["last_seen"] = time.time() - 10
    record = store.get_authorization("permanent-token")
    assert record is not None
    assert record["permanent"] is True
    assert record["name"] == "我的手机"


def test_login_rate_limit():
    limiter = LoginRateLimiter(max_attempts=2, window_seconds=600)
    assert limiter.can_attempt("device")
    assert limiter.record_failure("device") == 1
    assert limiter.record_failure("device") == 0
    assert not limiter.can_attempt("device")
    limiter.clear("device")
    assert limiter.can_attempt("device")


def test_login_block_persists_and_can_be_unblocked(tmp_path):
    path = tmp_path / "login_attempts.json"
    limiter = LoginRateLimiter(max_attempts=1, path=path)
    assert limiter.record_failure("203.0.113.9") == 0
    assert not limiter.can_attempt("203.0.113.9")
    assert limiter.blocked_until("203.0.113.9") > time.time() + 23 * 60 * 60

    reloaded = LoginRateLimiter(max_attempts=1, path=path)
    blocked = reloaded.list_blocked()
    assert blocked and blocked[0]["label"] == "203.0.113.*"
    assert reloaded.unblock(blocked[0]["id"])
    assert reloaded.can_attempt("203.0.113.9")


def test_redirect_target_stays_local():
    assert safe_next("/news/123") == "/news/123"
    assert safe_next("https://example.com") == "/"
    assert safe_next("//example.com") == "/"


def test_fixed_tunnel_settings_require_https_and_token(tmp_path):
    launcher_path = Path(__file__).resolve().parents[2] / "local_server.py"
    spec = importlib.util.spec_from_file_location("osint_tunnel_settings_test", launcher_path)
    launcher = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(launcher)
    launcher.TUNNEL_SETTINGS_FILE = tmp_path / "tunnel-settings.json"
    launcher.TUNNEL_TOKEN_FILE = tmp_path / "tunnel-token.txt"
    launcher.TUNNEL_SETTINGS_FILE.write_text(
        json.dumps({"public_url": "https://news.example.com"}), encoding="utf-8"
    )
    assert launcher._load_tunnel_settings() is None
    launcher.TUNNEL_TOKEN_FILE.write_text("x" * 50, encoding="ascii")
    assert launcher._load_tunnel_settings() == {
        "public_url": "https://news.example.com"
    }


def test_tunnel_request_requires_pairing_code(tmp_path):
    launcher_path = Path(__file__).resolve().parents[2] / "local_server.py"
    spec = importlib.util.spec_from_file_location("osint_local_server_test", launcher_path)
    launcher = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(launcher)
    launcher.AUTH_STORE = DeviceAuthStore(tmp_path / "devices.json")
    launcher.RATE_LIMITER = LoginRateLimiter()

    server = ThreadingHTTPServer(("127.0.0.1", 0), launcher.LocalHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
    tunnel_headers = {
        "Host": "example.trycloudflare.com",
        "CF-Connecting-IP": "203.0.113.10",
    }
    try:
        connection.request("GET", "/", headers=tunnel_headers)
        response = connection.getresponse()
        response.read()
        assert response.status == 303
        assert response.getheader("Location", "").startswith("/device-login")

        body = urlencode(
            {"code": launcher.PAIRING_CODE, "name": "测试手机", "next": "/"}
        )
        connection.request(
            "POST",
            "/device-login",
            body=body,
            headers={
                **tunnel_headers,
                "Content-Type": "application/x-www-form-urlencoded",
                "Content-Length": str(len(body)),
            },
        )
        response = connection.getresponse()
        response.read()
        cookie = response.getheader("Set-Cookie")
        assert response.status == 303
        assert "HttpOnly" in cookie and "Secure" in cookie
        assert launcher.AUTH_STORE.list_devices()[0]["name"] == "测试手机"

        connection.request("GET", "/", headers={**tunnel_headers, "Cookie": cookie})
        response = connection.getresponse()
        response.read()
        assert response.status == 200

        device_id = launcher.AUTH_STORE.list_devices()[0]["id"]
        assert launcher.AUTH_STORE.set_permanent(device_id, True)
        connection.request("GET", "/", headers={**tunnel_headers, "Cookie": cookie})
        response = connection.getresponse()
        response.read()
        refreshed = [
            value for key, value in response.getheaders() if key.lower() == "set-cookie"
        ]
        assert any("Max-Age=34560000" in value for value in refreshed)

        assert launcher.AUTH_STORE.revoke(device_id)
        connection.request("GET", "/", headers={**tunnel_headers, "Cookie": cookie})
        response = connection.getresponse()
        response.read()
        assert response.status == 303
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
