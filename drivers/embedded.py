"""pywebview-based embedded driver. Optional — falls back to MockDriver if pywebview not installed."""

import base64
import os
import threading
import time
from pathlib import Path

from .base import Driver

# Lazy import — only attempt when EmbeddedDriver is actually instantiated.
# This keeps MINIMAL_WEBMCP_MOCK=1 mode 100% stdlib.
_HAS_WEBVIEW = None
_webview = None


def _try_import_webview():
    global _HAS_WEBVIEW, _webview
    if _HAS_WEBVIEW is None:
        try:
            import webview as _w
            _webview = _w
            _HAS_WEBVIEW = True
        except ImportError:
            _HAS_WEBVIEW = False
    return _HAS_WEBVIEW


_HERE = Path(__file__).parent
_pkg_vendor = _HERE.parent / "vendor" / "screenshot.js"
_file_vendor = _HERE / "vendor" / "screenshot.js"
# When this file is inlined into a single-file minimal_webmcp.py at <some_dir>/minimal_webmcp.py,
# __file__ resolves to <some_dir>/minimal_webmcp.py so _HERE = <some_dir>. The single-file
# bundle expects vendor/ next to the script. Also check the inlined minimal_webmcp/ dir.
_single_root = _HERE / "vendor" / "screenshot.js"
_single_pckg = _HERE / "minimal_webmcp" / "vendor" / "screenshot.js"

def _find_screenshot_js():
    for p in (_pkg_vendor, _file_vendor, _single_root, _single_pckg):
        if p.exists():
            return p
    return _pkg_vendor  # default; raises on read


