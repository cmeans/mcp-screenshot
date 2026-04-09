"""Screen capture layer — wraps mss + Pillow.

All platform-specific detection and error handling lives here so that
server.py stays clean and testable.
"""

from __future__ import annotations

import io
import logging
import os
import platform
import subprocess
import time
from pathlib import Path
from typing import Any, NoReturn

import mss as mss_module
from PIL import Image as PILImage

from mcp.server.fastmcp.exceptions import ToolError

from .errors import (
    LINUX_DISPLAY_HELP,
    MACOS_SCREEN_RECORDING,
    MSS_MONITORS_DOCS,
    ScreenshotError,
    _error_response,
)

logger = logging.getLogger(__name__)

VALID_OUTPUTS = ["base64", "file", "clipboard"]

# Portal screenshot timeout in seconds
_PORTAL_TIMEOUT = 8

# Where GNOME saves portal screenshots
_GNOME_SCREENSHOT_DIR = Path.home() / "Pictures" / "Screenshots"


def _detect_platform() -> dict[str, Any]:
    """Detect platform and display server for error messages."""
    info: dict[str, Any] = {
        "os": platform.system(),
        "is_linux": platform.system() == "Linux",
        "is_macos": platform.system() == "Darwin",
        "is_windows": platform.system() == "Windows",
    }
    if info["is_linux"]:
        info["display"] = os.environ.get("DISPLAY")
        info["wayland_display"] = os.environ.get("WAYLAND_DISPLAY")
        info["xdg_session_type"] = os.environ.get("XDG_SESSION_TYPE")
    return info


def _is_wayland() -> bool:
    """Check if we're running under Wayland."""
    return bool(os.environ.get("WAYLAND_DISPLAY"))


def _check_display_available() -> None:
    """Check that a display server is available on Linux.

    Raises structured error with actionable help if no display is found.
    """
    plat = _detect_platform()
    if not plat["is_linux"]:
        return

    has_display = plat.get("display") or plat.get("wayland_display")
    if not has_display:
        session_type = plat.get("xdg_session_type", "unknown")
        _error_response(
            "no_display",
            f"No display server found (DISPLAY and WAYLAND_DISPLAY are unset, "
            f"XDG_SESSION_TYPE={session_type!r}). "
            f"Screen capture requires a running display server.",
            retryable=False,
            suggestion="Run from a graphical session, or set DISPLAY=:0 if an X server is running.",
            help_url=LINUX_DISPLAY_HELP,
        )


def _validate_monitor(monitor: int, available_count: int) -> None:
    """Validate monitor index against available monitors."""
    if monitor < 0 or monitor > available_count - 1:
        valid_range = list(range(available_count))
        _error_response(
            "monitor_not_found",
            f"Monitor {monitor} not found. "
            f"Available monitors: 0 (all), {', '.join(str(i) for i in range(1, available_count))}.",
            retryable=False,
            param="monitor",
            value=monitor,
            valid=[str(v) for v in valid_range],
            suggestion=f"Use 0 for all monitors or 1-{available_count - 1} for a specific monitor.",
            help_url=MSS_MONITORS_DOCS,
        )


def _validate_region(region: list[int]) -> None:
    """Validate region format: [x, y, width, height] with positive dimensions."""
    if len(region) != 4:
        _error_response(
            "invalid_parameter",
            f"Region must be [x, y, width, height] (4 integers). Got {len(region)} values.",
            retryable=False,
            param="region",
            value=region,
            suggestion="Provide exactly 4 integers: [x, y, width, height].",
        )

    x, y, w, h = region

    if not all(isinstance(v, int) for v in region):
        _error_response(
            "invalid_parameter",
            "Region values must all be integers.",
            retryable=False,
            param="region",
            value=region,
            suggestion="Provide integer pixel coordinates: [x, y, width, height].",
        )

    if w <= 0 or h <= 0:
        _error_response(
            "invalid_parameter",
            f"Region width and height must be positive. Got width={w}, height={h}.",
            retryable=False,
            param="region",
            value=region,
            suggestion="Ensure width and height are greater than 0.",
        )


def _validate_output(output: str) -> None:
    """Validate output mode."""
    output_lower = output.strip().lower()
    if output_lower not in VALID_OUTPUTS:
        _error_response(
            "invalid_parameter",
            f"Unknown output mode: {output!r}.",
            retryable=False,
            param="output",
            value=output,
            valid=VALID_OUTPUTS,
        )


def _auto_crop_image(img: PILImage.Image) -> PILImage.Image:
    """Trim uniform borders from an image.

    Detects the bounding box of non-uniform content and crops to it.
    Returns the original image if no cropping is needed.
    """
    # Get the background color from the top-left pixel
    bg = img.getpixel((0, 0))

    # Create a background image of the same size and color
    bg_img = PILImage.new(img.mode, img.size, bg)

    # Find the bounding box of the difference
    from PIL import ImageChops

    diff = ImageChops.difference(img, bg_img)
    bbox = diff.getbbox()

    if bbox is None:
        # Entire image is uniform — return as-is
        return img

    return img.crop(bbox)


