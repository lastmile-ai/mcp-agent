from pathlib import Path

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


def test_materialize_skips_invalid_config(tmp_path: Path):
    cfg = tmp_path / "mcp_agent.config.yaml"
    cfg.write_text("invalid: [\n", encoding="utf-8")
    deployed_secrets = tmp_path / "mcp_agent.deployed.secrets.yaml"

    client = FakeSecretsClient()

    config_out, secrets_out = materialize_deployment_artifacts(
        config_dir=tmp_path,
        app_id="app_invalid",
        config_file=cfg,
        deployed_secrets_path=deployed_secrets,
        secrets_client=client,
        non_interactive=True,
    )

    assert config_out == cfg
    assert secrets_out.exists()
    assert yaml.safe_load(secrets_out.read_text(encoding="utf-8")) == {}
