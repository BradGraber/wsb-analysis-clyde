"""Unit tests for logging configuration

Tests verify that structlog is properly configured with:
- JSON output format
- File logging to logs/backend.log
- Support for all log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Exception stack traces for ERROR/CRITICAL levels
- Automatic logs/ directory creation
- Valid JSON output with expected fields
"""

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from unittest import mock

import pytest
import structlog

from src.backend.utils.logging_config import setup_logging, get_logger


@pytest.fixture
def temp_log_dir():
    """Create a temporary directory for test logs."""
    temp_dir = tempfile.mkdtemp(prefix="test_logs_")
    yield temp_dir
    # Cleanup
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)


@pytest.fixture
def clean_logging():
    """Reset logging configuration after each test."""
    yield
    # Clear structlog configuration
    structlog.reset_defaults()
    # Reset stdlib logging
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()


class TestSetupLogging:
    """Test setup_logging() function."""

    def test_creates_logs_directory(self, temp_log_dir, clean_logging):
        """Test that setup_logging creates logs/ directory if it doesn't exist."""
        log_dir = os.path.join(temp_log_dir, "logs")
        assert not os.path.exists(log_dir)

        setup_logging(log_dir=log_dir)

        assert os.path.exists(log_dir)
        assert os.path.isdir(log_dir)

    def test_creates_log_file(self, temp_log_dir, clean_logging):
        """Test that setup_logging creates the log file."""
        log_dir = os.path.join(temp_log_dir, "logs")
        setup_logging(log_dir=log_dir)

        log_file = os.path.join(log_dir, "backend.log")
        # File may not exist until first log entry, so we'll log something
        logger = get_logger()
        logger.info("test_message")

        assert os.path.exists(log_file)
        assert os.path.isfile(log_file)

    def test_custom_log_filename(self, temp_log_dir, clean_logging):
        """Test that setup_logging respects custom log filename."""
        log_dir = os.path.join(temp_log_dir, "logs")
        custom_filename = "custom.log"
        setup_logging(log_dir=log_dir, log_filename=custom_filename)

        logger = get_logger()
        logger.info("test_message")

        log_file = os.path.join(log_dir, custom_filename)
        assert os.path.exists(log_file)


class TestLogLevels:
    """Test all log levels produce valid JSON output."""

    def test_debug_level(self, temp_log_dir, clean_logging):
        """Test DEBUG level logging."""
        log_dir = os.path.join(temp_log_dir, "logs")
        setup_logging(log_dir=log_dir)

        logger = get_logger("test.debug")
        logger.debug("debug_event", key="value", count=42)

        log_file = os.path.join(log_dir, "backend.log")
        with open(log_file, "r") as f:
            lines = f.readlines()
            # Filter for our debug line (skip console echo line if present)
            debug_lines = [line for line in lines if "debug_event" in line]
            assert len(debug_lines) >= 1
            log_entry = json.loads(debug_lines[0])

        assert log_entry["event"] == "debug_event"
        assert log_entry["level"] == "debug"
        assert log_entry["key"] == "value"
        assert log_entry["count"] == 42
        assert "timestamp" in log_entry
        assert log_entry["logger"] == "test.debug"

    def test_info_level(self, temp_log_dir, clean_logging):
        """Test INFO level logging."""
        log_dir = os.path.join(temp_log_dir, "logs")
        setup_logging(log_dir=log_dir)

        logger = get_logger("test.info")
        logger.info("info_event", status="running", progress=0.5)

        log_file = os.path.join(log_dir, "backend.log")
        with open(log_file, "r") as f:
            lines = f.readlines()
            info_lines = [line for line in lines if "info_event" in line]
            log_entry = json.loads(info_lines[0])

        assert log_entry["event"] == "info_event"
        assert log_entry["level"] == "info"
        assert log_entry["status"] == "running"
        assert log_entry["progress"] == 0.5
        assert "timestamp" in log_entry
        assert log_entry["logger"] == "test.info"

    def test_warning_level(self, temp_log_dir, clean_logging):
        """Test WARNING level logging."""
        log_dir = os.path.join(temp_log_dir, "logs")
        setup_logging(log_dir=log_dir)

        logger = get_logger("test.warning")
        logger.warning("warning_event", message="API rate limit approaching", remaining=10)

        log_file = os.path.join(log_dir, "backend.log")
        with open(log_file, "r") as f:
            lines = f.readlines()
            warning_lines = [line for line in lines if "warning_event" in line]
            log_entry = json.loads(warning_lines[0])

        assert log_entry["event"] == "warning_event"
        assert log_entry["level"] == "warning"
        assert log_entry["message"] == "API rate limit approaching"
        assert log_entry["remaining"] == 10
        assert "timestamp" in log_entry

    def test_error_level(self, temp_log_dir, clean_logging):
        """Test ERROR level logging."""
        log_dir = os.path.join(temp_log_dir, "logs")
        setup_logging(log_dir=log_dir)

        logger = get_logger("test.error")
        logger.error("error_event", operation="fetch_data", ticker="AAPL")

        log_file = os.path.join(log_dir, "backend.log")
        with open(log_file, "r") as f:
            lines = f.readlines()
            error_lines = [line for line in lines if "error_event" in line]
            log_entry = json.loads(error_lines[0])

        assert log_entry["event"] == "error_event"
        assert log_entry["level"] == "error"
        assert log_entry["operation"] == "fetch_data"
        assert log_entry["ticker"] == "AAPL"
        assert "timestamp" in log_entry

    def test_critical_level(self, temp_log_dir, clean_logging):
        """Test CRITICAL level logging."""
        log_dir = os.path.join(temp_log_dir, "logs")
        setup_logging(log_dir=log_dir)

        logger = get_logger("test.critical")
        logger.critical("critical_event", reason="Database connection lost", attempt=3)

        log_file = os.path.join(log_dir, "backend.log")
        with open(log_file, "r") as f:
            lines = f.readlines()
            critical_lines = [line for line in lines if "critical_event" in line]
            log_entry = json.loads(critical_lines[0])

        assert log_entry["event"] == "critical_event"
        assert log_entry["level"] == "critical"
        assert log_entry["reason"] == "Database connection lost"
        assert log_entry["attempt"] == 3
        assert "timestamp" in log_entry


