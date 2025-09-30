import os
import threading
import warnings
from unittest.mock import patch

from pydantic_yaml import to_yaml_str
import pytest
import yaml

import mcp_agent.config
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
    def clear_test_env(self, monkeypatch: pytest.MonkeyPatch):
        # Ensure a clean env before each test
        monkeypatch.delenv("MCP_APP_SETTINGS_PRELOAD", raising=False)
        monkeypatch.delenv("MCP_APP_SETTINGS_PRELOAD_STRICT", raising=False)

    @pytest.fixture(scope="session")
    def example_settings(self):
        return _EXAMPLE_SETTINGS

    @pytest.fixture(scope="function")
    def settings_env(self, example_settings: Settings, monkeypatch: pytest.MonkeyPatch):
        settings_str = to_yaml_str(example_settings)
        monkeypatch.setenv("MCP_APP_SETTINGS_PRELOAD", settings_str)

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
    def invalid_settings_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv(
            "MCP_APP_SETTINGS_PRELOAD",
            """
            badsadwewqeqr231232321
        """,
        )

    def test_config_preload_invalid_lenient(self, invalid_settings_env):
        assert os.environ.get("MCP_APP_SETTINGS_PRELOAD")
        assert os.environ.get("MCP_APP_SETTINGS_PRELOAD_STRICT") is None
        loaded_settings = get_settings()
        assert loaded_settings

    @pytest.fixture(scope="function")
    def strict_parsing_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("MCP_APP_SETTINGS_PRELOAD_STRICT", "true")

    def test_config_preload_invalid_throws(
        self, invalid_settings_env, strict_parsing_env
    ):
        assert os.environ.get("MCP_APP_SETTINGS_PRELOAD")
        assert os.environ.get("MCP_APP_SETTINGS_PRELOAD_STRICT") == "true"
        with pytest.raises(ValueError):
            get_settings()


