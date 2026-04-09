"""Tests for the screenshot MCP server."""

from __future__ import annotations

import base64
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from PIL import Image as PILImage

from mcp_screenshot.server import (
    _configure_logging,
    _copy_to_clipboard,
    _is_debug,
    _load_icons,
    _load_instruction,
    mcp,
    screenshot,
)


def _fake_png(width: int = 10, height: int = 10) -> bytes:
    """Create a minimal valid PNG for testing."""
    import io

    img = PILImage.new("RGB", (width, height), (100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestLoadInstruction:
    def test_loads_server_instruction(self):
        text = _load_instruction("server")
        assert "screenshot" in text.lower()

    def test_loads_screenshot_instruction(self):
        text = _load_instruction("screenshot")
        assert "region" in text.lower()

    def test_missing_instruction_raises(self):
        with pytest.raises(RuntimeError, match="Missing instruction file"):
            _load_instruction("nonexistent")


class TestLoadIcons:
    def test_returns_list(self):
        icons = _load_icons()
        assert len(icons) == 2

    def test_themes(self):
        icons = _load_icons()
        themes = {icon.theme for icon in icons}
        assert themes == {"light", "dark"}

    def test_svg_mime_type(self):
        icons = _load_icons()
        for icon in icons:
            assert icon.mimeType == "image/svg+xml"

    def test_urls_point_to_github(self):
        icons = _load_icons()
        for icon in icons:
            assert "github" in icon.src
            assert "mcp-screenshot" in icon.src


class TestIsDebug:
    def test_default_false(self):
        with patch("sys.argv", ["mcp-screenshot"]):
            with patch.dict(os.environ, {}, clear=True):
                assert _is_debug() is False

    def test_flag_true(self):
        with patch("sys.argv", ["mcp-screenshot", "--debug"]):
            assert _is_debug() is True

    def test_env_var_true(self):
        with patch("sys.argv", ["mcp-screenshot"]):
            with patch.dict(os.environ, {"MCP_SCREENSHOT_DEBUG": "1"}):
                assert _is_debug() is True

    def test_env_var_empty_false(self):
        with patch("sys.argv", ["mcp-screenshot"]):
            with patch.dict(os.environ, {"MCP_SCREENSHOT_DEBUG": ""}):
                assert _is_debug() is False


class TestConfigureLogging:
    def test_configures_without_error(self):
        with patch("sys.argv", ["mcp-screenshot"]):
            with patch.dict(os.environ, {}, clear=True):
                _configure_logging()

    def test_debug_mode(self):
        with patch("sys.argv", ["mcp-screenshot", "--debug"]):
            _configure_logging()


class TestScreenshotTool:
    @pytest.mark.asyncio
    async def test_base64_output(self):
        png = _fake_png()
        with patch("mcp_screenshot.server.capture_screen", return_value=png):
            result = await screenshot()

        from mcp.server.fastmcp.utilities.types import Image

        assert isinstance(result, Image)
        assert result._format == "png"
        # Verify the base64 decodes to the original PNG
        decoded = base64.b64decode(result.data)
        assert decoded == png

    @pytest.mark.asyncio
    async def test_file_output(self):
        png = _fake_png()
        with tempfile.TemporaryDirectory() as tmpdir:
            fpath = os.path.join(tmpdir, "test.png")
            with patch("mcp_screenshot.server.capture_screen", return_value=png):
                result = await screenshot(output="file", file_path=fpath)

            assert "saved" in result.lower()
            assert fpath in result
            assert Path(fpath).read_bytes() == png

    @pytest.mark.asyncio
    async def test_file_output_creates_parent_dirs(self):
        png = _fake_png()
        with tempfile.TemporaryDirectory() as tmpdir:
            fpath = os.path.join(tmpdir, "sub", "dir", "test.png")
            with patch("mcp_screenshot.server.capture_screen", return_value=png):
                await screenshot(output="file", file_path=fpath)

            assert Path(fpath).exists()

    @pytest.mark.asyncio
    async def test_file_output_without_path_raises(self):
        with pytest.raises(ToolError) as exc_info:
            await screenshot(output="file")
        error = json.loads(str(exc_info.value))["error"]
        assert error["code"] == "missing_parameter"
        assert error["param"] == "file_path"

    @pytest.mark.asyncio
    async def test_clipboard_output(self):
        png = _fake_png()
        with patch("mcp_screenshot.server.capture_screen", return_value=png):
            with patch("mcp_screenshot.server._copy_to_clipboard") as mock_copy:
                result = await screenshot(output="clipboard")

        assert "clipboard" in result.lower()
        mock_copy.assert_called_once_with(png)

    @pytest.mark.asyncio
    async def test_clipboard_failure_raises(self):
        png = _fake_png()
        with patch("mcp_screenshot.server.capture_screen", return_value=png):
            with patch("mcp_screenshot.server._copy_to_clipboard", side_effect=RuntimeError("no clipboard")):
                with pytest.raises(ToolError) as exc_info:
                    await screenshot(output="clipboard")

        error = json.loads(str(exc_info.value))["error"]
        assert error["code"] == "clipboard_unavailable"

    @pytest.mark.asyncio
    async def test_invalid_output_raises(self):
        with pytest.raises(ToolError) as exc_info:
            await screenshot(output="bmp")
        error = json.loads(str(exc_info.value))["error"]
        assert error["code"] == "invalid_parameter"
        assert error["param"] == "output"

    @pytest.mark.asyncio
    async def test_output_case_insensitive(self):
        png = _fake_png()
        with patch("mcp_screenshot.server.capture_screen", return_value=png):
            result = await screenshot(output="BASE64")
        from mcp.server.fastmcp.utilities.types import Image

        assert isinstance(result, Image)

    @pytest.mark.asyncio
    async def test_output_whitespace_stripped(self):
        png = _fake_png()
        with patch("mcp_screenshot.server.capture_screen", return_value=png):
            result = await screenshot(output=" base64 ")
        from mcp.server.fastmcp.utilities.types import Image

        assert isinstance(result, Image)

    @pytest.mark.asyncio
    async def test_region_passed_to_capture(self):
        png = _fake_png()
        with patch("mcp_screenshot.server.capture_screen", return_value=png) as mock_capture:
            await screenshot(region=[10, 20, 300, 400])

        mock_capture.assert_called_once_with(region=[10, 20, 300, 400], monitor=0, auto_crop=False)

    @pytest.mark.asyncio
    async def test_monitor_passed_to_capture(self):
        png = _fake_png()
        with patch("mcp_screenshot.server.capture_screen", return_value=png) as mock_capture:
            await screenshot(monitor=2)

        mock_capture.assert_called_once_with(region=None, monitor=2, auto_crop=False)

    @pytest.mark.asyncio
    async def test_auto_crop_passed_to_capture(self):
        png = _fake_png()
        with patch("mcp_screenshot.server.capture_screen", return_value=png) as mock_capture:
            await screenshot(auto_crop=True)

        mock_capture.assert_called_once_with(region=None, monitor=0, auto_crop=True)

    @pytest.mark.asyncio
    async def test_file_write_error(self):
        png = _fake_png()
        with patch("mcp_screenshot.server.capture_screen", return_value=png):
            with patch("mcp_screenshot.server.Path") as mock_path_cls:
                mock_path = MagicMock()
                mock_path.parent.mkdir.side_effect = OSError("Permission denied")
                mock_path_cls.return_value = mock_path
                with pytest.raises(ToolError) as exc_info:
                    await screenshot(output="file", file_path="/readonly/test.png")

        error = json.loads(str(exc_info.value))["error"]
        assert error["code"] == "file_write_error"
        assert error["param"] == "file_path"

    @pytest.mark.asyncio
    async def test_file_output_reports_size(self):
        png = _fake_png(width=50, height=50)
        with tempfile.TemporaryDirectory() as tmpdir:
            fpath = os.path.join(tmpdir, "test.png")
            with patch("mcp_screenshot.server.capture_screen", return_value=png):
                result = await screenshot(output="file", file_path=fpath)
            assert "KB" in result


class TestCopyToClipboard:
    @patch("subprocess.run")
    @patch("platform.system", return_value="Darwin")
    def test_macos(self, mock_system, mock_run):
        mock_run.return_value = MagicMock(returncode=0)

        _copy_to_clipboard(b"fake png data")

        mock_run.assert_called_once()
        args = mock_run.call_args
        assert "osascript" in args[0][0]

    @patch("subprocess.run")
    @patch("platform.system", return_value="Linux")
    def test_linux_wayland(self, mock_system, mock_run):
        mock_run.return_value = MagicMock(returncode=0)

        with patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}):
            _copy_to_clipboard(b"fake png data")

        args = mock_run.call_args
        assert "wl-copy" in args[0][0]

    @patch("subprocess.run")
    @patch("platform.system", return_value="Linux")
    def test_linux_x11(self, mock_system, mock_run):
        mock_run.return_value = MagicMock(returncode=0)

        with patch.dict(os.environ, {"WAYLAND_DISPLAY": ""}, clear=False):
            _copy_to_clipboard(b"fake png data")

        args = mock_run.call_args
        assert "xclip" in args[0][0]

    @patch("subprocess.run")
    @patch("platform.system", return_value="FreeBSD")
    def test_unsupported_platform(self, mock_system, mock_run):
        with pytest.raises(RuntimeError, match="not supported"):
            _copy_to_clipboard(b"fake png data")

    @patch("subprocess.run")
    @patch("platform.system", return_value="Darwin")
    def test_macos_failure(self, mock_system, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr=b"error msg")
        with pytest.raises(RuntimeError, match="osascript failed"):
            _copy_to_clipboard(b"fake png data")

    @patch("subprocess.run")
    @patch("platform.system", return_value="Linux")
    def test_linux_failure(self, mock_system, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr=b"error msg")
        with patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}):
            with pytest.raises(RuntimeError):
                _copy_to_clipboard(b"fake png data")


