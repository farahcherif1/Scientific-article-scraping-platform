import json
import logging
import sys

from app.infra.logging import JsonFormatter, configure_logging


def test_json_formatter_includes_standard_and_extra_fields():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="app.infra.retries",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request_completed",
        args=(),
        exc_info=None,
    )
    record.source = "openalex"
    record.keyword = "ai"
    record.duration_s = 0.42

    output = json.loads(formatter.format(record))

    assert output["level"] == "INFO"
    assert output["logger"] == "app.infra.retries"
    assert output["message"] == "request_completed"
    assert output["source"] == "openalex"
    assert output["keyword"] == "ai"
    assert output["duration_s"] == 0.42


def test_json_formatter_serializes_exception_info():
    formatter = JsonFormatter()
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        record = logging.LogRecord(
            name="app.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="request_failed",
            args=(),
            exc_info=sys.exc_info(),
        )

    output = json.loads(formatter.format(record))
    assert "RuntimeError: boom" in output["exc_info"]


def test_configure_logging_installs_json_formatter_on_root():
    configure_logging("DEBUG")
    try:
        root = logging.getLogger()
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, JsonFormatter)
        assert root.level == logging.DEBUG
    finally:
        configure_logging("INFO")  # don't leak DEBUG level into other tests
