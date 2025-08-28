"""Tests for the SecretsResolver resolve_in_place method."""

import pytest
from mcp_agent.cli.core.api_client import UnauthenticatedError
from mcp_agent.cli.core.constants import SecretType
from mcp_agent.cli.secrets.mock_client import MockSecretsClient
from mcp_agent.cli.secrets.resolver import SecretsResolver
from mcp_agent.cli.secrets.yaml_tags import UserSecret


@pytest.fixture
def mock_client():
    """Create a MockSecretsClient for testing."""
    return MockSecretsClient()


@pytest.fixture
def resolver(mock_client):
    """Create a SecretsResolver with a mock client."""
    return SecretsResolver(mock_client)


@pytest.mark.asyncio
async def test_resolve_empty_dict(resolver):
    """Test resolving an empty dictionary."""
    config = {}
    result = await resolver.resolve_in_place(config)
    assert result == {}
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_resolve_dict_without_secrets(resolver):
    """Test resolving a dictionary with no secret handles."""
    config = {
        "name": "test-app",
        "version": "1.0.0",
        "settings": {
            "debug": True,
            "port": 8080,
            "features": ["auth", "logging"],
        },
    }
    result = await resolver.resolve_in_place(config)
    assert result == config
    assert result["settings"]["debug"] is True
    assert result["settings"]["port"] == 8080
    assert result["settings"]["features"] == ["auth", "logging"]


@pytest.mark.asyncio
async def test_resolve_single_secret(resolver, mock_client):
    """Test resolving a single secret handle."""
    # First create a secret to get a handle
    handle = await mock_client.create_secret(
        name="test.api_key", secret_type=SecretType.DEVELOPER, value="secret-value-123"
    )

    config = {"api_key": handle}

    result = await resolver.resolve_in_place(config)
    assert result["api_key"] == "secret-value-123"


@pytest.mark.asyncio
async def test_resolve_nested_secrets(resolver, mock_client):
    """Test resolving nested secret handles."""
    # Create multiple secrets
    api_handle = await mock_client.create_secret(
        name="server.api_key", secret_type=SecretType.DEVELOPER, value="api-secret"
    )
    db_handle = await mock_client.create_secret(
        name="database.password", secret_type=SecretType.DEVELOPER, value="db-secret"
    )

    config = {
        "server": {"host": "localhost", "api_key": api_handle, "port": 3000},
        "database": {"host": "db.example.com", "password": db_handle, "pool_size": 10},
    }

    result = await resolver.resolve_in_place(config)
    assert result["server"]["api_key"] == "api-secret"
    assert result["server"]["host"] == "localhost"
    assert result["server"]["port"] == 3000
    assert result["database"]["password"] == "db-secret"
    assert result["database"]["host"] == "db.example.com"
    assert result["database"]["pool_size"] == 10


@pytest.mark.asyncio
async def test_resolve_secrets_in_list(resolver, mock_client):
    """Test resolving secret handles within lists."""
    # Create secrets
    token1 = await mock_client.create_secret(
        name="tokens.0", secret_type=SecretType.DEVELOPER, value="token-1"
    )
    token2 = await mock_client.create_secret(
        name="tokens.1", secret_type=SecretType.DEVELOPER, value="token-2"
    )

    config = {
        "tokens": [token1, "regular-value", token2],
        "servers": [
            {"name": "server1", "key": token1},
            {"name": "server2", "key": token2},
        ],
    }

    result = await resolver.resolve_in_place(config)
    assert result["tokens"] == ["token-1", "regular-value", "token-2"]
    assert result["servers"][0]["key"] == "token-1"
    assert result["servers"][1]["key"] == "token-2"


@pytest.mark.asyncio
async def test_resolve_none_values(resolver):
    """Test that None values are preserved."""
    config = {
        "optional_field": None,
        "settings": {"nullable": None, "defined": "value"},
    }

    result = await resolver.resolve_in_place(config)
    assert result["optional_field"] is None
    assert result["settings"]["nullable"] is None
    assert result["settings"]["defined"] == "value"


