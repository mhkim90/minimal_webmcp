"""Qt-native window grab. Bypasses the WebEngine canvas pipeline.

Used as tier 2 of the embedded driver's 3-tier screenshot path:
  1. JS `__minimal_webmcp_screenshot()` (canvas.toDataURL) — may fail
     under offscreen QPA + no GPU because the WebEngine rasterizer
     stubs the SVG-via-Image decode.
  2. `QPixmap.grab()` on the pywebview top-level widget — works under
     `QT_QPA_PLATFORM=offscreen` because that QPA was designed exactly
     for "render Qt widgets to pixmap" use cases.
  3. Page-digest dict (`__minimal_webmcp_page_digest()`) — always works
     but returns structured metadata, not an image.

Binding-agnostic via qtpy (a pywebview dependency). Tested against
PySide6 and PyQt5; qtpy's API_NAME exposes the active binding so the
grab helper does not care which one is loaded. PySide2 is intentionally
unsupported — it is incompatible with Python 3.11+ in some installs.
"""

import time


def _app():
    """Return the live QApplication / QGuiApplication instance, or None."""
    try:
        from qtpy import QtWidgets
        app = QtWidgets.QApplication.instance()
        if app is not None:
            return app
        from qtpy import QtGui
        return QtGui.QGuiApplication.instance()
    except Exception:
        return None


def _find_window(timeout_s=2.0):
    """Find a visible top-level QWidget or QWindow. Returns (widget, name)
    or (None, None) on failure. Polls briefly because the window may not
    be visible yet at the time of the first call.
    """
    try:
        from qtpy import QtWidgets, QtGui
    except Exception:
        return None, None
    app = _app()
    if app is None:
        return None, None
    name = None
    try:
        from qtpy import API_NAME as name
    except Exception:
        pass
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            tops = app.topLevelWidgets()
        except Exception:
            tops = []
        for w in tops:
            try:
                if w.isVisible() and w.width() > 0 and w.height() > 0:
                    return w, name
            except Exception:
                continue
        try:
            wins = QtGui.QGuiApplication.topLevelWindows()
        except Exception:
            wins = []
        for win in wins:
            try:
                if win.isVisible() and win.width() > 0 and win.height() > 0:
                    return win, name
            except Exception:
                continue
        try:
            app.processEvents()
        except Exception:
            pass
        time.sleep(0.05)
    return None, name


def _encode_pixmap_to_png(pix):
    """Encode a QPixmap to PNG bytes via QBuffer. Returns bytes or None."""
    try:
        from qtpy import QtCore
        buf = QtCore.QBuffer()
        buf.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        ok = pix.save(buf, "PNG")
        data = bytes(buf.data()) if ok else b""
        buf.close()
        return data if len(data) > 100 else None
    except Exception:
        return None


def grab_window_as_png(settle_ms=200, timeout_ms=5000):
    """Grab the top-level window to PNG bytes. Never raises.

    Returns PNG bytes on success, or None on any failure. Caller is
    expected to fall through to the next tier when None is returned.
    """
    win, _name = _find_window()
    if win is None:
        return None
    try:
        from qtpy import QtWidgets
        app = QtWidgets.QApplication.instance()
    except Exception:
        app = None
    # Paint settle: repaint + processEvents loop. Some WebEngine pages
    # finish painting after `loaded` fires; the settle loop lets the
    # GPU/CPU pipeline catch up before we grab.
    settle_deadline = time.time() + max(0, settle_ms) / 1000.0
    while time.time() < settle_deadline:
        try:
            if hasattr(win, "repaint"):
                win.repaint()
        except Exception:
            pass
        try:
            if app is not None:
                app.processEvents()
        except Exception:
            pass
        time.sleep(0.02)
    # The actual grab. Qt grab is synchronous, so we measure wall-clock
    # time and treat an over-budget call as a failure (returns None so
    # the caller falls through to the next tier).
    start = time.time()
    pix = None
    try:
        if hasattr(win, "grab"):
            pix = win.grab()
        elif hasattr(win, "grabWindow"):
            pix = win.grabWindow()
    except Exception:
        pix = None
    elapsed_ms = (time.time() - start) * 1000.0
    if pix is None or elapsed_ms > timeout_ms:
        return None
    try:
        if hasattr(pix, "isNull") and pix.isNull():
            return None
    except Exception:
        pass
    return _encode_pixmap_to_png(pix)
