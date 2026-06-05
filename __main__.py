"""Entry point: python3 -m minimal_webmcp. Stdlib core, optional pywebview for embed mode."""

import os
import sys
import threading
import traceback

from . import server
from . import _qt_env
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
            "MINIMAL_WEBMCP_MOCK=1 python3 -m minimal_webmcp"
        )
    if sys.platform == "darwin":
        return (
            "# macOS (uses system Cocoa via PyObjC):\n"
            "pip install --user pywebview\n"
            "# If Qt backend desired: pip install --user 'pywebview[qt]'\n"
            "\n"
            "# Mock mode (no install):\n"
            "MINIMAL_WEBMCP_MOCK=1 python3 -m minimal_webmcp"
        )
    if sys.platform == "win32":
        return (
            "# Windows:\n"
            "pip install --user 'pywebview[qt]'\n"
            "\n"
            "# Mock mode:\n"
            "$env:MINIMAL_WEBMCP_MOCK=1; python -m minimal_webmcp"
        )
    return "pip install --user pywebview"


def _run_embedded(headless):
    """Embedded mode: webview.start() runs the GUI on the main thread (pywebview 6.x
    requirement), and server.run() runs in a worker thread started by webview."""
    try:
        driver = make_driver("embedded", headless=headless)
    except Exception as e:
        sys.stderr.write(f"minimal_webmcp: cannot create embedded driver: {e}\n")
        if "pywebview" in str(e).lower() or "No module named 'webview'" in str(e):
            sys.stderr.write("\n" + _install_hint() + "\n")
        sys.stderr.flush()
        return 1

    # Create the window on the main thread; webview.start() will spin the event loop here.
    try:
        driver._start()
    except Exception as e:
        sys.stderr.write(f"minimal_webmcp: driver _start error: {e}\n")
        sys.stderr.flush()
        return 1

    sys.stderr.write("minimal_webmcp: starting embedded driver\n")
    sys.stderr.flush()

    state = {"rc": 0}

    def _serve():
        # Runs in the worker thread created by webview.start().
        try:
            driver.wait_ready(timeout=60)
            sys.stderr.write("minimal_webmcp: ready\n")
            sys.stderr.flush()
            server.run(driver)
        except KeyboardInterrupt:
            pass
        except Exception as e:
            sys.stderr.write(f"minimal_webmcp: serve error: {e}\n{traceback.format_exc()}")
            sys.stderr.flush()
            state["rc"] = 1
        finally:
            try:
                driver.close()  # destroys window so webview.start() returns
            except Exception:
                pass

    import webview as _webview
    try:
        _webview.start(_serve)
    except KeyboardInterrupt:
        pass
    return state["rc"]


def main(argv=None):
    argv = argv or sys.argv[1:]

    # --print-install: print recommended pip install line and exit
    if "--print-install" in argv:
        sys.stdout.write(_install_hint() + "\n")
        return 0

    mock = os.environ.get("MINIMAL_WEBMCP_MOCK") == "1"
    # Accept both MINIMAL_WEBMCP_HEADLESS (canonical) and MINIMAL_MCP_HEADLESS (alias).
    headless = (
        os.environ.get("MINIMAL_WEBMCP_HEADLESS") == "1"
        or os.environ.get("MINIMAL_MCP_HEADLESS") == "1"
    )

    # Headless + no-GPU setup MUST happen before any code path that
    # could import pywebview or construct QApplication. See _qt_env docstring.
    _qt_env.configure_qt_for_headless(headless=headless)

    if mock:
        sys.stderr.write("minimal_webmcp: MOCK mode (no real browser)\n")
        sys.stderr.flush()
        try:
            server.run(make_driver("mock"))
        except KeyboardInterrupt:
            pass
        return 0

    # Default: embedded pywebview on main thread, server in worker.
    return _run_embedded(headless)


if __name__ == "__main__":
    main()
