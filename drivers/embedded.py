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

    def __init__(self, headless=False, width=1024, height=768, title="minimal_webmcp"):
        if not _try_import_webview():
            raise RuntimeError(
                "pywebview not installed. Run: pip install 'pywebview>=6.0,<7'\n"
                "or set MINIMAL_WEBMCP_MOCK=1 for offline testing."
            )
        self._headless = headless
        self._width = width
        self._height = height
        self._title = title
        self._window = None
        self._ready = threading.Event()
        self._error = None
        self._loop_thread = None

    def _start(self):
        if self._loop_thread is not None:
            return
        # Set Qt offscreen platform for headless
        if self._headless:
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        # Load screenshot.js to inject later
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
                # Inject screenshot helper
                self._window.evaluate_js(self._screenshot_js)
                self._ready.set()
            except Exception as e:
                self._error = e
                self._ready.set()

        self._window.events.loaded += _on_loaded

        def _loop():
            try:
                _webview.start()
            except Exception as e:
                self._error = e
                self._ready.set()

        self._loop_thread = threading.Thread(target=_loop, daemon=True)
        self._loop_thread.start()
        # Wait for window to be ready
        if not self._ready.wait(timeout=30):
            raise RuntimeError("webview: window did not become ready in 30s")
        if self._error:
            raise self._error

    def _ensure(self):
        if self._loop_thread is None:
            self._start()

    def navigate(self, url):
        self._ensure()
        self._window.load_url(url)
        # Wait for load by polling get_current_url
        deadline = time.time() + 30
        while time.time() < deadline:
            cur = self._window.get_current_url()
            if cur and cur != "about:blank":
                break
            time.sleep(0.1)
        title = self.evaluate("document.title") or ""
        return {"url": url, "title": title}

    def evaluate(self, js):
        self._ensure()
        # evaluate_js returns the value directly when no callback (sync)
        return self._window.evaluate_js(js)

    def screenshot(self):
        self._ensure()
        b64 = self.evaluate("__minimal_webmcp_screenshot()")
        if isinstance(b64, str):
            return base64.b64decode(b64)
        raise RuntimeError("screenshot: no data returned (page may block SVG/canvas)")

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
