"""Performance harness for `minimal_webmcp` — stdlib only.

Spawns `python3 -m minimal_webmcp` as a subprocess and measures cold-startup
time and per-tool call latency (median + p95 across N iterations), plus
peak RSS via /proc/<pid>/status. Used to establish the headless/no-GPU
perf baseline that the upcoming optimizer must beat by 2x.

Modes:
  * MOCK (default): MINIMAL_WEBMCP_MOCK=1, no browser, fast CI.
  * --embedded: MINIMAL_WEBMCP_MOCK=0, MINIMAL_WEBMCP_HEADLESS=1,
                 PYWEBVIEW_GUI=qt. If pywebview/Qt is not importable, the
                 harness prints "EMBEDDED UNAVAILABLE: <reason>" and exits 0.

Soft upper bounds (MOCK only — sanity checks, not perf targets):
  median evaluate < 200 ms; median screenshot < 300 ms.
"""

import argparse, json, os, select, statistics, subprocess, sys, time

TOOLS = [
    ("navigate",   {"url": "https://example.com/"}),
    ("evaluate",   {"js": "1+1"}),
    ("screenshot", {}),
    ("get_text",   {"selector": "body"}),
    ("get_html",   {}),
    ("page_info",  {}),
    ("click",      {"selector": "button"}),
    ("type_text",  {"selector": "input", "text": "hello"}),
    ("wait_for",   {"selector": "div", "timeout_ms": 200}),
]


