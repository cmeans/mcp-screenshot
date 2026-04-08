"""Screenshot MCP Server.

MCP server that captures screenshots of the screen or specific regions
for AI agent visual analysis. Cross-platform, zero external dependencies.
"""

from __future__ import annotations

import base64
import logging
import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.utilities.types import Image
from mcp.types import Icon

from .capture import VALID_OUTPUTS, capture_screen, _validate_output
from .errors import _error_response

logger = logging.getLogger(__name__)


def _is_debug() -> bool:
    """Check if debug mode is enabled via --debug flag or env var."""
    return "--debug" in sys.argv or os.environ.get("MCP_SCREENSHOT_DEBUG", "") == "1"


def _configure_logging() -> None:
    """Configure root logging for the mcp_screenshot package."""
    level = logging.DEBUG if _is_debug() else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("mcp_screenshot").setLevel(level)


_INSTRUCTIONS_DIR = Path(__file__).parent / "instructions"
_ICON_BASE_URL = "https://raw.githubusercontent.com/cmeans/mcp-screenshot/main/src/mcp_screenshot/icons"


def _load_instruction(name: str) -> str:
    """Load an instruction file from the instructions/ directory."""
    path = _INSTRUCTIONS_DIR / f"{name}.md"
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        raise RuntimeError(
            f"Missing instruction file: {path}. "
            "The mcp-screenshot package may be installed incorrectly."
        ) from None


def _load_icons() -> list[Icon]:
    """Return Icon objects pointing to hosted SVGs on GitHub."""
    icons = []
    theme_map = {"light": "mcp-screenshot-icon-chart.svg", "dark": "mcp-screenshot-icon-diagram.svg"}
    for theme, filename in theme_map.items():
        icons.append(Icon(
            src=f"{_ICON_BASE_URL}/{filename}",
            mimeType="image/svg+xml",
            theme=theme,
        ))
    return icons


mcp = FastMCP(
    "mcp_screenshot",
    instructions=_load_instruction("server"),
    icons=_load_icons(),
)


@mcp.tool(
    name="screenshot",
    description=_load_instruction("screenshot"),
    annotations={
        "title": "Take Screenshot",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def screenshot(
    region: list[int] | None = None,
    monitor: int = 0,
    output: str = "base64",
    file_path: str | None = None,
    auto_crop: bool = False,
):
    """Capture a screenshot of the screen or a specific region."""
    output = output.strip().lower()
    _validate_output(output)

    # Validate file_path requirement
    if output == "file" and not file_path:
        _error_response(
            "missing_parameter",
            "file_path is required when output='file'.",
            retryable=False,
            param="file_path",
            suggestion="Provide a file path, e.g. file_path='/tmp/screenshot.png'.",
        )

    logger.debug(
        "screenshot called: region=%r monitor=%r output=%r file_path=%r auto_crop=%r",
        region, monitor, output, file_path, auto_crop,
    )

    png_bytes = capture_screen(region=region, monitor=monitor, auto_crop=auto_crop)

    if output == "base64":
        encoded = base64.b64encode(png_bytes).decode("ascii")
        return Image(data=encoded, format="png")

    if output == "file":
        assert file_path is not None  # validated above
        try:
            dest = Path(file_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(png_bytes)
        except OSError as e:
            _error_response(
                "file_write_error",
                f"Failed to write screenshot to {file_path!r}: {e}",
                retryable=False,
                param="file_path",
                value=file_path,
                suggestion="Check that the directory exists and you have write permission.",
            )
        size_kb = len(png_bytes) / 1024
        return f"Screenshot saved to {file_path} ({size_kb:.1f} KB)"

    if output == "clipboard":
        try:
            _copy_to_clipboard(png_bytes)
        except Exception as e:
            _error_response(
                "clipboard_unavailable",
                f"Failed to copy screenshot to clipboard: {e}",
                retryable=True,
                suggestion="Ensure a clipboard manager is running (e.g. wl-copy on Wayland, xclip on X11).",
            )
        return "Screenshot copied to clipboard."

    # unreachable — _validate_output already checked
    _error_response(
        "invalid_parameter",
        f"Unknown output mode: {output!r}.",
        retryable=False,
        param="output",
        value=output,
        valid=VALID_OUTPUTS,
    )


def _copy_to_clipboard(png_bytes: bytes) -> None:
    """Copy PNG bytes to the system clipboard.

    Uses platform-appropriate methods:
    - macOS: pbcopy via subprocess
    - Linux: wl-copy (Wayland) or xclip (X11)
    - Windows: PowerShell
    """
    import platform as _platform
    import subprocess

    system = _platform.system()

    if system == "Darwin":
        # macOS: use osascript to set clipboard to image data
        proc = subprocess.run(
            ["osascript", "-e", 'set the clipboard to (read (POSIX file "/dev/stdin") as «class PNGf»)'],
            input=png_bytes,
            capture_output=True,
            timeout=10,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"osascript failed: {proc.stderr.decode(errors='replace')}")

    elif system == "Linux":
        wayland = os.environ.get("WAYLAND_DISPLAY")
        if wayland:
            cmd = ["wl-copy", "--type", "image/png"]
        else:
            cmd = ["xclip", "-selection", "clipboard", "-t", "image/png"]

        proc = subprocess.run(
            cmd,
            input=png_bytes,
            capture_output=True,
            timeout=10,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"{cmd[0]} failed: {proc.stderr.decode(errors='replace')}")

    elif system == "Windows":
        # Windows: use PowerShell to set clipboard image
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(png_bytes)
            tmp_path = tmp.name
        try:
            proc = subprocess.run(
                ["powershell", "-Command",
                 f"Add-Type -AssemblyName System.Windows.Forms; "
                 f"[System.Windows.Forms.Clipboard]::SetImage("
                 f"[System.Drawing.Image]::FromFile('{tmp_path}'))"],
                capture_output=True,
                timeout=10,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"PowerShell clipboard failed: {proc.stderr.decode(errors='replace')}")
        finally:
            os.unlink(tmp_path)

    else:
        raise RuntimeError(f"Clipboard not supported on {system}")


def main() -> None:
    """Entry point for the mcp-screenshot command."""
    _configure_logging()
    sys.argv = [a for a in sys.argv if a != "--debug"]
    mcp.run()


if __name__ == "__main__":
    main()
