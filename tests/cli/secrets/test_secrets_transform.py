"""Tests for secret transformation functionality.

This file tests the core functionality of transforming configurations with secret tags
into deployment-ready configurations with secret handles.
"""

import pytest
from unittest.mock import AsyncMock, patch

from mcp_agent_cloud.secrets.processor import (
    transform_config_recursive,
    process_secrets_in_config_str,
    process_config_secrets,
)
from mcp_agent_cloud.secrets.yaml_tags import (
    DeveloperSecret,
    UserSecret,
    load_yaml_with_secrets,
)
from mcp_agent_cloud.core.constants import (
    MCP_DEPLOYED_SECRETS_FILENAME,
    MCP_SECRETS_FILENAME,
    SecretType,
    UUID_PREFIX,
)


@pytest.fixture
def mock_secrets_client():
    """Create a mock SecretsClient."""
    client = AsyncMock()

    # Mock the create_secret method to return UUIDs with correct prefix
    async def mock_create_secret(name, secret_type, value):
        # Check that value is required for all secret types
        if value is None or value.strip() == "":
            raise ValueError(f"Secret '{name}' requires a non-empty value")

        # Create predictable but unique UUIDs for testing
        if secret_type == SecretType.DEVELOPER:
            # Use the required prefix from the constants
            return f"{UUID_PREFIX}12345678-abcd-1234-efgh-dev-{name.replace('.', '-')}"
        elif secret_type == SecretType.USER:
            return f"{UUID_PREFIX}98765432-wxyz-9876-abcd-usr-{name.replace('.', '-')}"
        else:
            raise ValueError(f"Invalid secret type: {secret_type}")

    client.create_secret.side_effect = mock_create_secret
    return client