def find_pkg():
    """Return (cwd, pythonpath) so `python3 -m minimal_webmcp` works.

    Prefers the worktree's own package (the test's parent's parent's
    sibling) when present, so the harness measures the worktree under
    test, not the original package higher up the tree.
    """
    cur = os.path.realpath(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    # First: the worktree's parent dir -- if cur is `feature-perf-headless`
    # with an __init__.py, the harness will need cwd=cur, pkg_root=cur, and
    # the caller will use the basename of cur as the module name.
    if os.path.exists(os.path.join(cur, "__init__.py")):
        # The "package" is cur itself. Use cwd=cur, PYTHONPATH=cur's parent.
        return cur, os.path.dirname(cur)
    # Fallback: walk up looking for a sibling minimal_webmcp dir.
    for _ in range(8):
        if os.path.basename(cur) == "minimal_webmcp":
            return os.path.dirname(cur), os.path.dirname(cur)
        cand = os.path.join(cur, "minimal_webmcp")
        if os.path.isdir(cand) and os.path.exists(os.path.join(cand, "__init__.py")):
            return cur, cur
        cur = os.path.dirname(cur)
    raise RuntimeError("cannot locate minimal_webmcp package source")


def read_rss_kb(pid):
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


def build_env(embedded, pkg_root):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = pkg_root
    env.setdefault("PATH", "/usr/bin:/bin")
    env["MINIMAL_WEBMCP_MOCK"] = "0" if embedded else "1"
    if embedded:
        env["MINIMAL_WEBMCP_HEADLESS"] = "1"
        env["PYWEBVIEW_GUI"] = "qt"
    return env


def check_embedded():
    code = (
        "import importlib.util as u\n"
        "mods=['webview','PyQt5','PyQt6','PySide2','PySide6']\n"
        "got=[m for m in mods if u.find_spec(m)]\n"
        "ok='webview' in got and any(q in got for q in ['PyQt5','PyQt6','PySide2','PySide6'])\n"
        "print('OK' if ok else 'NO', ','.join(got) or '<none>')\n"
    )
    try:
        r = subprocess.run([sys.executable, "-c", code],
                           capture_output=True, text=True, timeout=10)
    except Exception as e:
        return False, f"probe crashed: {e}"
    if r.returncode != 0:
        return False, f"probe failed: {r.stderr.strip()[:200] or 'no stderr'}"
    out = r.stdout.strip().splitlines()
    if not out:
        return False, "probe produced no output"
    flag, _, have = out[-1].partition(" ")
    return (True, have) if flag == "OK" else (False, f"missing imports; have: {have or '<none>'}")


def send(proc, obj):
    proc.stdin.write(json.dumps(obj) + "\n")
    proc.stdin.flush()


def readline_dl(proc, deadline):
    while True:
        if time.perf_counter() >= deadline:
            return None
        rem = max(0.0, deadline - time.perf_counter())
        r, _, _ = select.select([proc.stdout], [], [], min(rem, 0.25))
        if not r: continue
        line = proc.stdout.readline()
        return line or None


def time_call(proc, name, args, id_val, timeout=30.0):
    send(proc, {"jsonrpc": "2.0", "id": id_val, "method": "tools/call",
                "params": {"name": name, "arguments": args}})
    t0 = time.perf_counter()
    line = readline_dl(proc, t0 + timeout)
    dt = time.perf_counter() - t0
    if line is None:
        return None, None
    try:
        return dt, json.loads(line)
    except json.JSONDecodeError:
        return dt, None


def percentile(values, q):
    if not values: return None
    s = sorted(values)
    return s[max(0, min(len(s) - 1, int(q * len(s))))]


def summarise(samples):
    ok = [s for s in samples if s is not None]
    if not ok:
        return {"median_ms": None, "p95_ms": None, "n_ok": 0, "n_total": len(samples)}
    return {
        "median_ms": round(statistics.median(ok) * 1000, 3),
        "p95_ms":    round(percentile(ok, 0.95) * 1000, 3),
        "n_ok":      len(ok), "n_total": len(samples),
    }


def run(embedded, iters, json_out, fail_on_soft):
    pkg_root, _ = find_pkg()
    if embedded:
        ok, reason = check_embedded()
        if not ok:
            print(f"EMBEDDED UNAVAILABLE: {reason}")
            return 0
        print(f"embedded mode: pywebview + Qt detected ({reason})")
    env = build_env(embedded, pkg_root)
    proc = subprocess.Popen(
        [sys.executable, "-m", os.path.basename(pkg_root)], cwd=pkg_root, env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, universal_newlines=True, bufsize=1,
    )
    try:
        t0 = time.perf_counter()
        send(proc, {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "perf", "version": "0.0.1"},
        }})
        first = readline_dl(proc, t0 + 30.0)
        startup_s = time.perf_counter() - t0 if first else None
        if first is None:
            err = proc.stderr.read() if proc.stderr else ""
            print(f"FAIL: server did not respond to initialize within 30s\nstderr: {err[:1000]}")
            return 2
        first_resp = json.loads(first)
        if "error" in first_resp:
            print(f"FAIL: initialize returned error: {first_resp}")
            return 2
        send(proc, {"jsonrpc": "2.0", "method": "initialized", "params": {}})

        samples = {n: [] for n, _ in TOOLS}
        next_id = 1
        for tool_name, tool_args in TOOLS:
            for i in range(iters):
                args = dict(tool_args)
                if tool_name == "navigate":
                    args["url"] = f"https://e.com/{i}"
                dt, resp = time_call(proc, tool_name, args, next_id)
                next_id += 1
                if dt is None:
                    print(f"WARN: {tool_name} iter {i} timed out")
                elif resp is None or "error" in resp:
                    print(f"WARN: {tool_name} iter {i} bad response: {resp}")
                else:
                    samples[tool_name].append(dt)
        rss_kb = read_rss_kb(proc.pid)
    finally:
        try: proc.stdin.close()
        except Exception: pass
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=2)
        try: stderr_tail = (proc.stderr.read() if proc.stderr else "")[-2000:]
        except Exception: stderr_tail = ""

    report = {
        "mode": "embedded" if embedded else "mock",
        "iters": iters,
        "startup_ms": round(startup_s * 1000, 3) if startup_s is not None else None,
        "rss_kb": rss_kb,
        "tools": {n: summarise(samples[n]) for n, _ in TOOLS},
        "env": {"python": sys.version.split()[0], "platform": sys.platform,
                "warmup": False},
    }

    print(f"\n=== perf baseline ({report['mode']}, iters={iters}) ===")
    if report["startup_ms"] is not None:
        print(f"startup (Popen -> first response): {report['startup_ms']:.1f} ms")
    print(f"peak RSS: {rss_kb} kB" if rss_kb else "peak RSS: <unavailable>")
    print(f"{'tool':<12} {'median':>12} {'p95':>12} {'n_ok':>6} {'n_total':>8}")
    for n, _ in TOOLS:
        s = report["tools"][n]
        med = f"{s['median_ms']:.3f}ms" if s["median_ms"] is not None else "n/a"
        p95 = f"{s['p95_ms']:.3f}ms"    if s["p95_ms"]    is not None else "n/a"
        print(f"{n:<12} {med:>12} {p95:>12} {s['n_ok']:>6} {s['n_total']:>8}")

    if json_out:
        with open(json_out, "w") as f:
            json.dump(report, f, indent=2, sort_keys=True)
        print(f"\nwrote {json_out}")

    if stderr_tail.strip():
        print(f"\n--- server stderr (last 2KB) ---\n{stderr_tail}\n--- end ---")

    failures = []
    if not embedded:
        me = report["tools"]["evaluate"]["median_ms"]
        ms = report["tools"]["screenshot"]["median_ms"]
        if me is not None and me >= 200.0:
            failures.append(f"evaluate median {me:.1f}ms >= 200ms")
        if ms is not None and ms >= 300.0:
            failures.append(f"screenshot median {ms:.1f}ms >= 300ms")
    if failures and fail_on_soft:
        print("\nSOFT BOUND FAILURES:")
        for f in failures: print(f"  - {f}")
        return 1
    print("\nPERF OK")
    return 0


def main():
    ap = argparse.ArgumentParser(description="minimal_webmcp perf harness (stdlib only)")
    ap.add_argument("--embedded", action="store_true", help="embedded headless mode")
    ap.add_argument("--iters", type=int, default=20, help="iterations per tool (default 20)")
    ap.add_argument("--json", metavar="PATH", default=None, help="write JSON report")
    ap.add_argument("--no-fail-on-soft", action="store_true", help="warn but don't fail on soft bounds")
    a = ap.parse_args()
    return run(a.embedded, a.iters, a.json, not a.no_fail_on_soft)


if __name__ == "__main__":
    sys.exit(main())
