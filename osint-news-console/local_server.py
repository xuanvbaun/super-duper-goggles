"""Windows launcher: local web server, device-code gate and Cloudflare tunnel."""

from __future__ import annotations

import hmac
import http.client
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from html import escape
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend" / "dist"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.device_auth import (  # noqa: E402 - backend path is resolved at runtime
    DEVICE_TTL_SECONDS,
    PERMANENT_COOKIE_SECONDS,
    DeviceAuthStore,
    LoginRateLimiter,
    safe_next as _safe_next,
)

BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000
WEB_HOST = "127.0.0.1"
WEB_PORT = 5173
CLOUDFLARED = ROOT / "cloudflared.exe"
PUBLIC_URL_FILE = ROOT / "PUBLIC_URL.txt"
PUBLIC_URL_PATTERN = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")

DEVICE_COOKIE = "osint_device"
PAIRING_CODE = f"{secrets.randbelow(100_000_000):08d}"
ADMIN_NONCE = secrets.token_urlsafe(24)
AUTH_FILE = BACKEND / "data" / "authorized_devices.json"
LOGIN_FILE = BACKEND / "data" / "login_attempts.json"
TUNNEL_SETTINGS_FILE = BACKEND / "data" / "tunnel-settings.json"
TUNNEL_TOKEN_FILE = BACKEND / "data" / "tunnel-token.txt"


AUTH_STORE = DeviceAuthStore(AUTH_FILE)
RATE_LIMITER = LoginRateLimiter(path=LOGIN_FILE)


def _format_timestamp(value: float) -> str:
    if not value:
        return "—"
    return datetime.fromtimestamp(value, ZoneInfo("Asia/Shanghai")).strftime(
        "%Y-%m-%d %H:%M"
    )


def _load_tunnel_settings() -> dict[str, str] | None:
    try:
        data = json.loads(TUNNEL_SETTINGS_FILE.read_text(encoding="utf-8"))
        public_url = str(data.get("public_url", "")).strip().rstrip("/")
        parsed = urlsplit(public_url)
        if (
            parsed.scheme == "https"
            and parsed.netloc
            and TUNNEL_TOKEN_FILE.exists()
            and TUNNEL_TOKEN_FILE.stat().st_size > 20
        ):
            return {"public_url": public_url}
    except (OSError, ValueError, TypeError):
        pass
    return None