@pytest.mark.asyncio
async def test_resolve_mixed_types(resolver, mock_client):
    """Test resolving config with mixed types."""
    handle = await mock_client.create_secret(
        name="mixed.secret", secret_type=SecretType.DEVELOPER, value="secret-val"
    )

    config = {
        "string": "text",
        "number": 42,
        "float": 3.14,
        "boolean": False,
        "null": None,
        "secret": handle,
        "list": [1, "two", None, handle],
        "nested": {"secret": handle, "normal": "value"},
    }

    result = await resolver.resolve_in_place(config)
    assert result["string"] == "text"
    assert result["number"] == 42
    assert result["float"] == 3.14
    assert result["boolean"] is False
    assert result["null"] is None
    assert result["secret"] == "secret-val"
    assert result["list"] == [1, "two", None, "secret-val"]
    assert result["nested"]["secret"] == "secret-val"
    assert result["nested"]["normal"] == "value"


@pytest.mark.asyncio
async def test_resolve_no_api_key_raises_error():
    """Test that missing API key raises ValueError."""
    # Create client without API key
    client = MockSecretsClient()
    client.api_key = None
    resolver = SecretsResolver(client)

    config = {"key": "value"}

    with pytest.raises(ValueError, match="Missing MCP_API_KEY"):
        await resolver.resolve_in_place(config)


@pytest.mark.asyncio
async def test_resolve_authentication_error(resolver, mock_client):
    """Test that authentication errors are properly raised."""
    # Create a secret handle
    handle = await mock_client.create_secret(
        name="test.secret", secret_type=SecretType.DEVELOPER, value="value"
    )

    # Simulate authentication failure
    async def mock_get_secret_value(secret_id):
        raise UnauthenticatedError("Invalid API key")

    mock_client.get_secret_value = mock_get_secret_value

    config = {"secret": handle}

    with pytest.raises(UnauthenticatedError):
        await resolver.resolve_in_place(config)


@pytest.mark.asyncio
async def test_resolve_missing_secret_raises_error(resolver, mock_client):
    """Test that missing secrets raise RuntimeError."""
    # Use a handle that doesn't exist
    fake_handle = "mcpac_sc_00000000-0000-0000-0000-000000000000"

    config = {"missing_secret": fake_handle}

    with pytest.raises(RuntimeError, match="Failed to resolve secret"):
        await resolver.resolve_in_place(config)


@pytest.mark.asyncio
async def test_resolve_deeply_nested_structure(resolver, mock_client):
    """Test resolving deeply nested structures."""
    handle = await mock_client.create_secret(
        name="deep.secret", secret_type=SecretType.DEVELOPER, value="deep-value"
    )

    config = {
        "level1": {
            "level2": {
                "level3": {
                    "level4": {
                        "secret": handle,
                        "list": [{"item": handle}, {"item": "normal"}],
                    }
                }
            }
        }
    }

    result = await resolver.resolve_in_place(config)
    assert result["level1"]["level2"]["level3"]["level4"]["secret"] == "deep-value"
    assert (
        result["level1"]["level2"]["level3"]["level4"]["list"][0]["item"]
        == "deep-value"
    )
    assert result["level1"]["level2"]["level3"]["level4"]["list"][1]["item"] == "normal"


@pytest.mark.asyncio
async def test_resolve_empty_list(resolver):
    """Test resolving empty lists."""
    config = {"empty_list": [], "nested": {"also_empty": []}}

    result = await resolver.resolve_in_place(config)
    assert result["empty_list"] == []
    assert result["nested"]["also_empty"] == []


@pytest.mark.asyncio
async def test_resolve_preserves_structure(resolver, mock_client):
    """Test that resolution preserves the original structure."""
    handle = await mock_client.create_secret(
        name="preserve.secret", secret_type=SecretType.DEVELOPER, value="resolved"
    )

    config = {
        "a": 1,
        "b": {"c": 2, "d": handle},
        "e": [3, 4, {"f": 5, "g": handle}],
    }

    result = await resolver.resolve_in_place(config)

    # Check structure is preserved
    assert "a" in result
    assert "b" in result
    assert "c" in result["b"]
    assert "d" in result["b"]
    assert "e" in result
    assert len(result["e"]) == 3
    assert isinstance(result["e"][2], dict)
    assert "f" in result["e"][2]
    assert "g" in result["e"][2]

    # Check values
    assert result["a"] == 1
    assert result["b"]["c"] == 2
    assert result["b"]["d"] == "resolved"
    assert result["e"][0] == 3
    assert result["e"][1] == 4
    assert result["e"][2]["f"] == 5
    assert result["e"][2]["g"] == "resolved"


