# minimal_webmcp

Minimal [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server for browser automation.

- **Stdlib-first core**
- **Optional `pywebview` embedded backend**
- **9 user-facing browser tools**
- **Headless + no-GPU support**
- **Offline MOCK mode for testing and CI**

## Features

- **Stdlib-only core path** — `server.py`, `tools.py`, `ws.py`, `drivers/mock.py`, and `_qt_env.py` use only the Python standard library.
- **MCP stdio transport** — newline-delimited JSON-RPC 2.0 over stdin/stdout.
- **Two driver modes**
  - `MockDriver` — in-memory, no browser, used for tests and CI.
  - `EmbeddedDriver` — launches an OS-native webview via `pywebview`.
- **9 browser tools**
  - `navigate`
  - `screenshot`
  - `click`
  - `type_text`
  - `get_text`
  - `get_html`
  - `wait_for`
  - `page_info`
  - `evaluate`
- **Screenshot fallback behavior**
  - The `screenshot` tool tries to return a real PNG first.
  - If PNG rendering is unavailable, it returns a structured fallback payload instead of failing silently.
- **No telemetry / no external network dependency in the screenshot pipeline**
- **Headless + no-GPU mode**
  - Supports `MINIMAL_WEBMCP_HEADLESS=1`
  - Also accepts the alias `MINIMAL_MCP_HEADLESS=1`
  - Configures Qt/WebEngine for offscreen software rendering

## Requirements

### Python

- Python 3.6+
- No third-party packages required for MOCK mode or the stdlib core paths

### Runtime dependencies

| Mode | What you need |
|------|---------------|
| **MOCK** (`MINIMAL_WEBMCP_MOCK=1`) | Nothing |
| **Embedded** (default) | `pywebview` + a GUI backend |
| **Tests** | Nothing |

### Embedded mode dependencies

`pywebview` does not bundle a GUI toolkit. Install `pywebview` and one supported backend.

Example:

```bash
pip install --user 'pywebview>=6.0,<7'
```

Linux users may need a Qt or GTK backend depending on their environment.  
For Qt-based rendering, install one of:

```bash
pip install --user PyQt5
pip install --user PyQt6
pip install --user PySide2
pip install --user PySide6
```

For Linux GTK-based environments:

```bash
sudo apt install python3-gi gir1.2-webkit2-4.0   # Debian/Ubuntu
sudo dnf install python3-gobject gtk3 webkit2gtk3 # Fedora/RHEL
pip install --user pywebview
```

## Installation

### From source

The package lives at the repository root, so run it from the parent directory with `PYTHONPATH` pointing to the repo parent:

```bash
PYTHONPATH=. python3 -m minimal_webmcp
```

If you later add packaging metadata (`pyproject.toml` or `setup.py`), editable install also works:

```bash
pip install -e .
python3 -m minimal_webmcp
```

### Print platform install hint

```bash
python3 -m minimal_webmcp --print-install
```

## Usage

### Run modes

| Mode | Invocation |
|------|------------|
| MOCK (offline, no browser) | `MINIMAL_WEBMCP_MOCK=1 python3 -m minimal_webmcp` |
| Embedded (default) | `python3 -m minimal_webmcp` |
| Embedded headless (offscreen Qt) | `MINIMAL_WEBMCP_HEADLESS=1 python3 -m minimal_webmcp` |
| Print install hint | `python3 -m minimal_webmcp --print-install` |

### Environment variables

| Variable | Effect |
|----------|--------|
| `MINIMAL_WEBMCP_MOCK=1` | Use `MockDriver` |
| `MINIMAL_WEBMCP_HEADLESS=1` | Enable offscreen Qt / software rendering configuration |
| `MINIMAL_MCP_HEADLESS=1` | Alias for `MINIMAL_WEBMCP_HEADLESS=1` |
| `PYWEBVIEW_GUI=qt` | Force Qt renderer on Linux |
| `PYWEBVIEW_LOG=WARNING` | Reduce pywebview noise in headless mode |
| `MINIMAL_WEBMCP_GRAB_SETTLE_MS` | Delay before Qt screenshot grab |
| `MINIMAL_WEBMCP_GRAB_TIMEOUT_MS` | Timeout for a single screenshot grab |
| `MINIMAL_WEBMCP_NAVIGATE_WAIT_FOR_LOAD` | Default `navigate` waiting strategy |

### Headless + no-GPU

When `MINIMAL_WEBMCP_HEADLESS=1` is set, the runtime configures Qt/WebEngine for offscreen operation:

- `QT_QPA_PLATFORM=offscreen`
- software OpenGL / software rendering hints
- Chromium flags tuned for offscreen, no-GPU execution
- Linux: `PYWEBVIEW_GUI=qt` is set automatically when possible

This mode is intended for environments without a GPU or display server.

## JSON-RPC wire format

The server speaks MCP over **newline-delimited JSON-RPC 2.0** on stdin/stdout.

- One JSON object per line on stdin
- One JSON object per line on stdout
- Logs go to stderr

### Minimal handshake

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"cli","version":"0.0.1"}}}' \
  | MINIMAL_WEBMCP_MOCK=1 python3 -m minimal_webmcp
