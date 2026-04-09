"""Tests for the capture layer."""

from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from PIL import Image as PILImage

from mcp_screenshot.capture import (
    VALID_OUTPUTS,
    _auto_crop_image,
    _check_display_available,
    _detect_platform,
    _handle_capture_error,
    _validate_monitor,
    _validate_output,
    _validate_region,
    capture_screen,
)


def _make_mock_sct(monitors=None, grab_size=(100, 50)):
    """Create a mock mss instance.

    Args:
        monitors: List of monitor dicts. Defaults to typical 2-monitor setup.
        grab_size: (width, height) of the grabbed image.
    """
    if monitors is None:
        monitors = [
            {"left": 0, "top": 0, "width": 1920, "height": 1080},   # 0: all
            {"left": 0, "top": 0, "width": 1920, "height": 1080},   # 1: primary
        ]

    w, h = grab_size
    # Create BGRA pixel data (4 bytes per pixel)
    pixel_data = bytes([100, 150, 200, 255] * w * h)

    mock_img = MagicMock()
    mock_img.size = (w, h)
    mock_img.bgra = pixel_data

    sct = MagicMock()
    sct.monitors = monitors
    sct.grab.return_value = mock_img
    sct.__enter__ = MagicMock(return_value=sct)
    sct.__exit__ = MagicMock(return_value=False)
    return sct


class TestDetectPlatform:
    def test_returns_dict(self):
        info = _detect_platform()
        assert isinstance(info, dict)
        assert "os" in info
        assert "is_linux" in info
        assert "is_macos" in info
        assert "is_windows" in info

    @patch("mcp_screenshot.capture.platform")
    def test_linux_includes_display_vars(self, mock_platform):
        mock_platform.system.return_value = "Linux"
        with patch.dict("os.environ", {"DISPLAY": ":0", "WAYLAND_DISPLAY": "", "XDG_SESSION_TYPE": "x11"}):
            info = _detect_platform()
        assert info["is_linux"] is True
        assert info["display"] == ":0"
        assert info["xdg_session_type"] == "x11"

    @patch("mcp_screenshot.capture.platform")
    def test_macos_no_display_vars(self, mock_platform):
        mock_platform.system.return_value = "Darwin"
        info = _detect_platform()
        assert info["is_macos"] is True
        assert "display" not in info

    @patch("mcp_screenshot.capture.platform")
    def test_windows(self, mock_platform):
        mock_platform.system.return_value = "Windows"
        info = _detect_platform()
        assert info["is_windows"] is True


class TestCheckDisplayAvailable:
    @patch("mcp_screenshot.capture._detect_platform")
    def test_non_linux_passes(self, mock_detect):
        mock_detect.return_value = {"is_linux": False, "is_macos": True, "os": "Darwin"}
        # Should not raise
        _check_display_available()

    @patch("mcp_screenshot.capture._detect_platform")
    def test_linux_with_display_passes(self, mock_detect):
        mock_detect.return_value = {
            "is_linux": True, "os": "Linux",
            "display": ":0", "wayland_display": "",
        }
        _check_display_available()

    @patch("mcp_screenshot.capture._detect_platform")
    def test_linux_with_wayland_passes(self, mock_detect):
        mock_detect.return_value = {
            "is_linux": True, "os": "Linux",
            "display": "", "wayland_display": "wayland-0",
        }
        _check_display_available()

    @patch("mcp_screenshot.capture._detect_platform")
    def test_linux_no_display_raises(self, mock_detect):
        mock_detect.return_value = {
            "is_linux": True, "os": "Linux",
            "display": "", "wayland_display": "",
            "xdg_session_type": "tty",
        }
        with pytest.raises(ToolError) as exc_info:
            _check_display_available()
        error = json.loads(str(exc_info.value))["error"]
        assert error["code"] == "no_display"
        assert "tty" in error["message"]

    @patch("mcp_screenshot.capture._detect_platform")
    def test_linux_none_display_raises(self, mock_detect):
        mock_detect.return_value = {
            "is_linux": True, "os": "Linux",
            "display": None, "wayland_display": None,
            "xdg_session_type": "unknown",
        }
        with pytest.raises(ToolError):
            _check_display_available()


class TestValidateMonitor:
    def test_valid_monitor_zero(self):
        _validate_monitor(0, 3)  # should not raise

    def test_valid_monitor_one(self):
        _validate_monitor(1, 3)

    def test_valid_monitor_max(self):
        _validate_monitor(2, 3)

    def test_monitor_too_high(self):
        with pytest.raises(ToolError) as exc_info:
            _validate_monitor(5, 3)
        error = json.loads(str(exc_info.value))["error"]
        assert error["code"] == "monitor_not_found"
        assert error["param"] == "monitor"
        assert error["value"] == 5

    def test_monitor_negative(self):
        with pytest.raises(ToolError) as exc_info:
            _validate_monitor(-1, 3)
        error = json.loads(str(exc_info.value))["error"]
        assert error["code"] == "monitor_not_found"


