#!/usr/bin/env python3
"""
lazycatter desktop entry

starts the local fastapi server on loopback
then opens the same ui in a native window
no browser
no docker
no command prompt for the end user
closing the window stops the server
"""

from __future__ import annotations

import os
import secrets
import socket
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path


APP_NAME = "LazyCatter"
DEFAULT_PORT = 8787


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _appdata_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _log_path() -> Path:
    return _appdata_dir() / "desktop.log"


def _log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n"
    try:
        with _log_path().open("a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError:
        pass


def _show_error(message: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, APP_NAME, 0x10)
    except Exception:
        print(message, file=sys.stderr)


def _load_or_create_ui_token() -> str:
    """keep a random ui gate secret under appdata
    never a discord token"""
    token_path = _appdata_dir() / "ui_token.txt"
    if token_path.is_file():
        existing = token_path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    token = secrets.token_urlsafe(24)
    token_path.write_text(token + "\n", encoding="utf-8")
    try:
        token_path.chmod(0o600)
    except OSError:
        pass
    return token


def _pick_port(preferred: int = DEFAULT_PORT) -> int:
    for port in range(preferred, preferred + 40):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free local port found for LazyCatter.")


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.35)
        try:
            sock.connect(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _wait_ready(url: str, port: int, server: threading.Thread, errors: list, timeout: float = 45.0) -> None:
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        if errors:
            raise RuntimeError(f"Server failed to start: {errors[0]}")
        if not server.is_alive() and not _port_open(port):
            detail = errors[0] if errors else "server thread exited early"
            raise RuntimeError(f"Server failed to start: {detail}")
        try:
            if _port_open(port):
                with urllib.request.urlopen(url, timeout=2.0) as resp:
                    if 200 <= resp.status < 500:
                        return
        except urllib.error.HTTPError as exc:
            # app answered http
            # ui route might still be loading
            if exc.code < 500:
                return
            last_err = exc
        except Exception as exc:  # noqa: BLE001
            last_err = exc
        time.sleep(0.2)
    raise RuntimeError(f"LazyCatter UI did not start: {last_err}")


def main() -> int:
    # windowed pyinstaller builds leave stdout/stderr as None
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

    # imports need to work from source tree and frozen exe
    here = Path(__file__).resolve().parent
    root = here.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))

    os.environ["LAZYCATTER_DESKTOP"] = "1"
    os.environ["HOST"] = "127.0.0.1"
    os.environ["LAZYCATTER_UI_TOKEN"] = _load_or_create_ui_token()

    port = _pick_port(int(os.environ.get("PORT", str(DEFAULT_PORT))))
    os.environ["PORT"] = str(port)
    url = f"http://127.0.0.1:{port}/"
    _log(f"starting on {url} frozen={getattr(sys, 'frozen', False)}")

    # import after env is set
    # so app picks up token + desktop flag
    try:
        from app import run_server  # noqa: WPS433 intentional late import
    except Exception:
        _show_error("Failed to load LazyCatter:\n\n" + traceback.format_exc())
        return 1

    errors: list = []

    def _on_error(exc: BaseException) -> None:
        errors.append(exc)
        _log("server error:\n" + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))

    server = threading.Thread(
        target=run_server,
        kwargs={"host": "127.0.0.1", "port": port, "on_error": _on_error},
        name="lazycatter-server",
        daemon=True,
    )
    server.start()
    try:
        _wait_ready(url, port, server, errors)
    except Exception as exc:
        _show_error(
            "LazyCatter could not start its local window.\n\n"
            + f"{exc}\n\n"
            + f"Details: {_log_path()}\n\n"
            + "Close any old LazyCatter windows and try again. "
            + "If it keeps failing, open a GitHub Issue at "
            + "https://github.com/ShahriarAHaque/LazyCatter/issues"
        )
        return 1

    _log("server ready")

    try:
        import webview
        import webbrowser
    except ImportError:
        import webbrowser

        webbrowser.open(url)
        _show_error(
            f"{APP_NAME} could not open its desktop window (pywebview missing).\n"
            f"Opened the browser at {url} instead.\n"
            "Close the browser tab when finished.\n\n"
            "Dev install: pip install -r bot/requirements-desktop.txt"
        )
        try:
            while server.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        return 0

    class _Bridge:
        def open_url(self, web_url: str) -> None:
            if isinstance(web_url, str) and web_url.startswith(("http://", "https://")):
                webbrowser.open(web_url)

    # open http(s) links outside the app window
    # in the system browser
    try:
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    except Exception:
        pass

    webview.create_window(
        f"{APP_NAME}",
        url,
        width=980,
        height=820,
        min_size=(720, 560),
        text_select=True,
        js_api=_Bridge(),
    )
    webview.start()
    _log("window closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
