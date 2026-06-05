"""Mock driver — for tests, no browser needed. Implements Driver interface."""

from .base import Driver


class MockDriver(Driver):
    """In-memory driver. Returns canned data so the MCP plumbing can be tested offline."""

    def __init__(self):
        self._title = "Mock Page"
        self._url = "about:blank"

    def navigate(self, url):
        self._url = url
        return {"url": url, "title": self._title}

    def evaluate(self, js):
        if "html_bytes" in js and "url:" in js:
            return {
                "url": self._url, "title": self._title,
                "html_bytes": 36, "text_chars": 10,
                "iframes": 0, "scripts": 0, "images": 0, "stylesheets": 0,
                "viewport": {"w": 1024, "h": 768},
                "scroll": {"w": 1024, "h": 768},
            }
        if "document.title" in js:
            return self._title
        if "1+1" in js:
            return 2
        if "!!document.querySelector" in js:
            return True
        if "textContent" in js:
            return "mock text content"
        if "outerHTML" in js:
            return "<html><body>mock</body></html>"
        if "location.href" in js:
            return self._url
        if "focus" in js or "click" in js:
            return True
        if "__minimal_webmcp_page_digest" in js:
            return {
                "url": self._url, "title": self._title,
                "html_bytes": 36, "text_chars": 10,
                "iframes": 0, "scripts": 0, "images": 0,
                "viewport": {"w": 1024, "h": 768},
                "scroll": {"w": 1024, "h": 768},
            }
        return "mock"

    def screenshot(self):
        # MOCK mode simulates a working canvas: the screenshot tool returns
        # a real (1x1 transparent) PNG. The embedded driver's fallback path
        # (returning a page-digest dict) is not exercised here, but
        # `screenshot_fallback` is a test-only helper that lets test_plumbing
        # assert the fallback shape.
        return (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa3z\xd1\xc0"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )

    def screenshot_fallback(self):
        """Test helper: returns the page-digest shape the embedded
        driver produces when the canvas pipeline is unavailable. Lets
        test_plumbing exercise the fallback path through MOCK without
        needing a real webview."""
        digest = self.evaluate("__minimal_webmcp_page_digest()")
        return {
            "fallback": True,
            "kind": "page_digest",
            "data": digest,
            "note": "screenshot_fallback: MOCK simulating embedded-driver fallback",
        }

    def send_keys(self, text):
        pass

    def close(self):
        pass
