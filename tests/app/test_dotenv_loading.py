import os

from mcp_agent.app import MCPApp
from mcp_agent.config import Settings


def test_apply_environment_bindings_loads_dotenv_files(tmp_path, monkeypatch):
    env_file = tmp_path / ".env.mcp-cloud"
    env_file.write_text("MY_SECRET=from-dotenv\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MY_SECRET", raising=False)

    settings = Settings(env=["MY_SECRET"])
    app = MCPApp(settings=settings)
    app._apply_environment_bindings()

    assert os.environ["MY_SECRET"] == "from-dotenv"
    monkeypatch.delenv("MY_SECRET", raising=False)


def test_local_env_takes_precedence_over_cloud(monkeypatch, tmp_path):
    dot_env = tmp_path / ".env"
    dot_env.write_text("MY_SECRET=local-value\n", encoding="utf-8")
    cloud_env = tmp_path / ".env.mcp-cloud"
    cloud_env.write_text("MY_SECRET=cloud-value\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MY_SECRET", raising=False)

    settings = Settings(env=["MY_SECRET"])
    app = MCPApp(settings=settings)
    app._apply_environment_bindings()

    assert os.environ["MY_SECRET"] == "local-value"
    monkeypatch.delenv("MY_SECRET", raising=False)


def test_config_fallback_overrides_existing_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "original")
    settings = Settings(env=[{"SUPABASE_URL": "https://fallback.example"}])
    app = MCPApp(settings=settings)
    app._apply_environment_bindings()

    assert os.environ["SUPABASE_URL"] == "https://fallback.example"
    monkeypatch.delenv("SUPABASE_URL", raising=False)
