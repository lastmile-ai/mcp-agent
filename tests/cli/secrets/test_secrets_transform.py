"""Tests for secret transformation functionality.

This file tests the core functionality of transforming configurations with raw secrets
into deployment-ready configurations with secret handles.
"""

from unittest.mock import AsyncMock, patch

import pytest
from mcp_agent.cli.core.constants import (
    MCP_DEPLOYED_SECRETS_FILENAME,
    MCP_SECRETS_FILENAME,
    UUID_PREFIX,
    SecretType,
)
from mcp_agent.cli.secrets.processor import (
    process_config_secrets,
    process_secrets_in_config_str,
    transform_config_recursive,
)
from mcp_agent.cli.secrets.yaml_tags import (
    DeveloperSecret,
    UserSecret,
    load_yaml_with_secrets,
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
    async def test_transform_deployment_secret(self, mock_secrets_client):
        """Test transforming raw secrets to deployment secret handles."""
        # Create a config with raw secret values
        config = {"api": {"key": "test-api-key-value"}}

        # Transform the config - mock user choosing deployment secret (option 1)
        with (
            patch("rich.prompt.Prompt.ask", return_value="1"),
            patch.dict("os.environ", {}, clear=True),
        ):
            result = await transform_config_recursive(config, mock_secrets_client)

        # Verify the result
        assert "api" in result
        assert "key" in result["api"]

        # Raw secret should be replaced with UUID handle
        secret_handle = result["api"]["key"]
        assert isinstance(secret_handle, str)
        assert secret_handle.startswith(UUID_PREFIX)

        # Verify create_secret was called with the correct value
        mock_secrets_client.create_secret.assert_called_once()
        call_args = mock_secrets_client.create_secret.call_args
        assert call_args[1]["name"] == "api.key"
        assert call_args[1]["secret_type"] == SecretType.DEVELOPER
        assert call_args[1]["value"] == "test-api-key-value"

    @pytest.mark.asyncio
    async def test_user_secret_remains(self, mock_secrets_client):
        """Test that user secrets become tags when user chooses option 2."""
        # Create a config with raw secret value
        config = {"user": {"password": "user-password-value"}}

        # Transform the config - mock user choosing user secret (option 2)
        with (
            patch("rich.prompt.Prompt.ask", return_value="2"),
            patch.dict("os.environ", {}, clear=True),
        ):
            result = await transform_config_recursive(config, mock_secrets_client)

        # Verify the raw secret becomes a UserSecret object
        assert isinstance(result["user"]["password"], UserSecret)
        # UserSecret objects don't store the original value in the new approach
        assert result["user"]["password"].value is None

        # Verify create_secret was NOT called for user secrets
        mock_secrets_client.create_secret.assert_not_called()

    @pytest.mark.asyncio
    async def test_mixed_secrets_and_nested_structures(self, mock_secrets_client):
        """Test transforming a complex config with both types of secrets."""
        # Create a complex config with raw secret values
        config = {
            "api": {
                "key": "dev-api-key-value",
                "user_token": "user-token-value",
            },
            "database": {
                "password": "dev-db-password-value",
                "user_password": "user-password-value",
            },
            "nested": {
                "level2": {
                    "level3": {
                        "api_key": "nested-key-value",
                        "user_key": "nested-user-key-value",
                    }
                },
                "array": [
                    {"secret": "array-item-1-value"},
                    {"secret": "array-user-item-value"},
                ],
            },
        }

        # Mock the Prompt.ask to alternate between deployment (1) and user (2) secrets
        mock_responses = ["1", "2", "1", "2", "1", "2", "1", "2"]  # 8 secrets total

        with (
            patch("rich.prompt.Prompt.ask", side_effect=mock_responses),
            patch.dict("os.environ", {}, clear=True),
        ):
            result = await transform_config_recursive(
                config, mock_secrets_client, non_interactive=False
            )

        # Verify deployment secrets (every odd position) are transformed to handles
        assert isinstance(result["api"]["key"], str)
        assert result["api"]["key"].startswith(UUID_PREFIX)

        assert isinstance(result["database"]["password"], str)
        assert result["database"]["password"].startswith(UUID_PREFIX)

        assert isinstance(result["nested"]["level2"]["level3"]["api_key"], str)
        assert result["nested"]["level2"]["level3"]["api_key"].startswith(UUID_PREFIX)

        assert isinstance(result["nested"]["array"][0]["secret"], str)
        assert result["nested"]["array"][0]["secret"].startswith(UUID_PREFIX)

        # Verify user secrets (every even position) remain as UserSecret objects
        assert isinstance(result["api"]["user_token"], UserSecret)
        assert result["api"]["user_token"].value is None

        assert isinstance(result["database"]["user_password"], UserSecret)
        assert result["database"]["user_password"].value is None

        assert isinstance(result["nested"]["level2"]["level3"]["user_key"], UserSecret)
        assert result["nested"]["level2"]["level3"]["user_key"].value is None

        assert isinstance(result["nested"]["array"][1]["secret"], UserSecret)
        assert result["nested"]["array"][1]["secret"].value is None

        # Verify create_secret was called 4 times (only for deployment secrets)
        assert mock_secrets_client.create_secret.call_count == 4

    @pytest.mark.asyncio
    async def test_raw_secret_processing_non_interactive(self, mock_secrets_client):
        """Test processing raw secrets in non-interactive mode (becomes deployment secret)."""
        # In non-interactive mode, all raw secrets become deployment secrets
        config = {"api": {"key": "my-secret-value"}}

        # Transform in non-interactive mode
        result = await transform_config_recursive(
            config,
            mock_secrets_client,
            non_interactive=True,
        )

        # Verify the result contains deployment secret handles
        assert isinstance(result["api"]["key"], str)
        assert result["api"]["key"].startswith(UUID_PREFIX)

        # Verify create_secret was called with the raw value
        mock_secrets_client.create_secret.assert_called_once()
        _args, kwargs = mock_secrets_client.create_secret.call_args
        assert kwargs["name"] == "api.key"
        assert kwargs["value"] == "my-secret-value"
        assert kwargs["secret_type"] == SecretType.DEVELOPER

    @pytest.mark.asyncio
    async def test_empty_secret_value_skipped(self, mock_secrets_client):
        """Test that empty secret values are skipped."""
        # Create config with empty secret value
        config = {"server": {"api_key": ""}}

        # Empty secret should be skipped, not raise an error
        result = await transform_config_recursive(
            config,
            mock_secrets_client,
            non_interactive=True,
        )

        # The secret should be skipped, so the key shouldn't be in the result
        assert "server" not in result

    @pytest.mark.asyncio
    async def test_tagged_secrets_rejected_in_input(self, mock_secrets_client):
        """Test that tagged secrets in input are rejected with clear error."""
        dev_secret = DeveloperSecret("some-value")
        user_secret = UserSecret()

        # Attempt to transform the tagged secret - should be rejected
        with pytest.raises(
            ValueError,
            match="Input secrets config at .* contains secret tag. Input should contain raw secrets, not tags.",
        ):
            await transform_config_recursive(
                dev_secret, mock_secrets_client, "server.api_key", non_interactive=True
            )

        with pytest.raises(
            ValueError,
            match="Input secrets config at .* contains secret tag. Input should contain raw secrets, not tags.",
        ):
            await transform_config_recursive(
                user_secret, mock_secrets_client, "server.api_key", non_interactive=True
            )


class TestProcessSecretsInConfig:
    """Tests for the process_secrets_in_config_str function."""

    @pytest.mark.asyncio
    async def test_process_yaml_content(self, mock_secrets_client):
        """Test processing secrets in YAML content."""
        yaml_content = """
        server:
          bedrock:
            api_key: dev-api-key-value
            user_api_key: user-key-value
        database:
          password: db-password-value
          user_password: user-password-value
        """

        # Mock user choices: deployment, user, deployment, user
        mock_responses = ["1", "2", "1", "2"]

        # Process the YAML content with mocked dependencies
        with (
            patch("rich.prompt.Prompt.ask", side_effect=mock_responses),
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
        assert isinstance(result["server"]["bedrock"]["user_api_key"], UserSecret)
        assert result["server"]["bedrock"]["user_api_key"].value is None
        assert result["database"]["password"].startswith(UUID_PREFIX)
        assert isinstance(result["database"]["user_password"], UserSecret)

        # Verify create_secret was called twice (only for deployment secrets)
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
            api_key: dev-api-key-value
            user_api_key: user-key-value
        """

        with open(input_path, "w", encoding="utf-8") as f:
            f.write(yaml_content)

        # Mock user choices: deployment, user
        mock_responses = ["1", "2"]

        # Mock the file write operation and other dependencies
        with (
            patch("rich.prompt.Prompt.ask", side_effect=mock_responses),
            patch.dict("os.environ", {}, clear=True),
            patch("mcp_agent.cli.secrets.processor.print_secret_summary"),
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

            with open(output_path, "r", encoding="utf-8") as f:
                output_content = f.read()
            deployed_secrets_yaml = load_yaml_with_secrets(output_content)
            assert deployed_secrets_yaml["server"]["bedrock"]["api_key"].startswith(
                UUID_PREFIX
            )
            assert isinstance(
                deployed_secrets_yaml["server"]["bedrock"]["user_api_key"], UserSecret
            )

            # Verify the result contains the expected stats
            assert "deployment_secrets" in result
            assert "user_secrets" in result
            assert len(result["deployment_secrets"]) == 1
            assert len(result["user_secrets"]) == 1

    @pytest.mark.asyncio
    async def test_reuse_existing_secrets(self, mock_secrets_client, tmp_path):
        """Test reusing existing secrets from output file."""
        # Create test input file
        input_path = tmp_path / MCP_SECRETS_FILENAME
        output_path = tmp_path / MCP_DEPLOYED_SECRETS_FILENAME

        # Input YAML with raw secret values
        input_yaml_content = """
        server:
          bedrock:
            api_key: bedrock-secret-value
            user_api_key: user-key-value
          anthropic:
            api_key: anthropic-secret-value
        database:
          password: db-password-value
        """

        existing_bedrock_api_key = f"{UUID_PREFIX}00000000-1234-1234-1234-123456789000"
        existing_anthropic_api_key = (
            f"{UUID_PREFIX}00000001-1234-1234-1234-123456789001"
        )
        existing_key_to_exclude = f"{UUID_PREFIX}00000002-1234-1234-1234-123456789002"

        # Existing output YAML with some transformed secrets
        existing_output_yaml = f"""
        server:
          bedrock:
            api_key: {existing_bedrock_api_key}
            user_api_key: !user_secret
          anthropic:
            api_key: {existing_anthropic_api_key}
        # This key doesn't exist in the new input - should be excluded
        removed:
          key: {existing_key_to_exclude}
        """

        # Write the files
        with open(input_path, "w", encoding="utf-8") as f:
            f.write(input_yaml_content)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(existing_output_yaml)

        # Mock get_secret_value to return values that match input for reuse
        async def mock_get_secret_value(secret_handle):
            if secret_handle == existing_bedrock_api_key:
                return "bedrock-secret-value"
            elif secret_handle == existing_anthropic_api_key:
                return "anthropic-secret-value"
            elif secret_handle == existing_key_to_exclude:
                return "old-removed-value"
            return None

        mock_secrets_client.get_secret_value.side_effect = mock_get_secret_value

        # Mock user choices and prompts
        # Only user_api_key and database.password need choices (bedrock and anthropic api_key are reused)
        mock_responses = [
            "2",
            "1",
        ]  # user secret for user_api_key, deployment for database.password
        mock_confirmations = [True]  # Exclude the removed key

        # Set up our mocks
        with (
            patch("rich.prompt.Prompt.ask", side_effect=mock_responses),
            patch("typer.confirm", side_effect=mock_confirmations),
            patch.dict("os.environ", {}, clear=True),
            patch("mcp_agent.cli.secrets.processor.print_secret_summary"),
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
            assert isinstance(deployed_secrets_yaml["database"]["password"], str)
            assert deployed_secrets_yaml["database"]["password"].startswith(UUID_PREFIX)

            # Verify user_api_key remains as UserSecret
            assert isinstance(
                deployed_secrets_yaml["server"]["bedrock"]["user_api_key"],
                UserSecret,
            )

            # Verify the context has the correct stats
            assert "deployment_secrets" in result
            assert "user_secrets" in result
            assert "reused_secrets" in result
            # Check if we have exactly 1 new secret and 2 reused secrets
            assert len(result["deployment_secrets"]) == 1  # Only DB_PASSWORD
            assert len(result["reused_secrets"]) == 2  # The bedrock and anthropic keys
            assert len(result["user_secrets"]) == 1  # user_api_key
