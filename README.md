# minimal_webmcp

Minimal [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server for browser automation. Designed from the ground up for LLM-agent tool use with an obsessive focus on zero-dependency operation, minimal latency, and graceful degradation under resource constraints.

- **Stdlib-first core** — `server.py`, `tools.py`, `ws.py`, `drivers/mock.py`, `_qt_env.py`, and `drivers/qt_grab.py` use only the Python standard library
- **Optional `pywebview` embedded backend** — OS-native webview (Qt/GTK/Cocoa/Win32) for real browser automation when available
- **10 browser tools** (9 user-facing + 1 test-only helper) — navigate, screenshot, click, type, extract text/HTML, evaluate JS, wait for elements, inspect page metadata
- **Headless + no-GPU support** — offscreen QPA, software rendering, Chromium flags tuned for containers and headless servers
- **Offline MOCK mode** — in-memory browser for testing and CI; no install, no browser, no network
- **3-tier screenshot pipeline** — graceful fallback from real PNG (JS canvas or Qt native grab) to structured page digest when rendering is unavailable

---

## Architecture

### Driver pattern

The server speaks to an abstract `Driver` interface (`drivers/base.py:4`), allowing browser backends to be swapped without touching the MCP protocol layer:

```
server.py ──► tools.py ──► Driver (abstract)
                              ├── MockDriver      — in-memory for offline/CI
                              └── EmbeddedDriver  — pywebview for real automation
```

The tools layer (`tools.py`) is completely browser-agnostic. Every tool dispatches through `driver.evaluate()`, `driver.navigate()`, or `driver.screenshot()` — the same code path works against both backends.

### stdio transport

The server speaks MCP over **newline-delimited JSON-RPC 2.0** on stdin/stdout. Logs go to stderr. No HTTP, no sockets, no SSE — just raw bytes over pipes. This makes it trivially embeddable in any MCP client that can spawn a subprocess.

### Key design decisions

- **One JS round-trip per tool call** — tools like `type_text` and `click` do focus+set+dispatch in a single `driver.evaluate()` IIFE, not two (removes ~1 IPC round-trip per call)
- **O(1) tool lookup** — `server.py:20` uses a frozen set instead of a linear `any()` scan on each `tools/call`
- **Reusable JSON encoder** — a single `json.JSONEncoder` instance avoids per-call allocation (`server.py:23`)
- **Lazy imports** — `pywebview` is only imported when `EmbeddedDriver` is actually instantiated; MOCK mode stays 100% stdlib
- **Single-file bundle support** — the embedded driver searches multiple paths for `vendor/screenshot.js` to support both package and single-file deployment

---

## File map

```text
minimal_webmcp/
├── __init__.py              # Package docstring + __version__ (0.2.1)
├── __main__.py              # Entry point. Reads env vars, configures Qt, chooses driver, runs server.
├── server.py                # JSON-RPC 2.0 dispatcher over NDJSON stdio. O(1) tool lookup, reusable encoder.
├── tools.py                 # Tool definitions (TOOL_DEFS) + call_tool() dispatch. Browser-agnostic.
├── ws.py                    # Hand-rolled WebSocket client (RFC 6455). Stdlib only. Client-side masking.
├── _qt_env.py               # Headless + no-GPU Qt environment configuration. Must run BEFORE QApplication.
├── drivers/
│   ├── __init__.py          # make_driver() factory: "mock" | "embedded"
│   ├── base.py              # Abstract Driver interface (navigate, evaluate, screenshot, send_keys, close)
│   ├── mock.py              # MockDriver — canned data for tests/CI. Also implements screenshot_fallback().
│   ├── embedded.py          # EmbeddedDriver — pywebview-backed real browser. 3-tier screenshot.
│   └── qt_grab.py           # Qt-native QPixmap.grab() — tier 2 of screenshot pipeline. Binding-agnostic via qtpy.
├── vendor/
│   └── screenshot.js        # Injected JS: __minimal_webmcp_screenshot() (SVG→canvas→PNG) + __minimal_webmcp_page_digest()
├── tests/
│   └── test_plumbing.py     # E2E test: spawns server in MOCK mode, exercises all tools + error paths + fallback
└── docs/
    └── perf-notes.md         # Performance measurement harness docs
```

---

## Driver modes

### MockDriver (`MINIMAL_WEBMCP_MOCK=1`)

An in-memory driver that returns canned responses. No browser, no GUI toolkit, no network. The implementation lives entirely in `drivers/mock.py` and uses zero third-party imports.

| Capability | Behavior |
|---|---|
| `navigate()` | Stores URL internally, returns `{url, title: "Mock Page"}` |
| `evaluate()` | Pattern-matches JS against known expressions (title, outerHTML, 1+1, click, etc.) |
| `screenshot()` | Returns a valid 1×1 transparent PNG (real PNG bytes, not a dict) |
| `screenshot_fallback()` | Returns the page-digest fallback shape for E2E fallback-path testing |

MOCK mode is ~1.2 µs per `tools/call` — the floor of what Python + stdlib + stdio can produce.

### EmbeddedDriver (default, requires `pywebview`)

Launches an OS-native webview via [`pywebview`](https://pywebview.flowrl.com) (Qt/GTK on Linux, Cocoa on macOS, Win32 on Windows). Runs the MCP server loop on a worker thread while the GUI event loop occupies the main thread (pywebview 6.x requirement).

Key behaviors:
- **Cold start** — Chromium WebEngine cold start ~200–500 ms; headless mode may take 2–5 s for first paint
- **Warm calls** — per-`evaluate` round-trip dominated by Chromium IPC (~few hundred µs)
- **3-tier screenshot** — see below
- **`wait_for_load`** — polls `document.readyState === 'complete'` and non-empty title from Python (pywebview's `evaluate_js` does not await Promises)

---

## Headless + no-GPU mode

When `MINIMAL_WEBMCP_HEADLESS=1` (or the alias `MINIMAL_MCP_HEADLESS=1`) is set, `_qt_env.py:85` configures the Qt/WebEngine runtime for offscreen operation **before** any QApplication is constructed. This ordering is critical — setting `QT_QPA_PLATFORM` or `QTWEBENGINE_CHROMIUM_FLAGS` after QApplication creation has no effect.

### What gets configured

| Setting | Value |
|---|---|
| `QT_QPA_PLATFORM` | `offscreen` |
| `PYWEBVIEW_GUI` (Linux) | `qt` (setdefault) |
| `PYWEBVIEW_LOG` | `WARNING` (setdefault) |
| `QT_QUICK_BACKEND` | `software` (setdefault) |
| `QSG_RHI_BACKEND` | `software` (setdefault) |
| `QT_OPENGL` | `software` (setdefault) |
| `Qt.AA_UseSoftwareOpenGL` | `True` (set on whichever Qt binding is importable) |

### Chromium flags

Packed into `QTWEBENGINE_CHROMIUM_FLAGS` (if not already set) — a recipe tuned for offscreen/no-GPU execution:

```
--disable-gpu
--use-gl=swiftshader
--disable-gpu-compositing
--in-process-gpu
--disable-dev-shm-usage
--disable-background-timer-throttling
--disable-renderer-backgrounding
--disable-backgrounding-occluded-windows
--disable-features=Translate,BackForwardCache,MediaRouter,VizDisplayCompositor
--no-first-run
--no-default-browser-check
```

When running as root (e.g. Docker), `--no-sandbox` is appended automatically.

### Why this matters

Under offscreen QPA without these settings, Chromium may:
- Attempt to acquire a GL context from a background thread and abort with `"Cannot make QOpenGLContext current in a different thread"`
- Take 2–5× longer for first paint
- Fail at `canvas.toDataURL()` (returns empty data — handled by the 3-tier screenshot fallback)

With the full configuration applied, cold-start is ~2× faster and the per-call round-trip is ~5× faster.

---

## Screenshot pipeline (3 tiers)

The embedded driver's `screenshot()` method (`drivers/embedded.py:184`) uses a 3-tier fallback chain. Each tier is attempted in order; if one fails, the next is tried.

### Tier 1: JS canvas path (non-headless only)

`__minimal_webmcp_screenshot()` in `vendor/screenshot.js:5` — clones the DOM, inlines stylesheets into a `<style>` element, serializes to SVG, renders via `<foreignObject>`, draws onto a `<canvas>`, and calls `canvas.toDataURL('image/png')`.

- Works on real display servers
- Skipped in headless mode — under offscreen QPA the canvas rasterizer can **abort the process** at the C++ level, and Python's try/except cannot catch it
- Returns a base64-encoded PNG string

### Tier 2: Qt-native grab

`grab_window_as_png()` in `drivers/qt_grab.py:115` — uses Qt's own `QPixmap.grab()` on the top-level widget. This bypasses the WebEngine canvas pipeline entirely.

- Works under `QT_QPA_PLATFORM=offscreen` (that QPA was designed for "render Qt widgets to pixmap" use cases)
- Binding-agnostic via `qtpy` (a pywebview dependency — supports PyQt5, PyQt6, PySide2, PySide6)
- Uses a process-lifetime window reference cache to avoid O(N) widget scans
- Includes a paint-settle loop (repaint + processEvents) before the grab
- Falls through if the grab takes longer than `grab_timeout_ms`

### Tier 3: Page digest fallback (always works)

`__minimal_webmcp_page_digest()` in `vendor/screenshot.js:69` — returns a structured metadata object instead of an image:

```json
{
  "url": "...",
  "title": "...",
  "html_bytes": 12345,
  "text_chars": 678,
  "iframes": 0,
  "scripts": 5,
  "images": 3,
  "viewport": {"w": 1024, "h": 768},
  "scroll": {"w": 1024, "h": 2048}
}
```

The server layer wraps this as a text content with a `[FALLBACK]` prefix so LLM clients see the degradation signal immediately.

---

## Tools reference

All tools are exposed through `tools.TOOL_DEFS` (line 9) and dispatched by `tools.call_tool()`.

### `navigate`
Navigate the browser to a URL. Returns `{url, title}`.
- **Required:** `url` (string)
- **Optional:** `wait_for_load` (bool, default `false`) — when `true`, waits for the `load` event and non-empty title; when `false`, polls for URL change only (fast, ~10 ms for vanilla HTML)
- **Default `wait_for_load`** can be set globally via `MINIMAL_WEBMCP_NAVIGATE_WAIT_FOR_LOAD=1`

### `screenshot`
Capture a PNG screenshot. Returns MCP image content (type: `"image"`, base64 PNG) or a fallback text payload.
- **Optional:** `path` (string) — force-save to file; response returns `saved_to` path
- **Optional:** `inline` (bool) — force base64 inline even if large
- **Optional:** `max_bytes` (int, default `1048576`) — inline threshold; PNGs larger than this are auto-saved to `/tmp`

### `click`
Click the first element matched by a CSS selector. Returns `{ok: true}`.
- **Required:** `selector` (CSS selector string)
- Raises if element not found

### `type_text`
Focus an element and set its value (replaces existing content, does not append). Returns `{ok: true}`.
- **Required:** `selector` (CSS selector), `text` (string)
- Uses native value setter via `HTMLInputElement.prototype.value` for React-controlled inputs
- Dispatches `input` and `change` events
- For contenteditable elements, uses `execCommand('insertText')`

### `get_text`
Get the `textContent` of the page or a scoped element. Auto-truncates at 100K chars (returns first 50K).
- **Optional:** `selector` (CSS selector) — scope to a sub-element
- **Optional:** `full` (bool) — skip truncation, return everything

### `get_html`
Get the `outerHTML` of the page or a scoped element. Auto-truncates at 200KB (returns first 100KB).
- **Optional:** `selector` (CSS selector) — scope to a sub-element
- **Optional:** `full` (bool) — skip truncation
- **Optional:** `max_bytes` (int, default `204800`) — custom inline threshold

### `wait_for`
Poll until a CSS selector matches an element in the DOM. Returns `{found: bool}`.
- **Required:** `selector` (CSS selector)
- **Optional:** `timeout_ms` (int, default `5000`)

### `page_info`
Cheap page probe — returns metadata without touching large content. Call this **before** `get_html` on big pages to decide whether you need the full HTML.
- Returns: `{url, title, html_bytes, text_chars, iframes, scripts, images, stylesheets, viewport: {w, h}, scroll: {w, h}}`

### `evaluate`
Evaluate a JavaScript expression in the page. The value is returned as JSON.
- **Required:** `js` (string) — a single expression (not a statement)
- Examples: `"document.title"`, `"1+1"`, `"document.querySelectorAll('a').length"`

### `screenshot_fallback` (test-only)
Returns the structured page-digest shape that the embedded driver produces when the canvas pipeline is unavailable. Exists for plumbing tests; should not be used in normal automation.

---

## Requirements

### Python

- Python 3.6+
- No third-party packages required for MOCK mode or the stdlib core paths

### Runtime dependencies

| Mode | What you need |
|---|---|
| **MOCK** (`MINIMAL_WEBMCP_MOCK=1`) | Nothing — 100% stdlib |
| **Embedded** (default) | `pywebview` + a GUI backend |
| **Tests** | Nothing — tests run in MOCK mode |

### Embedded mode backends

`pywebview` does not bundle a GUI toolkit. Install `pywebview` and one supported backend.

**Linux (Qt, recommended for headless):**

```bash
pip install --user 'pywebview[qt]'
# or individually:
pip install --user pywebview PySide6
```

**Linux (GTK):**

```bash
# Debian/Ubuntu
sudo apt install python3-gi gir1.2-webkit2-4.0
pip install --user pywebview

# Fedora/RHEL
sudo dnf install python3-gobject gtk3 webkit2gtk3
pip install --user pywebview
```

**RHEL 8.x (glibc 2.28):**

```bash
# System PySide2 is the most compatible option on RHEL 8
sudo dnf install python3-pyside2 && pip install --user pywebview
```

**macOS:**

```bash
pip install --user pywebview   # uses system Cocoa/WebKit via PyObjC
```

**Windows:**

```bash
pip install --user 'pywebview[qt]'
```

---

## Installation

### From source (run from parent directory)

The package lives at the repository root. Set `PYTHONPATH` to the repo's parent directory:

```bash
PYTHONPATH=. python3 -m minimal_webmcp
```

### Print platform-specific install hint

```bash
python3 -m minimal_webmcp --print-install
```

Output varies by platform and includes the recommended pip/dnf commands.

---

## Usage

### Run modes

| Mode | Invocation |
|---|---|
| MOCK (offline, no browser) | `MINIMAL_WEBMCP_MOCK=1 python3 -m minimal_webmcp` |
| Embedded (default) | `python3 -m minimal_webmcp` |
| Embedded headless (offscreen Qt) | `MINIMAL_WEBMCP_HEADLESS=1 python3 -m minimal_webmcp` |
| Print install hint | `python3 -m minimal_webmcp --print-install` |

### Environment variables

| Variable | Effect |
|---|---|
| `MINIMAL_WEBMCP_MOCK=1` | Use `MockDriver` (no browser, 100% stdlib) |
| `MINIMAL_WEBMCP_HEADLESS=1` | Enable offscreen Qt / software rendering configuration |
| `MINIMAL_MCP_HEADLESS=1` | Alias for `MINIMAL_WEBMCP_HEADLESS=1` |
| `PYWEBVIEW_GUI=qt` | Force Qt renderer on Linux |
| `PYWEBVIEW_LOG=WARNING` | Reduce pywebview noise in headless mode |
| `MINIMAL_WEBMCP_GRAB_SETTLE_MS` | Delay (ms) before Qt screenshot grab (default: 30 headless, 200 real display) |
| `MINIMAL_WEBMCP_GRAB_TIMEOUT_MS` | Timeout (ms) for a single Qt grab (default: 5000) |
| `MINIMAL_WEBMCP_NAVIGATE_WAIT_FOR_LOAD` | Default `navigate` waiting strategy (`1`/`true` for SPA-friendly load-waiting) |
| `QTWEBENGINE_CHROMIUM_FLAGS` | Override the default Chromium flag recipe for headless mode |

---

## JSON-RPC wire format

The server speaks MCP over **newline-delimited JSON-RPC 2.0** on stdin/stdout.

- One JSON object per line on stdin (requests)
- One JSON object per line on stdout (responses)
- `id: null` means notification (no response)
- Logs and diagnostics go to stderr only

### Handshake

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"cli","version":"0.0.1"}}}' \
  | MINIMAL_WEBMCP_MOCK=1 python3 -m minimal_webmcp
