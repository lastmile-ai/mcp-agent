"""Unified tests for YAML tag handling for MCP Agent Cloud secrets.

This file consolidates tests for YAML tag handling and validation.
"""

from unittest import TestCase

from mcp_agent.cli.core.constants import SECRET_ID_PATTERN, UUID_PREFIX
from mcp_agent.cli.secrets.yaml_tags import (
    DeveloperSecret,
    UserSecret,
    dump_yaml_with_secrets,
    load_yaml_with_secrets,
)


class TestYamlSecretTags(TestCase):
    """Test handling of YAML tags for secrets."""

    def test_round_trip_serialization(self):
        """Test that secrets can be round-tripped through YAML."""
        # Test cases with different combinations
        test_cases = [
            # Basic secrets
            {
                "server": {
                    "api_key": DeveloperSecret("dev-api-key"),
                    "user_token": UserSecret("user-token"),
                }
            },
            # Empty values
            {
                "server": {
                    "api_key": DeveloperSecret(),
                    "user_token": UserSecret(),
                }
            },
            # Nested structure
            {
                "server": {
                    "providers": {
                        "bedrock": {
                            "api_key": DeveloperSecret("bedrock-key"),
                            "region": "us-west-2",
                        },
                        "openai": {
                            "api_key": UserSecret("openai-key"),
                            "org_id": "org-123",
                        },
                    },
                    "database": {
                        "password": DeveloperSecret("db-password"),
                        "user_password": UserSecret("user-db-password"),
                    },
                }
            },
            # Mixed with non-secret values
            {
                "server": {
                    "api_key": DeveloperSecret("dev-api-key"),
                    "port": 8080,
                    "debug": True,
                    "tags": ["prod", "us-west"],
                    "metadata": {
                        "created_at": "2023-01-01",
                        "created_by": UserSecret("user-123"),
                    },
                }
            },
        ]

        for config in test_cases:
            # Dump to YAML
            yaml_str = dump_yaml_with_secrets(config)

            # Load back
            loaded = load_yaml_with_secrets(yaml_str)

            # Verify structure is preserved
            self._verify_config_structure(config, loaded)

    def _verify_config_structure(self, original, loaded):
        """Helper to verify config structure is preserved."""
        if isinstance(original, dict):
            assert isinstance(loaded, dict)
            for key, value in original.items():
                assert key in loaded
                self._verify_config_structure(value, loaded[key])
        elif isinstance(original, list):
            assert isinstance(loaded, list)
            assert len(original) == len(loaded)
            for orig_item, loaded_item in zip(original, loaded):
                self._verify_config_structure(orig_item, loaded_item)
        elif isinstance(original, DeveloperSecret):
            assert isinstance(loaded, DeveloperSecret)
            assert loaded.value == original.value
        elif isinstance(original, UserSecret):
            assert isinstance(loaded, UserSecret)
            assert loaded.value == original.value
        else:
            assert loaded == original

    def test_empty_tags_handling(self):
        """Test handling of empty tags."""
        # Create YAML with empty tags
        yaml_str = """
        server:
          empty_dev_secret: !developer_secret
          empty_user_secret: !user_secret
        """

        # Load and verify
        loaded = load_yaml_with_secrets(yaml_str)
        assert isinstance(loaded["server"]["empty_dev_secret"], DeveloperSecret)
        assert loaded["server"]["empty_dev_secret"].value is None
        assert isinstance(loaded["server"]["empty_user_secret"], UserSecret)
        assert loaded["server"]["empty_user_secret"].value is None

        # Round-trip and verify no empty quotes
        dumped = dump_yaml_with_secrets(loaded)
        assert '!developer_secret ""' not in dumped
        assert '!user_secret ""' not in dumped
        assert "empty_dev_secret: !developer_secret" in dumped
        assert "empty_user_secret: !user_secret" in dumped

    def test_uuid_handle_handling(self):
        """Test handling of UUID handles."""
        # Create YAML with UUID handles and secret tags
        yaml_str = f"""
        server:
          bedrock:
            # Deployed secret with UUID handle
            api_key: "{UUID_PREFIX}12345678-abcd-1234-a123-123456789abc"
            # User secret that will be collected during configure
            user_access_key: !user_secret USER_KEY
        database:
          # Another deployed secret with UUID handle
          password: "{UUID_PREFIX}87654321-dcba-4321-b321-987654321cba"
        """

        # Load and verify
        loaded = load_yaml_with_secrets(yaml_str)

        # Verify UUID handles are preserved as strings
        assert isinstance(loaded["server"]["bedrock"]["api_key"], str)
        assert loaded["server"]["bedrock"]["api_key"].startswith(UUID_PREFIX)
        assert (
            loaded["server"]["bedrock"]["api_key"]
            == f"{UUID_PREFIX}12345678-abcd-1234-a123-123456789abc"
        )

        # Verify UUID handle pattern matches
        assert (
            SECRET_ID_PATTERN.match(loaded["server"]["bedrock"]["api_key"]) is not None
        )
        assert SECRET_ID_PATTERN.match(loaded["database"]["password"]) is not None

        # User secret tag should still be recognized
        assert isinstance(loaded["server"]["bedrock"]["user_access_key"], UserSecret)
        assert loaded["server"]["bedrock"]["user_access_key"].value == "USER_KEY"

        # Round-trip test - dump and reload
        dumped = dump_yaml_with_secrets(loaded)
        reloaded = load_yaml_with_secrets(dumped)

        # Verify all values are preserved exactly
        assert (
            reloaded["server"]["bedrock"]["api_key"]
            == f"{UUID_PREFIX}12345678-abcd-1234-a123-123456789abc"
        )
        assert (
            reloaded["database"]["password"]
            == f"{UUID_PREFIX}87654321-dcba-4321-b321-987654321cba"
        )
        assert isinstance(reloaded["server"]["bedrock"]["user_access_key"], UserSecret)
        assert reloaded["server"]["bedrock"]["user_access_key"].value == "USER_KEY"

    def test_uuid_pattern_validation(self):
        """Test UUID pattern validation for handles."""
        # Valid handles
        valid_handles = [
            f"{UUID_PREFIX}12345678-abcd-1234-a123-123456789abc",
            f"{UUID_PREFIX}00000000-0000-0000-0000-000000000000",
            f"{UUID_PREFIX}ffffffff-ffff-ffff-ffff-ffffffffffff",
        ]

        # Invalid handles
        invalid_handles = [
            # Missing prefix
            "12345678-abcd-1234-a123-123456789abc",
            # Wrong prefix
            "wrong_prefix_12345678-abcd-1234-a123-123456789abc",
            # Malformed UUID
            f"{UUID_PREFIX}12345678abcd1234a123123456789abc",
            f"{UUID_PREFIX}12345678-abcd-1234-a123",
            # Invalid characters
            f"{UUID_PREFIX}1234567g-abcd-1234-a123-123456789abc",
            # Empty string
            "",
        ]

        # Test all valid handles
        for handle in valid_handles:
            assert SECRET_ID_PATTERN.match(handle) is not None, (
                f"Valid handle {handle} didn't match pattern"
            )

        # Test all invalid handles
        for handle in invalid_handles:
            assert SECRET_ID_PATTERN.match(handle) is None, (
                f"Invalid handle {handle} matched pattern"
            )