class TestExceptionLogging:
    """Test that ERROR and CRITICAL levels include full stack traces."""

    def test_error_with_exception(self, temp_log_dir, clean_logging):
        """Test ERROR level with exc_info=True includes stack trace."""
        log_dir = os.path.join(temp_log_dir, "logs")
        setup_logging(log_dir=log_dir)

        logger = get_logger("test.exception")

        # Generate an exception
        try:
            raise ValueError("Test exception for error level")
        except ValueError:
            logger.error("error_with_exception", exc_info=True, operation="test_operation")

        log_file = os.path.join(log_dir, "backend.log")
        with open(log_file, "r") as f:
            lines = f.readlines()
            error_lines = [line for line in lines if "error_with_exception" in line]
            log_entry = json.loads(error_lines[0])

        assert log_entry["event"] == "error_with_exception"
        assert log_entry["level"] == "error"
        assert "exception" in log_entry
        # Verify stack trace contains key elements
        assert "ValueError" in log_entry["exception"]
        assert "Test exception for error level" in log_entry["exception"]
        assert "Traceback" in log_entry["exception"]

    def test_critical_with_exception(self, temp_log_dir, clean_logging):
        """Test CRITICAL level with exc_info=True includes stack trace."""
        log_dir = os.path.join(temp_log_dir, "logs")
        setup_logging(log_dir=log_dir)

        logger = get_logger("test.exception")

        # Generate an exception
        try:
            raise RuntimeError("Critical system failure")
        except RuntimeError:
            logger.critical("critical_with_exception", exc_info=True, system="database")

        log_file = os.path.join(log_dir, "backend.log")
        with open(log_file, "r") as f:
            lines = f.readlines()
            critical_lines = [line for line in lines if "critical_with_exception" in line]
            log_entry = json.loads(critical_lines[0])

        assert log_entry["event"] == "critical_with_exception"
        assert log_entry["level"] == "critical"
        assert "exception" in log_entry
        assert "RuntimeError" in log_entry["exception"]
        assert "Critical system failure" in log_entry["exception"]
        assert "Traceback" in log_entry["exception"]

    def test_error_without_exc_info_no_exception_field(self, temp_log_dir, clean_logging):
        """Test ERROR without exc_info doesn't include exception field."""
        log_dir = os.path.join(temp_log_dir, "logs")
        setup_logging(log_dir=log_dir)

        logger = get_logger("test.no_exception")
        logger.error("error_without_exception", reason="Validation failed")

        log_file = os.path.join(log_dir, "backend.log")
        with open(log_file, "r") as f:
            lines = f.readlines()
            error_lines = [line for line in lines if "error_without_exception" in line]
            log_entry = json.loads(error_lines[0])

        assert log_entry["event"] == "error_without_exception"
        assert log_entry["level"] == "error"
        assert "exception" not in log_entry


