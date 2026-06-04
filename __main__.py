"""Entry point: python3 -m webmcp. Stdlib core, optional pywebview for embed mode."""

import os
import sys
import threading
import traceback

from . import server
from .drivers import make_driver


def _install_hint():
    """Return recommended pip install line for the current platform."""
    if sys.platform.startswith("linux"):
        # RHEL 8.x + glibc 2.28 friendly
        return (
            "# RHEL 8.x (uses system PySide2 — minimal pip install):\n"
            "sudo dnf install python3-pyside2 && pip install --user pywebview\n"
            "\n"
            "# Or pure pip (PySide6, needs glibc 2.28+):\n"
            "pip install --user 'pywebview[qt]'\n"
            "\n"
            "# Or mock mode (no install):\n"
            "WEBMCP_MOCK=1 python3 -m webmcp"
        )
    if sys.platform == "darwin":
        return (
            "# macOS (uses system Cocoa via PyObjC):\n"
            "pip install --user pywebview\n"
            "# If Qt backend desired: pip install --user 'pywebview[qt]'\n"
            "\n"
            "# Mock mode (no install):\n"
            "WEBMCP_MOCK=1 python3 -m webmcp"
        )
    if sys.platform == "win32":
        return (
            "# Windows:\n"
            "pip install --user 'pywebview[qt]'\n"
            "\n"
            "# Mock mode:\n"
            "$env:WEBMCP_MOCK=1; python -m webmcp"
        )
    return "pip install --user pywebview"


class DriverProxy:
    """Forwards to a real driver once it's ready. Blocks until ready (or error)."""

    def __init__(self, ready_event, get_driver, get_error):
        self._ready = ready_event
        self._get_driver = get_driver
        self._get_error = get_error

    def __getattr__(self, name):
        if not self._ready.wait(timeout=60):
            raise RuntimeError("webmcp: driver not ready within 60s")
        err = self._get_error()
        if err is not None:
            raise err
        driver = self._get_driver()
        if driver is None:
            raise RuntimeError("webmcp: driver unavailable")
        return getattr(driver, name)


def _bootstrap(kind, kwargs, state):
    """Background: instantiate driver."""
    try:
        sys.stderr.write(f"webmcp: starting {kind} driver\n")
        sys.stderr.flush()
        driver = make_driver(kind, **kwargs)
        if hasattr(driver, "_start"):
            driver._start()
        state["driver"] = driver
        sys.stderr.write("webmcp: ready\n")
        sys.stderr.flush()
    except Exception as e:
        state["error"] = e
        sys.stderr.write(f"webmcp: bootstrap error: {e}\n")
        if "pywebview" in str(e).lower() or "No module named 'webview'" in str(e):
            sys.stderr.write("\n" + _install_hint() + "\n")
        sys.stderr.flush()
    finally:
        state["ready"].set()


def main(argv=None):
    argv = argv or sys.argv[1:]

    # --print-install: print recommended pip install line and exit
    if "--print-install" in argv:
        sys.stdout.write(_install_hint() + "\n")
        return 0

    mock = os.environ.get("WEBMCP_MOCK") == "1"
    headless = os.environ.get("WEBMCP_HEADLESS") == "1"

    if mock:
        sys.stderr.write("webmcp: MOCK mode (no real browser)\n")
        sys.stderr.flush()
        try:
            server.run(make_driver("mock"))
        except KeyboardInterrupt:
            pass
        return 0

    # Default: embedded pywebview
    state = {"ready": threading.Event(), "driver": None, "error": None}
    kwargs = {}
    if headless:
        kwargs["headless"] = True
    threading.Thread(
        target=_bootstrap, args=("embedded", kwargs, state), daemon=True
    ).start()

    proxy = DriverProxy(
        state["ready"],
        lambda: state["driver"],
        lambda: state["error"],
    )

    try:
        server.run(proxy)
    except KeyboardInterrupt:
        pass
    finally:
        driver = state["driver"]
        if driver is not None:
            try:
                driver.close()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    main()
