"""
Utility module to generate JWT tokens for testing the secrets service API.

This module generates JWT tokens compatible with the validation in the web app's
validateApiToken function, which is used to authenticate requests to the secrets API.

Usage as a script:
    python -m tests.utils.jwt_generator [--user-id USER_ID] [--email EMAIL] [--name NAME] [--api-token] [--prefix]

Example:
    python -m tests.utils.jwt_generator --user-id "test-user-123" --email "test@example.com" --api-token --prefix
"""

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import uuid

# Constants
API_TOKEN_PREFIX = "lm_mcp_api_"
MAX_TOKEN_AGE = 60 * 60 * 24 * 365 * 5  # 5 years (same as in the web app)


def base64url_encode(data):
    """
    Base64url encoding as specified in RFC 7515.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")

    encoded = base64.urlsafe_b64encode(data).rstrip(b"=")
    return encoded.decode("utf-8")


def simple_jwt_encode(payload, secret):
    """
    Simple JWT encoder without external libraries.

    Args:
        payload: Dict containing the JWT claims
        secret: Secret key for signing

    Returns:
        JWT token string
    """
    if isinstance(secret, str):
        secret = secret.encode("utf-8")

    # Create JWT header
    header = {"alg": "HS256", "typ": "JWT"}

    # Encode header and payload
    header_encoded = base64url_encode(json.dumps(header, separators=(",", ":")))
    payload_encoded = base64url_encode(json.dumps(payload, separators=(",", ":")))

    # Create signature
    signing_input = f"{header_encoded}.{payload_encoded}".encode("utf-8")
    signature = hmac.new(secret, signing_input, hashlib.sha256).digest()
    signature_encoded = base64url_encode(signature)

    # Return complete JWT
    return f"{header_encoded}.{payload_encoded}.{signature_encoded}"


def generate_jwt(
    user_id: str,
    email: str = None,
    name: str = None,
    api_token: bool = True,
    prefix: bool = False,
    nextauth_secret: str = None,
    expiry_days: int = 365,
):
    """
    Generate a JWT token compatible with validateApiToken in the web app.

    Args:
        user_id: The user ID to include in the token
        email: Optional email to include in the token
        name: Optional name to include in the token
        api_token: Whether this is an API token (vs a session token)
        prefix: Whether to add the API_TOKEN_PREFIX to the token
        nextauth_secret: The secret used to sign the token (if not provided, will look for env var)
        expiry_days: Number of days until token expiry

    Returns:
        The generated JWT token as a string
    """
    # Get the NEXTAUTH_SECRET from environment or .env file if not provided
    if not nextauth_secret:
        # First check environment variable
        nextauth_secret = os.environ.get("NEXTAUTH_SECRET")

        # If not in environment, try to read from www/.env file
        if not nextauth_secret:
            env_path = "/home/ubuntu/lmai/mcp-agent-cloud/www/.env"
            if os.path.exists(env_path):
                with open(env_path, "r") as f:
                    for line in f:
                        if line.startswith("NEXTAUTH_SECRET="):
                            # Extract value between quotes if present
                            parts = line.strip().split("=", 1)
                            if len(parts) == 2:
                                secret = parts[1].strip()
                                # Remove surrounding quotes if present
                                if (
                                    secret.startswith('"') and secret.endswith('"')
                                ) or (secret.startswith("'") and secret.endswith("'")):
                                    secret = secret[1:-1]
                                nextauth_secret = secret
                                break

        # If still not found, use the hardcoded value from the .env file
        if not nextauth_secret:
            nextauth_secret = "3Jk0h98K1KKB7Jyh3/Kgp0bAKM0DSMcx1Jk7FJ6boNw"
            print(
                "Warning: Using hardcoded NEXTAUTH_SECRET for testing.", file=sys.stderr
            )

    # Calculate expiry time
    now = int(time.time())
    expiry = now + (60 * 60 * 24 * expiry_days)  # days to seconds

    # Construct the token payload
    payload = {
        # Standard JWT claims
        "iat": now,  # Issued at time
        "exp": expiry,  # Expiry time
        "jti": str(uuid.uuid4()),  # JWT ID - unique identifier for the token
        # NextAuth specific claims
        "id": user_id,  # User ID
    }

    # Add optional fields
    if email:
        payload["email"] = email

    if name:
        payload["name"] = name

    # Add API token flag - this mirrors the structure in createApiToken
    if api_token:
        payload["apiToken"] = True

    # Sign the token
    token = simple_jwt_encode(payload, nextauth_secret)

    # Add prefix if requested
    if prefix and api_token:
        return f"{API_TOKEN_PREFIX}{token}"
    else:
        return token


def main():
    parser = argparse.ArgumentParser(
        description="Generate JWT tokens for testing the secrets service API"
    )
    parser.add_argument(
        "--user-id", default=str(uuid.uuid4()), help="User ID to include in the token"
    )
    parser.add_argument("--email", help="Email to include in the token")
    parser.add_argument("--name", help="Name to include in the token")
    parser.add_argument(
        "--api-token", action="store_true", help="Include apiToken: true in the payload"
    )
    parser.add_argument(
        "--prefix", action="store_true", help="Add the API_TOKEN_PREFIX to the token"
    )
    parser.add_argument(
        "--nextauth-secret",
        help="Secret to use for signing (defaults to NEXTAUTH_SECRET env var)",
    )
    parser.add_argument(
        "--expiry-days", type=int, default=365, help="Number of days until token expiry"
    )

    args = parser.parse_args()

    token = generate_jwt(
        user_id=args.user_id,
        email=args.email,
        name=args.name,
        api_token=args.api_token,
        prefix=args.prefix,
        nextauth_secret=args.nextauth_secret,
        expiry_days=args.expiry_days,
    )

    print(token)


def generate_test_token():
    return generate_jwt(
        user_id="user_id",
        email="email",
        name="name",
        api_token=True,
        prefix=True,
        nextauth_secret="nextauthsecret",
        expiry_days=365,
    )


if __name__ == "__main__":
    main()
