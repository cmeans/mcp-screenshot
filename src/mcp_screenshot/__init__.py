"""MCP server for AI-agent-driven screen capture."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("mcp-screenshot")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"
