import pytest
from unittest.mock import MagicMock

from mcp_agent.config import NvidiaSettings
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.augmented_llm_nvidia import NvidiaAugmentedLLM


class TestNvidiaAugmentedLLM:
    """
    Tests for the NvidiaAugmentedLLM class.
    """

    @pytest.fixture
    def mock_llm(self, mock_context):
        """
        Creates a mock NVIDIA LLM instance with common mocks set up.
        """
        mock_context.config.nvidia = NvidiaSettings(
            default_model=None,
            base_url="https://integrate.api.nvidia.com/v1",
        )

        llm = NvidiaAugmentedLLM(name="test", context=mock_context)
        llm.history = MagicMock()
        llm.history.get = MagicMock(return_value=[])
        llm.history.set = MagicMock()

        return llm

    def test_initialization(self, mock_llm):
        """
        Test that NvidiaAugmentedLLM initializes correctly.
        """
        assert mock_llm.name == "test"
        assert mock_llm.provider == "NVIDIA"

    def test_get_provider_config(self, mock_context):
        """
        Test that get_provider_config returns the nvidia config.
        """
        mock_context.config.nvidia = NvidiaSettings(
            base_url="https://integrate.api.nvidia.com/v1",
        )

        config = NvidiaAugmentedLLM.get_provider_config(mock_context)

        assert config is not None
        assert config.base_url == "https://integrate.api.nvidia.com/v1"

    def test_default_settings(self, monkeypatch):
        """
        Test that NvidiaSettings has correct defaults.
        """
        monkeypatch.delenv("NVIDIA_BASE_URL", raising=False)
        monkeypatch.delenv("NVIDIA_DEFAULT_MODEL", raising=False)

        settings = NvidiaSettings()

        assert settings.base_url == "https://integrate.api.nvidia.com/v1"
        assert settings.default_model is None

    def test_api_key_from_environment(self, mock_context, monkeypatch):
        """
        Test that api_key is read from NVIDIA_API_KEY.
        """
        monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
        mock_context.config.nvidia = NvidiaSettings(
            base_url="https://integrate.api.nvidia.com/v1",
        )

        llm = NvidiaAugmentedLLM(name="test", context=mock_context)

        assert hasattr(llm.context.config.nvidia, "api_key")
        assert llm.context.config.nvidia.api_key == "test-key"

    def test_base_url_override(self, monkeypatch):
        """
        Test that base_url can be overridden for self-hosted NIM.
        """
        monkeypatch.setenv("NVIDIA_BASE_URL", "http://localhost:8000/v1")

        assert NvidiaSettings().base_url == "http://localhost:8000/v1"
        assert (
            NvidiaSettings(base_url="http://nim.internal:8000/v1").base_url
            == "http://nim.internal:8000/v1"
        )

    @pytest.mark.asyncio
    async def test_select_model_uses_config_default(self, mock_context):
        """
        Test that select_model returns the config's default_model when set.
        """
        mock_context.config.nvidia = NvidiaSettings(
            default_model="nvidia/nemotron-3.5-super-vl-120b-a12b",
            base_url="https://integrate.api.nvidia.com/v1",
        )

        llm = NvidiaAugmentedLLM(name="test", context=mock_context)

        model = await llm.select_model()

        assert model == "nvidia/nemotron-3.5-super-vl-120b-a12b"

    @pytest.mark.asyncio
    async def test_select_model_request_params_override(self, mock_context):
        """
        Test that select_model prioritizes request_params.model over config.
        """
        mock_context.config.nvidia = NvidiaSettings(
            default_model="nvidia/nemotron-3.5-super-vl-120b-a12b",
            base_url="https://integrate.api.nvidia.com/v1",
        )

        llm = NvidiaAugmentedLLM(name="test", context=mock_context)

        # Request params should override config
        request_params = RequestParams(model="custom-model")
        model = await llm.select_model(request_params)

        assert model == "custom-model"

    @pytest.mark.asyncio
    async def test_select_model_no_config_default(self, mock_context):
        """
        Test that select_model falls back to parent when no config default_model.
        """

        mock_context.config.nvidia = NvidiaSettings(
            default_model=None,
            base_url="https://integrate.api.nvidia.com/v1",
        )

        llm = NvidiaAugmentedLLM(name="test", context=mock_context)

        # Mock the parent's select_model to verify fallback behavior
        original_select = NvidiaAugmentedLLM.__bases__[0].select_model
        parent_called = False

        async def mock_parent_select(self, request_params=None):
            nonlocal parent_called
            parent_called = True
            return "benchmark-model"

        NvidiaAugmentedLLM.__bases__[0].select_model = mock_parent_select

        try:
            model = await llm.select_model()
            assert parent_called, (
                "Parent's select_model should be called when no config default"
            )
            assert model == "benchmark-model"
        finally:
            # Restore original
            NvidiaAugmentedLLM.__bases__[0].select_model = original_select