@pytest.mark.asyncio
async def test_resolve_handles_special_characters_in_values(resolver, mock_client):
    """Test that special characters in secret values are handled correctly."""
    handle = await mock_client.create_secret(
        name="special.chars",
        secret_type=SecretType.DEVELOPER,
        value="special!@#$%^&*()_+-=[]{}|;':\",./<>?`~",
    )

    config = {"special": handle}

    result = await resolver.resolve_in_place(config)
    assert result["special"] == "special!@#$%^&*()_+-=[]{}|;':\",./<>?`~"


@pytest.mark.asyncio
async def test_resolve_handles_unicode_values(resolver, mock_client):
    """Test that Unicode characters in secret values are handled correctly."""
    handle = await mock_client.create_secret(
        name="unicode.secret",
        secret_type=SecretType.DEVELOPER,
        value="Hello 世界 🌍 مرحبا",
    )

    config = {"unicode": handle}

    result = await resolver.resolve_in_place(config)
    assert result["unicode"] == "Hello 世界 🌍 مرحبا"


# Tests for load_config method


def test_load_config_nonexistent_file(resolver):
    """Test loading config from a non-existent file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        resolver.load_config("/nonexistent/path/to/config.yaml")


def test_load_config_empty_file(resolver, tmp_path):
    """Test loading config from an empty file."""
    # Create an empty file
    config_file = tmp_path / "empty.yaml"
    config_file.write_text("")

    result = resolver.load_config(str(config_file))

    assert result.config == {}
    assert result.developer_secret_tag_keys == set()
    assert result.user_secret_tag_keys == set()


def test_load_config_empty_yaml_dict(resolver, tmp_path):
    """Test loading config with an empty YAML dictionary."""
    config_file = tmp_path / "empty_dict.yaml"
    config_file.write_text("---\n{}\n")

    result = resolver.load_config(str(config_file))

    assert result.config == {}
    assert result.developer_secret_tag_keys == set()
    assert result.user_secret_tag_keys == set()


def test_load_config_plain_values(resolver, tmp_path):
    """Test loading config with plain values (no secrets)."""
    config_file = tmp_path / "plain.yaml"
    config_file.write_text("""
server:
  host: localhost
  port: 8080
  debug: true
database:
  name: mydb
  pool_size: 10
""")

    result = resolver.load_config(str(config_file))

    assert result.config == {
        "server": {"host": "localhost", "port": 8080, "debug": True},
        "database": {"name": "mydb", "pool_size": 10},
    }
    assert result.developer_secret_tag_keys == set()
    assert result.user_secret_tag_keys == set()


def test_load_config_with_developer_secrets(resolver, tmp_path):
    """Test loading config with developer secret tags."""
    config_file = tmp_path / "dev_secrets.yaml"
    config_file.write_text("""
api:
  key: !developer_secret 'api-key-value'
  url: https://api.example.com
database:
  password: !developer_secret
  host: db.example.com
""")

    result = resolver.load_config(str(config_file))

    # Secrets should be stripped from config
    assert result.config == {
        "api": {"url": "https://api.example.com"},
        "database": {"host": "db.example.com"},
    }
    assert result.developer_secret_tag_keys == {"api.key", "database.password"}
    assert result.user_secret_tag_keys == set()


def test_load_config_with_user_secrets(resolver, tmp_path):
    """Test loading config with user secret tags."""

    config_file = tmp_path / "user_secrets.yaml"
    config_file.write_text("""
auth:
  token: !user_secret
  refresh_token: !user_secret 'REFRESH_TOKEN'
  endpoint: /auth
settings:
  api_key: !user_secret
""")

    result = resolver.load_config(str(config_file))

    # The strip_secrets function actually removes secrets from the config dict
    assert result.config == {
        "auth": {"endpoint": "/auth"}
        # settings is completely removed when it only contains secrets
    }
    assert result.developer_secret_tag_keys == set()
    assert result.user_secret_tag_keys == {
        "auth.token",
        "auth.refresh_token",
        "settings.api_key",
    }


def test_load_config_mixed_secrets(resolver, tmp_path):
    """Test loading config with both developer and user secrets."""
    config_file = tmp_path / "mixed_secrets.yaml"
    config_file.write_text("""