class TestTransformConfigRecursive:
    """Tests for the transform_config_recursive function."""

    @pytest.mark.asyncio
    async def test_transform_developer_secret(self, mock_secrets_client):
        """Test transforming developer secrets to UUIDs."""
        # Create a config with a developer secret
        config = {"api": {"key": DeveloperSecret("test-api-key")}}

        # Transform the config - mock typer.prompt to avoid terminal interaction
        with (
            patch("typer.prompt", return_value="test-value"),
            patch.dict("os.environ", {}, clear=True),
        ):
            result = await transform_config_recursive(
                config, mock_secrets_client
            )

        # Verify the result
        assert "api" in result
        assert "key" in result["api"]

        # Developer secret should be replaced with UUID
        dev_uuid = result["api"]["key"]
        assert isinstance(dev_uuid, str)
        assert dev_uuid.startswith(UUID_PREFIX)

        # Verify create_secret was called with the correct value
        mock_secrets_client.create_secret.assert_called_once()
        call_args = mock_secrets_client.create_secret.call_args
        assert call_args[1]["name"] == "api.key"
        assert call_args[1]["secret_type"] == SecretType.DEVELOPER
        assert call_args[1]["value"] in ["test-api-key", "test-value"]

    @pytest.mark.asyncio
    async def test_user_secret_remains(self, mock_secrets_client):
        """Test that user secrets remain as tags during deploy phase."""
        # Create a config with a user secret
        config = {"user": {"password": UserSecret("user-password")}}

        # Transform the config
        result = await transform_config_recursive(config, mock_secrets_client)

        # Verify the user secret remains as a UserSecret object
        assert isinstance(result["user"]["password"], UserSecret)
        assert result["user"]["password"].value == "user-password"

        # Verify create_secret was NOT called for user secrets
        mock_secrets_client.create_secret.assert_not_called()

    @pytest.mark.asyncio
    async def test_mixed_secrets_and_nested_structures(
        self, mock_secrets_client
    ):
        """Test transforming a complex config with both types of secrets."""
        # Create a complex config with both types of secrets
        config = {
            "api": {
                "key": DeveloperSecret("dev-api-key"),
                "user_token": UserSecret("user-token"),
            },
            "database": {
                "password": DeveloperSecret("dev-db-password"),
                "user_password": UserSecret(),  # Empty user secret
            },
            "nested": {
                "level2": {
                    "level3": {
                        "api_key": DeveloperSecret("nested-key"),
                        "user_key": UserSecret("nested-user-key"),
                    }
                },
                "array": [
                    {"secret": DeveloperSecret("array-item-1")},
                    {"secret": UserSecret("array-user-item")},
                ],
            },
        }

        # Transform the config - mock typer.prompt to avoid terminal interaction
        with (
            patch("typer.prompt", return_value="test-value"),
            patch.dict("os.environ", {}, clear=True),
        ):
            result = await transform_config_recursive(
                config, mock_secrets_client
            )

        # Verify developer secrets are transformed
        assert isinstance(result["api"]["key"], str)
        assert result["api"]["key"].startswith(UUID_PREFIX)

        assert isinstance(result["database"]["password"], str)
        assert result["database"]["password"].startswith(UUID_PREFIX)

        assert isinstance(result["nested"]["level2"]["level3"]["api_key"], str)
        assert result["nested"]["level2"]["level3"]["api_key"].startswith(
            UUID_PREFIX
        )

        assert isinstance(result["nested"]["array"][0]["secret"], str)
        assert result["nested"]["array"][0]["secret"].startswith(UUID_PREFIX)

        # Verify user secrets remain as UserSecret objects
        assert isinstance(result["api"]["user_token"], UserSecret)
        assert result["api"]["user_token"].value == "user-token"

        assert isinstance(result["database"]["user_password"], UserSecret)
        assert result["database"]["user_password"].value is None

        assert isinstance(
            result["nested"]["level2"]["level3"]["user_key"], UserSecret
        )
        assert (
            result["nested"]["level2"]["level3"]["user_key"].value
            == "nested-user-key"
        )

        assert isinstance(result["nested"]["array"][1]["secret"], UserSecret)
        assert (
            result["nested"]["array"][1]["secret"].value == "array-user-item"
        )

        # Verify create_secret was called the correct number of times (only for developer secrets)
        assert mock_secrets_client.create_secret.call_count == 4

    @pytest.mark.asyncio
    async def test_environment_variable_resolution(self, mock_secrets_client):
        """Test processing environment variables in developer secrets."""
        # Test with environment variable resolution
        dev_secret = DeveloperSecret("ENV_VAR_NAME")

        # Set up the environment variables
        with (
            patch.dict("os.environ", {"ENV_VAR_NAME": "env-value"}),
            patch("typer.prompt", return_value="should-not-be-used"),
        ):

            # Transform the secret
            result = await transform_config_recursive(
                dev_secret,
                mock_secrets_client,
                "api.key",
                non_interactive=False,
            )

            # Verify the result is a UUID handle
            assert isinstance(result, str)
            assert result.startswith(UUID_PREFIX)

            # Verify create_secret was called with the env var value
            mock_secrets_client.create_secret.assert_called_once()
            args, kwargs = mock_secrets_client.create_secret.call_args
            assert kwargs["value"] == "env-value"

    @pytest.mark.asyncio
    async def test_missing_env_var_with_non_interactive(
        self, mock_secrets_client
    ):
        """Test that missing env vars raise an error in non-interactive mode."""
        # Create developer secret with env var reference
        dev_secret = DeveloperSecret("NON_EXISTENT_ENV_VAR")

        # Ensure env var doesn't exist and run in non-interactive mode
        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(
                ValueError,
                match="Developer secret at .* has no value.*non-interactive is set",
            ),
        ):
            await transform_config_recursive(
                dev_secret,
                mock_secrets_client,
                "server.api_key",
                non_interactive=True,
            )


class TestProcessSecretsInConfig:
    """Tests for the process_secrets_in_config_str function."""

    @pytest.mark.asyncio
    async def test_process_yaml_content(self, mock_secrets_client):
        """Test processing secrets in YAML content."""
        yaml_content = """
        server:
          bedrock:
            api_key: !developer_secret dev-api-key
            user_api_key: !user_secret user-key
        database:
          password: !developer_secret db-password
          user_password: !user_secret
        """

        # Process the YAML content with mocked dependencies
        with (
            patch("typer.prompt", return_value="test-value"),
            patch.dict("os.environ", {}, clear=True),
        ):
            result = await process_secrets_in_config_str(
                input_secrets_content=yaml_content,
                existing_secrets_content=None,
                client=mock_secrets_client,
                non_interactive=False,
            )

        # Verify the output format
        assert result["server"]["bedrock"]["api_key"].startswith(UUID_PREFIX)
        assert isinstance(
            result["server"]["bedrock"]["user_api_key"], UserSecret
        )
        assert result["server"]["bedrock"]["user_api_key"].value == "user-key"
        assert result["database"]["password"].startswith(UUID_PREFIX)
        assert isinstance(result["database"]["user_password"], UserSecret)

        # Verify create_secret was called twice (only for developer secrets)
        assert mock_secrets_client.create_secret.call_count == 2