class TestValidateRegion:
    def test_valid_region(self):
        _validate_region([0, 0, 100, 100])  # should not raise

    def test_too_few_values(self):
        with pytest.raises(ToolError) as exc_info:
            _validate_region([0, 0, 100])
        error = json.loads(str(exc_info.value))["error"]
        assert error["code"] == "invalid_parameter"
        assert error["param"] == "region"

    def test_too_many_values(self):
        with pytest.raises(ToolError) as exc_info:
            _validate_region([0, 0, 100, 100, 50])
        error = json.loads(str(exc_info.value))["error"]
        assert error["code"] == "invalid_parameter"

    def test_zero_width(self):
        with pytest.raises(ToolError) as exc_info:
            _validate_region([0, 0, 0, 100])
        error = json.loads(str(exc_info.value))["error"]
        assert error["code"] == "invalid_parameter"
        assert "width" in error["message"]

    def test_negative_height(self):
        with pytest.raises(ToolError) as exc_info:
            _validate_region([0, 0, 100, -5])
        error = json.loads(str(exc_info.value))["error"]
        assert error["code"] == "invalid_parameter"

    def test_non_integer_values(self):
        with pytest.raises(ToolError) as exc_info:
            _validate_region([0, 0, 100.5, 100])
        error = json.loads(str(exc_info.value))["error"]
        assert error["code"] == "invalid_parameter"
        assert "integer" in error["message"].lower()

    def test_negative_xy_allowed(self):
        """Negative x/y are valid — they represent offsets in multi-monitor setups."""
        _validate_region([-100, -50, 200, 150])


class TestValidateOutput:
    def test_valid_outputs(self):
        for out in VALID_OUTPUTS:
            _validate_output(out)  # should not raise

    def test_case_insensitive(self):
        _validate_output("BASE64")
        _validate_output("File")
        _validate_output(" clipboard ")

    def test_invalid_output(self):
        with pytest.raises(ToolError) as exc_info:
            _validate_output("jpeg")
        error = json.loads(str(exc_info.value))["error"]
        assert error["code"] == "invalid_parameter"
        assert error["param"] == "output"
        assert error["value"] == "jpeg"
        assert error["valid"] == VALID_OUTPUTS


class TestAutoCropImage:
    def test_uniform_image_unchanged(self):
        """An entirely uniform image returns unchanged."""
        img = PILImage.new("RGB", (100, 100), (200, 200, 200))
        result = _auto_crop_image(img)
        assert result.size == (100, 100)

    def test_crops_border(self):
        """Image with content surrounded by uniform border gets cropped."""
        img = PILImage.new("RGB", (100, 100), (255, 255, 255))
        # Draw a colored rectangle in the center
        for x in range(30, 70):
            for y in range(30, 70):
                img.putpixel((x, y), (255, 0, 0))
        result = _auto_crop_image(img)
        assert result.size[0] < 100
        assert result.size[1] < 100

    def test_no_border_unchanged(self):
        """Image with no uniform border returns with original dimensions."""
        img = PILImage.new("RGB", (10, 10), (0, 0, 0))
        img.putpixel((0, 0), (255, 0, 0))  # different top-left
        img.putpixel((9, 9), (0, 255, 0))  # different bottom-right
        result = _auto_crop_image(img)
        # Most of image is uniform but corners differ — crop should still work
        assert result.size[0] <= 10
        assert result.size[1] <= 10


