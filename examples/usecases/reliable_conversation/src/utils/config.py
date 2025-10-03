"""
Configuration utilities for Reliable Conversation Manager.
"""

from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.llm.augmented_llm_anthropic import AnthropicAugmentedLLM
from typing import Type, Any


def get_llm_class(provider: str = "openai") -> Type:
    """Get LLM class based on provider name"""
    if provider.lower() == "anthropic":
        return AnthropicAugmentedLLM
    else:
        return OpenAIAugmentedLLM


def extract_rcm_config(app_config: Any) -> dict:
    """Extract RCM-specific configuration from app config"""
    rcm_config = {}

    # Extract from rcm section if it exists
    if hasattr(app_config, "rcm"):
        rcm_config.update(app_config.rcm)

    # Set defaults
    rcm_config.setdefault("quality_threshold", 0.8)
    rcm_config.setdefault("max_refinement_attempts", 3)
    rcm_config.setdefault("consolidation_interval", 3)
    rcm_config.setdefault("use_claude_code", False)
    rcm_config.setdefault("evaluator_model_provider", "openai")
    rcm_config.setdefault("verbose_metrics", False)
    rcm_config.setdefault("mcp_servers", [])  # Default to empty list

    return rcm_config