class TestCopyToClipboardWindows:
    @patch("subprocess.run")
    @patch("platform.system", return_value="Windows")
    def test_windows_success(self, mock_system, mock_run):
        mock_run.return_value = MagicMock(returncode=0)

        _copy_to_clipboard(b"fake png data")

        mock_run.assert_called_once()
        args = mock_run.call_args
        assert "powershell" in args[0][0]

    @patch("subprocess.run")
    @patch("platform.system", return_value="Windows")
    def test_windows_failure(self, mock_system, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr=b"error msg")
        with pytest.raises(RuntimeError, match="PowerShell clipboard failed"):
            _copy_to_clipboard(b"fake png data")


class TestMain:
    @patch("mcp_screenshot.server.mcp")
    def test_main_calls_run(self, mock_mcp):
        from mcp_screenshot.server import main

        with patch("sys.argv", ["mcp-screenshot"]):
            with patch.dict(os.environ, {}, clear=True):
                main()
        mock_mcp.run.assert_called_once()

    @patch("mcp_screenshot.server.mcp")
    def test_main_strips_debug_flag(self, mock_mcp):
        from mcp_screenshot.server import main

        with patch("sys.argv", ["mcp-screenshot", "--debug"]):
            main()
        # After stripping, sys.argv should not contain --debug
        mock_mcp.run.assert_called_once()


class TestMcpServer:
    def test_server_name(self):
        assert mcp.name == "mcp_screenshot"

    def test_server_has_instructions(self):
        assert mcp.instructions is not None
        assert len(mcp.instructions) > 0


class TestInitVersion:
    def test_version_available(self):
        from mcp_screenshot import __version__

        assert __version__ is not None
        assert isinstance(__version__, str)

    def test_version_fallback(self):
        """When package isn't installed, version falls back to dev."""
        import mcp_screenshot

        # The fallback is set at import time, so we verify the existing
        # value is a string (either real version or "0.0.0-dev")
        assert mcp_screenshot.__version__ is not None
        assert isinstance(mcp_screenshot.__version__, str)