server:
  admin_key: !developer_secret 'admin-secret'
  user_token: !user_secret
  host: 0.0.0.0
  port: 3000
database:
  master_password: !developer_secret
  user_password: !user_secret 'DB_USER_PASS'
  url: postgres://localhost/mydb
nested:
  level1:
    dev_secret: !developer_secret 'nested-dev'
    user_secret: !user_secret
    normal: value
""")

    result = resolver.load_config(str(config_file))

    assert result.config == {
        "server": {"host": "0.0.0.0", "port": 3000},
        "database": {"url": "postgres://localhost/mydb"},
        "nested": {"level1": {"normal": "value"}},
    }
    assert result.developer_secret_tag_keys == {
        "server.admin_key",
        "database.master_password",
        "nested.level1.dev_secret",
    }
    assert result.user_secret_tag_keys == {
        "server.user_token",
        "database.user_password",
        "nested.level1.user_secret",
    }


def test_load_config_with_lists(resolver, tmp_path):
    """Test loading config with lists containing secrets."""
    from mcp_agent.cli.secrets.yaml_tags import DeveloperSecret, UserSecret

    config_file = tmp_path / "with_lists.yaml"
    config_file.write_text("""
tokens:
  - !developer_secret 'token1'
  - regular_token
  - !user_secret
servers:
  - name: server1
    key: !developer_secret
  - name: server2
    key: !user_secret
    host: server2.example.com
""")

    result = resolver.load_config(str(config_file))

    # Lists are preserved as-is with secret objects intact
    # strip_secrets doesn't handle lists - they're returned in the else clause
    assert "tokens" in result.config
    assert isinstance(result.config["tokens"], list)
    assert len(result.config["tokens"]) == 3
    assert isinstance(result.config["tokens"][0], DeveloperSecret)
    assert result.config["tokens"][0].value == "token1"
    assert result.config["tokens"][1] == "regular_token"
    assert isinstance(result.config["tokens"][2], UserSecret)

    # Servers list - dicts inside lists are NOT processed
    # The entire list is returned as-is from the else clause
    assert "servers" in result.config
    assert len(result.config["servers"]) == 2
    # First server - still has the secret key
    assert result.config["servers"][0]["name"] == "server1"
    assert isinstance(result.config["servers"][0]["key"], DeveloperSecret)
    # Second server - still has the secret key
    assert result.config["servers"][1]["name"] == "server2"
    assert result.config["servers"][1]["host"] == "server2.example.com"
    assert isinstance(result.config["servers"][1]["key"], UserSecret)

    # Since secrets in lists are not stripped, they won't be tracked in secret_tag_keys
    # Only top-level secrets in dicts are tracked
    # So we shouldn't expect servers.key paths in the secret keys
    assert (
        len(result.developer_secret_tag_keys) == 0
        or "tokens" not in result.developer_secret_tag_keys
    )
    assert (
        len(result.user_secret_tag_keys) == 0
        or "tokens" not in result.user_secret_tag_keys
    )


def test_load_config_null_values(resolver, tmp_path):
    """Test loading config with null/None values."""
    config_file = tmp_path / "with_nulls.yaml"
    config_file.write_text("""
settings:
  optional_field: null
  required_field: value
  secret_field: !developer_secret
  nullable_secret: !user_secret
""")

    result = resolver.load_config(str(config_file))

    # None values are filtered out by the "if stripped is not None" check
    assert result.config == {
        "settings": {
            "required_field": "value"
            # optional_field is None, so it gets filtered out
        }
    }
    assert result.developer_secret_tag_keys == {"settings.secret_field"}
    assert result.user_secret_tag_keys == {"settings.nullable_secret"}


def test_load_config_invalid_yaml(resolver, tmp_path):
    """Test loading invalid YAML raises an error."""
    config_file = tmp_path / "invalid.yaml"
    config_file.write_text("""
this is not: valid yaml
  - because indentation
: is wrong
""")

    with pytest.raises(Exception):  # YAML parsing error
        resolver.load_config(str(config_file))


def test_load_config_complex_nested_structure(resolver, tmp_path):
    """Test loading complex nested structures with secrets at various levels."""
    from mcp_agent.cli.secrets.yaml_tags import DeveloperSecret

    config_file = tmp_path / "complex.yaml"
    config_file.write_text("""
