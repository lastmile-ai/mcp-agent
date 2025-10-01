from mcp_agent.middleware.redact import redact_text

def test_redacts_common_tokens():
    s = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc"
    out = redact_text(s)
    assert "[REDACTED]" in out
    s2 = "Authorization: token ghp_abcdefghijklmnopqrstuvwxyz"
    out2 = redact_text(s2)
    assert "[REDACTED]" in out2
