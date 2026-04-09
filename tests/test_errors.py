"""Tests for structured error handling."""

from __future__ import annotations

import json

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from mcp_screenshot.errors import ScreenshotError, _error_response


class TestErrorResponse:
    """Test the _error_response structured error helper."""

    def test_raises_tool_error(self):
        with pytest.raises(ToolError):
            _error_response("test_code", "test message", retryable=False)

    def test_basic_envelope(self):
        with pytest.raises(ToolError) as exc_info:
            _error_response("invalid_parameter", "Bad value", retryable=False)

        payload = json.loads(str(exc_info.value))
        assert payload["status"] == "error"
        assert payload["error"]["code"] == "invalid_parameter"
        assert payload["error"]["message"] == "Bad value"
        assert payload["error"]["retryable"] is False

    def test_retryable_true(self):
        with pytest.raises(ToolError) as exc_info:
            _error_response("capture_failed", "Timeout", retryable=True)

        payload = json.loads(str(exc_info.value))
        assert payload["error"]["retryable"] is True

    def test_with_param_and_value(self):
        with pytest.raises(ToolError) as exc_info:
            _error_response(
                "invalid_parameter",
                "Bad output",
                retryable=False,
                param="output",
                value="jpeg",
            )

        error = json.loads(str(exc_info.value))["error"]
        assert error["param"] == "output"
        assert error["value"] == "jpeg"

    def test_with_valid_options(self):
        with pytest.raises(ToolError) as exc_info:
            _error_response(
                "invalid_parameter",
                "Bad output",
                retryable=False,
                param="output",
                value="jpeg",
                valid=["base64", "file", "clipboard"],
            )

        error = json.loads(str(exc_info.value))["error"]
        assert error["valid"] == ["base64", "file", "clipboard"]

    def test_with_suggestion(self):
        with pytest.raises(ToolError) as exc_info:
            _error_response(
                "missing_parameter",
                "file_path is required",
                retryable=False,
                suggestion="Provide a file path.",
            )

        error = json.loads(str(exc_info.value))["error"]
        assert error["suggestion"] == "Provide a file path."

    def test_with_help_url(self):
        with pytest.raises(ToolError) as exc_info:
            _error_response(
                "permission_denied",
                "Screen Recording required",
                retryable=True,
                help_url="https://support.apple.com/screen-recording",
            )

        error = json.loads(str(exc_info.value))["error"]
        assert error["help_url"] == "https://support.apple.com/screen-recording"

    def test_all_fields(self):
        with pytest.raises(ToolError) as exc_info:
            _error_response(
                "invalid_parameter",
                "Bad monitor",
                retryable=False,
                param="monitor",
                value=5,
                valid=["0", "1", "2"],
                suggestion="Use 0 for all monitors.",
                help_url="https://docs.example.com",
            )

        error = json.loads(str(exc_info.value))["error"]
        assert error["code"] == "invalid_parameter"
        assert error["message"] == "Bad monitor"
        assert error["retryable"] is False
        assert error["param"] == "monitor"
        assert error["value"] == 5
        assert error["valid"] == ["0", "1", "2"]
        assert error["suggestion"] == "Use 0 for all monitors."
        assert error["help_url"] == "https://docs.example.com"

    def test_omitted_optional_fields_absent(self):
        """Optional fields should not appear in the envelope when not provided."""
        with pytest.raises(ToolError) as exc_info:
            _error_response("test_code", "msg", retryable=False)

        error = json.loads(str(exc_info.value))["error"]
        assert "param" not in error
        assert "value" not in error
        assert "valid" not in error
        assert "suggestion" not in error
        assert "help_url" not in error

    def test_valid_json(self):
        """The error message must be valid JSON."""
        with pytest.raises(ToolError) as exc_info:
            _error_response("code", "msg", retryable=False)

        # Should not raise
        json.loads(str(exc_info.value))


class TestScreenshotError:
    """Test the ScreenshotError exception."""

    def test_is_exception(self):
        assert issubclass(ScreenshotError, Exception)

    def test_message(self):
        err = ScreenshotError("capture failed")
        assert str(err) == "capture failed"
