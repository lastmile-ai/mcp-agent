import os

from pydantic_yaml import to_yaml_str
import pytest

from mcp_agent.config import (
    Settings,
    LoggerSettings,
    MCPSettings,
    MCPServerSettings,
    OpenAISettings,
    AnthropicSettings,
    get_settings,
    _clear_global_settings,
)  # pylint: disable=import-private-name

_EXAMPLE_SETTINGS = Settings(
    execution_engine="asyncio",
    logger=LoggerSettings(type="file", level="debug"),
    mcp=MCPSettings(
        servers={
            "fetch": MCPServerSettings(
                command="uvx",
                args=["mcp-server-fetch"],
            ),
            "filesystem": MCPServerSettings(
                command="npx",
                args=["-y", "@modelcontextprotocol/server-filesystem"],
            ),
        }
    ),
    openai=OpenAISettings(
        api_key="sk-my-openai-api-key",
    ),
    anthropic=AnthropicSettings(
        api_key="sk-my-anthropic-api-key",
    ),
)


class TestConfigPreload:
    @pytest.fixture(autouse=True)
    def clear_global_settings(self):
        _clear_global_settings()

    @pytest.fixture(autouse=True)
    def clear_test_env(self):
        yield
        if "MCP_APP_SETTINGS_PRELOAD" in os.environ:
            del os.environ["MCP_APP_SETTINGS_PRELOAD"]
        if "MCP_APP_SETTINGS_PRELOAD_STRICT" in os.environ:
            del os.environ["MCP_APP_SETTINGS_PRELOAD_STRICT"]

    @pytest.fixture(scope="session")
    def example_settings(self):
        return _EXAMPLE_SETTINGS

    @pytest.fixture(scope="function")
    def settings_env(self, example_settings: Settings):
        settings_str = to_yaml_str(example_settings)
        os.environ["MCP_APP_SETTINGS_PRELOAD"] = settings_str

    def test_config_preload(self, example_settings: Settings, settings_env):
        assert os.environ.get("MCP_APP_SETTINGS_PRELOAD")
        loaded_settings = get_settings()
        assert loaded_settings == example_settings

    def test_config_preload_override(self, example_settings: Settings, settings_env):
        assert os.environ.get("MCP_APP_SETTINGS_PRELOAD")
        loaded_settings = get_settings("./fake_path/mcp-agent.config.yaml")
        assert loaded_settings == example_settings

    # Invalid string value with lenient parsing
    @pytest.fixture(scope="function")
    def invalid_settings_env(self):
        os.environ["MCP_APP_SETTINGS_PRELOAD"] = """
            badsadwewqeqr231232321
        """

    def test_config_preload_invalid_lenient(self, invalid_settings_env):
        assert os.environ.get("MCP_APP_SETTINGS_PRELOAD")
        assert os.environ.get("MCP_APP_SETTINGS_PRELOAD_STRICT") is None
        loaded_settings = get_settings()
        assert loaded_settings

    @pytest.fixture(scope="function")
    def strict_parsing_env(self):
        os.environ["MCP_APP_SETTINGS_PRELOAD_STRICT"] = "true"

    def test_config_preload_invalid_throws(
        self, invalid_settings_env, strict_parsing_env
    ):
        assert os.environ.get("MCP_APP_SETTINGS_PRELOAD")
        assert os.environ.get("MCP_APP_SETTINGS_PRELOAD_STRICT") == "true"
        with pytest.raises(ValueError):
            get_settings()