```

Successful initialize response:

```json
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05","serverInfo":{"name":"minimal_webmcp","version":"0.2.1"},"capabilities":{"tools":{}}}}
```

### Supported methods

| Method | Direction | Description |
|---|---|---|
| `initialize` | Client → Server | MCP handshake; server returns capabilities |
| `initialized` | Client → Server | Notification; no response |
| `ping` | Client → Server | Returns `{}` |
| `tools/list` | Client → Server | Returns all tool definitions |
| `tools/call` | Client → Server | Invoke a tool with `{name, arguments}` |
| `notifications/cancelled` | Client → Server | Notification; no response |

### Screenshot response shapes

1. **PNG image** — `content[0]` has `type: "image"`, `data: "<base64>"`, `mimeType: "image/png"`
2. **Saved PNG** — `content[0]` has `type: "text"`, text contains `{"saved_to": "<path>", ...}`
3. **Fallback digest** — `content[0]` has `type: "text"`, text starts with `[FALLBACK]` followed by a JSON digest block

### Error codes

| Code | Meaning |
|---|---|
| `-32700` | Parse error (invalid JSON) |
| `-32601` | Unknown method or tool |
| `-32602` | Invalid params (e.g., missing tool name) |
| `-32603` | Internal/tool error |

---

## Editor integration

The server is a stdio MCP server — compatible with any MCP-aware client.

### opencode

```jsonc
{
  "mcp": {
    "minimal_webmcp": {
      "type": "local",
      "command": ["python3", "-m", "minimal_webmcp"],
      "enabled": true,
      "environment": {
        "PYTHONPATH": "/home/yourname",
        "MINIMAL_WEBMCP_MOCK": "1"
      }
    }
  }
}
```

### Claude Code

```jsonc
{
  "mcpServers": {
    "minimal_webmcp": {
      "type": "stdio",
      "command": "python3",
      "args": ["-m", "minimal_webmcp"],
      "env": {
        "PYTHONPATH": "/home/yourname",
        "MINIMAL_WEBMCP_MOCK": "1"
      }
    }
  }
}
```

### VS Code Copilot

```jsonc
{
  "servers": {
    "minimal_webmcp": {
      "type": "stdio",
      "command": "python3",
      "args": ["-m", "minimal_webmcp"],
      "env": {
        "PYTHONPATH": "/home/yourname",
        "MINIMAL_WEBMCP_MOCK": "1"
      }
    }
  }
}
```

---

## WebSocket client (stdlib)

`ws.py` contains a hand-rolled RFC 6455 WebSocket client with zero dependencies. It handles:

- HTTP upgrade handshake with `Sec-WebSocket-Accept` validation
- Client-side masking (required by spec)
- Text frames (opcode 0x1), binary frames (opcode 0x2)
- Ping/pong handling (opcode 0x9 / 0xA)
- Close frame (opcode 0x8)
- No fragmentation support (single-frame messages only)

This is used when connecting to browser debugging protocols (CDP, Marionette) directly, though the current `EmbeddedDriver` uses pywebview's `evaluate_js` bridge instead.

---

## Tests

### Plumbing test (E2E, MOCK mode)

```bash
python3 tests/test_plumbing.py
```

This test:
1. Spawns `python3 -m minimal_webmcp` in MOCK mode as a subprocess
2. Exercises the full MCP handshake (`initialize` → `initialized`)
3. Calls `tools/list` and asserts all 10 tools are registered
4. Calls every tool: `navigate`, `screenshot`, `click`, `type_text`, `get_text`, `get_html`, `wait_for`, `evaluate`, `page_info`, `screenshot_fallback`
5. Exercises error paths: unknown tool (`-32601`), parse error (`-32700`)
6. Asserts the screenshot fallback shape (`[FALLBACK]` prefix, `fallback: true`, `kind: "page_digest"`)
7. Validates both PNG inline and file-save screenshot paths

### CI

`.github/workflows/tests.yml` runs the plumbing test on `ubuntu-latest` on push/PR to `main`. Uses a minimal checkout (no `actions/checkout`) for speed — the entire test runs in under 1 second.

### Performance harness

`docs/perf-notes.md` documents a separate performance measurement harness that times per-tool-call round-trips in both MOCK and embedded modes.

---

## Performance characteristics

| Path | `tools/call` latency | Notes |
|---|---|---|
| MOCK `evaluate` | ~1.2 µs | Floor — CPython + stdio + NDJSON dispatch only |
| MOCK `screenshot` | < 300 µs | Canned 1×1 PNG |
| Embedded `evaluate` | ~few hundred µs | Chromium IPC round-trip |
| Embedded `navigate` (fast) | ~10–50 ms | URL poll only; no load-event wait |
| Embedded `navigate` (load) | 200–2000 ms | Full page load + readyState check |
| Embedded `screenshot` (Qt) | ~10–50 ms | QPixmap.grab() + PNG encode |
| Embedded cold start | 200–500 ms | Warm Chromium process |
| Embedded cold start (headless) | 2–5 s | Cold Chromium under offscreen QPA |

---

## Project status

- **Version:** `0.2.1`
- **MCP protocol version:** `2024-11-05`
- **Transport:** stdio, NDJSON
- **Core:** stdlib-only
- **Embedded mode:** optional, via `pywebview >= 6.0, < 7`
- **Target platforms:** Linux (primary), macOS, Windows
