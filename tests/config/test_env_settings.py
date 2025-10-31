import pytest

from mcp_agent.config import Settings


def test_env_iter_specs_supports_string_and_dict():
    settings = Settings(env=["OPENAI_API_KEY", {"SUPABASE_URL": "https://example.com"}])
    items = list(settings.iter_env_specs())
    assert items == [
        ("OPENAI_API_KEY", None),
        ("SUPABASE_URL", "https://example.com"),
    ]


def test_env_validation_rejects_empty_string():
    with pytest.raises(ValueError):
        Settings(env=[""])