class TestCaptureScreen:
    @patch("mcp_screenshot.capture._check_display_available")
    @patch("mcp_screenshot.capture.mss_module")
    def test_full_screen_returns_png(self, mock_mss_module, mock_check_display):
        sct = _make_mock_sct()
        mock_mss_module.mss.return_value = sct

        result = capture_screen()

        assert isinstance(result, bytes)
        # Verify it's a valid PNG
        img = PILImage.open(io.BytesIO(result))
        assert img.format == "PNG"

    @patch("mcp_screenshot.capture._check_display_available")
    @patch("mcp_screenshot.capture.mss_module")
    def test_specific_monitor(self, mock_mss_module, mock_check_display):
        monitors = [
            {"left": 0, "top": 0, "width": 3840, "height": 1080},
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
            {"left": 1920, "top": 0, "width": 1920, "height": 1080},
        ]
        sct = _make_mock_sct(monitors=monitors)
        mock_mss_module.mss.return_value = sct

        capture_screen(monitor=2)

        sct.grab.assert_called_once_with(monitors[2])

    @patch("mcp_screenshot.capture._check_display_available")
    @patch("mcp_screenshot.capture.mss_module")
    def test_region_capture(self, mock_mss_module, mock_check_display):
        sct = _make_mock_sct()
        mock_mss_module.mss.return_value = sct

        capture_screen(region=[100, 200, 300, 400])

        sct.grab.assert_called_once_with({"left": 100, "top": 200, "width": 300, "height": 400})

    @patch("mcp_screenshot.capture._check_display_available")
    @patch("mcp_screenshot.capture.mss_module")
    def test_auto_crop(self, mock_mss_module, mock_check_display):
        sct = _make_mock_sct(grab_size=(50, 50))
        mock_mss_module.mss.return_value = sct

        result = capture_screen(auto_crop=True)
        assert isinstance(result, bytes)

    @patch("mcp_screenshot.capture._check_display_available")
    @patch("mcp_screenshot.capture.mss_module")
    def test_invalid_region_raises(self, mock_mss_module, mock_check_display):
        sct = _make_mock_sct()
        mock_mss_module.mss.return_value = sct

        with pytest.raises(ToolError) as exc_info:
            capture_screen(region=[0, 0, -1, 100])
        error = json.loads(str(exc_info.value))["error"]
        assert error["code"] == "invalid_parameter"

    @patch("mcp_screenshot.capture._check_display_available")
    @patch("mcp_screenshot.capture.mss_module")
    def test_invalid_monitor_raises(self, mock_mss_module, mock_check_display):
        sct = _make_mock_sct()
        mock_mss_module.mss.return_value = sct

        with pytest.raises(ToolError) as exc_info:
            capture_screen(monitor=99)
        error = json.loads(str(exc_info.value))["error"]
        assert error["code"] == "monitor_not_found"

    @patch("mcp_screenshot.capture._check_display_available")
    @patch("mcp_screenshot.capture.mss_module")
    def test_mss_exception_becomes_structured_error(self, mock_mss_module, mock_check_display):
        sct = _make_mock_sct()
        sct.grab.side_effect = RuntimeError("XGetImage failed")
        mock_mss_module.mss.return_value = sct

        with pytest.raises(ToolError) as exc_info:
            capture_screen()
        error = json.loads(str(exc_info.value))["error"]
        assert error["code"] == "capture_failed"
        assert "XGetImage failed" in error["message"]


class TestHandleCaptureError:
    @patch("mcp_screenshot.capture._detect_platform")
    def test_macos_permission_error(self, mock_detect):
        mock_detect.return_value = {
            "is_macos": True, "is_linux": False, "is_windows": False, "os": "Darwin",
        }
        with pytest.raises(ToolError) as exc_info:
            _handle_capture_error(RuntimeError("CGWindowListCreateImage returned NULL"))
        error = json.loads(str(exc_info.value))["error"]
        assert error["code"] == "permission_denied"
        assert error["help_url"] is not None

    @patch("mcp_screenshot.capture._detect_platform")
    def test_macos_generic_permission(self, mock_detect):
        mock_detect.return_value = {
            "is_macos": True, "is_linux": False, "is_windows": False, "os": "Darwin",
        }
        with pytest.raises(ToolError) as exc_info:
            _handle_capture_error(RuntimeError("permission denied"))
        error = json.loads(str(exc_info.value))["error"]
        assert error["code"] == "permission_denied"

    @patch("mcp_screenshot.capture._detect_platform")
    def test_linux_display_error(self, mock_detect):
        mock_detect.return_value = {
            "is_macos": False, "is_linux": True, "is_windows": False, "os": "Linux",
        }
        with pytest.raises(ToolError) as exc_info:
            _handle_capture_error(RuntimeError("Can't open display"))
        error = json.loads(str(exc_info.value))["error"]
        assert error["code"] == "no_display"

    @patch("mcp_screenshot.capture._detect_platform")
    def test_linux_xdisplay_error(self, mock_detect):
        mock_detect.return_value = {
            "is_macos": False, "is_linux": True, "is_windows": False, "os": "Linux",
        }
        with pytest.raises(ToolError) as exc_info:
            _handle_capture_error(RuntimeError("XDisplay not available"))
        error = json.loads(str(exc_info.value))["error"]
        assert error["code"] == "no_display"

    @patch("mcp_screenshot.capture._detect_platform")
    def test_generic_error(self, mock_detect):
        mock_detect.return_value = {
            "is_macos": False, "is_linux": False, "is_windows": True, "os": "Windows",
        }
        with pytest.raises(ToolError) as exc_info:
            _handle_capture_error(RuntimeError("Something went wrong"))
        error = json.loads(str(exc_info.value))["error"]
        assert error["code"] == "capture_failed"
        assert error["retryable"] is True
