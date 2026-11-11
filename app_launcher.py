"""Standalone desktop application launcher for Finance Pulse Analytics.

Binds the Flask application cleanly to loopback 127.0.0.1 on an ephemeral port,
waits for /health readiness, and opens a native pywebview desktop window with
automatic web browser fallback. Also supports headless server mode and remote
Admin portal connections.
"""
from __future__ import annotations

import argparse
import getpass
import json
import logging
import multiprocessing
import os
import signal
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [FINANCE-PULSE] %(message)s")
logger = logging.getLogger("FinancePulse.Launcher")


def find_free_port(host: str = "127.0.0.1") -> int:
    """Return an available ephemeral TCP port on loopback."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def wait_for_server(host: str, port: int, expected_title: str = "", timeout_sec: float = 15.0) -> bool:
    """Poll /health until HTTP 200 reports status == 'ok'."""
    url = f"http://{host}:{port}/health"
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "FinancePulse-Launcher"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    payload = json.loads(resp.read().decode("utf-8"))
                    if payload.get("status") == "ok" and (not expected_title or payload.get("title") == expected_title):
                        return True
        except (urllib.error.URLError, ConnectionRefusedError, TimeoutError, socket.timeout, ValueError, OSError):
            time.sleep(0.1)
    return False


class FlaskServerThread(threading.Thread):
    """Managed daemon thread hosting Werkzeug threaded WSGI server."""

    def __init__(self, flask_app, host: str, port: int):
        super().__init__(daemon=True)
        from werkzeug.serving import make_server

        self.host = host
        self.port = port
        self.server = make_server(host, port, flask_app, threaded=True)

    def run(self) -> None:
        self.server.serve_forever()

    def stop(self) -> None:
        try:
            self.server.shutdown()
            self.server.server_close()
            if self.is_alive():
                self.join(timeout=3.0)
        except Exception:
            pass


def normalize_start_path(raw_path: str, admin_mode: bool) -> str:
    if raw_path:
        return raw_path if raw_path.startswith("/") else f"/{raw_path}"
    return "/admin/login" if admin_mode else "/"


def resolve_remote_url(cli_remote: str, start_path: str) -> Optional[str]:
    remote = (cli_remote or os.environ.get("FINANCE_PULSE_REMOTE_URL") or "").strip().rstrip("/")
    if not remote:
        return None
    if not remote.startswith(("http://", "https://")):
        remote = f"https://{remote}"
    return f"{remote}{start_path}"


def create_admin_account_cli(email: str, password: str, name: str) -> int:
    """Create an administrator account in the active database safely."""
    from datetime import datetime
    from werkzeug.security import generate_password_hash
    from database.db import connect, initialize

    initialize()
    clean_email = (email or "").strip().lower()
    if "@" not in clean_email:
        print("Error: Provide a valid email address.", file=sys.stderr)
        return 1
    if len(password or "") < 8:
        print("Error: Password must be at least 8 characters.", file=sys.stderr)
        return 1
    clean_name = (name or "System Administrator").strip() or "System Administrator"

    conn = connect()
    try:
        existing = conn.execute("SELECT id, role FROM users WHERE email=?", (clean_email,)).fetchone()
        now = datetime.utcnow().isoformat()
        pw_hash = generate_password_hash(password, method="pbkdf2:sha256")
        if existing:
            conn.execute(
                "UPDATE users SET name=?, password_hash=?, role='admin', status='active' WHERE id=?",
                (clean_name, pw_hash, existing["id"]),
            )
            conn.commit()
            print(f"Updated administrator account: {clean_email}")
        else:
            cur = conn.execute(
                "INSERT INTO users(name,email,password_hash,role,status,created_at) VALUES(?,?,?,?,?,?)",
                (clean_name, clean_email, pw_hash, "admin", "active", now),
            )
            conn.execute(
                "INSERT INTO workspaces(owner_user_id,name,created_at) VALUES(?,?,?)",
                (cur.lastrowid, f"{clean_name}'s workspace", now),
            )
            conn.commit()
            print(f"Created administrator account: {clean_email}")
    finally:
        conn.close()
    return 0


def _find_windows_chromium_app_browser() -> Optional[str]:
    """Locate Microsoft Edge or Google Chrome on Windows for chromeless --app mode."""
    import shutil

    candidates = []
    for env_var in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        root = os.environ.get(env_var)
        if not root:
            continue
        candidates.extend([
            Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe",
        ])
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    for binary in ("msedge.exe", "msedge", "chrome.exe", "chrome"):
        found = shutil.which(binary)
        if found:
            return found
    return None


def _open_chromium_app_window(
    target_url: str,
    storage_dir: Optional[Path] = None,
    on_close_callback=None,
) -> bool:
    """Launch Edge/Chrome in standalone chromeless --app window mode on Windows."""
    import subprocess

    browser = _find_windows_chromium_app_browser()
    if not browser:
        return False

    cmd = [
        browser,
        f"--app={target_url}",
        "--window-size=1320,860",
        "--new-window",
        "--no-first-run",
    ]
    if storage_dir is not None:
        shell_dir = Path(storage_dir).parent / "app_shell_profile"
    else:
        import config

        shell_dir = Path(config.DATA_DIR) / "app_shell_profile"
    shell_dir.mkdir(parents=True, exist_ok=True)
    cmd.append(f"--user-data-dir={shell_dir}")

    try:
        proc = subprocess.Popen(cmd)
    except OSError as exc:
        _write_launcher_diag(f"Chromium --app launch failed ({browser}): {exc!r}")
        return False
    try:
        start_ts = time.monotonic()
        proc.wait()
        # If the browser immediately handed off to an already-running process, keep server alive.
        if time.monotonic() - start_ts < 2.0 and proc.poll() is not None:
            while True:
                time.sleep(0.5)
    except KeyboardInterrupt:
        try:
            proc.terminate()
        except Exception:
            pass
    finally:
        if on_close_callback:
            on_close_callback()
    return True


def _write_launcher_diag(detail: str) -> None:
    try:
        import config

        log_path = Path(config.DATA_DIR) / "launcher.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {detail}\n")
    except Exception:
        pass


def open_native_or_browser(
    title: str,
    target_url: str,
    use_browser: bool,
    storage_dir: Optional[Path] = None,
    on_close_callback=None,
) -> None:
    if use_browser:
        import webbrowser

        logger.info("Opening browser at %s", target_url)
        webbrowser.open(target_url)
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            if on_close_callback:
                on_close_callback()
        return

    try:
        import webview

        if hasattr(webview, "settings"):
            webview.settings["ALLOW_DOWNLOADS"] = True
            webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True

        window = webview.create_window(
            title=title,
            url=target_url,
            width=1320,
            height=860,
            min_size=(960, 640),
            resizable=True,
            text_select=True,
            background_color="#F5F5F7",
            confirm_close=False,
        )

        def _closed():
            logger.info("Desktop window closed.")
            if on_close_callback:
                on_close_callback()

        window.events.closed += _closed
        if storage_dir is not None:
            try:
                storage_dir.mkdir(parents=True, exist_ok=True)
                webview.start(debug=False, private_mode=False, storage_path=str(storage_dir))
            except Exception as storage_exc:
                _write_launcher_diag(f"pywebview persistent storage fallback: {storage_exc!r}")
                webview.start(debug=False)
        else:
            webview.start(debug=False)
    except Exception as exc:
        logger.warning("Native desktop view unavailable (%s). Trying standalone app window fallback...", exc)
        _write_launcher_diag(f"pywebview failed ({exc!r}); attempting Chromium --app fallback")
        if sys.platform == "win32" and _open_chromium_app_window(
            target_url=target_url,
            storage_dir=storage_dir,
            on_close_callback=on_close_callback,
        ):
            return

        import webbrowser

        webbrowser.open(target_url)
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            if on_close_callback:
                on_close_callback()


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Finance Pulse Analytics Desktop Launcher")
    parser.add_argument("--browser", action="store_true", help="Open in default web browser instead of native desktop window.")
    parser.add_argument("--headless", "--server-only", dest="headless", action="store_true", help="Run embedded WSGI server without GUI.")
    parser.add_argument("--public", action="store_true", help="Bind to all network interfaces (0.0.0.0) for wireless LAN/tunnel access.")
    parser.add_argument("--admin", action="store_true", help="Open directly in the Administrator Portal (/admin/login).")
    parser.add_argument("--path", default="", help="Initial route path to open (e.g. / or /admin/login).")
    parser.add_argument("--host", default="127.0.0.1", help="Loopback bind host (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=0, help="TCP port to bind (0 selects a free ephemeral port).")
    parser.add_argument("--data-dir", default="", help="Override persistent SQLite & upload storage directory.")
    parser.add_argument("--remote-url", default="", help="Connect desktop shell to a hosted Finance Pulse Analytics server URL.")
    parser.add_argument("--create-admin", action="store_true", help="Create/update an admin account in the local database and exit.")
    parser.add_argument("--admin-email", default="", help="Admin email for --create-admin.")
    parser.add_argument("--admin-name", default="System Administrator", help="Admin display name for --create-admin.")
    # Ignore macOS Finder process serial number flags (-psn_0_...) cleanly when launched via .app bundle
    args, _ = parser.parse_known_args(argv)
    return args


def _lan_ipv4() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def main(argv: Optional[list[str]] = None) -> int:
    multiprocessing.freeze_support()
    args = parse_args(argv)

    if args.data_dir:
        os.environ["FINANCE_PULSE_DATA_DIR"] = str(Path(args.data_dir).expanduser().resolve())

    import config
    import updater

    if args.create_admin:
        email = args.admin_email or os.environ.get("FINANCE_PULSE_ADMIN_EMAIL") or input("Administrator email: ")
        pw = os.environ.get("FINANCE_PULSE_ADMIN_PASSWORD") or getpass.getpass("Administrator password (min 8 chars): ")
        return create_admin_account_cli(email=email, password=pw, name=args.admin_name)

    start_path = normalize_start_path(args.path, args.admin)
    remote_target = resolve_remote_url(args.remote_url, start_path)
    if remote_target and not args.headless:
        logger.info("Connecting to hosted server: %s", remote_target)
        webview_cache = config.DATA_DIR / ("webview_admin" if args.admin else "webview_user")
        open_native_or_browser(
            title=config.APP_NAME,
            target_url=remote_target,
            use_browser=args.browser,
            storage_dir=webview_cache,
        )
        return 0

    import app as flask_module

    bind_host = "0.0.0.0" if args.public and args.host == "127.0.0.1" else args.host
    probe_host = "127.0.0.1" if bind_host == "0.0.0.0" else bind_host
    port = args.port if args.port > 0 else find_free_port(probe_host)
    logger.info("Starting %s on http://%s:%s", config.APP_NAME, bind_host, port)
    if bind_host == "0.0.0.0":
        logger.info("LAN Wireless Sync URL: http://%s:%s", _lan_ipv4(), port)
    server_thread = FlaskServerThread(flask_module.app, bind_host, port)
    server_thread.start()

    if not wait_for_server(probe_host, port, expected_title=config.APP_TITLE, timeout_sec=25.0):
        logger.error("Health check failed on http://%s:%s/health", probe_host, port)
        server_thread.stop()
        return 1

    updater.start_background_update_check()

    def _shutdown(*_args):
        server_thread.stop()

    signal.signal(signal.SIGTERM, _shutdown)

    if args.headless:
        print(f"READY http://{probe_host}:{port}{start_path}", flush=True)
        try:
            while server_thread.is_alive():
                time.sleep(0.4)
        except KeyboardInterrupt:
            pass
        finally:
            server_thread.stop()
        return 0

    target_url = f"http://{probe_host}:{port}{start_path}"
    webview_cache = config.DATA_DIR / ("webview_admin" if args.admin else "webview_user")
    open_native_or_browser(
        title=config.APP_NAME,
        target_url=target_url,
        use_browser=args.browser,
        storage_dir=webview_cache,
        on_close_callback=server_thread.stop,
    )
    server_thread.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