def test_realistic_yaml_examples():
    """Test handling of realistic YAML examples."""

    # Example with various tag combinations
    yaml_str = """
    # Example deployment configuration with secrets
    server:
      bedrock:
        # Value comes from env var BEDROCK_KEY
        api_key: !developer_secret BEDROCK_KEY
        # Value collected during configure, env var USER_KEY is an override
        user_access_key: !user_secret USER_KEY 
      openai:
        api_key: !developer_secret
        org_id: "org-123456"
    database:
      # Must be prompted for during deploy
      password: !developer_secret 
      host: "localhost"
      port: 5432
    """

    # Load and verify
    loaded = load_yaml_with_secrets(yaml_str)

    # Verify structure and tags
    assert isinstance(loaded["server"]["bedrock"]["api_key"], DeveloperSecret)
    assert loaded["server"]["bedrock"]["api_key"].value == "BEDROCK_KEY"
    assert isinstance(loaded["server"]["bedrock"]["user_access_key"], UserSecret)
    assert loaded["server"]["bedrock"]["user_access_key"].value == "USER_KEY"
    assert isinstance(loaded["server"]["openai"]["api_key"], DeveloperSecret)
    assert loaded["server"]["openai"]["api_key"].value is None
    assert loaded["server"]["openai"]["org_id"] == "org-123456"
    assert isinstance(loaded["database"]["password"], DeveloperSecret)
    assert loaded["database"]["password"].value is None
    assert loaded["database"]["host"] == "localhost"
    assert loaded["database"]["port"] == 5432

    # Test round-trip
    dumped = dump_yaml_with_secrets(loaded)
    reloaded = load_yaml_with_secrets(dumped)

    # Verify same structure is preserved in round-trip
    assert isinstance(reloaded["server"]["bedrock"]["api_key"], DeveloperSecret)
    assert reloaded["server"]["bedrock"]["api_key"].value == "BEDROCK_KEY"
    assert isinstance(reloaded["server"]["bedrock"]["user_access_key"], UserSecret)
    assert reloaded["server"]["bedrock"]["user_access_key"].value == "USER_KEY"
    assert isinstance(reloaded["server"]["openai"]["api_key"], DeveloperSecret)
    assert reloaded["server"]["openai"]["api_key"].value is None
    assert isinstance(reloaded["database"]["password"], DeveloperSecret)
    assert reloaded["database"]["password"].value is None


