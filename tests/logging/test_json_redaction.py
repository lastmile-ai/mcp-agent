from mcp_agent.logging.json_serializer import JSONSerializer

def test_redacts_authorization_and_github_token():
    s = JSONSerializer()
    data = {"Authorization": "Bearer secret123", "github_token": "ghs_abc", "ok": "v"}
    out = s.serialize(data)
    # Should keep keys but redact values
    assert "Authorization" in out and out["Authorization"] != "Bearer secret123"
    assert "github_token" in out and out["github_token"] != "ghs_abc"
    assert out["ok"] == "v"
