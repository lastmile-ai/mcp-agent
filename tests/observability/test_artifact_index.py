from mcp_agent.artifacts.index import ArtifactIndex


def test_build_index(tmp_path):
    idx = ArtifactIndex(root=tmp_path)
    idx.persist_bytes("run-1", "run-summary.json", b"{}", media_type="application/json")
    idx.persist_bytes("run-1", "diffs/patch.diff", b"--- a\n+++ b", media_type="text/plain")

    index = idx.build_index("run-1")
    assert index["run_id"] == "run-1"
    names = {entry["name"] for entry in index["artifacts"]}
    assert "run-summary.json" in names
    assert "diffs/patch.diff" in names

    data, media_type = idx.get_artifact("run-1", "run-summary.json")
    assert data == b"{}"
    assert media_type == "application/json"

