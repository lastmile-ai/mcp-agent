import pytest

from mcp_agent.config import get_settings, _clear_global_settings


class TestConfigEnvAliases:
    @pytest.fixture(autouse=True)
    def clear_settings(self):
        _clear_global_settings()

    @pytest.fixture(autouse=True)
    def isolate_env(self, monkeypatch):
        # Clear potential colliding env vars across providers
        for key in [
            # OpenAI
            "OPENAI_API_KEY",
            "OPENAI__API_KEY",
            "openai__api_key",
            # Anthropic
            "ANTHROPIC_API_KEY",
            "ANTHROPIC__API_KEY",
            "anthropic__api_key",
            "ANTHROPIC__PROVIDER",
            # Azure
            "AZURE_OPENAI_API_KEY",
            "AZURE_AI_API_KEY",
            "AZURE__API_KEY",
            "azure__api_key",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_AI_ENDPOINT",
            "AZURE__ENDPOINT",
            "azure__endpoint",
            # Google
            "GOOGLE_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE__API_KEY",
            "google__api_key",
            # Bedrock
            "AWS_ACCESS_KEY_ID",
            "bedrock__aws_access_key_id",
            "AWS_SECRET_ACCESS_KEY",
            "bedrock__aws_secret_access_key",
            "AWS_SESSION_TOKEN",
            "bedrock__aws_session_token",
            "AWS_REGION",
            "bedrock__aws_region",
            "AWS_PROFILE",
            "bedrock__profile",
            "BEDROCK__AWS_ACCESS_KEY_ID",
            "BEDROCK__AWS_SECRET_ACCESS_KEY",
            "BEDROCK__AWS_SESSION_TOKEN",
            "BEDROCK__AWS_REGION",
            "BEDROCK__PROFILE",
        ]:
            monkeypatch.delenv(key, raising=False)

    @pytest.mark.parametrize("env_name", ["OPENAI_API_KEY", "OPENAI__API_KEY"])
    def test_openai_api_key_env_variants(self, monkeypatch, env_name):
        value = "sk-openai-env"
        monkeypatch.setenv(env_name, value)
        settings = get_settings()
        assert settings.openai is not None
        assert getattr(settings.openai, "api_key") == value

    @pytest.mark.parametrize("env_name", ["ANTHROPIC_API_KEY", "ANTHROPIC__API_KEY"])
    def test_anthropic_api_key_env_variants(self, monkeypatch, env_name):
        value = "sk-anthropic-env"
        monkeypatch.setenv(env_name, value)
        settings = get_settings()
        assert settings.anthropic is not None
        assert getattr(settings.anthropic, "api_key") == value

    @pytest.mark.parametrize(
        "env_name",
        ["AZURE_OPENAI_API_KEY", "AZURE_AI_API_KEY", "AZURE__API_KEY"],
    )
    def test_azure_api_key_env_variants(self, monkeypatch, env_name):
        value = "az-key-env"
        monkeypatch.setenv(env_name, value)
        settings = get_settings()
        assert settings.azure is not None
        assert getattr(settings.azure, "api_key") == value

    @pytest.mark.parametrize(
        "env_name",
        ["AZURE_OPENAI_ENDPOINT", "AZURE_AI_ENDPOINT", "AZURE__ENDPOINT"],
    )
    def test_azure_endpoint_env_variants(self, monkeypatch, env_name):
        value = "https://azure.example"
        monkeypatch.setenv(env_name, value)
        settings = get_settings()
        assert settings.azure is not None
        assert getattr(settings.azure, "endpoint") == value

    @pytest.mark.parametrize(
        "env_name",
        ["GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE__API_KEY"],
    )
    def test_google_api_key_env_variants(self, monkeypatch, env_name):
        value = "g-api-env"
        monkeypatch.setenv(env_name, value)
        settings = get_settings()
        assert settings.google is not None
        assert getattr(settings.google, "api_key") == value

    @pytest.mark.parametrize(
        "env_name, attr, value",
        [
            ("AWS_ACCESS_KEY_ID", "aws_access_key_id", "AKIA_ENV"),
            ("AWS_SECRET_ACCESS_KEY", "aws_secret_access_key", "SECRET_ENV"),
            ("AWS_SESSION_TOKEN", "aws_session_token", "TOKEN_ENV"),
            ("AWS_REGION", "aws_region", "us-east-1"),
            ("AWS_PROFILE", "profile", "dev"),
        ],
    )
    def test_bedrock_flat_env(self, monkeypatch, env_name, attr, value):
        monkeypatch.setenv(env_name, value)
        settings = get_settings()
        assert settings.bedrock is not None
        assert getattr(settings.bedrock, attr) == value

    def test_aliases_from_yaml_preload(self, monkeypatch):
        yaml_payload = """
openai:
  OPENAI_API_KEY: sk-openai-yaml
anthropic:
  ANTHROPIC_API_KEY: sk-anthropic-yaml
azure:
  AZURE_OPENAI_API_KEY: az-key-yaml
  AZURE_OPENAI_ENDPOINT: https://azure.openai.example
google:
  GEMINI_API_KEY: g-api-gemini-yaml
bedrock:
  AWS_ACCESS_KEY_ID: AKIA_YAML
  AWS_SECRET_ACCESS_KEY: SECRET_YAML
  AWS_SESSION_TOKEN: TOKEN_YAML
  AWS_REGION: us-east-2
  AWS_PROFILE: default
"""
        monkeypatch.setenv("MCP_APP_SETTINGS_PRELOAD", yaml_payload)
        settings = get_settings()
        assert (
            settings.openai and getattr(settings.openai, "api_key") == "sk-openai-yaml"
        )
        assert (
            settings.anthropic
            and getattr(settings.anthropic, "api_key") == "sk-anthropic-yaml"
        )
        assert settings.azure and getattr(settings.azure, "api_key") == "az-key-yaml"
        assert getattr(settings.azure, "endpoint") == "https://azure.openai.example"
        assert (
            settings.google
            and getattr(settings.google, "api_key") == "g-api-gemini-yaml"
        )
        assert (
            settings.bedrock
            and getattr(settings.bedrock, "aws_access_key_id") == "AKIA_YAML"
        )
        assert getattr(settings.bedrock, "aws_secret_access_key") == "SECRET_YAML"
        assert getattr(settings.bedrock, "aws_session_token") == "TOKEN_YAML"
        assert getattr(settings.bedrock, "aws_region") == "us-east-2"
        assert getattr(settings.bedrock, "profile") == "default"

    def test_preload_yaml_overrides_env(self, monkeypatch):
        # Even when env is set, YAML (preload) wins for that provider
        monkeypatch.setenv("OPENAI_API_KEY", "env-openai")
        yaml_payload = """
openai:
  api_key: yaml-openai
"""
        monkeypatch.setenv("MCP_APP_SETTINGS_PRELOAD", yaml_payload)
        settings = get_settings()
        assert getattr(settings.openai, "api_key") == "yaml-openai"

    def test_yaml_used_when_env_missing_value(self, monkeypatch):
        yaml_payload = """
    openai:
      api_key: yaml-openai
    """
        monkeypatch.setenv("MCP_APP_SETTINGS_PRELOAD", yaml_payload)
        settings = get_settings()
        assert getattr(settings.openai, "api_key") == "yaml-openai"

        # Now set ENV
        monkeypatch.setenv("OPENAI_API_KEY", "env-openai")
        settings = get_settings()
        # Preload remains authoritative; env should not override when preload is set
        assert getattr(settings.openai, "api_key") == "yaml-openai"

    def test_env_vs_secrets_yaml_precedence(self, monkeypatch):
        # Simulate having a config + secrets file loaded by injecting preload as those mappings
        yaml_payload = """
openai:
  api_key: yaml-openai
anthropic:
  api_key: yaml-claude
"""
        monkeypatch.setenv("MCP_APP_SETTINGS_PRELOAD", yaml_payload)

        # Without env, values come from YAML
        settings = get_settings()
        assert getattr(settings.openai, "api_key") == "yaml-openai"
        assert getattr(settings.anthropic, "api_key") == "yaml-claude"

        # Now set env and ensure it overrides YAML when preload is NOT set
        monkeypatch.delenv("MCP_APP_SETTINGS_PRELOAD", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "env-openai")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "env-claude")
        _clear_global_settings()
        settings = get_settings()
        assert getattr(settings.openai, "api_key") == "env-openai"
        assert getattr(settings.anthropic, "api_key") == "env-claude"

    def test_dotenv_loading_from_cwd(self, monkeypatch, tmp_path):
        # Create a temp project with a .env
        proj = tmp_path / "proj"
        proj.mkdir()
        env_file = proj / ".env"
        env_file.write_text(
            "OPENAI_API_KEY=dotenv-openai\nANTHROPIC_API_KEY=dotenv-claude\n"
        )

        # Change working directory
        monkeypatch.chdir(proj)
        _clear_global_settings()
        settings = get_settings()
        assert getattr(settings.openai, "api_key") == "dotenv-openai"
        assert getattr(settings.anthropic, "api_key") == "dotenv-claude"

    def test_nested_and_flat_env_compat(self, monkeypatch):
        # Flat env
        monkeypatch.setenv("OPENAI_API_KEY", "flat-openai")
        # Nested style via env_nested_delimiter at top level
        monkeypatch.setenv("ANTHROPIC__API_KEY", "nested-claude")
        _clear_global_settings()
        settings = get_settings()
        assert getattr(settings.openai, "api_key") == "flat-openai"
        assert getattr(settings.anthropic, "api_key") == "nested-claude"

    def test_anthropic_provider_bedrock_via_nested_env(self, monkeypatch):
        # Verify nested env path sets provider and AWS creds on Anthropic settings
        monkeypatch.setenv("ANTHROPIC__PROVIDER", "bedrock")
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA_TEST")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "SECRET_TEST")
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        settings = get_settings()
        assert getattr(settings.anthropic, "provider") == "bedrock"
        assert getattr(settings.anthropic, "aws_access_key_id") == "AKIA_TEST"
        assert getattr(settings.anthropic, "aws_secret_access_key") == "SECRET_TEST"
        assert getattr(settings.anthropic, "aws_region") == "us-east-1"
