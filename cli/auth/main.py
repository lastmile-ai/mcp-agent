import json
import os
import tempfile
from typing import Optional

from .constants import DEFAULT_CREDENTIALS_PATH, ALTERNATE_CREDENTIALS_PATHS
from mcp_agent.cli.utils.ux import print_warning
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

    # Write atomically to avoid partial or trailing content issues
    # Use a temp file in the same directory, then replace
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=".credentials.json.", dir=cred_dir, text=True
    )
    try:
        with os.fdopen(tmp_fd, "w") as f:
            f.write(credentials.to_json())
            f.flush()
            os.fsync(f.fileno())
        # Ensure restricted permissions (0600)
        try:
            os.chmod(tmp_path, 0o600)
        except OSError:
            pass
        # Atomic replace
        os.replace(tmp_path, credentials_path)
        # Ensure final file perms in case replace inherited different mode
        try:
            os.chmod(credentials_path, 0o600)
        except OSError:
            pass
    finally:
        # Clean up temp if replace failed
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass


def load_credentials() -> Optional[UserCredentials]:
    """Load user credentials from the credentials file.

    Returns:
        UserCredentials object if it exists, None otherwise
    """
    # Try primary location
    primary_path = os.path.expanduser(DEFAULT_CREDENTIALS_PATH)
    paths_to_try = [primary_path] + [
        os.path.expanduser(p) for p in ALTERNATE_CREDENTIALS_PATHS
    ]

    for path in paths_to_try:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return UserCredentials.from_json(f.read())
            except (json.JSONDecodeError, KeyError, ValueError):
                # Corrupted credentials; warn and continue to other locations
                try:
                    print_warning(
                        f"Detected corrupted credentials file at {path}. Please run 'mcp-agent login' again to re-authenticate."
                    )
                except Exception:
                    pass
                continue
    return None


def clear_credentials() -> bool:
    """Clear stored credentials.

    Returns:
        bool: True if credentials were cleared, False if none existed
    """
    removed = False
    paths = [os.path.expanduser(DEFAULT_CREDENTIALS_PATH)] + [
        os.path.expanduser(p) for p in ALTERNATE_CREDENTIALS_PATHS
    ]
    for path in paths:
        if os.path.exists(path):
            try:
                os.remove(path)
                removed = True
            except OSError:
                pass
    return removed


def load_api_key_credentials() -> Optional[str]:
    """Load an API key from the credentials file (backward compatibility).

    Returns:
        String. API key if it exists, None otherwise
    """
    credentials = load_credentials()
    return credentials.api_key if credentials else None
