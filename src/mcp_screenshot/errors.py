"""Structured error handling for mcp-screenshot.

Every tool error is a JSON envelope inside a ToolError, giving AI agents
machine-readable fields (code, param, valid options, help_url) to
self-correct without human intervention.
"""

from __future__ import annotations

import json
from typing import Any, NoReturn

from mcp.server.fastmcp.exceptions import ToolError


class ScreenshotError(Exception):
    """Raised when screen capture fails at the platform level."""


# help_url constants
MSS_DOCS = "https://python-mss.readthedocs.io/en/stable/"
MSS_MONITORS_DOCS = "https://python-mss.readthedocs.io/en/stable/api.html#mss.base.MSSBase.monitors"
MACOS_SCREEN_RECORDING = "https://support.apple.com/guide/mac-help/control-access-to-screen-recording-on-mac-mchld6aa7d23/mac"
LINUX_DISPLAY_HELP = "https://wiki.archlinux.org/title/Xorg#Display"


def _error_response(
    code: str,
    message: str,
    *,
    retryable: bool,
    param: str | None = None,
    value: Any | None = None,
    valid: list[str] | None = None,
    suggestion: str | None = None,
    help_url: str | None = None,
) -> NoReturn:
    """Build a structured error envelope and raise ToolError.

    The MCP SDK wraps ToolError in a CallToolResult with isError=True,
    so clients get proper error signaling. The JSON envelope provides
    structured fields for smart clients alongside a human-readable message.

    Raises:
        ToolError: always -- this function never returns.
    """
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "retryable": retryable,
    }
    if param is not None:
        error["param"] = param
    if value is not None:
        error["value"] = value
    if valid is not None:
        error["valid"] = valid
    if suggestion is not None:
        error["suggestion"] = suggestion
    if help_url is not None:
        error["help_url"] = help_url

    raise ToolError(json.dumps({"status": "error", "error": error}))
