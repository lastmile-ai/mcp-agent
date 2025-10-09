import json
from importlib import import_module
from pathlib import Path

Manifest = import_module("mcp_agent.context.models").Manifest  # lazy import


def test_schema_matches_model():
    schema_path = Path(__file__).parents[2] / "schema" / "context.manifest.schema.json"
    with open(schema_path, "r", encoding="utf-8") as f:
        on_disk = json.load(f)
    generated = Manifest.model_json_schema()
    # Compare a few stable, meaningful keys rather than exact dict
    assert on_disk.get("title") == generated.get("title")
    assert "properties" in on_disk and "properties" in generated
    assert set(on_disk["properties"].keys()) == set(generated["properties"].keys())


def test_manifest_roundtrip():
    m = Manifest(slices=[], meta={})
    blob = m.model_dump_json()
    m2 = Manifest.model_validate_json(blob)
    assert m2.meta.created_at  # auto-populated