class TestSetGlobalParameter:
    """Test suite for the set_global parameter in get_settings()."""

    @pytest.fixture(autouse=True)
    def clear_global_settings(self):
        """Clear global settings before and after each test."""
        _clear_global_settings()
        yield
        _clear_global_settings()

    @pytest.fixture(autouse=True)
    def clear_test_env(self, monkeypatch: pytest.MonkeyPatch):
        """Ensure a clean environment before each test."""
        monkeypatch.delenv("MCP_APP_SETTINGS_PRELOAD", raising=False)
        monkeypatch.delenv("MCP_APP_SETTINGS_PRELOAD_STRICT", raising=False)

    @pytest.fixture
    def sample_config(self):
        """Create a sample configuration dictionary."""
        return {
            "execution_engine": "asyncio",
            "logger": {
                "type": "console",
                "level": "info",
            },
            "mcp": {
                "servers": {
                    "test_server": {
                        "command": "python",
                        "args": ["-m", "test_server"],
                    }
                }
            },
        }

    def test_default_sets_global_state(self, sample_config):
        """Test that get_settings() with default parameters sets global state."""
        # Verify global settings is None initially
        assert mcp_agent.config._settings is None

        # Mock file operations
        yaml_content = yaml.dump(sample_config)
        config_path = "/fake/path/config.yaml"

        with patch("mcp_agent.config._check_file_exists", return_value=True):
            with patch(
                "mcp_agent.config._read_file_content", return_value=yaml_content
            ):
                # Load settings with default behavior
                settings = get_settings(config_path=config_path)

                # Verify global state was set
                assert mcp_agent.config._settings is not None
                assert mcp_agent.config._settings == settings
                assert settings.execution_engine == "asyncio"

    def test_set_global_false_no_global_state(self, sample_config):
        """Test that set_global=False doesn't modify global state."""
        assert mcp_agent.config._settings is None

        yaml_content = yaml.dump(sample_config)
        config_path = "/fake/path/config.yaml"

        with patch("mcp_agent.config._check_file_exists", return_value=True):
            with patch(
                "mcp_agent.config._read_file_content", return_value=yaml_content
            ):
                settings = get_settings(config_path=config_path, set_global=False)

                # Global state should remain None
                assert mcp_agent.config._settings is None
                # But we should still get valid settings
                assert settings is not None
                assert settings.execution_engine == "asyncio"

    def test_explicit_set_global_true(self, sample_config):
        """Test explicitly passing set_global=True."""
        assert mcp_agent.config._settings is None

        yaml_content = yaml.dump(sample_config)
        config_path = "/fake/path/config.yaml"

        with patch("mcp_agent.config._check_file_exists", return_value=True):
            with patch(
                "mcp_agent.config._read_file_content", return_value=yaml_content
            ):
                settings = get_settings(config_path=config_path, set_global=True)

                assert mcp_agent.config._settings is not None
                assert mcp_agent.config._settings == settings

    def test_returns_cached_global_when_set(self, sample_config):
        """Test that subsequent calls return cached global settings."""
        yaml_content = yaml.dump(sample_config)
        config_path = "/fake/path/config.yaml"

        with patch("mcp_agent.config._check_file_exists", return_value=True):
            with patch(
                "mcp_agent.config._read_file_content", return_value=yaml_content
            ):
                # First call sets global state
                settings1 = get_settings(config_path=config_path)

                # Second call without path should return cached global
                settings2 = get_settings()

                # They should be the same object
                assert settings1 is settings2
                assert mcp_agent.config._settings is settings1

    def test_no_cached_return_when_set_global_false(self, sample_config):
        """Test that set_global=False always loads fresh settings."""
        yaml_content = yaml.dump(sample_config)
        config_path = "/fake/path/config.yaml"

        with patch("mcp_agent.config._check_file_exists", return_value=True):
            with patch(
                "mcp_agent.config._read_file_content", return_value=yaml_content
            ):
                # First call with set_global=False
                settings1 = get_settings(config_path=config_path, set_global=False)

                # Second call with set_global=False
                settings2 = get_settings(config_path=config_path, set_global=False)

                # They should be different objects (not cached)
                assert settings1 is not settings2
                # But have the same content
                assert settings1 == settings2
                # Global should remain None
                assert mcp_agent.config._settings is None

    def test_preload_with_set_global_false(self, sample_config, monkeypatch):
        """Test preload configuration with set_global=False."""
        settings_str = to_yaml_str(Settings(**sample_config))
        monkeypatch.setenv("MCP_APP_SETTINGS_PRELOAD", settings_str)

        settings = get_settings(set_global=False)

        # Global state should not be set
        assert mcp_agent.config._settings is None

        # Settings should be loaded from preload
        assert settings is not None
        assert settings.execution_engine == "asyncio"

    def test_explicit_config_path_with_cache_returns_cached(self, sample_config):
        """Test that explicit config_path still returns cached settings when global cache exists."""
        # First config with different values
        initial_config = {
            "execution_engine": "asyncio",
            "logger": {
                "type": "console",
                "level": "info",
            },
        }

        # Second config with different values (won't be loaded due to cache)
        updated_config = {
            "execution_engine": "temporal",  # Different value (valid option)
            "logger": {
                "type": "file",  # Different value
                "level": "debug",  # Different value
            },
        }

        initial_yaml = yaml.dump(initial_config)
        updated_yaml = yaml.dump(updated_config)

        # First load to set global cache with initial config
        with patch("mcp_agent.config._check_file_exists", return_value=True):
            with patch(
                "mcp_agent.config._read_file_content", return_value=initial_yaml
            ):
                settings1 = get_settings(config_path="/fake/path/initial.yaml")
                assert settings1.execution_engine == "asyncio"
                assert settings1.logger.type == "console"
                assert settings1.logger.level == "info"
                assert mcp_agent.config._settings == settings1

        # Second call without config_path should return cached settings
        settings2 = get_settings()
        assert settings2 is settings1
        assert settings2.execution_engine == "asyncio"

        # Third call with different config_path still returns cached settings (current behavior)
        with patch("mcp_agent.config._check_file_exists", return_value=True):
            with patch(
                "mcp_agent.config._read_file_content", return_value=updated_yaml
            ):
                settings3 = get_settings(config_path="/fake/path/updated.yaml")
                # Still returns cached settings, not the new config
                assert settings3 is settings1
                assert settings3.execution_engine == "asyncio"
                assert settings3.logger.type == "console"
                assert settings3.logger.level == "info"
                assert mcp_agent.config._settings == settings1

        # To actually load new config, must use set_global=False
        with patch("mcp_agent.config._check_file_exists", return_value=True):
            with patch(
                "mcp_agent.config._read_file_content", return_value=updated_yaml
            ):
                settings4 = get_settings(
                    config_path="/fake/path/updated.yaml", set_global=False
                )
                # Now we get the new config
                assert settings4.execution_engine == "temporal"
                assert settings4.logger.type == "file"
                assert settings4.logger.level == "debug"
                # But global cache is unchanged
                assert mcp_agent.config._settings == settings1


