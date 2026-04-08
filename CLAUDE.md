# mcp-screenshot

AI-agent-driven screen capture MCP server.

## Project structure

- `src/mcp_screenshot/` — package source
  - `server.py` — FastMCP server, tool handler
  - `capture.py` — mss wrapper, region/monitor logic, auto-crop
  - `errors.py` — structured error helper (`_error_response`)
  - `instructions/` — markdown tool descriptions loaded at startup
  - `icons/` — SVG icons (light/dark theme)
- `tests/` — pytest suite (target: 99%+ coverage)

## Development

```bash
uv sync --extra dev          # install deps
uv run pytest --cov          # run tests with coverage
uv run mcp-screenshot        # start server locally
```

## Conventions

- Structured errors via `_error_response()` in `errors.py` — always include error code, message, retryable flag
- Tool descriptions live in `instructions/*.md`, not inline strings
- Mirror patterns from mcp-clipboard (same author)
- All async tool handlers
