from datetime import datetime, timezone

import pytest

from mcp_agent.audit.store import AuditRecord, AuditStore


def test_write_and_iter(tmp_path):
    store = AuditStore(root=tmp_path, enabled=True)
    record = AuditRecord(
        ts=datetime(2024, 1, 1, tzinfo=timezone.utc),
        run_id="run-1",
        trace_id="abc",
        actor="system",
        action="LLM_CALL",
        target="llm",
        params_hash="deadbeef",
        outcome="success",
        error_code=None,
    )
    store.write(record)
    rows = store.iter_records("run-1")
    assert len(rows) == 1
    assert rows[0]["action"] == "LLM_CALL"
    assert rows[0]["params_hash"] == "deadbeef"


def test_invalid_actor_rejected(tmp_path):
    store = AuditStore(root=tmp_path, enabled=True)
    record = AuditRecord(run_id="run-1", trace_id="abc", actor="invalid", action="TEST_RUN")
    with pytest.raises(ValueError):
        store.write(record)