def _page(title: str, body: str, *, wide: bool = False) -> bytes:
    width = "980px" if wide else "460px"
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><style>
*{{box-sizing:border-box}}:root{{color-scheme:dark}}
body{{margin:0;min-height:100vh;background:radial-gradient(circle at 70% -10%,#1b4b7629,transparent 36%),#071321;color:#edf4ff;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei','Segoe UI',sans-serif}}
body:before{{content:'OSINT NEWS CONSOLE';display:block;position:fixed;top:22px;left:28px;color:#62aaff;font-size:10px;font-weight:800;letter-spacing:1.8px}}
main{{max-width:{width};margin:7vh auto;padding:30px;border:1px solid #89a9cf33;border-radius:14px;background:linear-gradient(145deg,#142740f2,#0d1d30f7);box-shadow:0 22px 60px #00000052}}
h1,h2{{margin:0 0 10px}}h1{{font-size:27px;letter-spacing:.2px}}h2{{font-size:17px;margin-top:30px;border-bottom:1px solid #89a9cf2b;padding-bottom:10px}}
p{{color:#9eacc1;line-height:1.7}}label{{display:block;margin:18px 0 7px;color:#c9d8eb;font-size:13px;font-weight:700}}
input{{width:100%;padding:12px;border:1px solid #89a9cf38;border-radius:8px;outline:0;background:#071a2d;color:#edf4ff;font-size:16px}}
input:focus{{border-color:#62aaff}}input::placeholder{{color:#6f7f96}}input.code-input{{font-size:22px;letter-spacing:5px;text-align:center}}
button{{padding:10px 14px;border:1px solid #62aaff73;border-radius:8px;background:#62aaff;color:#061321;font-weight:750;cursor:pointer;transition:.16s ease}}
button:hover{{filter:brightness(1.08)}}button.secondary{{border-color:#89a9cf38;background:#1a3553;color:#c9d8eb}}button.danger{{border-color:#ff625e66;background:#a83c3a;color:white}}form.inline{{display:inline-flex;gap:6px;align-items:center;margin:5px 4px 0 0}}
.error{{color:#ffaaa7;background:#ff625e12;padding:11px;border:1px solid #ff625e42;border-left:3px solid #ff625e;border-radius:7px}}.code{{font-size:30px;letter-spacing:6px;font-weight:800;text-align:center;padding:14px;border:1px dashed #62aaffb3;border-radius:9px;background:#071a2d;color:#86c2ff}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:12px}}.card{{border:1px solid #89a9cf29;border-radius:10px;background:#101f33;padding:16px}}.card strong{{display:block;font-size:15px;margin-bottom:7px}}.meta{{font-size:11px;color:#8798b0;line-height:1.75}}.badge{{display:inline-block;padding:2px 7px;border:1px solid #89a9cf33;border-radius:999px;background:#1a2e47;color:#9eacc1;font-size:10px;margin-left:7px}}.badge.good{{border-color:#55c98b4d;background:#55c98b16;color:#72dba3}}
small{{color:#6f7f96}}@media(max-width:700px){{body:before{{display:none}}main{{margin:0;padding:24px 18px;min-height:100vh;border:0;border-radius:0}}.grid{{grid-template-columns:1fr}}}}
</style></head><body><main>{body}</main></body></html>""".encode("utf-8")


class LocalHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND), **kwargs)

    def _is_tunnel_request(self) -> bool:
        host = self.headers.get("Host", "").split(":", 1)[0].lower()
        return bool(self.headers.get("CF-Connecting-IP")) or host.endswith(
            ".trycloudflare.com"
        )

    def _client_key(self) -> str:
        return self.headers.get("CF-Connecting-IP") or self.client_address[0]

    def _device_token(self) -> str | None:
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except Exception:  # noqa: BLE001 - 非法 Cookie 只视为未登录
            return None
        morsel = cookie.get(DEVICE_COOKIE)
        return morsel.value if morsel else None

    def _authorized(self) -> bool:
        # 服务只监听 127.0.0.1；本机直连免登录，Cloudflare 请求必须验证。
        if not self._is_tunnel_request():
            self._auth_record = {"local": True}
            return True
        self._auth_record = AUTH_STORE.get_authorization(
            self._device_token(), self._client_key()
        )
        return self._auth_record is not None

    def end_headers(self) -> None:
        record = getattr(self, "_auth_record", None)
        token = self._device_token()
        if self._is_tunnel_request() and record and token:
            max_age = (
                PERMANENT_COOKIE_SECONDS
                if record.get("permanent", False)
                else DEVICE_TTL_SECONDS
            )
            self.send_header(
                "Set-Cookie",
                f"{DEVICE_COOKIE}={token}; Path=/; Max-Age={max_age}; "
                "HttpOnly; Secure; SameSite=Strict",
            )
        super().end_headers()

    def _send_html(
        self,
        status: int,
        payload: bytes,
        *,
        cookie: str | None = None,
        location: str | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'",
        )
        if cookie:
            self.send_header("Set-Cookie", cookie)
        if location:
            self.send_header("Location", location)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    def _redirect(self, location: str, cookie: str | None = None) -> None:
        self._send_html(303, b"", cookie=cookie, location=location)

    def _login_page(self, message: str = "", status: int = 200) -> None:
        query = parse_qs(urlsplit(self.path).query)
        next_path = _safe_next(query.get("next", ["/"])[0])
        error = f'<p class="error">{escape(message)}</p>' if message else ""
        body = f"""
<h1>设备验证</h1><p>这是受保护的 OSINT 新闻控制台。请输入电脑启动窗口显示的 8 位设备码。</p>{error}
<form method="post" action="/device-login"><input type="hidden" name="next" value="{escape(next_path, quote=True)}">
<label for="name">设备名称</label><input id="name" name="name" maxlength="40" placeholder="例如：我的手机">
<label for="code">设备码</label><input class="code-input" id="code" name="code" inputmode="numeric" pattern="[0-9]{{8}}" maxlength="8" autocomplete="one-time-code" autofocus required>
<button type="submit" style="width:100%;margin-top:14px">授权此设备30天</button></form><p><small>连续输错 5 次会按当前公网地址限制 24 小时。需要永久访问时，先完成配对，再由本机管理页设为永久。</small></p>"""
        self._send_html(status, _page("设备验证", body))

    def _admin_page(self, message: str = "") -> None:
        if self._is_tunnel_request():
            self.send_error(404)
            return
        notice = f'<p class="error">{escape(message)}</p>' if message else ""
        devices = AUTH_STORE.list_devices()
        device_cards = []
        for device in devices:
            device_id = escape(device["id"], quote=True)
            mode = (
                '<span class="badge good">永久授权</span>'
                if device.get("permanent")
                else '<span class="badge">30天授权</span>'
            )
            toggle_action = "temporary" if device.get("permanent") else "permanent"
            toggle_label = "改为30天" if device.get("permanent") else "设为永久"
            device_cards.append(
                f"""<div class="card"><strong>{escape(device['name'])}{mode}</strong>
<div class="meta">首次授权：{_format_timestamp(device['created_at'])}<br>最后使用：{_format_timestamp(device['last_seen'])}<br>最近地址：{escape(device.get('last_ip') or '—')}</div>
<form class="inline" method="post" action="/device-admin/device"><input type="hidden" name="nonce" value="{ADMIN_NONCE}"><input type="hidden" name="device_id" value="{device_id}"><input type="hidden" name="action" value="{toggle_action}"><button class="secondary" type="submit">{toggle_label}</button></form>
<form class="inline" method="post" action="/device-admin/device"><input type="hidden" name="nonce" value="{ADMIN_NONCE}"><input type="hidden" name="device_id" value="{device_id}"><input type="hidden" name="action" value="revoke"><button class="danger" type="submit">撤销</button></form></div>"""
            )
        if not device_cards:
            device_cards.append('<div class="card"><p>还没有已授权设备。</p></div>')

        blocks = RATE_LIMITER.list_blocked()
        block_cards = []
        for block in blocks:
            block_cards.append(
                f"""<div class="card"><strong>{escape(block['label'])}</strong><div class="meta">限制至：{_format_timestamp(block['until'])}</div>
<form class="inline" method="post" action="/device-admin/unblock"><input type="hidden" name="nonce" value="{ADMIN_NONCE}"><input type="hidden" name="block_id" value="{escape(block['id'], quote=True)}"><button class="secondary" type="submit">解除限制</button></form></div>"""
            )
        if not block_cards:
            block_cards.append('<div class="card"><p>当前没有被限制的地址。</p></div>')

        tunnel = _load_tunnel_settings()
        tunnel_text = (
            f"固定网址：<strong>{escape(tunnel['public_url'])}</strong>"
            if tunnel
            else "当前使用随机临时网址；运行 configure-fixed-url.bat 后切换固定网址。"
        )
        body = f"""
<h1>设备安全中心</h1>{notice}<p>{tunnel_text}</p><p>当前启动设备码：</p><div class="code">{PAIRING_CODE}</div>
<h2>已授权设备 · {len(devices)}</h2><div class="grid">{''.join(device_cards)}</div>
<form method="post" action="/device-admin/revoke"><input type="hidden" name="nonce" value="{ADMIN_NONCE}"><button class="danger" type="submit" style="margin-top:14px">撤销全部设备授权</button></form>
<h2>登录限制</h2><div class="grid">{''.join(block_cards)}</div>
<p><small>永久授权表示服务端不会自动过期，但清除浏览器 Cookie、更换浏览器或手动撤销后仍需重新配对。本页面只能从当前电脑的 127.0.0.1 地址打开。</small></p>"""
        self._send_html(200, _page("设备安全中心", body, wide=True))

    def _read_form(self) -> dict[str, str]:
        length = min(int(self.headers.get("Content-Length", "0")), 4096)
        values = parse_qs(self.rfile.read(length).decode("utf-8", errors="replace"))
        return {key: items[0] for key, items in values.items() if items}

    def _handle_login(self) -> None:
        key = self._client_key()
        if not RATE_LIMITER.can_attempt(key):
            blocked_until = RATE_LIMITER.blocked_until(key)
            self._login_page(
                f"尝试次数过多，已限制至 {_format_timestamp(blocked_until)}。",
                429,
            )
            return
        form = self._read_form()
        code = re.sub(r"\D", "", form.get("code", ""))
        device_name = form.get("name", "").strip()[:40] or "未命名设备"
        next_path = _safe_next(form.get("next"))
        if not hmac.compare_digest(code, PAIRING_CODE):
            remaining = RATE_LIMITER.record_failure(key)
            message = (
                f"设备码错误，还可尝试 {remaining} 次。"
                if remaining
                else "设备码错误，已按当前公网地址限制 24 小时。"
            )
            self.path = f"/device-login?next={quote(next_path, safe='/')}"
            self._login_page(message, 401 if remaining else 429)
            return
        RATE_LIMITER.clear(key)
        token = secrets.token_urlsafe(32)
        AUTH_STORE.authorize(token, device_name, key)
        cookie = (
            f"{DEVICE_COOKIE}={token}; Path=/; Max-Age={DEVICE_TTL_SECONDS}; "
            "HttpOnly; Secure; SameSite=Strict"
        )
        self._redirect(next_path, cookie)

    def _deny_unauthorized(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api" or path.startswith("/api/"):
            payload = json.dumps({"detail": "设备未授权"}, ensure_ascii=False).encode(
                "utf-8"
            )
            self.send_response(401)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self._redirect(f"/device-login?next={quote(_safe_next(self.path), safe='/?:=&')}")

    def _proxy(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else None
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower()
            not in {"host", "connection", "content-length", "cookie"}
        }
        connection = http.client.HTTPConnection(BACKEND_HOST, BACKEND_PORT, timeout=120)
        try:
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            payload = response.read()
            self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() not in {
                    "connection",
                    "transfer-encoding",
                    "content-length",
                }:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        finally:
            connection.close()

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/device-login":
            if self._authorized() and self._is_tunnel_request():
                query = parse_qs(urlsplit(self.path).query)
                self._redirect(_safe_next(query.get("next", ["/"])[0]))
            else:
                self._login_page()
            return
        if path == "/device-admin":
            self._admin_page()
            return
        if not self._authorized():
            self._deny_unauthorized()
            return
        if path == "/api" or path.startswith("/api/"):
            self._proxy()
            return
        requested = path.lstrip("/")
        if requested and not (FRONTEND / requested).exists():
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path == "/device-login":
            self._handle_login()
            return
        if path == "/device-admin/revoke":
            if self._is_tunnel_request():
                self.send_error(404)
                return
            form = self._read_form()
            if not hmac.compare_digest(form.get("nonce", ""), ADMIN_NONCE):
                self.send_error(403)
                return
            count = AUTH_STORE.revoke_all()
            self._admin_page(f"已撤销 {count} 台设备的授权。")
            return
        if path == "/device-admin/device":
            if self._is_tunnel_request():
                self.send_error(404)
                return
            form = self._read_form()
            if not hmac.compare_digest(form.get("nonce", ""), ADMIN_NONCE):
                self.send_error(403)
                return
            device_id = form.get("device_id", "")
            action = form.get("action", "")
            if action == "permanent":
                changed = AUTH_STORE.set_permanent(device_id, True)
                message = "设备已改为永久授权。" if changed else "未找到该设备。"
            elif action == "temporary":
                changed = AUTH_STORE.set_permanent(device_id, False)
                message = "设备已改为30天授权。" if changed else "未找到该设备。"
            elif action == "revoke":
                changed = AUTH_STORE.revoke(device_id)
                message = "设备授权已撤销。" if changed else "未找到该设备。"
            else:
                message = "未知的设备操作。"
            self._admin_page(message)
            return
        if path == "/device-admin/unblock":
            if self._is_tunnel_request():
                self.send_error(404)
                return
            form = self._read_form()
            if not hmac.compare_digest(form.get("nonce", ""), ADMIN_NONCE):
                self.send_error(403)
                return
            changed = RATE_LIMITER.unblock(form.get("block_id", ""))
            self._admin_page("登录限制已解除。" if changed else "未找到该限制。")
            return
        if not self._authorized():
            self._deny_unauthorized()
            return
        self._proxy()

    def _authenticated_proxy(self) -> None:
        if not self._authorized():
            self._deny_unauthorized()
            return
        self._proxy()

    do_PUT = _authenticated_proxy
    do_PATCH = _authenticated_proxy
    do_DELETE = _authenticated_proxy
    do_OPTIONS = _authenticated_proxy


def wait_for_backend(seconds: int = 30) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            connection = http.client.HTTPConnection(BACKEND_HOST, BACKEND_PORT, timeout=2)
            connection.request("GET", "/")
            response = connection.getresponse()
            response.read()
            connection.close()
            if response.status == 200:
                return
        except OSError:
            time.sleep(1)
    raise RuntimeError("Backend did not start within 30 seconds.")


def start_public_tunnel(local_address: str) -> subprocess.Popen[str]:
    """Start a configured named tunnel, otherwise use a temporary Quick Tunnel."""
    if not CLOUDFLARED.exists():
        raise RuntimeError("cloudflared.exe is missing; run install-to-d.bat again.")
    PUBLIC_URL_FILE.unlink(missing_ok=True)
    settings = _load_tunnel_settings()
    if settings:
        public_url = settings["public_url"]
        tunnel = subprocess.Popen(
            [
                str(CLOUDFLARED),
                "tunnel",
                "--no-autoupdate",
                "run",
                "--token-file",
                str(TUNNEL_TOKEN_FILE),
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        PUBLIC_URL_FILE.write_text(public_url + "\n", encoding="utf-8")
        print("\n" + "=" * 64)
        print(f"固定公网地址：{public_url}")
        print(f"设备码：{PAIRING_CODE}")
        print("新设备首次打开需要输入设备码；已授权设备按权限继续访问。")
        print("本机设备管理：http://127.0.0.1:5173/device-admin")
        print("=" * 64 + "\n")

        def capture_named_output() -> None:
            assert tunnel.stdout is not None
            for line in tunnel.stdout:
                print(f"[cloudflared] {line.rstrip()}")
            if tunnel.returncode not in {None, 0}:
                print("固定隧道启动失败，请检查 token、域名路由和网络。")

        threading.Thread(target=capture_named_output, daemon=True).start()

        def open_named_url() -> None:
            time.sleep(2)
            if tunnel.poll() is None:
                webbrowser.open(public_url)

        threading.Thread(target=open_named_url, daemon=True).start()
        return tunnel

    tunnel = subprocess.Popen(
        [str(CLOUDFLARED), "tunnel", "--no-autoupdate", "--url", local_address],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    def capture_output() -> None:
        public_url: str | None = None
        assert tunnel.stdout is not None
        for line in tunnel.stdout:
            print(f"[cloudflared] {line.rstrip()}")
            match = PUBLIC_URL_PATTERN.search(line)
            if match and public_url is None:
                public_url = match.group(0)
                PUBLIC_URL_FILE.write_text(public_url + "\n", encoding="utf-8")
                print("\n" + "=" * 64)
                print(f"公网访问地址：{public_url}")
                print(f"设备码：{PAIRING_CODE}")
                print("当前未配置固定隧道；关闭窗口后临时地址失效。")
                print("运行 configure-fixed-url.bat 可切换为固定网址。")
                print("本机设备管理：http://127.0.0.1:5173/device-admin")
                print("=" * 64 + "\n")
                webbrowser.open(public_url)
        if public_url is None:
            print("公网隧道未生成，请检查网络或重新启动。")

    threading.Thread(target=capture_output, daemon=True).start()
    return tunnel


def main() -> None:
    if not FRONTEND.exists():
        raise RuntimeError("frontend/dist is missing; reinstall the deployment package.")
    env = os.environ.copy()
    env["OSINT_CONFIG_DIR"] = str(ROOT)
    backend = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            BACKEND_HOST,
            "--port",
            str(BACKEND_PORT),
        ],
        cwd=BACKEND,
        env=env,
    )
    tunnel: subprocess.Popen[str] | None = None
    server: ThreadingHTTPServer | None = None
    try:
        wait_for_backend()
        server = ThreadingHTTPServer((WEB_HOST, WEB_PORT), LocalHandler)
        address = f"http://127.0.0.1:{WEB_PORT}"
        print(f"本机访问地址：{address}（本机免设备码）")
        print(f"本次启动设备码：{PAIRING_CODE}")
        print("正在生成公网访问地址，请稍候……")
        tunnel = start_public_tunnel(address)
        print("按 Ctrl+C 或关闭本窗口可停止服务。")
        webbrowser.open(address)
        server.serve_forever()
    finally:
        if server is not None:
            server.server_close()
        if tunnel is not None:
            tunnel.terminate()
            try:
                tunnel.wait(timeout=10)
            except subprocess.TimeoutExpired:
                tunnel.kill()
        backend.terminate()
        try:
            backend.wait(timeout=10)
        except subprocess.TimeoutExpired:
            backend.kill()


if __name__ == "__main__":
    main()
