"""Tests for the secrets YAML tag handling."""

import unittest

import yaml
from mcp_agent.cli.secrets.yaml_tags import (
    DeveloperSecret,
    SecretYamlDumper,
    SecretYamlLoader,
    UserSecret,
    dump_yaml_with_secrets,
    load_yaml_with_secrets,
)


class TestYamlSecretTags(unittest.TestCase):
    """Test case for YAML secret tag handling."""

    def test_basic_round_trip(self):
        """Test basic round-trip serialization and deserialization."""
        # Create test data with both types of secrets
        config = {
            "server": {
                "api_key": DeveloperSecret("some-value"),
                "empty_dev_secret": DeveloperSecret(),
                "user_token": UserSecret("user-value"),
                "empty_user_secret": UserSecret(),
            }
        }

        # Dump to YAML
        yaml_str = dump_yaml_with_secrets(config)

        # Verify output format
        self.assertIn("api_key: !developer_secret 'some-value'", yaml_str)
        self.assertIn("empty_dev_secret: !developer_secret", yaml_str)  # No quotes
        self.assertIn("user_token: !user_secret 'user-value'", yaml_str)
        self.assertIn("empty_user_secret: !user_secret", yaml_str)  # No quotes

        # Load back
        loaded = load_yaml_with_secrets(yaml_str)

        # Verify structure and values
        self.assertIsInstance(loaded, dict)
        self.assertIn("server", loaded)

        server = loaded["server"]
        self.assertIsInstance(server["api_key"], DeveloperSecret)
        self.assertEqual(server["api_key"].value, "some-value")

        self.assertIsInstance(server["empty_dev_secret"], DeveloperSecret)
        self.assertIsNone(server["empty_dev_secret"].value)

        self.assertIsInstance(server["user_token"], UserSecret)
        self.assertEqual(server["user_token"].value, "user-value")

        self.assertIsInstance(server["empty_user_secret"], UserSecret)
        self.assertIsNone(server["empty_user_secret"].value)

    def test_direct_yaml_format(self):
        """Test loading YAML string with empty tags directly."""
        yaml_with_empty_tags = """
server:
  api_key: !developer_secret 'key123'
  empty_dev_secret: !developer_secret
  user_token: !user_secret 'token456'
  empty_user_secret: !user_secret
"""
        # Load the YAML
        loaded = load_yaml_with_secrets(yaml_with_empty_tags)

        # Verify structure and values
        server = loaded["server"]
        self.assertEqual(server["api_key"].value, "key123")
        self.assertIsNone(server["empty_dev_secret"].value)
        self.assertEqual(server["user_token"].value, "token456")
        self.assertIsNone(server["empty_user_secret"].value)

    def test_nested_structure(self):
        """Test handling of secrets in nested structures."""
        # Create nested test data
        config = {
            "server": {
                "providers": {
                    "bedrock": {
                        "api_key": DeveloperSecret("bedrock-key"),
                    },
                    "openai": {
                        "api_key": UserSecret("openai-key"),
                    },
                }
            }
        }

        # Dump to YAML
        yaml_str = dump_yaml_with_secrets(config)

        # Load back
        loaded = load_yaml_with_secrets(yaml_str)

        # Verify nested structure
        self.assertEqual(
            loaded["server"]["providers"]["bedrock"]["api_key"].value, "bedrock-key"
        )
        self.assertEqual(
            loaded["server"]["providers"]["openai"]["api_key"].value, "openai-key"
        )

    def test_integration_with_standard_yaml(self):
        """Test that our custom tags work with standard YAML functions."""
        # Create test data
        config = {
            "server": {
                "api_key": DeveloperSecret("api-key"),
                "port": 8080,  # Regular value
                "debug": True,  # Regular value
            }
        }

        # Dump using our custom dumper
        yaml_str = yaml.dump(config, Dumper=SecretYamlDumper, default_flow_style=False)

        # Post-process to remove empty quotes if any
        processed_yaml = yaml_str.replace(" ''", "")

        # Load using our custom loader
        loaded = yaml.load(processed_yaml, Loader=SecretYamlLoader)

        # Verify mix of regular and secret values
        self.assertEqual(loaded["server"]["port"], 8080)
        self.assertEqual(loaded["server"]["debug"], True)
        self.assertIsInstance(loaded["server"]["api_key"], DeveloperSecret)
        self.assertEqual(loaded["server"]["api_key"].value, "api-key")


if __name__ == "__main__":
    unittest.main()