class TestJSONFormat:
    """Test that log output is valid JSON with expected fields."""

    def test_valid_json_format(self, temp_log_dir, clean_logging):
        """Test that log entries are valid JSON."""
        log_dir = os.path.join(temp_log_dir, "logs")
        setup_logging(log_dir=log_dir)

        logger = get_logger("test.json")
        logger.info("json_test_event", field1="value1", field2=123, field3=True)

        log_file = os.path.join(log_dir, "backend.log")
        with open(log_file, "r") as f:
            lines = f.readlines()
            json_lines = [line for line in lines if "json_test_event" in line]
            # Should not raise JSONDecodeError
            log_entry = json.loads(json_lines[0])

        # Verify it's a dictionary with expected structure
        assert isinstance(log_entry, dict)
        assert "event" in log_entry
        assert "level" in log_entry
        assert "timestamp" in log_entry
        assert "logger" in log_entry

    def test_timestamp_format(self, temp_log_dir, clean_logging):
        """Test that timestamp is in ISO 8601 format."""
        log_dir = os.path.join(temp_log_dir, "logs")
        setup_logging(log_dir=log_dir)

        logger = get_logger("test.timestamp")
        logger.info("timestamp_test")

        log_file = os.path.join(log_dir, "backend.log")
        with open(log_file, "r") as f:
            lines = f.readlines()
            timestamp_lines = [line for line in lines if "timestamp_test" in line]
            log_entry = json.loads(timestamp_lines[0])

        # Verify timestamp format (ISO 8601 with timezone)
        timestamp = log_entry["timestamp"]
        # Should contain date separator and timezone indicator
        assert "T" in timestamp
        assert timestamp.endswith("Z") or "+" in timestamp or "-" in timestamp[-6:]

    def test_custom_fields_preserved(self, temp_log_dir, clean_logging):
        """Test that custom fields are preserved in JSON output."""
        log_dir = os.path.join(temp_log_dir, "logs")
        setup_logging(log_dir=log_dir)

        logger = get_logger("test.fields")
        logger.info(
            "custom_fields_test",
            run_id=12345,
            phase="acquisition",
            ticker="AAPL",
            confidence=0.85,
            is_active=True,
            metadata={"key": "value"}
        )

        log_file = os.path.join(log_dir, "backend.log")
        with open(log_file, "r") as f:
            lines = f.readlines()
            fields_lines = [line for line in lines if "custom_fields_test" in line]
            log_entry = json.loads(fields_lines[0])

        # Verify all custom fields are present with correct types
        assert log_entry["run_id"] == 12345
        assert log_entry["phase"] == "acquisition"
        assert log_entry["ticker"] == "AAPL"
        assert log_entry["confidence"] == 0.85
        assert log_entry["is_active"] is True
        assert log_entry["metadata"] == {"key": "value"}


class TestGetLogger:
    """Test get_logger() convenience function."""

    def test_get_logger_returns_bound_logger(self, temp_log_dir, clean_logging):
        """Test that get_logger returns a structlog logger that can log."""
        log_dir = os.path.join(temp_log_dir, "logs")
        setup_logging(log_dir=log_dir)

        logger = get_logger("test.get_logger")

        # The logger should have standard log methods
        assert hasattr(logger, 'debug')
        assert hasattr(logger, 'info')
        assert hasattr(logger, 'warning')
        assert hasattr(logger, 'error')
        assert hasattr(logger, 'critical')

        # Verify it can actually log
        logger.info("test_message")
        log_file = os.path.join(log_dir, "backend.log")
        assert os.path.exists(log_file)

    def test_get_logger_with_name(self, temp_log_dir, clean_logging):
        """Test that get_logger uses the provided name."""
        log_dir = os.path.join(temp_log_dir, "logs")
        setup_logging(log_dir=log_dir)

        logger_name = "test.named_logger"
        logger = get_logger(logger_name)
        logger.info("named_logger_test")

        log_file = os.path.join(log_dir, "backend.log")
        with open(log_file, "r") as f:
            lines = f.readlines()
            named_lines = [line for line in lines if "named_logger_test" in line]
            log_entry = json.loads(named_lines[0])

        assert log_entry["logger"] == logger_name

    def test_get_logger_without_name(self, temp_log_dir, clean_logging):
        """Test that get_logger works without a name."""
        log_dir = os.path.join(temp_log_dir, "logs")
        setup_logging(log_dir=log_dir)

        logger = get_logger()
        logger.info("unnamed_logger_test")

        log_file = os.path.join(log_dir, "backend.log")
        with open(log_file, "r") as f:
            lines = f.readlines()
            unnamed_lines = [line for line in lines if "unnamed_logger_test" in line]
            log_entry = json.loads(unnamed_lines[0])

        # Should have a logger field (root or None)
        assert "logger" in log_entry
