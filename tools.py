"""Tool definitions and dispatch. Browser-agnostic; works on any driver."""

import base64
import json
import time
from pathlib import Path


TOOL_DEFS = [
    {
        "name": "navigate",
        "description": "Navigate the browser to a URL. Returns the final URL and page title.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to navigate to"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "screenshot",
        "description": "Capture a PNG screenshot. Auto: if PNG < 1MB, returns base64 inline; if larger, saves to auto-generated /tmp path and returns only the path. Pass 'path' to force a file location. Pass 'inline=true' to force base64 even if large. Pass 'max_bytes' to change threshold (default 1048576).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Force-save to this file path; response returns saved_to instead of data"},
                "inline": {"type": "boolean", "description": "Force base64 inline even if large (default false)"},
                "max_bytes": {"type": "integer", "description": "Inline threshold in bytes (default 1048576)"},
            },
        },
    },
    {
        "name": "click",
        "description": "Click the first element matched by a CSS selector.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS selector"},
            },
            "required": ["selector"],
        },
    },
    {
        "name": "type_text",
        "description": "Focus an element (CSS selector) and type text into it. Uses Input.insertText/CDP or SendKeys/Marionette.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS selector for input/textarea/contenteditable"},
                "text": {"type": "string", "description": "Text to type"},
            },
            "required": ["selector", "text"],
        },
    },
    {
        "name": "get_text",
        "description": "Get the textContent. Auto: if total size <= 100K chars, returns full; if larger, returns first 50K chars plus total size. Use 'full=true' for everything. Use 'selector' to scope to a sub-element.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "Optional CSS selector"},
                "full": {"type": "boolean", "description": "Skip cap, return full text (default false)"},
            },
        },
    },
    {
        "name": "get_html",
        "description": "Get the outerHTML. Auto: if total size <= 200KB, returns full inline; if larger, returns first 100KB plus total size and a flag. Use 'max_bytes' to set inline threshold (default 204800). Use 'full=true' to always return everything (may be huge). Use 'selector' to scope to a sub-element.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "Optional CSS selector"},
                "max_bytes": {"type": "integer", "description": "Inline threshold; content <= this is returned fully (default 204800)"},
                "full": {"type": "boolean", "description": "Skip cap, return full HTML (default false)"},
            },
        },
    },
    {
        "name": "wait_for",
        "description": "Poll until a CSS selector matches an element in the DOM. Returns {found: bool}.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS selector to wait for"},
                "timeout_ms": {"type": "integer", "description": "Timeout in ms (default 5000)"},
            },
            "required": ["selector"],
        },
    },
    {
        "name": "page_info",
        "description": "Get page metadata: HTML byte size, text char count, iframe/script/image counts, viewport size. Cheap probe — call this BEFORE get_html on big pages.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "evaluate",
        "description": "Evaluate a JavaScript expression in the page. The expression must be a single expression; its value is returned as JSON.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "js": {"type": "string", "description": "JavaScript expression to evaluate"},
            },
            "required": ["js"],
        },
    },
    {
        "name": "screenshot_fallback",
        "description": "Test-only helper: returns the structured page-digest shape that the embedded driver produces when the canvas pipeline is unavailable. Useful for verifying the screenshot fallback path through MOCK without a real webview.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]


def _js_str(s):
    return json.dumps(s)


def call_tool(driver, name, args):
    if name == "navigate":
        return driver.navigate(args["url"])

    if name == "screenshot":
        result = driver.screenshot()
        # The driver now returns a 3-tuple: ("image"|"text_fallback", payload, size).
        # server.py uses the kind to pick the MCP content type:
        #   - "image"         -> type:"image", data:base64, mimeType:"image/png"
        #   - "text_fallback" -> type:"text", text:"[FALLBACK] ...\n\n<dict>"
        # If the user asked for a `path` or `inline=true`, we still return a
        # plain dict so server.py wraps it in the default text content type
        # (those are metadata responses, not images).
        if isinstance(result, tuple) and len(result) == 3 and result[0] == "text_fallback":
            return result  # server wraps with [FALLBACK] prefix
        if isinstance(result, tuple) and len(result) == 3 and result[0] == "image":
            png = result[1]
            png_size = result[2]
        elif isinstance(result, dict) and result.get("fallback"):
            # Back-compat for any driver that still returns a dict directly.
            return result
        else:
            png = result
            png_size = len(png)
        max_bytes = int(args.get("max_bytes") or 1048576)
        # If caller forces a path -> save and return path only (text meta).
        if args.get("path"):
            p = Path(args["path"])
            p.write_bytes(png)
            return {"saved_to": str(p), "size": png_size}
        # If caller forces inline -> return base64 (text meta).
        if args.get("inline"):
            return {"data": base64.b64encode(png).decode("ascii"), "size": png_size}
        # Auto: small enough -> return as MCP image content; too big -> auto-save.
        if png_size <= max_bytes:
            return ("image", png, png_size)
        import tempfile, os
        tmpdir = tempfile.gettempdir()
        fname = f"minimal_webmcp_shot_{int(time.time()*1000)}.png"
        full_path = os.path.join(tmpdir, fname)
        Path(full_path).write_bytes(png)
        return {
            "saved_to": full_path,
            "size": png_size,
            "truncated": False,
            "note": f"PNG too large for inline ({png_size} > {max_bytes}); auto-saved. Read with cat or screenshot inline=true to see bytes.",
        }

    if name == "click":
        sel = args["selector"]
        sel_js = _js_str(sel)
        ok = driver.evaluate(
            f"(()=>{{const e=document.querySelector({sel_js});"
            f"if(!e)return false;e.click();return true;}})()"
        )
        if not ok:
            raise RuntimeError(f"element not found: {sel}")
        return {"ok": True}

    if name == "type_text":
        sel = args["selector"]
        text = args["text"]
        sel_js = _js_str(sel)
        text_js = json.dumps(text)
        # Single round-trip: focus + type in one IIFE. Saves one
        # evaluate_js bridge call per type_text (was 2: focus + send_keys).
        ok = driver.evaluate(
            f"(()=>{{"
            f"const e=document.querySelector({sel_js});"
            f"if(!e)return false;"
            f"e.focus();"
            f"const a=document.activeElement;"
            f"if(!a||!(a.tagName==='INPUT'||a.tagName==='TEXTAREA'||a.isContentEditable))return false;"
            f"if(a.tagName==='INPUT'||a.tagName==='TEXTAREA'){{"
            f"  const proto=a.tagName==='INPUT'?HTMLInputElement.prototype:HTMLTextAreaElement.prototype;"
            f"  const setter=Object.getOwnPropertyDescriptor(proto,'value').set;"
            f"  setter.call(a,a.value+{text_js});"
            f"  a.dispatchEvent(new Event('input',{{bubbles:true}}));"
            f"  a.dispatchEvent(new Event('change',{{bubbles:true}}));"
            f"}}else{{"
            f"  document.execCommand('insertText',false,{text_js});"
            f"}}"
            f"return true;"
            f"}})()"
        )
        if not ok:
            raise RuntimeError(
                f"type_text: element not focusable or not input/textarea/contenteditable: {sel}"
            )
        return {"ok": True}

    if name == "get_text":
        sel = args.get("selector")
        if sel:
            sel_js = _js_str(sel)
            v = driver.evaluate(
                f"(()=>{{const e=document.querySelector({sel_js});"
                f"return e?e.textContent:null;}})()"
            )
        else:
            v = driver.evaluate("document.body ? document.body.textContent : ''")
        if v is None:
            return {"text": None}
        if not isinstance(v, str):
            return {"text": v, "size": 0}
        size = len(v)
        full = bool(args.get("full"))
        if full:
            return {"text": v, "size": size, "truncated": False}
        if size <= 100 * 1024:
            return {"text": v, "size": size, "truncated": False}
        return {
            "text": v[:50 * 1024],
            "truncated": True,
            "size": size,
            "returned": 50 * 1024,
            "note": "Text > 100K chars; returned first 50K. Use full=true for everything, or selector= to scope.",
        }

    if name == "get_html":
        sel = args.get("selector")
        if sel:
            sel_js = _js_str(sel)
            v = driver.evaluate(
                f"(()=>{{const e=document.querySelector({sel_js});"
                f"return e?e.outerHTML:null;}})()"
            )
        else:
            v = driver.evaluate("document.documentElement.outerHTML")
        if v is None:
            return {"html": None}
        if not isinstance(v, str):
            return {"html": v, "size": 0}
        encoded = v.encode("utf-8")
        size = len(encoded)
        full = bool(args.get("full"))
        if full:
            return {"html": v, "size": size, "truncated": False}
        # Auto: under cap -> return full; over -> truncate
        # default cap 200KB - if total is over 200KB, return first 100KB
        if size <= 200 * 1024:
            return {"html": v, "size": size, "truncated": False}
        out_bytes = encoded[:100 * 1024]
        return {
            "html": out_bytes.decode("utf-8", errors="ignore"),
            "truncated": True,
            "size": size,
            "returned": len(out_bytes),
            "note": f"HTML > 200KB; returned first 100KB. Use full=true for the entire page, or selector= to scope.",
        }

    if name == "wait_for":
        sel = args["selector"]
        timeout_ms = int(args.get("timeout_ms") or 5000)
        sel_js = _js_str(sel)
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            found = driver.evaluate(f"!!document.querySelector({sel_js})")
            if found:
                return {"found": True}
            time.sleep(0.1)
        return {"found": False}

    if name == "evaluate":
        v = driver.evaluate(args["js"])
        return {"value": v}

    if name == "page_info":
        info = driver.evaluate("""(()=>{
            const d = document;
            return {
                url: location.href,
                title: d.title,
                html_bytes: (d.documentElement.outerHTML||'').length,
                text_chars: (d.body ? d.body.textContent : '').length,
                iframes: d.querySelectorAll('iframe').length,
                scripts: d.querySelectorAll('script').length,
                images: d.querySelectorAll('img').length,
                stylesheets: d.querySelectorAll('link[rel=stylesheet]').length,
                viewport: {w: innerWidth, h: innerHeight},
                scroll: {w: d.documentElement.scrollWidth, h: d.documentElement.scrollHeight},
            };
        })()""")
        return info or {}

    if name == "screenshot_fallback":
        # Test-only helper. Lets the E2E plumbing test verify the
        # fallback shape through MOCK without a real webview. Wrapped in
        # a ("text_fallback", ...) tuple so the server layer applies the
        # `[FALLBACK]` text-content prefix consistently with the real
        # embedded driver's degraded-result path.
        fb = driver.screenshot_fallback() if hasattr(driver, "screenshot_fallback") else None
        if fb is None:
            fb = {"fallback": True, "kind": "page_digest",
                  "data": {}, "note": "driver does not implement screenshot_fallback"}
        return ("text_fallback", fb, 0)

    raise ValueError(f"unknown tool: {name}")
