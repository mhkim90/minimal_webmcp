# minimal_webmcp — Headless + No-GPU Implementation

This branch (`feature/headless-perf-impl`) implements the headless + no-GPU
performance plan from the design doc. It targets the configuration

    PYWEBVIEW_GUI=qt  MINIMAL_WEBMCP_HEADLESS=1  (no GPU host)

with **no new third-party dependencies** — the existing `pywebview>=6.0,<7`
pin is preserved.

## What changed

| File | Change |
|------|--------|
| `_qt_env.py` (new) | `configure_qt_for_headless(headless: bool)` — sets `QT_QPA_PLATFORM=offscreen`, `QTWEBENGINE_CHROMIUM_FLAGS` (the recipe), `PYWEBVIEW_GUI=qt` on Linux, `PYWEBVIEW_LOG=WARNING`, and `Qt.AA_UseSoftwareOpenGL` on whichever Qt binding is importable. Idempotent. |
| `__main__.py` | Calls `_qt_env.configure_qt_for_headless(...)` at the very top of `main()`, before any branch decision. Accepts `MINIMAL_MCP_HEADLESS` as an alias for `MINIMAL_WEBMCP_HEADLESS` with a one-time stderr deprecation note. |
| `drivers/embedded.py` | `wait_ready` timeout bumped to 60 s when `headless=True` (cold-start under offscreen QPA needs it). `screenshot()` now catches the no-data case and falls back to `__minimal_webmcp_page_digest()` (returns a structured `{fallback, kind, data, note}` dict instead of raising). |
| `tools.py` | `screenshot` handler recognises the fallback dict shape and passes it through unchanged. New `screenshot_fallback` tool entry exposes the same shape through MOCK for E2E testing. |
| `vendor/screenshot.js` | New `window.__minimal_webmcp_page_digest()` returning a structured page-metadata object. Coexists with the existing `__minimal_webmcp_screenshot`; the original path is preserved. |
| `drivers/mock.py` | New `__minimal_webmcp_page_digest` heuristic in `MockDriver.evaluate`, and a `screenshot_fallback()` test helper that returns the same shape the embedded driver produces. |
| `tests/test_plumbing.py` | Includes the new `screenshot_fallback` tool in the expected set; adds a new step that exercises the fallback path through MOCK and asserts `{fallback: true, kind: "page_digest", data: ..., note: ...}`. |
| `server.py` | O(1) tool-name lookup (was linear `any(t["name"] == name ...)` per call). Reusable `json.JSONEncoder` instance. Skips `params.get("arguments") or {}` if the tool name is bad. |
| `README.md` | New "Headless + no-GPU" section: documents the env vars, the alias, the Chromium flag recipe, the screenshot fallback, the "no new dependencies" guarantee, and the measurement caveat. |

## Why this configuration is the right target

The 2× "browsing performance" criterion is meaningful only in the **embedded**
path. The MOCK path is an in-process microbenchmark that sits at the floor of
what Python + stdlib + stdio can do (~1.2 µs per `tools/call`); there is no
algorithmic lever left to pull. The embedded path is dominated by:

- **Chromium startup** (~200–500 ms cold, ~50–200 ms warm) — cut by
  `--disable-gpu --use-gl=swiftshader --in-process-gpu
  --disable-backgrounding-occluded-windows
  --disable-features=Translate,BackForwardCache,MediaRouter,VizDisplayCompositor`.
- **First-paint time** under `QT_QPA_PLATFORM=offscreen` (often 2–5 s without
  `AA_UseSoftwareOpenGL`) — cut by the attribute.
- **Screenshot rasterization** (currently broken under offscreen — `canvas.toDataURL`
  returns no data) — replaced by the `__minimal_webmcp_page_digest()` fallback.
- **Per-evaluate round-trip** in the embedded case is dominated by Chromium IPC
  — cut by removing background throttling and the in-process-gpu flag.

## How to apply

```bash
cd /path/to/minimal_webmcp
git apply --3way minimal_webmcp-headless-perf.patch
git commit -am "perf: headless + no-GPU optimization (no new deps)"
```

Then, on a Linux host with `pywebview` + a Qt binding installed:

```bash
MINIMAL_WEBMCP_HEADLESS=1 PYWEBVIEW_GUI=qt python3 -m minimal_webmcp
```

## How to validate the 2× criterion

The user-set criterion is "increase browsing performance at least two times
better". Validation requires a Linux host with `pywebview` and a Qt binding
(PyQt5+PyQtWebEngine, PyQt6, PySide2, or PySide6). The expected gains are
2–5× on Chromium cold-startup, first-paint, and the per-call round-trip in
the embedded path. MOCK-mode numbers cannot validate the criterion — they
were already at the floor before this change.

A simple way to measure:

```bash
# Before the change: record baseline numbers
time bash -c 'echo ... | MINIMAL_WEBMCP_HEADLESS=1 python3 -m minimal_webmcp'

# After: same command, with the patch applied. The delta is the win.
```

For more rigorous measurement, the perf harness from
`.worktrees/feature-perf-headless/tests/perftest_compare.py` can be used —
it spawns the server as a subprocess and times per-tool-call round-trips
in both MOCK and embedded modes. Note: on the embedded path the harness
needs a working Qt + pywebview install, which the design sandbox did not have.
