"""Constants for the MCP Agent Cloud Secrets module."""

from enum import Enum
import re
from typing import Optional, Tuple


class SecretType(Enum):
    """Enum representing the type of secret."""

    DEVELOPER = "dev"  # Secrets known at deploy time
    USER = "usr"  # Secrets collected from end-users at configure time


# Standard UUID pattern for secret IDs
# The API now returns standard UUIDs directly
UUID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"

# Support for test UUIDs in test environments (allows letters in some segments)
TEST_UUID_PATTERN = r"^[0-9a-f]{8}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{12}$"

# Combined pattern for UUID validation
HANDLE_PATTERN = re.compile(f"({UUID_PATTERN})|({TEST_UUID_PATTERN})")

# Environment variable names
ENV_API_BASE_URL = "MCP_API_BASE_URL"
ENV_API_KEY = "MCP_API_KEY"

# Default values
DEFAULT_API_BASE_URL = "http://localhost:3000/api"
