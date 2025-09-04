import json
import os
from typing import Optional

from .constants import DEFAULT_CREDENTIALS_PATH
from .models import UserCredentials


def save_credentials(credentials: UserCredentials) -> None:
    """Save user credentials to the credentials file.

    Args:
        credentials: UserCredentials object to persist

    Returns:
        None
    """
    credentials_path = os.path.expanduser(DEFAULT_CREDENTIALS_PATH)
    cred_dir = os.path.dirname(credentials_path)
    os.makedirs(cred_dir, exist_ok=True)
    try:
        os.chmod(cred_dir, 0o700)
    except OSError:
        pass

    # Create file with restricted permissions (0600) to prevent leakage
    fd = os.open(credentials_path, os.O_WRONLY | os.O_CREAT, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(credentials.to_json())


def load_credentials() -> Optional[UserCredentials]:
    """Load user credentials from the credentials file.

    Returns:
        UserCredentials object if it exists, None otherwise
    """
    credentials_path = os.path.expanduser(DEFAULT_CREDENTIALS_PATH)
    if os.path.exists(credentials_path):
        try:
            with open(credentials_path, "r", encoding="utf-8") as f:
                return UserCredentials.from_json(f.read())
        except (json.JSONDecodeError, KeyError, ValueError):
            # Handle corrupted or old format credentials
            return None
    return None


def clear_credentials() -> bool:
    """Clear stored credentials.

    Returns:
        bool: True if credentials were cleared, False if none existed
    """
    credentials_path = os.path.expanduser(DEFAULT_CREDENTIALS_PATH)
    if os.path.exists(credentials_path):
        os.remove(credentials_path)
        return True
    return False


def load_api_key_credentials() -> Optional[str]:
    """Load an API key from the credentials file (backward compatibility).

    Returns:
        String. API key if it exists, None otherwise
    """
    credentials = load_credentials()
    return credentials.api_key if credentials else None
