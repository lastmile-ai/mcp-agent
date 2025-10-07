import yaml
from mcp_agent.registry.loader import load_tools_yaml

def test_parse_tools_yaml_list():
    data = {"tools": [{"name":"x","base_url":"http://x:1","version":"1.0.0"}]}
    # emulate reading from file by writing to a temp file
    import pathlib
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d)/"tools.yaml"
        p.write_text(yaml.safe_dump(data))
        out = load_tools_yaml(str(p))
    assert out and out[0]["name"] == "x" and out[0]["base_url"].startswith("http://x")