def test_deployed_secrets_example():
    """Test handling of post-deployment YAML with UUID handles."""

    yaml_str = f"""
    # Post-deployment configuration
    server:
      bedrock:
        api_key: "{UUID_PREFIX}12345678-abcd-1234-a123-123456789abc"
        # User secret tag remains for configure phase
        user_access_key: !user_secret USER_KEY 
      openai:
        api_key: "{UUID_PREFIX}23456789-bcde-2345-b234-234567890bcd"
    database:
      password: "{UUID_PREFIX}87654321-dcba-4321-b321-987654321cba"
    """

    # Load and verify
    loaded = load_yaml_with_secrets(yaml_str)

    # Verify UUID handles and remaining user secret
    assert (
        loaded["server"]["bedrock"]["api_key"]
        == f"{UUID_PREFIX}12345678-abcd-1234-a123-123456789abc"
    )
    assert isinstance(loaded["server"]["bedrock"]["user_access_key"], UserSecret)
    assert loaded["server"]["bedrock"]["user_access_key"].value == "USER_KEY"
    assert (
        loaded["server"]["openai"]["api_key"]
        == f"{UUID_PREFIX}23456789-bcde-2345-b234-234567890bcd"
    )
    assert (
        loaded["database"]["password"]
        == f"{UUID_PREFIX}87654321-dcba-4321-b321-987654321cba"
    )


def test_fully_configured_secrets_example():
    """Test handling of fully configured secrets with all UUIDs."""

    yaml_str = f"""
    # Fully configured with all secrets as UUID handles
    server:
      bedrock:
        api_key: "{UUID_PREFIX}12345678-abcd-1234-a123-123456789abc"
        # User secret now has a UUID handle too
        user_access_key: "{UUID_PREFIX}98765432-edcb-5432-c432-567890123def"
      openai:
        api_key: "{UUID_PREFIX}23456789-bcde-2345-b234-234567890bcd"
    database:
      password: "{UUID_PREFIX}87654321-dcba-4321-b321-987654321cba"
    """

    # Load and verify
    loaded = load_yaml_with_secrets(yaml_str)

    # All values should be string UUIDs with correct prefix
    assert (
        loaded["server"]["bedrock"]["api_key"]
        == f"{UUID_PREFIX}12345678-abcd-1234-a123-123456789abc"
    )
    assert (
        loaded["server"]["bedrock"]["user_access_key"]
        == f"{UUID_PREFIX}98765432-edcb-5432-c432-567890123def"
    )
    assert (
        loaded["server"]["openai"]["api_key"]
        == f"{UUID_PREFIX}23456789-bcde-2345-b234-234567890bcd"
    )
    assert (
        loaded["database"]["password"]
        == f"{UUID_PREFIX}87654321-dcba-4321-b321-987654321cba"
    )

    # Check that all handles match UUID pattern
    for path in [
        "server.bedrock.api_key",
        "server.bedrock.user_access_key",
        "server.openai.api_key",
        "database.password",
    ]:
        parts = path.split(".")
        value = loaded
        for part in parts:
            value = value[part]
        assert SECRET_ID_PATTERN.match(value) is not None
