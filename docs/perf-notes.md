# Performance notes — `minimal_webmcp`

This directory holds the perf harness (`tests/perf_headless.py`) and the
recorded baseline (`tests/perf_baseline.json`) used as the 2x bar the upcoming
headless/Qt optimizer must beat. The harness is **stdlib only** — no psutil,
no requests, no playwright — so it can run in any environment that has the
project's existing dependencies (which are also stdlib, except for the
optional pywebview used in embedded mode).

## Two measurement modes

The harness supports two modes, switched by `--embedded` (default is MOCK):

* **MOCK** (`MINIMAL_WEBMCP_MOCK=1`, no real browser) — fast CI falsifier.
  Each tool call round-trips through a `MockDriver` that returns canned
  strings; the numbers below the page are the **ceiling** the MOCK path can
  produce. The harness asserts soft upper bounds (median `evaluate` < 200 ms,
  median `screenshot` < 300 ms) so a future regression to the dispatch layer
  is caught even on the trivial path.
* **--embedded** (`MINIMAL_WEBMCP_MOCK=0`, `MINIMAL_WEBMCP_HEADLESS=1`,
  `PYWEBVIEW_GUI=qt`) — exercises the real pywebview + QtWebEngine path. On
  hosts without pywebview or a Qt binding the harness prints
  `EMBEDDED UNAVAILABLE: <reason>` and exits 0 (it is a soft probe, not a
  hard test). On a real deployment this is the mode whose numbers the
  optimizer is judged against.

The env vars the harness sets on the spawned subprocess:

| Var | MOCK | embedded | What it does |
|---|---|---|---|
| `MINIMAL_WEBMCP_MOCK` | `1` | `0` | pick `MockDriver` vs `EmbeddedDriver` |
| `MINIMAL_WEBMCP_HEADLESS` | (unset) | `1` | project reads this to set `QT_QPA_PLATFORM=offscreen` (after the optimizer lands) |
| `PYWEBVIEW_GUI` | (unset) | `qt` | force pywebview to pick QtWebEngine on Linux |
| `PYTHONPATH` | parent of `minimal_webmcp/` | same | makes `python3 -m minimal_webmcp` resolvable |

## How to reproduce

From the project root (the directory whose child is `minimal_webmcp/`):

```
# MOCK — 20 iterations per tool, JSON + human-readable output
python3 tests/perf_headless.py --iters 20 --json tests/perf_baseline.json

# Embedded — requires pywebview + a Qt binding
python3 tests/perf_headless.py --embedded

# Tighter / looser iteration count
python3 tests/perf_headless.py --iters 100
python3 tests/perf_headless.py --iters 5

# Don't fail CI on the soft sanity bounds (still reports them)
python3 tests/perf_headless.py --no-fail-on-soft
```

The harness picks the subprocess cwd and `PYTHONPATH` automatically by walking
up from the test file looking for the `minimal_webmcp/` package directory —
so it works equally well from a git worktree (`feature-perf-headless/`) and
from the main checkout.

## What the harness measures

For each of the nine tools (`navigate`, `evaluate`, `screenshot`, `get_text`,
`get_html`, `page_info`, `click`, `type_text`, `wait_for`):

* 20 round-trip calls over stdio (`tools/call` request -> `tools/call` response).
* Per-call wall-time from "JSON written to stdin" to "matching JSON read from stdout".
* `median` and `p95` (nearest-rank) over the 20 samples.
* `n_ok` / `n_total` reported in case any sample was lost to a timeout.

It also measures:

* **Startup** — `Popen` -> first NDJSON response (`initialize` reply). The
  include of Python import time, the project module import chain, and the
  dispatcher handshake. Currently ~25–30 ms in MOCK; the embedded path is
  expected to be in the 0.5–2 s ballpark per the optimizer's design target.
* **Peak RSS** — sampled once at the end of the run from
  `/proc/<pid>/status` (Linux only). The harness does not import `psutil`.

The number density is `round(..., 3)` (3 decimal places of ms) — fine for a
MOCK baseline, where the numbers are sub-millisecond. The optimizer should
re-run with `--iters 100` to denoise the embedded numbers.

## Reliability as a 2x-bar measurement

The harness is reliable enough to act as a 2x bar:

* It uses a single subprocess with a long-lived stdin/stdout pair, so the
  per-call measurement excludes process-spawn overhead and the second-and-
  onward imports. Only the first call (and the explicit startup) pay the
  import cost; the optimizer must optimize both axes.
* It runs 20 iterations per tool by default and reports `n_ok`/`n_total`
  so the verifier can spot a single dropped sample.
* The stdlib-only constraint means the harness itself is not the source of
  measurement noise — there is no GC, no GIL contention, no third-party
  tracing. The variance comes from the OS scheduler and the CPython
  interpreter, both of which affect the real workload too.
* The `readline_dl` helper uses `select.select` with a 250 ms poll so a dead
  subprocess can't wedge the harness past the per-call timeout.
* Soft upper bounds in MOCK mode (200 / 300 ms) are loose enough that a
  scheduler hiccup will not flake the test, but tight enough to catch a
  real regression in the JSON-RPC dispatch layer.
* To confirm stability, run `python3 tests/perf_headless.py --iters 100`
  twice and compare; the per-tool medians should agree within ~10 µs in MOCK.
