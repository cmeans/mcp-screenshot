# mcp-screenshot

[![PyPI version](https://img.shields.io/pypi/v/mcp-screenshot)](https://pypi.org/project/mcp-screenshot/)
[![Python versions](https://img.shields.io/pypi/pyversions/mcp-screenshot)](https://pypi.org/project/mcp-screenshot/)
[![License](https://img.shields.io/pypi/l/mcp-screenshot)](https://github.com/cmeans/mcp-screenshot/blob/main/LICENSE)
[![Tests](https://img.shields.io/github/actions/workflow/status/cmeans/mcp-screenshot/test.yml?label=tests)](https://github.com/cmeans/mcp-screenshot/actions/workflows/test.yml)
[![Coverage](https://codecov.io/gh/cmeans/mcp-screenshot/graph/badge.svg)](https://codecov.io/gh/cmeans/mcp-screenshot)
[![Downloads](https://img.shields.io/pypi/dm/mcp-screenshot)](https://pypi.org/project/mcp-screenshot/)

**AI-agent-driven screen capture MCP server.** Lets Claude (or any AI agent) capture screenshots to evaluate visual output it can't otherwise see — no human interaction needed.

Cross-platform. Zero external binary dependencies. Structured errors that help AI agents self-correct.

## Features

- **Single tool, full workflow** — capture the full screen, then zoom into a region with pixel coordinates
- **Cross-platform** — macOS, Linux (X11 + XWayland), Windows — works out of the box
- **Zero external deps** — uses [mss](https://python-mss.readthedocs.io/) (pure Python, native APIs on every platform)
- **Structured errors** — machine-readable JSON error envelopes with error codes, valid options, and help URLs so the AI can self-correct without asking the human
- **Multi-monitor** — capture all monitors or target a specific one
- **Auto-crop** — trim uniform borders from captures
- **Multiple output modes** — return image directly (base64), save to file, or copy to clipboard

## Quick Start

### Install

```bash
# Using uvx (recommended)
uvx mcp-screenshot

# Using pip
pip install mcp-screenshot
```

### Configure Claude Desktop

Add to your Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "screenshot": {
      "command": "uvx",
      "args": ["mcp-screenshot"]
    }
  }
}
```

### Configure Claude Code

Add to your Claude Code settings:

```json
{
  "mcpServers": {
    "screenshot": {
      "command": "uvx",
      "args": ["mcp-screenshot"]
    }
  }
}
```

## Tool: `screenshot`

Capture a screenshot of the screen or a specific region.

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `region` | `list[int]` | `None` | `[x, y, width, height]` in pixels. Omit for full screen. |
| `monitor` | `int` | `0` | Monitor index. `0` = all monitors, `1` = primary, `2` = secondary, etc. |
| `output` | `str` | `"base64"` | `"base64"` (return image), `"file"` (save to disk), `"clipboard"` (copy). |
| `file_path` | `str` | `None` | Required when `output="file"`. Path for the saved PNG. |
| `auto_crop` | `bool` | `False` | Trim uniform-color borders from the capture. |

### Agent Workflow

The typical two-step workflow:

1. **Full screen capture** — call `screenshot()` to see everything on screen
2. **Targeted capture** — identify coordinates from the full screenshot, then call `screenshot(region=[x, y, width, height])` for detail

### Output Modes

- **`base64`** (default) — returns the image directly as a PNG for visual analysis
- **`file`** — saves the PNG to the specified `file_path`
- **`clipboard`** — copies the image to the system clipboard

## Structured Errors

When something goes wrong, the tool returns machine-readable JSON errors instead of opaque strings:

```json
{
  "status": "error",
  "error": {
    "code": "monitor_not_found",
    "message": "Monitor 3 not found. Available monitors: 0 (all), 1, 2.",
    "retryable": false,
    "param": "monitor",
    "value": 3,
    "valid": ["0", "1", "2"],
    "suggestion": "Use 0 for all monitors or 1-2 for a specific monitor.",
    "help_url": "https://python-mss.readthedocs.io/en/stable/api.html#mss.base.MSSBase.monitors"
  }
}
```

Error codes: `invalid_parameter`, `missing_parameter`, `monitor_not_found`, `capture_failed`, `permission_denied`, `no_display`, `file_write_error`, `clipboard_unavailable`.

## Platform Notes

### macOS

Requires **Screen Recording** permission. Grant it in:
**System Settings > Privacy & Security > Screen Recording**

If permission isn't granted, the tool returns a `permission_denied` structured error with a direct link to Apple's support page.

### Linux

Requires a running display server (X11 or XWayland). The tool detects `DISPLAY` and `WAYLAND_DISPLAY` environment variables and returns an actionable `no_display` error if neither is set.

For **clipboard** output: requires `wl-copy` (Wayland) or `xclip` (X11).

### Windows

Works out of the box. For **clipboard** output, uses PowerShell.

## Development

```bash
git clone https://github.com/cmeans/mcp-screenshot.git
cd mcp-screenshot
uv sync --extra dev
uv run pytest --cov
```

## License

[Apache 2.0](LICENSE)