class TestThreadSafety:
    """Test thread safety with the set_global parameter."""

    @pytest.fixture(autouse=True)
    def clear_global_settings(self):
        """Clear global settings before and after each test."""
        _clear_global_settings()
        yield
        _clear_global_settings()

    @pytest.fixture
    def simple_config(self):
        """Simple config for thread safety tests."""
        return {"execution_engine": "asyncio"}

    def test_warning_from_non_main_thread_with_set_global(self):
        """Test that warning is issued when setting global from non-main thread."""
        warning_caught = []

        def load_in_thread():
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                get_settings(set_global=True)
                if w:
                    warning_caught.extend(w)

        thread = threading.Thread(target=load_in_thread)
        thread.start()
        thread.join()

        # Should have caught a warning
        assert len(warning_caught) > 0
        assert "non-main thread" in str(warning_caught[0].message)
        assert "set_global=False" in str(warning_caught[0].message)

    def test_no_warning_from_non_main_thread_without_set_global(self):
        """Test that no warning is issued with set_global=False from non-main thread."""
        warning_caught = []

        def load_in_thread():
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                get_settings(set_global=False)
                if w:
                    warning_caught.extend(w)

        thread = threading.Thread(target=load_in_thread)
        thread.start()
        thread.join()

        # Should not have any warnings
        assert len(warning_caught) == 0

    def test_no_warning_from_main_thread(self):
        """Test that no warning is issued from main thread."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            get_settings(set_global=True)

            # Should not have thread-related warnings
            thread_warnings = [
                warn for warn in w if "non-main thread" in str(warn.message)
            ]
            assert len(thread_warnings) == 0

    def test_multiple_threads_independent_settings(self, simple_config):
        """Test that multiple threads can load independent settings."""
        thread_settings = {}
        yaml_content = yaml.dump(simple_config)

        def load_settings(thread_id, config_path):
            settings = get_settings(config_path=config_path, set_global=False)
            thread_settings[thread_id] = settings

        # Mock at test level, not inside threads
        with patch("mcp_agent.config._check_file_exists", return_value=True):
            with patch(
                "mcp_agent.config._read_file_content", return_value=yaml_content
            ):
                # Create threads
                threads = []
                for i in range(3):
                    thread = threading.Thread(
                        target=load_settings, args=(i, "/fake/path/config.yaml")
                    )
                    threads.append(thread)
                    thread.start()

                # Wait for all threads
                for thread in threads:
                    thread.join()

        # Verify all threads got settings but global state wasn't set
        assert mcp_agent.config._settings is None
        assert len(thread_settings) == 3
        for i in range(3):
            assert thread_settings[i] is not None
            assert thread_settings[i].execution_engine == "asyncio"


class TestConfigMergingWithSetGlobal:
    """Test configuration merging with set_global parameter."""

    @pytest.fixture(autouse=True)
    def clear_global_settings(self):
        """Clear global settings before and after each test."""
        _clear_global_settings()
        yield
        _clear_global_settings()

    @pytest.fixture
    def config_data_with_secrets(self):
        """Config and secrets data for testing merging."""
        config_data = {
            "execution_engine": "asyncio",
            "openai": {"api_key": "config-key"},
        }
        secrets_data = {
            "openai": {"api_key": "secret-key"},
        }
        return config_data, secrets_data

    def test_config_and_secrets_merge_with_set_global_false(
        self, config_data_with_secrets
    ):
        """Test that config and secrets merge correctly without setting global state."""
        config_data, secrets_data = config_data_with_secrets

        # Merge the data as the config loader would
        merged_data = config_data.copy()
        merged_data["openai"] = secrets_data["openai"]  # Secrets override config

        # Mock the config file read with already merged data
        merged_yaml = yaml.dump(merged_data)

        config_path = "/fake/path/config.yaml"

        with patch("mcp_agent.config._check_file_exists", return_value=True):
            with patch("mcp_agent.config._read_file_content", return_value=merged_yaml):
                settings = get_settings(config_path=config_path, set_global=False)

                # Global state should not be set
                assert mcp_agent.config._settings is None

                # Settings should have the merged values
                assert settings.openai.api_key == "secret-key"
                assert settings.execution_engine == "asyncio"

    def test_default_settings_with_set_global_false(self):
        """Test loading default settings without setting global state."""
        # No config file, should load defaults
        settings = get_settings(set_global=False)

        # Global state should not be set
        assert mcp_agent.config._settings is None

        # Should get default settings
        assert settings is not None
        assert isinstance(settings, Settings)