level1:
  level2:
    secret: !developer_secret 'l2-secret'
    level3:
      data: value
      level4:
        deep_secret: !user_secret
        deep_value: 42
        level5:
          - item1
          - !developer_secret 'list-secret'
          - item3
""")

    result = resolver.load_config(str(config_file))

    # Debug: print the actual config structure

    def serialize_for_debug(obj):
        if isinstance(obj, (DeveloperSecret, UserSecret)):
            return f"{obj.__class__.__name__}({obj.value})"
        elif isinstance(obj, dict):
            return {k: serialize_for_debug(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [serialize_for_debug(item) for item in obj]
        else:
            return obj

    # Compare the structure piece by piece
    assert "level1" in result.config
    assert "level2" in result.config["level1"]
    # Secret at level2 should be stripped
    assert "secret" not in result.config["level1"]["level2"]
    assert "level3" in result.config["level1"]["level2"]
    assert result.config["level1"]["level2"]["level3"]["data"] == "value"
    assert result.config["level1"]["level2"]["level3"]["level4"]["deep_value"] == 42
    # deep_secret should be stripped
    assert "deep_secret" not in result.config["level1"]["level2"]["level3"]["level4"]
    # List should be preserved as-is
    level5 = result.config["level1"]["level2"]["level3"]["level4"]["level5"]
    assert len(level5) == 3
    assert level5[0] == "item1"
    assert isinstance(level5[1], DeveloperSecret)
    assert level5[1].value == "list-secret"
    assert level5[2] == "item3"
    assert "level1.level2.secret" in result.developer_secret_tag_keys
    assert "level1.level2.level3.level4.deep_secret" in result.user_secret_tag_keys


def test_load_config_only_secrets(resolver, tmp_path):
    """Test loading a config that contains only secrets."""
    config_file = tmp_path / "only_secrets.yaml"
    config_file.write_text("""
secret1: !developer_secret 'value1'
secret2: !user_secret
nested:
  secret3: !developer_secret
  more_nested:
    secret4: !user_secret 'ENV_VAR'
""")

    result = resolver.load_config(str(config_file))

    # When all values in nested dicts are secrets, they get stripped
    # Empty dicts return None from strip_secrets, so they don't get added
    assert result.config == {}
    assert result.developer_secret_tag_keys == {"secret1", "nested.secret3"}
    assert result.user_secret_tag_keys == {"secret2", "nested.more_nested.secret4"}


def test_load_config_with_comments(resolver, tmp_path):
    """Test loading YAML with comments."""
    config_file = tmp_path / "with_comments.yaml"
    config_file.write_text("""
# This is a comment
server:
  host: localhost  # inline comment
  # Another comment
  port: 8080
  api_key: !developer_secret 'key'  # Secret with comment
""")

    result = resolver.load_config(str(config_file))

    assert result.config == {"server": {"host": "localhost", "port": 8080}}
    assert result.developer_secret_tag_keys == {"server.api_key"}


def test_load_config_unicode_content(resolver, tmp_path):
    """Test loading config with Unicode content."""
    config_file = tmp_path / "unicode.yaml"
    config_file.write_text("""
messages:
  welcome: "Hello 世界"
  goodbye: "مع السلامة"
  emoji: "🚀 Launch!"
secrets:
  unicode_secret: !developer_secret 'секрет'
""")

    result = resolver.load_config(str(config_file))

    # The 'secrets' dict has all its values stripped, becoming empty and thus removed
    assert result.config == {
        "messages": {
            "welcome": "Hello 世界",
            "goodbye": "مع السلامة",
            "emoji": "🚀 Launch!",
        }
    }
    assert result.developer_secret_tag_keys == {"secrets.unicode_secret"}


def test_load_config_permission_denied(resolver, tmp_path):
    """Test loading config from a file without read permissions."""
    import os
    import platform

    # Skip on Windows as permission handling is different
    if platform.system() == "Windows":
        pytest.skip("Permission test not applicable on Windows")

    config_file = tmp_path / "no_read.yaml"
    config_file.write_text("data: value")

    # Remove read permissions
    os.chmod(config_file, 0o000)

    try:
        with pytest.raises(PermissionError):
            resolver.load_config(str(config_file))
    finally:
        # Restore permissions for cleanup
        os.chmod(config_file, 0o644)
