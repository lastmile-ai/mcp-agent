import io
import logging
import importlib


def _fresh_redact_module(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "super-secret")
    from mcp_agent.logging import redact as redact_module

    importlib.reload(redact_module)
    return redact_module


def test_redaction_hides_secrets(monkeypatch):
    redact = _fresh_redact_module(monkeypatch)
    logger = logging.getLogger("test_redaction")
    logger.handlers = []
    logger.setLevel(logging.INFO)
    logger.propagate = False
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger.addHandler(handler)
    redact.install_redaction_filter(logger)

    logger.info("token=%s", "super-secret")
    handler.flush()
    output = stream.getvalue()
    assert "super-secret" not in output
    assert redact.REDACTED in output


def test_redaction_masks_authorization_header(monkeypatch):
    redact = _fresh_redact_module(monkeypatch)
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg="Authorization: Bearer abc123",
        args=(),
        exc_info=None,
    )
    flt = redact.RedactionFilter()
    assert flt.filter(record)
    assert "abc123" not in record.msg
    assert record.msg.strip().endswith(redact.REDACTED)

