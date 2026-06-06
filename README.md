# minimal_webmcp

Minimal [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server for browser automation. Stdlib-only core, optional `pywebview` backend, 9 tools (navigate, screenshot, click, type_text, get_text, get_html, wait_for, page_info, evaluate), JSON-RPC 2.0 over stdio.

## Features

- **100% stdlib core** — `server.py`, `tools.py`, `drivers/base.py`, `drivers/mock.py`, `ws.py` use only `json`, `sys`, `os`, `threading`, `traceback`, `time`, `base64`, `hashlib`, `socket`, `struct`, `tempfile`, `pathlib`.
- **MCP-stdio transport** — newline-delimited JSON-RPC 2.0, protocol version `2024-11-05`, methods `initialize`, `initialized`, `ping`, `tools/list`, `tools/call`, `notifications/cancelled`.
- **Two drivers** —
  - `MockDriver` — in-memory, no browser. Used for offline tests and CI.
  - `EmbeddedDriver` — opens an OS-native webview via `pywebview` (Qt or GTK).
- **9 tools** — covers the common browser-automation actions: navigation, screenshots, clicks, typing, text/HTML extraction, wait-for-element, page info, and ad-hoc JS evaluation.
- **No telemetry, no network calls** — the embedded driver ships its own offline DOM-to-PNG `screenshot.js` (SVG `foreignObject` hack, no external dependencies).
- **Self-contained screenshot fallback** — screenshots that exceed the inline size threshold are auto-saved to `/tmp/minimal_webmcp_shot_<ms>.png` instead of being dropped.

## Requirements

### Python

- **Python 3.6+** (uses f-strings, f-string `=` self-doc, `dict` ordering).
- No third-party packages required for the core or for MOCK mode.

### Runtime dependencies

| Mode | What you need |
|------|---------------|
| **MOCK** (`MINIMAL_WEBMCP_MOCK=1`) | Nothing. Stdlib only. |
| **Embedded** (default) | `pywebview` + a GUI backend — see below. |
| **Tests** | Nothing. Stdlib only. |

#### Embedded mode — full transitive dependency list

`pywebview` does not bundle a GUI toolkit. You must install `pywebview` **and** one backend, **and** the matching WebEngine component for actual page rendering.

```bash
# 1. pywebview itself (pulls in qtpy transitively)
pip install --user 'pywebview>=6.0,<7'

# 2. One Qt binding — pick exactly one
pip install --user PyQt5            # + PyQtWebEngine (see step 3)
pip install --user PyQt6            # + PyQt6-Qt6
pip install --user PySide2
pip install --user PySide6

# 3. WebEngine — required, pywebview's Qt backend cannot render
#    pages without it. (Without this, `webview.start()` will hang.)
pip install --user PyQtWebEngine   # for PyQt5
# PyQt6 / PySide2 / PySide6 ship their WebEngine component in the
# main wheel on most platforms.

# Alternative GTK backend (Linux only):
sudo apt install python3-gi gir1.2-webkit2-4.0   # Debian/Ubuntu
sudo dnf install python3-gobject gtk3 webkit2gtk3 # Fedora/RHEL
pip install --user pywebview
```

Platform-specific recommended install lines (printed by `python3 -m minimal_webmcp --print-install`):

```bash
# Linux (RHEL 8 / glibc 2.28+ friendly, uses system PySide2)
sudo dnf install python3-pyside2 && pip install --user pywebview

# Linux (pure pip, needs glibc 2.28+)
pip install --user 'pywebview[qt]'

# macOS (system Cocoa via PyObjC)
pip install --user pywebview

# Windows
pip install --user 'pywebview[qt]'
```

> **Note:** "headless" embedded mode (`MINIMAL_WEBMCP_HEADLESS=1`) sets `QT_QPA_PLATFORM=offscreen` and works for most tools, but the DOM-to-PNG screenshot hack in `vendor/screenshot.js` relies on a working canvas and returns no data under the offscreen Qt backend (drop the flag and use a real display to get PNGs). The embedded driver is still a desktop browser, not a true headless engine — use MOCK mode for offline tests and CI.
>
> **pywebview 6.x threading:** `webview.start()` must run on the process main thread. The bundled `__main__.py` puts the GUI event loop on the main thread and runs the JSON-RPC loop in the webview's worker callback, so the standard `python3 -m minimal_webmcp` invocation is safe to use with `pywebview>=6.0,<7`. If you embed `EmbeddedDriver` in your own application, do not call `webview.start()` from a background thread — it will raise `WebViewException('pywebview must be run on a main thread.')`.

### Test dependencies

Stdlib only. `tests/test_plumbing.py` is a self-contained E2E test that spawns the server as a subprocess and exercises every tool.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `WebViewException: pywebview must be run on a main thread.` on launch | `webview.start()` was called from a background thread (incompatible with pywebview 6.x). | Use the bundled `python3 -m minimal_webmcp` entry point (already main-thread safe) or call `webview.start()` on the main thread of your own app. |
| `No module named minimal_webmcp` when launched by an MCP client (opencode, Claude Code, VS Code Copilot) | The client's `mcp.<name>.env` / `.environment` block is not reaching the subprocess. | Point the MCP `command` at a wrapper script that sets `PYTHONPATH` (and `MINIMAL_WEBMCP_HEADLESS=1` for headless) before `exec python -m minimal_webmcp`. See the opencode section above for an example. |
| `screenshot: no data returned (page may block SVG/canvas)` | `QT_QPA_PLATFORM=offscreen` blocks the canvas `toDataURL` call used by `vendor/screenshot.js`. | Drop `MINIMAL_WEBMCP_HEADLESS=1` and use a real display server (X11 / Wayland) for the embedded driver. |
| Server starts but `opencode mcp list` shows `failed` / `Connection closed` | Subprocess died before responding to `initialize` (e.g. because of the two issues above). | Check `opencode mcp list --print-logs --log-level DEBUG` for the `mcp stderr:` lines; the underlying traceback is the real error. |

## Installation

### From source (current setup)

The package directory **is** the project root — `__init__.py` and `__main__.py` live at the repo root, so the package is invoked as `python3 -m minimal_webmcp` from a parent directory on `PYTHONPATH`:

```bash
# From the parent of the repo (e.g. /home/user)
PYTHONPATH=. python3 -m minimal_webmcp
```

Or install the repo as an editable package (recommended once a `pyproject.toml` / `setup.py` is added):

```bash
pip install -e .
python3 -m minimal_webmcp
```

### One-line install hints

```bash
# Mock mode (no install needed)
MINIMAL_WEBMCP_MOCK=1 python3 -m minimal_webmcp

# Embedded mode (Linux, system Qt)
sudo dnf install python3-pyside2 && pip install --user pywebview
python3 -m minimal_webmcp

# Print the install hint for your platform without running the server
python3 -m minimal_webmcp --print-install
```

## Usage

### Run modes

| Mode | Invocation |
|------|------------|
| MOCK (offline, no browser) | `MINIMAL_WEBMCP_MOCK=1 python3 -m minimal_webmcp` |
| Embedded (default, real webview) | `python3 -m minimal_webmcp` |
| Embedded headless (offscreen Qt) | `MINIMAL_WEBMCP_HEADLESS=1 python3 -m minimal_webmcp` |
| Print install hint, exit | `python3 -m minimal_webmcp --print-install` |

### Environment variables

| Variable | Effect |
|----------|--------|
| `MINIMAL_WEBMCP_MOCK=1` | Use `MockDriver` (no browser). Stdlib-only mode. |
| `MINIMAL_WEBMCP_HEADLESS=1` | Set `QT_QPA_PLATFORM=offscreen` and apply the headless + no-GPU recipe. See [Headless + no-GPU](#headless--no-gpu) below. |
| `MINIMAL_MCP_HEADLESS=1` | Alias for `MINIMAL_WEBMCP_HEADLESS`. Prints a one-time deprecation note on stderr. |
| `PYWEBVIEW_GUI=qt` | Force the Qt renderer (Linux only). The headless recipe sets this automatically. |
| `PYWEBVIEW_LOG=INFO\|WARNING\|debug` | pywebview log level. Default `INFO`. The headless recipe sets `WARNING` automatically. |
| `MINIMAL_WEBMCP_QT_FLAGS="..."` | Override the default Chromium flag recipe (only used when this env var is unset). |
| `MINIMAL_WEBMCP_GRAB_SETTLE_MS` | Paint-settle delay (ms) before `QPixmap.grab()` in the embedded screenshot path. Default `200` on a real display, `30` in headless. Increase on slow hosts where the grab returns a blank pixmap. |
| `MINIMAL_WEBMCP_GRAB_TIMEOUT_MS` | Hard wall-clock cap (ms) on a single `QPixmap.grab()` call. Default `5000`. If exceeded, the embedded driver falls through to the page-digest fallback instead of blocking the JSON-RPC loop. |
| `MINIMAL_WEBMCP_NAVIGATE_WAIT_FOR_LOAD` | `0` (default) = `navigate` returns on URL change only (fast, works for vanilla HTML like the ToyPyResist Job Runner). `1` = `navigate` polls until the new page is fully loaded (URL change + `readyState=complete` + non-empty title) — slower, correct for SPAs and pages with heavy subresources where URL change happens before the page is actually ready. Can be overridden per call via the MCP `navigate` tool's `wait_for_load` arg. |

### Headless + no-GPU

When `MINIMAL_WEBMCP_HEADLESS=1` is set, `minimal_webmcp` runs the embedded driver under the offscreen QPA platform with a Chromium flag recipe designed to keep WebEngine performant when the host has no working GPU. The recipe is applied at process startup by `minimal_webmcp._qt_env.configure_qt_for_headless()`, which must run *before* pywebview's `webview.start()` constructs `QApplication` — that is why the call sits at the top of `main()` in `__main__.py`.

What the recipe does:

- Sets `QT_QPA_PLATFORM=offscreen` so Qt does not need a display server.
- Sets `QTWEBENGINE_CHROMIUM_FLAGS` to a fixed string (see `_DEFAULT_QT_FLAGS` in `_qt_env.py`) that:
  - Skips the GPU process (`--disable-gpu`).
  - Forces SwiftShader as the GL backend (`--use-gl=swiftshader`).
  - Runs the GPU process in-process (`--in-process-gpu`).
  - Uses `/tmp` instead of `/dev/shm` for shared memory (`--disable-dev-shm-usage`).
  - Disables background throttling (`--disable-background-timer-throttling`, `--disable-renderer-backgrounding`, `--disable-backgrounding-occluded-windows`).
  - Disables unused features (`--disable-features=Translate,BackForwardCache,MediaRouter,VizDisplayCompositor`).
- Adds `--no-sandbox` only when running as root.
- Sets `Qt.AA_UseSoftwareOpenGL` on whichever Qt binding is importable, so Qt's widget GL stack also uses software rendering. This avoids the first-paint hang under offscreen QPA.
- Sets `PYWEBVIEW_GUI=qt` on Linux and `PYWEBVIEW_LOG=WARNING` to reduce stderr noise.

#### Screenshot rendering tiers

The embedded `screenshot` tool tries three render paths, in order, and returns the first one that yields a usable PNG. This is what makes a real PNG reachable under the offscreen QPA + no-GPU combination, where the WebEngine canvas rasterizer is stubbed:

1. **JS canvas path** — `vendor/screenshot.js` builds an SVG `foreignObject` of the DOM, draws it onto a 2D canvas, and calls `canvas.toDataURL('image/png')`. Works on a real display server (X11 / Wayland) but typically returns no data under offscreen QPA + `--disable-gpu`.
2. **Qt-native grab** (`drivers/qt_grab.py`) — calls `QPixmap.grab()` on the top-level pywebview window (or `QWindow.grabWindow()` for QML backends), then encodes the pixmap to PNG via `QBuffer`. Works under `QT_QPA_PLATFORM=offscreen` because that QPA was designed exactly for "render Qt widgets to pixmap" use cases. Binding-agnostic via `qtpy` (a pywebview dependency), so it works with PySide6, PyQt6, or PyQt5. PySide2 is unsupported — it is incompatible with Python 3.11+ on some installs.
3. **Page-digest fallback** — `__minimal_webmcp_page_digest()` returns a structured `{fallback: true, kind: "page_digest", data: {...}, note: "..."}` object. Always works; use this as the floor when no real PNG is reachable.

The MCP `tools/call` envelope uses a different content type for each outcome so the LLM client can tell them apart at a glance:

- PNG returned (tier 1 or 2): `content[0] = {"type": "image", "data": "<base64>", "mimeType": "image/png"}` — the canonical MCP image content; modern clients (opencode, Claude desktop, etc.) render this inline.
- PNG unreachable (tier 3): `content[0] = {"type": "text", "text": "[FALLBACK] PNG unavailable; page digest returned.\n\n<json>"}` — the `[FALLBACK]` prefix in the first line is the visible signal; the JSON block that follows is the page-digest dict. `isError` is `false` because the call succeeded; the result is just degraded.

#### Screenshot tuning

Two env vars tune the Qt-native grab:

- `MINIMAL_WEBMCP_GRAB_SETTLE_MS` (default `200`) — paint-settle loop duration. Some WebEngine pages finish painting after `loaded` fires; the loop lets the GPU/CPU pipeline catch up before the grab. Increase on slow hosts where the grab returns a blank pixmap.
- `MINIMAL_WEBMCP_GRAB_TIMEOUT_MS` (default `5000`) — hard wall-clock cap on a single `grab()` call. If the grab runs longer than this, the embedded driver treats it as a failure and falls through to the page-digest tier instead of blocking the JSON-RPC loop.

#### No new dependencies

The grab helper uses `qtpy`, which is already a transitive dependency of `pywebview`. No new packages are added; no `pyproject.toml` is created; no existing driver is replaced.

#### Measurement caveat

MOCK mode in this codebase is already at the floor for Python+pipe+JSON-RPC (~1.2 µs per call); the 2× speedup is most meaningful for the embedded path, which is dominated by Chromium startup, network, and rendering — not by Python overhead. A real measurement requires a Linux host with `pywebview` and a Qt binding (PyQt5+PyQtWebEngine, PyQt6, PySide2, or PySide6).

### JSON-RPC wire format

The server speaks MCP over **newline-delimited JSON-RPC 2.0** on stdin/stdout. Each request is one JSON object per line; each response is one JSON object per line on stdout; logs go to stderr.

```bash
# Minimal handshake
echo '{"jsonrpc":"2.0","id":1,"method":"initialize",
       "params":{"protocolVersion":"2024-11-05",
                 "capabilities":{},
                 "clientInfo":{"name":"cli","version":"0.0.1"}}}' \
  | MINIMAL_WEBMCP_MOCK=1 python3 -m minimal_webmcp
```

Successful initialize response:
```json
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05",
  "serverInfo":{"name":"minimal_webmcp","version":"0.2.0"},
 "capabilities":{"tools":{}}}}
```

## Tools

All tools are listed in `tools.TOOL_DEFS` and dispatched by `server.py`. Tool-name prefix in MCP clients: `minimal_webmcp_<name>` (set by the client, not the server).

| Name | Required params | Optional params | Returns | Notes |
|------|-----------------|-----------------|---------|-------|
| `navigate` | `url` | `wait_for_load` (bool, default `false`) | `{url, title}` | Polls until page leaves `about:blank` (max 30 s). Default waits for URL change only (fast). Set `wait_for_load=true` to also wait for the new page's `load` event (slower, correct for SPAs and pages with heavy subresources). The default is the `MINIMAL_WEBMCP_NAVIGATE_WAIT_FOR_LOAD` env var (`0`/`1`). |
| `screenshot` | — | `path`, `inline`, `max_bytes` | MCP `type:"image"` (PNG) or `type:"text"` with `[FALLBACK]` prefix (page digest) | 3-tier render: JS canvas → `QPixmap.grab()` → page-digest. On a real PNG, returns proper MCP image content (`mimeType: image/png`) so modern clients render inline. On a degraded result, returns a text content whose first line is `[FALLBACK]` so the LLM sees the signal without parsing. `path` saves to a file and returns a text meta; `inline=true` returns a text content with base64. Default threshold for inline base64: 1 MB; larger PNGs auto-save to `/tmp/minimal_webmcp_shot_<ms>.png`. |
| `click` | `selector` | — | `{ok: true}` | Raises `RuntimeError` if selector not found. |
| `type_text` | `selector`, `text` | — | `{ok: true}` | Focuses element then sends keys; uses the React-compatible native `value` setter for `INPUT`/`TEXTAREA`. |
| `get_text` | — | `selector`, `full` | `{text, size, truncated?}` | `textContent`. Caps at 100 K chars; returns first 50 K + total size if larger. Set `full=true` to skip the cap. |
| `get_html` | — | `selector`, `max_bytes`, `full` | `{html, size, truncated?}` | `outerHTML`. Caps at 200 KB; returns first 100 KB + total size if larger. `max_bytes` overrides the default (204 800). `full=true` skips the cap. |
| `wait_for` | `selector` | `timeout_ms` | `{found: bool}` | Polls `document.querySelector` every 100 ms. Default timeout 5 000 ms. |
| `page_info` | — | — | `{url, title, html_bytes, text_chars, iframes, scripts, images, stylesheets, viewport, scroll}` | Cheap probe — call this before `get_html` on big pages. |
| `evaluate` | `js` | — | `{value}` | Single JS expression, returned as JSON. |

### Example tool calls

```jsonc
// tools/call — navigate
{"jsonrpc":"2.0","id":3,"method":"tools/call",
 "params":{"name":"navigate","arguments":{"url":"https://example.com"}}}

// tools/call — screenshot to file
{"jsonrpc":"2.0","id":5,"method":"tools/call",
 "params":{"name":"screenshot","arguments":{"path":"/tmp/shot.png"}}}

// tools/call — evaluate
{"jsonrpc":"2.0","id":4,"method":"tools/call",
 "params":{"name":"evaluate","arguments":{"js":"document.title"}}}

// tools/call — wait_for
{"jsonrpc":"2.0","id":9,"method":"tools/call",
 "params":{"name":"wait_for","arguments":{"selector":"#loaded","timeout_ms":3000}}}
```

Successful tool response (result body is JSON-encoded text in the `content[0].text` field per the MCP spec):

```json
{"jsonrpc":"2.0","id":3,"result":{"content":[{"type":"text","text":"{\"url\":\"https://example.com\",\"title\":\"Example Domain\"}"}],"isError":false}}
```

## Editor integration

The server is a stdio MCP server, so it works with any MCP-aware client. The
snippets below are **examples to copy into your own client config** — they are
not committed to the repo. Save them to the path your client reads, e.g.
`opencode.jsonc` for opencode, `.mcp.json` for Claude Code, or
`.vscode/mcp.json` for VS Code Copilot.

### opencode

`opencode.jsonc` in the project root (or `~/.config/opencode/config.jsonc`
for global). The `environment` block sets `PYTHONPATH` to the parent of the
repo and forces MOCK mode — edit it to use the embedded driver in a real
desktop session.

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
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

> **Note:** on some opencode installs the `mcp.<name>.environment` / `mcp.<name>.env` block is not propagated to the subprocess, which then fails to import the package (`No module named minimal_webmcp`). When that happens, point `command` at a wrapper script that sets the env itself:
>
> ```bash
> # /home/yourname/.local/bin/minimal_webmcp_server
> #!/usr/bin/env bash
> export PYTHONPATH="/home/yourname"
> export MINIMAL_WEBMCP_HEADLESS="${MINIMAL_WEBMCP_HEADLESS:-1}"
> exec /path/to/python -m minimal_webmcp
> ```
>
> ```jsonc
> {
>   "mcp": {
>     "minimal_webmcp": {
>       "type": "local",
>       "command": ["/home/yourname/.local/bin/minimal_webmcp_server"],
>       "enabled": true
>     }
>   }
> }
> ```

Tools register under the prefix `minimal_webmcp_*` (e.g. `minimal_webmcp_navigate`, `minimal_webmcp_screenshot`). Verify with `opencode mcp list` — the server should show as `connected` with 9 tools.

Example prompt:

```
Navigate to https://example.com with minimal_webmcp, then take a screenshot
and tell me the page title. Use minimal_webmcp.
```

### Claude Code

`.mcp.json` in the project root (or `~/.claude.json` for global). Claude
Code picks the project file up automatically when launched from the
project.

```json
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

Notes:
- Claude Code uses the key `mcpServers` (plural) and `type: "stdio"`.
- If you've installed the package with `pip install`, drop `PYTHONPATH` and
  `args` and just use `command: "minimal_webmcp"`.
- If `mcpServers.<name>.env` is not propagated on your install, point
  `command` at the wrapper script:

  ```json
  {
    "mcpServers": {
      "minimal_webmcp": {
        "command": "/home/yourname/.local/bin/minimal_webmcp_server"
      }
    }
  }
  ```

> **Note:** on some Claude Code installs the `mcpServers.<name>.env` block is not propagated to the subprocess, which then fails to import the package (`No module named minimal_webmcp`). When that happens, point `command` at a wrapper script that sets the env itself:
>
> ```bash
> # /home/yourname/.local/bin/minimal_webmcp_server
> #!/usr/bin/env bash
> export PYTHONPATH="/home/yourname"
> export MINIMAL_WEBMCP_HEADLESS="${MINIMAL_WEBMCP_HEADLESS:-1}"
> exec /path/to/python -m minimal_webmcp
> ```
>
> ```json
> {
>   "mcpServers": {
>     "minimal_webmcp": {
>       "type": "stdio",
>       "command": "/home/yourname/.local/bin/minimal_webmcp_server"
>     }
>   }
> }
> ```

Example prompt:

```
Open https://news.ycombinator.com with the minimal_webmcp tools, click the
first story link, and summarize the article body. Use minimal_webmcp.
```

### VS Code Copilot

`.vscode/mcp.json` in the project root. VS Code reads it for GitHub
Copilot's agent mode; MCP support must be enabled in the relevant VS Code /
Copilot Chat build.

```json
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

Notes:
- VS Code uses the key `servers` (not `mcpServers`).
- The first time VS Code loads the server it may prompt to trust it.
- Switch from MOCK to the real embedded driver by removing
  `MINIMAL_WEBMCP_MOCK` from the `env` block.
- If `servers.<name>.env` is not propagated on your install, point
  `command` at the wrapper script:

  ```json
  {
    "servers": {
      "minimal_webmcp": {
        "command": "/home/yourname/.local/bin/minimal_webmcp_server"
      }
    }
  }
  ```

> **Note:** on some VS Code / Copilot installs the `servers.<name>.env` block is not propagated to the subprocess, which then fails to import the package (`No module named minimal_webmcp`). When that happens, point `command` at a wrapper script that sets the env itself:
>
> ```bash
> # /home/yourname/.local/bin/minimal_webmcp_server
> #!/usr/bin/env bash
> export PYTHONPATH="/home/yourname"
> export MINIMAL_WEBMCP_HEADLESS="${MINIMAL_WEBMCP_HEADLESS:-1}"
> exec /path/to/python -m minimal_webmcp
> ```
>
> ```json
> {
>   "servers": {
>     "minimal_webmcp": {
>       "type": "stdio",
>       "command": "/home/yourname/.local/bin/minimal_webmcp_server"
>     }
>   }
> }
> ```

Example prompt (Copilot Chat, agent mode):

```
@workspace use minimal_webmcp to navigate to https://github.com/microsoft/vscode
and tell me the current star count.
```

## Architecture

```
minimal_webmcp/
├── __main__.py        # Entry point. Reads env, picks driver, runs server.
├── __init__.py        # Package docstring + __version__.
├── server.py          # JSON-RPC 2.0 dispatcher (stdio, NDJSON). Stdlib only.
├── tools.py           # TOOL_DEFS + call_tool(driver, name, args). Stdlib only.
├── ws.py              # Hand-rolled WebSocket client (RFC 6455). Stdlib only.
├── drivers/
│   ├── __init__.py    # make_driver(kind, **kwargs) factory.
│   ├── base.py        # Driver ABC: navigate / evaluate / screenshot / send_keys / close.
│   ├── mock.py        # MockDriver — canned responses, no browser.
│   └── embedded.py    # EmbeddedDriver — pywebview backend (lazy import).
├── vendor/
│   └── screenshot.js  # DOM-to-PNG via SVG foreignObject. No deps.
└── tests/
    └── test_plumbing.py  # E2E test: spawns the server, exercises every tool.
```

- **Transport** — stdio. `server.run` reads one JSON object per line from stdin and writes responses to stdout. Stderr is reserved for human-readable logs (`minimal_webmcp: MOCK mode ...`, `minimal_webmcp: ready`, etc.).
- **Driver abstraction** — `tools.py` is driver-agnostic. Adding a new backend (CDP, Marionette, Playwright) means subclassing `Driver` and registering it in `drivers/__init__.make_driver`.
- **Lazy imports** — `pywebview` is imported only when `EmbeddedDriver` is instantiated. This keeps MOCK mode 100 % stdlib.
- **Self-contained screenshot** — `vendor/screenshot.js` is injected into the page and turns the live DOM into a PNG using `XMLSerializer` + `Image` + `Canvas`. No external services.

## Tests

```bash
cd minimal_webmcp
python3 tests/test_plumbing.py
```

The test spawns the server in MOCK mode as a subprocess, runs through `initialize` → `tools/list` → all 9 `tools/call` paths → error paths (unknown tool, parse error) → `ping`, and prints `ALL OK` on success. Stdlib only, no fixtures required.

Expected output (abbreviated):

```
OK initialize
OK tools/list: ['click', 'evaluate', 'get_html', 'get_text', 'navigate', 'page_info', 'screenshot', 'type_text', 'wait_for']
OK navigate: {'url': 'https://example.com', 'title': 'Mock Page'}
OK evaluate: {'value': 2}
OK screenshot: size=69, magic valid
OK screenshot+file: 69 bytes -> /tmp/minimal_webmcp_test_shot.png
OK click
OK get_text: {'text': 'mock text content', 'size': 17, 'truncated': False}
OK get_html: <html><body>mock</body></html>...
OK wait_for: {'found': True}
OK type_text
OK unknown tool error: code=-32601
OK parse error: code=-32700
OK ping

ALL OK
```

## Project status

- **Version:** `0.2.0` (see `__init__.py`).
- **MCP protocol version:** `2024-11-05`.
- **Transport:** stdio, NDJSON.
- **Stdlib only** for the core, `tools.py`, `server.py`, `ws.py`, `drivers/mock.py`, and tests.
- **Optional:** `pywebview` + Qt or GTK for the embedded driver.