```

Successful initialize response:

```json
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05","serverInfo":{"name":"minimal_webmcp","version":"0.2.1"},"capabilities":{"tools":{}}}}
```

## Tools

All tools are exposed through `tools.TOOL_DEFS` and dispatched by `server.py`.

| Name | Required params | Optional params | Returns | Notes |
|------|-----------------|-----------------|---------|------|
| `navigate` | `url` | `wait_for_load` | `{url, title}` | Fast by default; waits for URL change unless `wait_for_load=true` |
| `screenshot` | — | `path`, `inline`, `max_bytes` | MCP image content or fallback text | Returns PNG when possible; otherwise returns fallback payload |
| `click` | `selector` | — | `{ok: true}` | Clicks first element matched by CSS selector |
| `type_text` | `selector`, `text` | — | `{ok: true}` | Uses native value setter for inputs/textareas |
| `get_text` | — | `selector`, `full` | `{text, size, truncated?}` | Uses `textContent` |
| `get_html` | — | `selector`, `max_bytes`, `full` | `{html, size, truncated?}` | Uses `outerHTML` |
| `wait_for` | `selector` | `timeout_ms` | `{found: bool}` | Polls DOM until selector appears |
| `page_info` | — | — | `{url, title, html_bytes, text_chars, iframes, scripts, images, stylesheets, viewport, scroll}` | Cheap page probe |
| `evaluate` | `js` | — | `{value}` | Evaluates a JavaScript expression |

### Screenshot behavior

`screenshot` supports three result shapes:

1. **PNG image content**
   - Returned as MCP `type: "image"`
2. **Saved PNG path**
   - Returned when the image is too large or `path` is specified
3. **Fallback digest**
   - Returned when screenshot rendering is unavailable in the embedded path

### Test-only helper

`screenshot_fallback` exists for plumbing tests and should not be used in normal automation.

## Editor integration

The server is a stdio MCP server, so it works with MCP-aware clients.

Example snippets below are for reference only.

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

## Architecture

```text
minimal_webmcp/
├── __main__.py        # Entry point. Reads env, configures Qt/headless mode, runs server.
├── __init__.py        # Package docstring + __version__.
├── server.py          # JSON-RPC 2.0 dispatcher over stdio.
├── tools.py           # Tool definitions + dispatch.
├── ws.py              # Hand-rolled WebSocket client (RFC 6455). Stdlib only.
├── _qt_env.py         # Headless + no-GPU Qt environment configuration.
├── drivers/
│   ├── __init__.py    # Driver factory.
│   ├── base.py        # Driver interface.
│   ├── mock.py        # MockDriver for tests and CI.
│   └── embedded.py    # EmbeddedDriver via pywebview.
├── vendor/
│   └── screenshot.js  # DOM-to-PNG / page-digest helper.
└── tests/
    └── test_plumbing.py
```

## Tests

```bash
cd minimal_webmcp
python3 tests/test_plumbing.py
```

The test suite runs the server in MOCK mode, exercises the MCP handshake, tool dispatch paths, error paths, and the screenshot fallback flow.

## Project status

- **Version:** `0.2.1`
- **MCP protocol version:** `2024-11-05`
- **Transport:** stdio, NDJSON
- **Core:** stdlib-only
- **Embedded mode:** optional, via `pywebview`
