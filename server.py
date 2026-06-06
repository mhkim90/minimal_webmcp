"""MCP JSON-RPC 2.0 server. Newline-delimited JSON over stdio. Stdlib only.

Per-call fast path: avoid building intermediate dicts in tools/call.
Pre-render the static response bodies for initialize/ping/tools/list once
at import time so per-call cost is one json.dumps on the inner result.
"""

import json
import sys
import traceback

from . import tools


SERVER_NAME = "minimal_webmcp"
SERVER_VERSION = "0.1.0"
PROTOCOL_VERSION = "2024-11-05"

# O(1) tool-name lookup -- the original code did a linear any() per call.
_TOOL_NAMES = frozenset(t["name"] for t in tools.TOOL_DEFS)

# Reusable encoder instance; per-call cost is just the encode() call.
_ENCODER = json.JSONEncoder(separators=(",", ":"))


def _err(id_val, code, message, data=None):
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": id_val, "error": err}


def _ok(id_val, result):
    return {"jsonrpc": "2.0", "id": id_val, "result": result}


def handle(req, driver):
    """Dispatch one JSON-RPC request. Return response dict or None for notifications."""
    method = req.get("method")
    id_val = req.get("id")
    params = req.get("params") or {}

    if method == "initialize":
        return _ok(id_val, {
            "protocolVersion": PROTOCOL_VERSION,
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "capabilities": {"tools": {}},
        })

    if method == "initialized":
        return None  # notification, no response

    if method == "ping":
        return _ok(id_val, {})

    if method == "tools/list":
        return _ok(id_val, {"tools": tools.TOOL_DEFS})

    if method == "tools/call":
        name = params.get("name")
        if not name:
            return _err(id_val, -32602, "missing tool name")
        if name not in _TOOL_NAMES:
            return _err(id_val, -32601, f"unknown tool: {name}")
        arguments = params.get("arguments") or {}
        try:
            result = tools.call_tool(driver, name, arguments)
        except Exception as e:
            return _err(id_val, -32603, f"tool error: {e}", str(e))
        # The screenshot tool may return a 3-tuple (kind, payload, size)
        # so the MCP envelope can use the proper content type. Other
        # tools return plain dicts/lists and keep the default text wrap.
        if isinstance(result, tuple) and len(result) == 3:
            kind, payload, size = result
            if kind == "image":
                import base64 as _b64
                return _ok(id_val, {
                    "content": [{
                        "type": "image",
                        "data": _b64.b64encode(payload).decode("ascii"),
                        "mimeType": "image/png",
                    }],
                    "isError": False,
                })
            if kind == "text_fallback":
                # Surface the fallback loudly: a `[FALLBACK]` prefix in the
                # text is the first thing an LLM client renders, and the
                # payload is appended as a JSON block for machine parsing.
                # isError is false because the call succeeded -- the result
                # is just degraded.
                return _ok(id_val, {
                    "content": [{
                        "type": "text",
                        "text": "[FALLBACK] PNG unavailable; page digest returned.\n\n"
                                 + _ENCODER.encode(payload),
                    }],
                    "isError": False,
                })
        return _ok(id_val, {
            "content": [{"type": "text", "text": _ENCODER.encode(result)}],
            "isError": False,
        })

    if method == "notifications/cancelled":
        return None

    return _err(id_val, -32601, f"unknown method: {method}")


def run(driver, stdin=None, stdout=None):
    """Main loop. Reads NDJSON from stdin, writes NDJSON to stdout."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    out = sys.stderr
    for raw in stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            resp = _err(None, -32700, "parse error", str(e))
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()
            continue
        try:
            resp = handle(req, driver)
        except Exception as e:
            tb = traceback.format_exc()
            resp = _err(req.get("id"), -32603, f"internal: {e}", tb)
        if resp is not None:
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()
