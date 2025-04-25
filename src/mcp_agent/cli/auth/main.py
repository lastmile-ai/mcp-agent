import os
from typing import Optional

from .constants import DEFAULT_CREDENTIALS_PATH


def save_api_key_credentials(api_key: str):
    """Save an API key to the credentials file.

    Args:
        api_key: API key to persist

    Returns:
        None
    """
    credentials_path = os.path.expanduser(DEFAULT_CREDENTIALS_PATH)
    os.makedirs(os.path.dirname(credentials_path), exist_ok=True)
    with open(credentials_path, "w", encoding="utf-8") as f:
        f.write(api_key)


def load_api_key_credentials() -> Optional[str]:
    """Load an API key from the credentials file.

    Returns:
        String. API key if it exists, None otherwise
    """
    credentials_path = os.path.expanduser(DEFAULT_CREDENTIALS_PATH)
    if os.path.exists(credentials_path):
        with open(credentials_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return None
