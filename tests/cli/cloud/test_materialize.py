from pathlib import Path
import textwrap

import httpx
import pytest
import yaml

from mcp_agent.cli.cloud.commands.deploy.materialize import (
    materialize_deployment_artifacts,
)


class FakeSecretsClient:
    def __init__(self):
        self.created = {}
        self.updated = {}

    async def create_secret(self, name, secret_type, value):
        handle = f"mcpac_sc_{name.replace('/', '_')}"
        self.created[name] = value
        return handle

    async def set_secret_value(self, handle, value):
        self.updated[handle] = value
        return True


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / "mcp_agent.config.yaml"
    cfg.write_text("name: sample-app\nenv:\n  - OPENAI_API_KEY\n", encoding="utf-8")
    return cfg


def test_materialize_creates_deployed_files(
    tmp_path: Path, config_file: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("OPENAI_API_KEY", "super-secret")
    secrets_client = FakeSecretsClient()
    deployed_secrets = tmp_path / "mcp_agent.deployed.secrets.yaml"

    deployed_config, deployed_secrets_path = materialize_deployment_artifacts(
        config_dir=tmp_path,
        app_id="app_123",
        config_file=config_file,
        deployed_secrets_path=deployed_secrets,
        secrets_client=secrets_client,
        non_interactive=True,
    )

    assert deployed_config.exists()
    assert deployed_secrets_path.exists()

    saved = yaml.safe_load(deployed_secrets_path.read_text(encoding="utf-8"))
    assert "env" in saved
    assert saved["env"][0]["OPENAI_API_KEY"].startswith("mcpac_sc_")
    assert secrets_client.created


def test_materialize_uses_fallback_value(tmp_path: Path):
    cfg = tmp_path / "mcp_agent.config.yaml"
    cfg.write_text(
        'env:\n  - {SUPABASE_URL: "https://example.com"}\n', encoding="utf-8"
    )
    secrets_client = FakeSecretsClient()
    deployed_secrets = tmp_path / "mcp_agent.deployed.secrets.yaml"

    materialize_deployment_artifacts(
        config_dir=tmp_path,
        app_id="app_456",
        config_file=cfg,
        deployed_secrets_path=deployed_secrets,
        secrets_client=secrets_client,
        non_interactive=True,
    )

    saved = yaml.safe_load(deployed_secrets.read_text(encoding="utf-8"))
    assert saved["env"][0]["SUPABASE_URL"].startswith("mcpac_sc_")
    assert (
        secrets_client.created["apps/app_456/env/SUPABASE_URL"] == "https://example.com"
    )


def test_materialize_reuses_existing_handles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    cfg = tmp_path / "mcp_agent.config.yaml"
    cfg.write_text("env:\n  - OPENAI_API_KEY\n", encoding="utf-8")
    existing_handle = "mcpac_sc_existing_handle"
    deployed_secrets = tmp_path / "mcp_agent.deployed.secrets.yaml"
    deployed_secrets.write_text(
        yaml.safe_dump({"env": [{"OPENAI_API_KEY": existing_handle}]}),
        encoding="utf-8",
    )

    class TrackingSecretsClient(FakeSecretsClient):
        async def create_secret(self, name, secret_type, value):  # pragma: no cover
            raise AssertionError("Should reuse existing handle")

    client = TrackingSecretsClient()
    monkeypatch.setenv("OPENAI_API_KEY", "fresh-secret")

    materialize_deployment_artifacts(
        config_dir=tmp_path,
        app_id="app_789",
        config_file=cfg,
        deployed_secrets_path=deployed_secrets,
        secrets_client=client,
        non_interactive=True,
    )

    assert client.updated[existing_handle] == "fresh-secret"


def test_materialize_recovers_from_deleted_handle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    cfg = tmp_path / "mcp_agent.config.yaml"
    cfg.write_text("env:\n  - OPENAI_API_KEY\n", encoding="utf-8")

    existing_handle = "mcpac_sc_existing_handle"
    deployed_secrets = tmp_path / "mcp_agent.deployed.secrets.yaml"
    deployed_secrets.write_text(
        yaml.safe_dump({"env": [{"OPENAI_API_KEY": existing_handle}]}),
        encoding="utf-8",
    )

    class DeletedHandleClient(FakeSecretsClient):
        async def set_secret_value(self, handle, value):
            response = httpx.Response(
                status_code=404,
                request=httpx.Request("POST", "https://example.com"),
                text="not found",
            )
            raise httpx.HTTPStatusError(
                "secret missing", request=response.request, response=response
            )

    client = DeletedHandleClient()
    monkeypatch.setenv("OPENAI_API_KEY", "fresh-secret")

    _, secrets_path = materialize_deployment_artifacts(
        config_dir=tmp_path,
        app_id="app_recover",
        config_file=cfg,
        deployed_secrets_path=deployed_secrets,
        secrets_client=client,
        non_interactive=True,
    )

    saved = yaml.safe_load(secrets_path.read_text(encoding="utf-8"))
    handle = saved["env"][0]["OPENAI_API_KEY"]
    assert handle != existing_handle


def test_materialize_skips_invalid_config(tmp_path: Path):
    cfg = tmp_path / "mcp_agent.config.yaml"
    cfg.write_text("invalid: [\n", encoding="utf-8")
    deployed_secrets = tmp_path / "mcp_agent.deployed.secrets.yaml"

    client = FakeSecretsClient()

    deployed_config_path, secrets_out = materialize_deployment_artifacts(
        config_dir=tmp_path,
        app_id="app_invalid",
        config_file=cfg,
        deployed_secrets_path=deployed_secrets,
        secrets_client=client,
        non_interactive=True,
    )

    assert deployed_config_path == cfg
    assert secrets_out.exists()
    assert yaml.safe_load(secrets_out.read_text(encoding="utf-8")) == {}


def test_materialize_prefers_app_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    cfg = tmp_path / "mcp_agent.config.yaml"
    cfg.write_text("name: from-config\n", encoding="utf-8")

    module_name = "main"
    main_path = tmp_path / f"{module_name}.py"
    main_path.write_text(
        textwrap.dedent(
            """
            from mcp_agent.app import MCPApp


            app = MCPApp()
            app.config.name = "from-app"
            """
        ),
        encoding="utf-8",
    )

    secrets_client = FakeSecretsClient()
    deployed_secrets = tmp_path / "mcp_agent.deployed.secrets.yaml"

    deployed_config_path, _ = materialize_deployment_artifacts(
        config_dir=tmp_path,
        app_id="app_appconfig",
        config_file=cfg,
        deployed_secrets_path=deployed_secrets,
        secrets_client=secrets_client,
        non_interactive=True,
    )

    realized = yaml.safe_load(deployed_config_path.read_text(encoding="utf-8"))
    assert realized["name"] == "from-app"


def test_deployed_config_redacts_secrets(tmp_path: Path):
    cfg = tmp_path / "mcp_agent.config.yaml"
    cfg.write_text(
        textwrap.dedent(
            """
            openai:
              api_key: "${oc.env:OPENAI_API_KEY}"
              default_model: gpt-4o
            """
        ),
        encoding="utf-8",
    )

    raw_secrets = tmp_path / "mcp_agent.secrets.yaml"
    raw_secrets.write_text("openai:\n  api_key: sk-live\n", encoding="utf-8")

    deployed_secrets = tmp_path / "mcp_agent.deployed.secrets.yaml"
    deployed_secrets.write_text(
        yaml.safe_dump({"openai": {"api_key": "mcpac_sc_handle"}}),
        encoding="utf-8",
    )

    secrets_client = FakeSecretsClient()
    deployed_config_path, _ = materialize_deployment_artifacts(
        config_dir=tmp_path,
        app_id="app_redact",
        config_file=cfg,
        deployed_secrets_path=deployed_secrets,
        secrets_client=secrets_client,
        non_interactive=True,
    )

    realized = yaml.safe_load(deployed_config_path.read_text(encoding="utf-8"))
    assert realized["openai"]["api_key"] == "${oc.env:OPENAI_API_KEY}"
    assert realized["openai"]["default_model"] == "gpt-4o"
    assert "sk-live" not in deployed_config_path.read_text(encoding="utf-8")


def test_deployed_config_omits_secret_only_nodes(tmp_path: Path):
    cfg = tmp_path / "mcp_agent.config.yaml"
    cfg.write_text("name: sample-app\n", encoding="utf-8")

    raw_secrets = tmp_path / "mcp_agent.secrets.yaml"
    raw_secrets.write_text("notion:\n  api_key: top-secret\n", encoding="utf-8")

    deployed_secrets = tmp_path / "mcp_agent.deployed.secrets.yaml"
    deployed_secrets.write_text(
        yaml.safe_dump({"notion": {"api_key": "mcpac_sc_handle"}}),
        encoding="utf-8",
    )

    secrets_client = FakeSecretsClient()
    deployed_config_path, _ = materialize_deployment_artifacts(
        config_dir=tmp_path,
        app_id="app_secret_nodes",
        config_file=cfg,
        deployed_secrets_path=deployed_secrets,
        secrets_client=secrets_client,
        non_interactive=True,
    )

    realized = yaml.safe_load(deployed_config_path.read_text(encoding="utf-8"))
    assert "notion" not in realized
    assert realized["name"] == "sample-app"


def test_deployed_config_omits_secret_only_nested_env(tmp_path: Path):
    cfg = tmp_path / "mcp_agent.config.yaml"
    cfg.write_text(
        textwrap.dedent(
            """
            name: sample-app
            mcp:
              servers:
                fetch:
                  command: uvx
                  args: ["mcp-server-fetch"]
            """
        ),
        encoding="utf-8",
    )

    raw_secrets = tmp_path / "mcp_agent.secrets.yaml"
    raw_secrets.write_text(
        textwrap.dedent(
            """
            mcp:
              servers:
                slack:
                  env:
                    SLACK_BOT_TOKEN: token
            """
        ),
        encoding="utf-8",
    )

    deployed_secrets = tmp_path / "mcp_agent.deployed.secrets.yaml"
    deployed_secrets.write_text(
        yaml.safe_dump(
            {
                "mcp": {
                    "servers": {
                        "slack": {
                            "env": {
                                "SLACK_BOT_TOKEN": "mcpac_sc_handle",
                            }
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    secrets_client = FakeSecretsClient()
    deployed_config_path, _ = materialize_deployment_artifacts(
        config_dir=tmp_path,
        app_id="app_nested_env",
        config_file=cfg,
        deployed_secrets_path=deployed_secrets,
        secrets_client=secrets_client,
        non_interactive=True,
    )

    realized = yaml.safe_load(deployed_config_path.read_text(encoding="utf-8"))
    servers = realized["mcp"]["servers"]
    assert "slack" not in servers
    assert "fetch" in servers


def test_deployed_config_preserves_env_declarations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    cfg = tmp_path / "mcp_agent.config.yaml"
    cfg.write_text(
        textwrap.dedent(
            """
            env:
              - OPENAI_API_KEY
              - {SUPABASE_URL: "https://db.example.com"}
            """
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    monkeypatch.delenv("SUPABASE_URL", raising=False)

    secrets_client = FakeSecretsClient()
    deployed_secrets = tmp_path / "mcp_agent.deployed.secrets.yaml"

    deployed_config_path, _ = materialize_deployment_artifacts(
        config_dir=tmp_path,
        app_id="app_env_preserve",
        config_file=cfg,
        deployed_secrets_path=deployed_secrets,
        secrets_client=secrets_client,
        non_interactive=True,
    )

    realized = yaml.safe_load(deployed_config_path.read_text(encoding="utf-8"))
    assert realized["env"] == [
        "OPENAI_API_KEY",
        {"SUPABASE_URL": "https://db.example.com"},
    ]
