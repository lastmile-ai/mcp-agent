"""Generate a test JWT token for integration tests.

This script creates a valid JWT token that can be used for testing the secrets API.
It uses the same signing process as the web app.

Usage:
    python -m tests.fixtures.test_jwt_generator
"""

import os
import uuid
import sys
from pathlib import Path

# Import the JWT generator from the utils package
from tests.utils.jwt_generator import generate_jwt

def generate_test_token():
    """Generate a test JWT token for API access.
    
    Returns:
        str: A formatted JWT token with the lm_mcp_api_ prefix
    """
    # Try to get the NEXTAUTH_SECRET from the environment
    nextauth_secret = os.environ.get("NEXTAUTH_SECRET")
    
    # If not in environment, try to read from www/.env file
    if not nextauth_secret:
        # Try to find the www/.env file relative to this script
        base_dir = Path(__file__).parent.parent.parent.parent.parent  # mcp-agent-cloud directory
        env_path = base_dir / "www" / ".env"
        
        if env_path.exists():
            print(f"Reading NEXTAUTH_SECRET from {env_path}")
            with open(env_path, "r") as f:
                for line in f:
                    if line.startswith("NEXTAUTH_SECRET="):
                        # Extract value between quotes if present
                        parts = line.strip().split("=", 1)
                        if len(parts) == 2:
                            secret = parts[1].strip()
                            # Remove surrounding quotes if present
                            if (secret.startswith('"') and secret.endswith('"')) or \
                                (secret.startswith("'") and secret.endswith("'")):
                                secret = secret[1:-1]
                            nextauth_secret = secret
                            os.environ["NEXTAUTH_SECRET"] = nextauth_secret
                            print(f"Found NEXTAUTH_SECRET in .env file")
                            break
    
    # If still not found, use the hardcoded value
    if not nextauth_secret:
        print("Warning: NEXTAUTH_SECRET not found in environment or .env. Using hardcoded secret.")
        nextauth_secret = "testsecretfortestinglocalapidevelopmentonly"
        os.environ["NEXTAUTH_SECRET"] = nextauth_secret
    
    # Generate a test token
    user_id = f"test-user-{uuid.uuid4()}"
    token = generate_jwt(
        user_id=user_id,
        email="test@example.com",
        api_token=True,
        prefix=True,  # Add the lm_mcp_api_ prefix
        nextauth_secret=nextauth_secret
    )
    
    return token


if __name__ == "__main__":
    token = generate_test_token()
    print(f"Test JWT Token (full): {token}")
    print(f"Test JWT Token (masked): {token[:30]}...{token[-10:]}")
    print("\nUse this token for testing the API:")
    print(f"export MCP_API_KEY='{token}'")