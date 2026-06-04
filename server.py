"""MCP JSON-RPC 2.0 server. Newline-delimited JSON over stdio. Stdlib only."""

import json
import sys
import traceback

from . import tools


SERVER_NAME = "webmcp"
SERVER_VERSION = "0.1.0"
PROTOCOL_VERSION = "2024-11-05"


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
        arguments = params.get("arguments") or {}
        if not name:
            return _err(id_val, -32602, "missing tool name")
        if not any(t["name"] == name for t in tools.TOOL_DEFS):
            return _err(id_val, -32601, f"unknown tool: {name}")
        try:
            result = tools.call_tool(driver, name, arguments)
        except Exception as e:
            return _err(id_val, -32603, f"tool error: {e}", str(e))
        return _ok(id_val, {
            "content": [{"type": "text", "text": json.dumps(result)}],
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