def _capture_wayland_portal() -> PILImage.Image:
    """Capture screenshot via xdg-desktop-portal on Wayland.

    Uses gdbus to call the portal Screenshot API, then watches the
    screenshot directory for a new file. This works on GNOME, KDE,
    and other desktop environments that implement the portal.

    Returns:
        Pillow Image of the captured screenshot.

    Raises:
        ScreenshotError: If the portal call fails or no screenshot appears.
    """
    # Record existing files before the call
    screenshot_dir = _GNOME_SCREENSHOT_DIR
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    existing = set(screenshot_dir.iterdir())
    before_time = time.time()

    # Call the portal
    try:
        result = subprocess.run(
            [
                "gdbus", "call", "--session",
                "--dest", "org.freedesktop.portal.Desktop",
                "--object-path", "/org/freedesktop/portal/desktop",
                "--method", "org.freedesktop.portal.Screenshot.Screenshot",
                "", '{"interactive": <false>}',
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError:
        raise ScreenshotError(
            "gdbus not found. Install glib2 or use an X11 session."
        )
    except subprocess.TimeoutExpired:
        raise ScreenshotError("Portal screenshot request timed out.")

    if result.returncode != 0:
        raise ScreenshotError(
            f"Portal screenshot failed: {result.stderr.strip()}"
        )

    logger.debug("Portal call succeeded: %s", result.stdout.strip())

    # Watch for a new file in the screenshot directory
    deadline = time.time() + _PORTAL_TIMEOUT
    new_file = None

    while time.time() < deadline:
        current = set(screenshot_dir.iterdir())
        new_files = current - existing

        # Also check for files modified after our call
        if not new_files:
            for f in current:
                if f.stat().st_mtime > before_time and f.suffix.lower() == ".png":
                    new_files = {f}
                    break

        if new_files:
            # Take the most recent one
            new_file = max(new_files, key=lambda f: f.stat().st_mtime)
            break

        time.sleep(0.3)

    if new_file is None:
        raise ScreenshotError(
            "Portal screenshot was requested but no file appeared. "
            "The desktop environment may have denied the request silently. "
            "Try adding the MCP server's terminal to the allowed screenshot list."
        )

    logger.debug("Portal screenshot saved to: %s", new_file)

    # Read and return as Pillow Image
    img = PILImage.open(new_file)
    img.load()  # Force read before we might delete
    return img


def capture_screen(
    region: list[int] | None = None,
    monitor: int = 0,
    auto_crop: bool = False,
) -> bytes:
    """Capture screen and return PNG bytes.

    On Linux Wayland, automatically falls back to the xdg-desktop-portal
    screenshot API when mss (X11-based) fails.

    Args:
        region: Optional [x, y, width, height] for partial capture.
        monitor: Monitor index (0=all, 1=primary, 2=secondary, ...).
        auto_crop: If True, trim uniform borders from the captured image.

    Returns:
        PNG image data as bytes.

    Raises:
        ScreenshotError: If capture fails at the platform level.
    """
    _check_display_available()

    img = None
    mss_error = None

    # Try mss first (works on X11, macOS, Windows)
    try:
        with mss_module.mss() as sct:
            # Validate monitor index
            _validate_monitor(monitor, len(sct.monitors))

            if region is not None:
                _validate_region(region)
                x, y, w, h = region
                grab_area = {"left": x, "top": y, "width": w, "height": h}
            else:
                grab_area = sct.monitors[monitor]

            sct_img = sct.grab(grab_area)

            # Convert to Pillow Image
            img = PILImage.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

    except (ScreenshotError, ToolError):
        raise
    except Exception as e:
        mss_error = e

    # Wayland fallback: if mss failed and we're on Wayland, try the portal
    if img is None and mss_error is not None:
        if _is_wayland():
            logger.debug(
                "mss failed on Wayland (%s), falling back to portal API",
                mss_error,
            )
            try:
                img = _capture_wayland_portal()

                # If a region was requested, crop the portal screenshot
                if region is not None:
                    _validate_region(region)
                    x, y, w, h = region
                    img = img.crop((x, y, x + w, y + h))

            except ScreenshotError:
                raise
            except Exception as e:
                # Portal also failed — report both errors
                _error_response(
                    "capture_failed",
                    f"Screen capture failed. "
                    f"mss (X11): {mss_error}. "
                    f"Portal (Wayland): {e}.",
                    retryable=True,
                    suggestion="Check that a display server is running and you have the necessary permissions.",
                )
        else:
            # Not Wayland — report the mss error directly
            _handle_capture_error(mss_error)

    if img is None:
        _error_response(
            "capture_failed",
            "Screen capture returned no image.",
            retryable=True,
            suggestion="Check that a display server is running and you have the necessary permissions.",
        )

    if auto_crop:
        img = _auto_crop_image(img)

    # Convert to PNG bytes
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _handle_capture_error(exc: Exception) -> NoReturn:
    """Convert platform exceptions into structured errors."""
    msg = str(exc)
    plat = _detect_platform()

    # macOS Screen Recording permission
    if plat["is_macos"] and ("permission" in msg.lower() or "CGWindowListCreateImage" in msg):
        _error_response(
            "permission_denied",
            "Screen Recording permission is required on macOS. "
            "Grant permission in System Settings > Privacy & Security > Screen Recording.",
            retryable=True,
            suggestion="Open System Settings > Privacy & Security > Screen Recording and enable access for your terminal or application.",
            help_url=MACOS_SCREEN_RECORDING,
        )

    # Linux display issues
    if plat["is_linux"] and ("display" in msg.lower() or "xdisplay" in msg.lower()):
        _error_response(
            "no_display",
            f"Cannot connect to display server: {msg}",
            retryable=False,
            suggestion="Ensure a graphical session is running and DISPLAY or WAYLAND_DISPLAY is set.",
            help_url=LINUX_DISPLAY_HELP,
        )

    # Generic capture failure
    _error_response(
        "capture_failed",
        f"Screen capture failed: {msg}",
        retryable=True,
        suggestion="Check that a display server is running and you have the necessary permissions.",
    )
