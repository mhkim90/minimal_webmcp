"""End-to-end test: spawn webmcp in MOCK mode, send JSON-RPC, check responses."""

import json
import os
import subprocess
import sys
import time


def send(proc, method, params=None, id_val=1):
    msg = {"jsonrpc": "2.0", "id": id_val, "method": method}
    if params is not None:
        msg["params"] = params
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()


def read_one(proc, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        line = proc.stdout.readline()
        if line:
            return json.loads(line)
    raise TimeoutError("no response")


def main():
    proc = subprocess.Popen(
        [sys.executable, "-m", "webmcp"],
        cwd="/workspace",
        env={"WEBMCP_MOCK": "1", "PATH": "/usr/bin:/bin"},
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    failures = []
    try:
        # 1. initialize
        send(proc, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0.0.1"},
        }, id_val=1)
        r = read_one(proc)
        assert r.get("id") == 1, f"initialize id mismatch: {r}"
        assert "result" in r, f"initialize no result: {r}"
        assert r["result"]["serverInfo"]["name"] == "webmcp"
        print("OK initialize")

        # 2. initialized notification
        send(proc, "initialized", {}, id_val=None)
        # No response expected for notification (id=null)

        # 3. tools/list
        send(proc, "tools/list", {}, id_val=2)
        r = read_one(proc)
        assert r.get("id") == 2
        tool_names = {t["name"] for t in r["result"]["tools"]}
        expected = {"navigate", "screenshot", "click", "type_text",
                    "get_text", "get_html", "wait_for", "evaluate", "page_info"}
        assert tool_names == expected, f"tool set mismatch: {tool_names}"
        print(f"OK tools/list: {sorted(tool_names)}")

        # 4. tools/call navigate
        send(proc, "tools/call", {
            "name": "navigate",
            "arguments": {"url": "https://example.com"},
        }, id_val=3)
        r = read_one(proc)
        assert r.get("id") == 3
        text = r["result"]["content"][0]["text"]
        result = json.loads(text)
        assert result["url"] == "https://example.com"
        assert result["title"] == "Mock Page"
        print(f"OK navigate: {result}")

        # 5. tools/call evaluate
        send(proc, "tools/call", {
            "name": "evaluate",
            "arguments": {"js": "1+1"},
        }, id_val=4)
        r = read_one(proc)
        text = r["result"]["content"][0]["text"]
        result = json.loads(text)
        assert result["value"] == 2, f"evaluate failed: {result}"
        print(f"OK evaluate: {result}")

        # 6. tools/call screenshot
        send(proc, "tools/call", {
            "name": "screenshot",
            "arguments": {},
        }, id_val=5)
        r = read_one(proc)
        text = r["result"]["content"][0]["text"]
        result = json.loads(text)
        assert result["size"] > 0
        assert result["data"]  # base64
        # Verify magic bytes after decode
        import base64
        png = base64.b64decode(result["data"])
        assert png[:8] == b"\x89PNG\r\n\x1a\n", f"bad PNG magic: {png[:8]!r}"
        print(f"OK screenshot: size={result['size']}, magic valid")

        # 6b. tools/call screenshot with file path
        shot_path = "/tmp/webmcp_test_shot.png"
        if os.path.exists(shot_path):
            os.remove(shot_path)
        send(proc, "tools/call", {
            "name": "screenshot",
            "arguments": {"path": shot_path},
        }, id_val=51)
        r = read_one(proc)
        text = r["result"]["content"][0]["text"]
        result = json.loads(text)
        assert result.get("saved_to") == shot_path
        assert os.path.exists(shot_path)
        assert os.path.getsize(shot_path) > 0
        with open(shot_path, "rb") as f:
            assert f.read(8) == b"\x89PNG\r\n\x1a\n"
        os.remove(shot_path)
        print(f"OK screenshot+file: {result['size']} bytes -> {shot_path}")

        # 7. tools/call click
        send(proc, "tools/call", {
            "name": "click",
            "arguments": {"selector": "button"},
        }, id_val=6)
        r = read_one(proc)
        text = r["result"]["content"][0]["text"]
        result = json.loads(text)
        assert result["ok"] is True
        print("OK click")

        # 8. tools/call get_text
        send(proc, "tools/call", {
            "name": "get_text",
            "arguments": {"selector": "body"},
        }, id_val=7)
        r = read_one(proc)
        text = r["result"]["content"][0]["text"]
        result = json.loads(text)
        print(f"OK get_text: {result}")

        # 9. tools/call get_html
        send(proc, "tools/call", {
            "name": "get_html",
            "arguments": {},
        }, id_val=8)
        r = read_one(proc)
        text = r["result"]["content"][0]["text"]
        result = json.loads(text)
        assert "html" in result
        print(f"OK get_html: {result['html'][:50]}...")

        # 10. tools/call wait_for
        send(proc, "tools/call", {
            "name": "wait_for",
            "arguments": {"selector": "div", "timeout_ms": 1000},
        }, id_val=9)
        r = read_one(proc)
        text = r["result"]["content"][0]["text"]
        result = json.loads(text)
        assert result["found"] is True
        print(f"OK wait_for: {result}")

        # 11. tools/call type_text
        send(proc, "tools/call", {
            "name": "type_text",
            "arguments": {"selector": "input", "text": "hello"},
        }, id_val=10)
        r = read_one(proc)
        text = r["result"]["content"][0]["text"]
        result = json.loads(text)
        assert result["ok"] is True
        print("OK type_text")

        # 12. error: unknown tool
        send(proc, "tools/call", {
            "name": "nonexistent",
            "arguments": {},
        }, id_val=11)
        r = read_one(proc)
        assert "error" in r, f"expected error for unknown tool: {r}"
        assert r["error"]["code"] == -32601
        print(f"OK unknown tool error: code={r['error']['code']}")

        # 13. error: parse error
        proc.stdin.write("not json\n")
        proc.stdin.flush()
        r = read_one(proc)
        assert "error" in r
        assert r["error"]["code"] == -32700
        print(f"OK parse error: code={r['error']['code']}")

        # 14. ping
        send(proc, "ping", {}, id_val=12)
        r = read_one(proc)
        assert r.get("id") == 12
        print("OK ping")

        # Exit
        proc.stdin.close()
        proc.wait(timeout=5)

    except Exception as e:
        failures.append(str(e))
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            stderr_out = proc.stderr.read()
            print(f"\n--- server stderr ---\n{stderr_out}\n--- end stderr ---")
        except Exception:
            pass
    finally:
        if proc.poll() is None:
            proc.kill()

    if failures:
        print(f"\nFAIL: {failures}")
        sys.exit(1)
    print("\nALL OK")


if __name__ == "__main__":
    main()