class EmbeddedDriver(Driver):
    """Uses pywebview to open an OS-native webview. Lazy start, sync evaluate."""

    def __init__(self, headless=False, width=1024, height=768, title="minimal_webmcp",
                 grab_settle_ms=None, grab_timeout_ms=5000,
                 navigate_wait_for_load=False):
        if not _try_import_webview():
            raise RuntimeError(
                "pywebview not installed. Run: pip install 'pywebview>=6.0,<7'\n"
                "or set MINIMAL_WEBMCP_MOCK=1 for offline testing."
            )
        self._headless = headless
        self._width = width
        self._height = height
        self._title = title
        # Headless (offscreen QPA, no GPU, no animations) needs a much
        # shorter paint-settle delay: the page is settled the moment the
        # grab fires, because nothing is animating. On a real display
        # server with possible animations, keep the original 200ms.
        if grab_settle_ms is None:
            grab_settle_ms = 30 if headless else 200
        self._grab_settle_ms = grab_settle_ms
        self._grab_timeout_ms = grab_timeout_ms
        # Default for the navigate() `wait_for_load` arg. Per-call arg
        # in MCP `navigate(wait_for_load=...)` overrides this.
        self._navigate_wait_for_load = bool(navigate_wait_for_load)
        self._window = None
        self._ready = threading.Event()
        self._error = None

    def _start(self):
        """Create the window and register the loaded hook.

        Must run on the process main thread (pywebview 6.x constraint applies to
        webview.start(), and create_window() is cheapest to call alongside it).
        The actual GUI event loop is started by the caller via webview.start();
        see __main__.py for the worker-thread pattern.
        """
        if self._window is not None:
            return
        if self._headless:
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        path = _find_screenshot_js()
        if not path.exists():
            raise RuntimeError(f"screenshot.js missing: tried {_pkg_vendor}, {_file_vendor}")
        self._screenshot_js = path.read_text()

        self._window = _webview.create_window(
            self._title,
            html="<html><body><h1>minimal_webmcp</h1><p>ready</p></body></html>",
            width=self._width,
            height=self._height,
            hidden=False,
        )

        def _on_loaded():
            try:
                self._window.evaluate_js(self._screenshot_js)
                self._ready.set()
            except Exception as e:
                self._error = e
                self._ready.set()

        self._window.events.loaded += _on_loaded

    def wait_ready(self, timeout=30):
        """Block until the initial window load event fires. Worker-thread side.

        Headless mode (no GPU, offscreen QPA) needs a longer timeout because
        cold-start of the WebEngine process and the first paint can take
        several seconds; the previous 30 s ceiling was too tight for some
        CI containers.
        """
        effective_timeout = timeout
        if getattr(self, "_headless", False):
            effective_timeout = max(timeout, 60)
        if not self._ready.wait(timeout=effective_timeout):
            raise RuntimeError(
                f"webview: window did not become ready in {effective_timeout}s"
            )
        if self._error:
            raise self._error

    def _ensure(self):
        if self._window is None:
            raise RuntimeError(
                "EmbeddedDriver: _start() must be called on the main thread "
                "and webview.start() must be running before tool calls."
            )

    def navigate(self, url, wait_for_load=None):
        self._ensure()
        # None = defer to the driver's startup default (set from
        # MINIMAL_WEBMCP_NAVIGATE_WAIT_FOR_LOAD). True/False = explicit.
        if wait_for_load is None:
            wait_for_load = self._navigate_wait_for_load
        self._window.load_url(url)
        if wait_for_load:
            # Wait for the new page to be fully loaded, not just for the
            # URL to change. Polls in Python: URL change (cheap C++ call)
            # first, then a JS evaluate to check readyState + title. The
            # title-non-empty check rejects the intermediate blank doc
            # that Qt WebEngine creates during reload (the blank doc is
            # itself readyState=complete with an empty title).
            # pywebview's evaluate_js does NOT await Promises on this
            # stack, so JS-side polling via `new Promise(...)` is not
            # an option -- poll from Python instead.
            deadline = time.time() + 30
            title = ""
            while time.time() < deadline:
                cur = self._window.get_current_url()
                if cur and cur != "about:blank":
                    state = self.evaluate(
                        "(()=>({r:document.readyState,t:document.title||''}))()"
                    ) or {}
                    if state.get("r") == "complete" and state.get("t"):
                        title = state["t"]
                        break
                time.sleep(0.05)
            return {"url": url, "title": title}
        # Default: URL poll (fast for vanilla HTML / 8776-class targets).
        # get_current_url() is a pywebview C++ call, not a JS bridge, so
        # the poll is cheap. URL change happens within ~10ms of load_url
        # for single-file pages; first poll usually exits immediately.
        deadline = time.time() + 30
        while time.time() < deadline:
            cur = self._window.get_current_url()
            if cur and cur != "about:blank":
                break
            time.sleep(0.05)
        title = self.evaluate("document.title") or ""
        return {"url": url, "title": title}

    def evaluate(self, js):
        self._ensure()
        # evaluate_js returns the value directly when no callback (sync)
        return self._window.evaluate_js(js)

    def screenshot(self):
        """3-tier screenshot. Returns a (kind, payload, size) tuple:

        - ("image", png_bytes, size)         on a real PNG capture
        - ("text_fallback", dict, 0)         on a degraded result (page
                                              digest dict; tools layer
                                              surfaces it as a `[FALLBACK]`
                                              text content with isError=false)

        Tiers, in order:
          1. JS `__minimal_webmcp_screenshot()` (canvas.toDataURL). May
             fail or return empty under offscreen QPA + no GPU because
             the WebEngine canvas rasterizer is stubbed. Skipped when
             running headless (offscreen QPA): the canvas pipeline can
             abort the process at the C++ level, and the Python
             try/except cannot catch that. The Qt grab tier is a
             strictly better choice in that mode.
          2. Qt-native `QPixmap.grab()` on the top-level window. Works
             under offscreen QPA because that QPA was designed for
             "render Qt widgets to pixmap" use cases.
          3. `__minimal_webmcp_page_digest()` — always works, returns
             a structured page-metadata dict instead of an image.
        """
        self._ensure()
        # Tier 1: JS canvas path. Only attempted when we have a real
        # display server (non-headless mode). Under offscreen QPA the
        # canvas pipeline can abort the process, which would skip the
        # Qt grab fallback below.
        if not self._headless:
            try:
                b64 = self.evaluate("__minimal_webmcp_screenshot()")
                if isinstance(b64, str) and b64:
                    png = base64.b64decode(b64)
                    if len(png) > 100:
                        return ("image", png, len(png))
            except Exception:
                pass
        # Tier 2: Qt-native grab (new). Bypasses the WebEngine canvas
        # pipeline entirely; uses Qt's own widget render path.
        try:
            from .qt_grab import grab_window_as_png
            png = grab_window_as_png(settle_ms=self._grab_settle_ms,
                                     timeout_ms=self._grab_timeout_ms)
            if png:
                return ("image", png, len(png))
        except Exception:
            pass
        # Tier 3: page-digest fallback (existing). Guaranteed to work.
        digest = self.evaluate("__minimal_webmcp_page_digest()") or {}
        return ("text_fallback", {
            "fallback": True,
            "kind": "page_digest",
            "data": digest,
            "note": (
                "PNG unavailable under offscreen QPA + no GPU; "
                "returned a page digest instead. Use page_info for full metadata."
            ),
        }, 0)

    def send_keys(self, text):
        self._ensure()
        # Native setter to support React etc.
        sel = "__activeSel"
        js = (
            "(async()=>{"
            "const a=document.activeElement;"
            "if(!a||!(a.tagName==='INPUT'||a.tagName==='TEXTAREA'||a.isContentEditable))return false;"
            "if(a.tagName==='INPUT'||a.tagName==='TEXTAREA'){"
            "  const proto=a.tagName==='INPUT'?HTMLInputElement.prototype:HTMLTextAreaElement.prototype;"
            "  const setter=Object.getOwnPropertyDescriptor(proto,'value').set;"
            "  setter.call(a,a.value+" + repr(text) + ");"
            "  a.dispatchEvent(new Event('input',{bubbles:true}));"
            "  a.dispatchEvent(new Event('change',{bubbles:true}));"
            "}else{"
            "  document.execCommand('insertText',false," + repr(text) + ");"
            "}"
            "return true;"
            "})()"
        )
        self.evaluate(js)

    def close(self):
        if self._window is not None:
            try:
                self._window.destroy()
            except Exception:
                pass
            self._window = None
