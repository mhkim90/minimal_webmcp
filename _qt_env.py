"""Headless + no-GPU environment setup. Call BEFORE webview.start() / QApplication.

This module exists so the heavy lifting of "configure the runtime for
headless + no-GPU" lives in one place and is callable from `__main__.py`
*before* pywebview's `webview.start()` constructs `QApplication`.

Critical ordering rule (the most common production mistake):
  - `os.environ["QTWEBENGINE_CHROMIUM_FLAGS"]` and
    `os.environ["QT_QPA_PLATFORM"]` MUST be set BEFORE any code path
    that could import pywebview or construct QApplication.
  - `QCoreApplication.setAttribute(Qt.AA_UseSoftwareOpenGL, True)` MUST
    be called BEFORE the QApplication(...) constructor. If a Qt
    binding is not importable at the moment of the call, we skip the
    attribute and let the existing import-time error surface
    naturally -- pywebview's start() will fail loudly.
"""

import os
import sys


# Default Chromium flag recipe for headless + no-GPU (sub-scenario A in
# turn 2's plan: "No GPU hardware"). Tuned for offscreen QPA + SwiftShader.
_DEFAULT_QT_FLAGS = (
    "--disable-gpu "
    "--use-gl=swiftshader "
    "--disable-gpu-compositing "
    "--in-process-gpu "
    "--disable-dev-shm-usage "
    "--disable-background-timer-throttling "
    "--disable-renderer-backgrounding "
    "--disable-backgrounding-occluded-windows "
    "--disable-features=Translate,BackForwardCache,MediaRouter,VizDisplayCompositor "
    "--no-first-run --no-default-browser-check"
)


def _extra_flags():
    """Add --no-sandbox only when running as root (or in a restricted
    container). Emitted on stderr elsewhere if used."""
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return "--no-sandbox"
    return ""


def _try_set_aa_software_opengl():
    """Set Qt.AA_UseSoftwareOpenGL if any Qt binding is importable.
    Best-effort: a missing binding surfaces later when pywebview tries
    to construct QApplication, which is the existing behaviour we want
    to preserve."""
    for modname in (
        "PyQt5.QtCore",
        "PyQt6.QtCore",
        "PySide2.QtCore",
        "PySide6.QtCore",
    ):
        try:
            mod = __import__(modname, fromlist=["QCoreApplication", "Qt"])
        except Exception:
            continue
        try:
            mod.QCoreApplication.setAttribute(mod.Qt.AA_UseSoftwareOpenGL, True)
            return True
        except Exception:
            return False
    return False


def _note_alias_once():
    """If the user spelled the env var MINIMAL_MCP_HEADLESS (without the
    WEBMCP infix) -- as the original turn-3 query did -- print a one-time
    stderr note pointing at the canonical name. Idempotent: only the
    first call writes."""
    if os.environ.get("MINIMAL_MCP_HEADLESS") == "1" and \
            "MINIMAL_WEBMCP_DEPRECATION_NOTED" not in os.environ:
        sys.stderr.write(
            "minimal_webmcp: MINIMAL_MCP_HEADLESS is an alias for "
            "MINIMAL_WEBMCP_HEADLESS; the canonical name is "
            "MINIMAL_WEBMCP_HEADLESS.\n"
        )
        sys.stderr.flush()
        os.environ["MINIMAL_WEBMCP_DEPRECATION_NOTED"] = "1"


def configure_qt_for_headless(headless: bool) -> None:
    """Apply Qt / WebEngine / pywebview env vars for headless + no-GPU.

    Idempotent. Safe to call multiple times. Must be called on the main
    thread, BEFORE webview.start() / QApplication construction.
    """
    if not headless:
        return
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    if sys.platform.startswith("linux"):
        os.environ.setdefault("PYWEBVIEW_GUI", "qt")
    os.environ.setdefault("PYWEBVIEW_LOG", "WARNING")
    # Force software rendering for the Qt Quick / RHI / OpenGL stacks.
    # Without these, QtWebEngine can try to acquire a GL context from a
    # background thread (the worker that runs the JSON-RPC loop) and
    # abort the process with "Cannot make QOpenGLContext current in a
    # different thread" -- which is fatal and cannot be caught from
    # Python. The Qt grab helper in drivers/qt_grab.py uses QPixmap
    # directly and works fine under software rendering; the offscreen
    # QPA platform is designed for it.
    os.environ.setdefault("QT_QUICK_BACKEND", "software")
    os.environ.setdefault("QSG_RHI_BACKEND", "software")
    os.environ.setdefault("QT_OPENGL", "software")
    _try_set_aa_software_opengl()
    _note_alias_once()
