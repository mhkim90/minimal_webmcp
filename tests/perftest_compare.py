"""Apples-to-apples perf comparison: baseline vs optimized.

Spawns a Python subprocess that imports either the baseline package
(`/workspace/minimal_webmcp/`) or the optimized worktree package
(`/workspace/minimal_webmcp/.worktrees/feature-perf-headless/`) using
importlib (bypassing the `-m` flag, which is fragile when the worktree's
basename contains a hyphen and Python's module name rules forbid it).

Measures:
  - Cold-startup time (initialize -> first response on stdout)
  - Per-tool call latency (median + p95 over 50 iterations)
  - Geometric mean speedup across the 9 tool categories
  - Verdict: >= 2x for every tool category, with the 2x bar reported

Stdlib only.
"""

import argparse
import json
import os
import statistics
import subprocess
import sys
import time


def _spawn(pkg_dir, pkg_name, mode="mock"):
    """Spawn a Python subprocess that runs the package as __main__,
    using importlib to avoid the module-name-with-hyphen problem."""
    code = (
        "import importlib.util, json, os, sys\n"
        f"_pkg_dir = {pkg_dir!r}\n"
        f"_pkg_name = {pkg_name!r}\n"
        "spec = importlib.util.spec_from_file_location(_pkg_name + '.__main__', _pkg_dir + '/__main__.py')\n"
        "parent = type(sys)(_pkg_name)\n"
        "parent.__path__ = [_pkg_dir]\n"
        "sys.modules[_pkg_name] = parent\n"
        "m = importlib.util.module_from_spec(spec)\n"
        "m.__package__ = _pkg_name\n"
        "sys.modules[_pkg_name + '.__main__'] = m\n"
        "spec.loader.exec_module(m)\n"
        "m.main()\n"
    )
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["MINIMAL_WEBMCP_MOCK"] = "1" if mode == "mock" else "0"
    if mode == "embedded":
        env["MINIMAL_WEBMCP_HEADLESS"] = "1"
        env["PYWEBVIEW_GUI"] = "qt"
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        cwd=pkg_dir, env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, universal_newlines=True,
    )
    return proc


def _read_line(proc, deadline_s=30.0):
    """Read one line from proc.stdout with a deadline. Returns None on timeout."""
    import select
    end = time.perf_counter() + deadline_s
    while time.perf_counter() < end:
        r, _, _ = select.select([proc.stdout], [], [], 0.05)
        if r:
            return proc.stdout.readline()
    return None


def measure(pkg_dir, label, tools=None, iters=50):
    if tools is None:
        tools = [
            "navigate", "evaluate", "screenshot", "get_text",
            "get_html", "page_info", "click", "type_text", "wait_for",
        ]
    print(f"--- {label} ---")
    # Pick a package name compatible with the directory's basename.
    # If the basename is a valid Python identifier (no hyphens), use it
    # directly; otherwise fall back to a literal name and set __package__
    # via the importlib trick.
    import re
    base = os.path.basename(os.path.realpath(pkg_dir))
    pkg_name = base if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", base) else "mw_pkg"
    proc = _spawn(pkg_dir, pkg_name, mode="mock")
    init = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "perftest", "version": "0.0.1"},
        },
    })
    proc.stdin.write(init + "\n"); proc.stdin.flush()
    t0 = time.perf_counter()
    line = _read_line(proc, 30.0)
    init_ms = (time.perf_counter() - t0) * 1000.0
    if not line:
        err = proc.stderr.read() if proc.stderr else ""
        proc.kill()
        return {"label": label, "error": f"server did not respond; stderr={err[:500]}"}
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "initialized", "params": {}}) + "\n")
    proc.stdin.flush()

    # Warmup
    for i in range(5):
        proc.stdin.write(json.dumps({
            "jsonrpc": "2.0", "id": i + 2, "method": "tools/call",
            "params": {"name": "evaluate", "arguments": {"js": "1+1"}},
        }) + "\n")
        proc.stdin.flush()
        _read_line(proc, 5.0)

    out = {"label": label, "startup_ms": round(init_ms, 3), "tools": {}}
    next_id = 100
    for tool in tools:
        times_us = []
        for i in range(iters):
            proc.stdin.write(json.dumps({
                "jsonrpc": "2.0", "id": next_id, "method": "tools/call",
                "params": {"name": tool, "arguments": {}},
            }) + "\n")
            proc.stdin.flush()
            t = time.perf_counter()
            line = _read_line(proc, 5.0)
            times_us.append((time.perf_counter() - t) * 1e6)
            next_id += 1
        out["tools"][tool] = {
            "median_us": round(statistics.median(times_us), 2),
            "p95_us": round(sorted(times_us)[int(len(times_us) * 0.95)], 2),
        }
    proc.stdin.close()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True,
                    help="Path to the baseline package (must contain __main__.py).")
    ap.add_argument("--optimized", required=True,
                    help="Path to the optimized package (must contain __main__.py).")
    ap.add_argument("--out", default="tests/perf_after.json",
                    help="Output path for the optimized results JSON.")
    ap.add_argument("--baseline-out", default="tests/perf_baseline_canonical.json",
                    help="Output path for the baseline results JSON.")
    ap.add_argument("--iters", type=int, default=50)
    args = ap.parse_args()

    baseline = measure(os.path.realpath(args.baseline), "BASELINE", iters=args.iters)
    optimized = measure(os.path.realpath(args.optimized), "OPTIMIZED", iters=args.iters)

    # Side-by-side comparison
    print()
    print("=" * 70)
    print(f"{'tool':<14} {'baseline us':>12} {'optimized us':>14} {'speedup':>9} {'>=2x':>5}")
    print("-" * 70)
    speedups = []
    for tool in baseline["tools"]:
        b = baseline["tools"][tool]["median_us"]
        o = optimized["tools"][tool]["median_us"]
        sp = b / o if o > 0 else float("inf")
        speedups.append(sp)
        print(f"{tool:<14} {b:>12.2f} {o:>14.2f} {sp:>8.1f}x {'YES' if sp >= 2.0 else 'no':>5}")
    geo = statistics.geometric_mean(speedups)
    print("-" * 70)
    print(f"{'GEOMEAN':<14} {'':>12} {'':>14} {geo:>8.1f}x {'YES' if geo >= 2.0 else 'no':>5}")
    print()
    print(f"startup: baseline={baseline['startup_ms']:.2f}ms "
          f"optimized={optimized['startup_ms']:.2f}ms "
          f"speedup={baseline['startup_ms']/max(0.001, optimized['startup_ms']):.2f}x")
    print()

    with open(args.baseline_out, "w") as f:
        json.dump(baseline, f, indent=2)
    with open(args.out, "w") as f:
        json.dump(optimized, f, indent=2)
    print(f"baseline  -> {args.baseline_out}")
    print(f"optimized -> {args.out}")


if __name__ == "__main__":
    main()
