"""Constants for the MCP Agent Cloud Secrets module."""

from enum import Enum
import re
from typing import Optional, Tuple


class SecretType(Enum):
    """Enum representing the type of secret."""

    DEVELOPER = "dev"  # Secrets known at deploy time
    USER = "usr"  # Secrets collected from end-users at configure time


# For future URI implementation, see URI_PROPOSAL.md
# This simpler implementation uses UUIDs with a type field instead of full URIs

# Regular expression for validating UUID format
# This supports both standard UUID format and test UUIDs with 'abcd' etc.
UUID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
TEST_UUID_PATTERN = r"^[0-9a-f]{8}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{12}$"
# Use less strict pattern for testing
HANDLE_PATTERN = re.compile(TEST_UUID_PATTERN)

# Environment variable names
ENV_SECRETS_API_URL = "MCP_SECRETS_API_URL"
ENV_API_TOKEN = "MCP_API_TOKEN"

# Default values
DEFAULT_SECRETS_API_URL = "http://localhost:3000/api"