class TestProcessConfigSecrets:
    """Tests for the process_config_secrets function."""

    @pytest.mark.asyncio
    async def test_process_config_file(self, mock_secrets_client, tmp_path):
        """Test processing secrets in a configuration file."""
        # Create test input file
        input_path = tmp_path / MCP_SECRETS_FILENAME
        output_path = tmp_path / MCP_DEPLOYED_SECRETS_FILENAME
        yaml_content = """
        server:
          bedrock:
            api_key: !developer_secret dev-api-key
            user_api_key: !user_secret user-key
        """

        with open(input_path, "w", encoding="utf-8") as f:
            f.write(yaml_content)

        # Mock the file write operation and other dependencies
        with (
            patch("typer.prompt", return_value="test-value"),
            patch.dict("os.environ", {}, clear=True),
            patch("mcp_agent_cloud.secrets.processor.print_secret_summary"),
        ):
            # Process the config
            result = await process_config_secrets(
                input_path=input_path,
                output_path=output_path,
                client=mock_secrets_client,
                non_interactive=False,
            )

            # Verify the output file was created
            assert output_path.exists()

            # Verify the result contains the expected stats
            assert "developer_secrets" in result
            assert "user_secrets" in result
            assert len(result["developer_secrets"]) == 1
            assert len(result["user_secrets"]) == 1

    @pytest.mark.asyncio
    async def test_reuse_existing_secrets(self, mock_secrets_client, tmp_path):
        """Test reusing existing secrets from output file."""
        # Create test input file
        input_path = tmp_path / MCP_SECRETS_FILENAME
        output_path = tmp_path / MCP_DEPLOYED_SECRETS_FILENAME

        # Input YAML with developer secrets
        input_yaml_content = """
        server:
          bedrock:
            api_key: !developer_secret BEDROCK_API_KEY
            user_api_key: !user_secret user-key
          anthropic:
            api_key: !developer_secret ANTHROPIC_API_KEY
        database:
          password: !developer_secret DB_PASSWORD
        """

        existing_bedrock_api_key = (
            f"{UUID_PREFIX}00000000-1234-1234-1234-123456789000"
        )
        existing_anthropic_api_key = (
            f"{UUID_PREFIX}00000001-1234-1234-1234-123456789001"
        )
        existing_key_to_exclude = (
            f"{UUID_PREFIX}00000002-1234-1234-1234-123456789002"
        )

        # Existing output YAML with some transformed secrets
        existing_output_yaml = f"""
        server:
          bedrock:
            api_key: {existing_bedrock_api_key}
            user_api_key: !user_secret user-key
          anthropic:
            api_key: {existing_anthropic_api_key}
        # This key doesn't exist in the new input
        removed:
          key: {existing_key_to_exclude}
        """

        # Write the files
        with open(input_path, "w", encoding="utf-8") as f:
            f.write(input_yaml_content)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(existing_output_yaml)

        # Set up our mocks
        with (
            patch("typer.prompt", return_value="test-value"),
            patch.dict("os.environ", {}, clear=True),
            patch("mcp_agent_cloud.secrets.processor.print_secret_summary"),
        ):

            # Process the config with existing output
            result = await process_config_secrets(
                input_path=input_path,
                output_path=output_path,
                client=mock_secrets_client,
                non_interactive=False,
            )

            # Read the updated output file
            with open(output_path, "r", encoding="utf-8") as f:
                updated_output = f.read()

            deployed_secrets_yaml = load_yaml_with_secrets(updated_output)

            print(f"Updated output:\n{updated_output}")
            # Verify the output contains reused secrets
            assert (
                deployed_secrets_yaml["server"]["bedrock"]["api_key"]
                == existing_bedrock_api_key
            )
            assert (
                deployed_secrets_yaml["server"]["anthropic"]["api_key"]
                == existing_anthropic_api_key
            )

            # Verify the removed key is no longer in the output
            assert "removed" not in deployed_secrets_yaml

            # Verify the new key was added and transformed
            assert isinstance(
                deployed_secrets_yaml["database"]["password"], str
            )
            assert deployed_secrets_yaml["database"]["password"].startswith(
                UUID_PREFIX
            )

            # Verify user_api_key remains as UserSecret
            assert isinstance(
                deployed_secrets_yaml["server"]["bedrock"]["user_api_key"],
                UserSecret,
            )
            assert (
                deployed_secrets_yaml["server"]["bedrock"][
                    "user_api_key"
                ].value
                == "user-key"
            )

            # Verify the context has the correct stats
            assert "developer_secrets" in result
            assert "user_secrets" in result
            assert "reused_secrets" in result
            # Check if we have exactly 1 new secret and 2 reused secrets
            assert len(result["developer_secrets"]) == 1  # Only DB_PASSWORD
            assert (
                len(result["reused_secrets"]) == 2
            )  # The bedrock and anthropic keys
            assert len(result["user_secrets"]) == 1  # user_api_key
