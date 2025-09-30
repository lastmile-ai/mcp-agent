"""
Standalone OAuth Flow Demonstration

This script demonstrates the OAuth flow for authenticating with GitHub
and storing tokens for use with MCP agents. This is useful for:
- Understanding the OAuth process
- Testing token acquisition and storage
- Debugging authentication issues
- Setting up tokens for the first time

Run this script interactively to authenticate with GitHub and store tokens.
"""

import asyncio
import json
import os
import secrets
import time
import urllib.parse
import webbrowser
from typing import Any, Dict, Optional

import aiohttp
from aiohttp import web


class GitHubOAuthDemo:
    """
    Demonstration of GitHub OAuth flow for MCP agent authentication.
    """

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str = None):
        """
        Initialize OAuth demo.

        Args:
            client_id: GitHub OAuth app client ID
            client_secret: GitHub OAuth app client secret
            redirect_uri: OAuth redirect URI (defaults to localhost)
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri or "http://localhost:8080/internal/oauth/callback"
        self.state = secrets.token_urlsafe(32)  # CSRF protection
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.token_expires_at: Optional[float] = None

    def get_authorization_url(self, scopes: list = None) -> str:
        """
        Generate the GitHub authorization URL.

        Args:
            scopes: List of OAuth scopes to request

        Returns:
            Authorization URL for the user to visit
        """
        if scopes is None:
            scopes = ["read:org", "public_repo"]  # Default scopes for GitHub MCP server

        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(scopes),
            "state": self.state,
            "response_type": "code",
        }

        base_url = "https://github.com/login/oauth/authorize"
        return f"{base_url}?{urllib.parse.urlencode(params)}"

    async def exchange_code_for_token(self, code: str, state: str) -> Dict[str, Any]:
        """
        Exchange authorization code for access token.

        Args:
            code: Authorization code from GitHub
            state: State parameter for CSRF protection

        Returns:
            Token response data

        Raises:
            ValueError: If state doesn't match or token exchange fails
        """
        if state != self.state:
            raise ValueError("State parameter mismatch - possible CSRF attack")

        token_url = "https://github.com/login/oauth/access_token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": self.redirect_uri,
        }

        headers = {
            "Accept": "application/json",
            "User-Agent": "MCP-Agent-OAuth-Demo/1.0"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(token_url, data=data, headers=headers) as response:
                if response.status != 200:
                    raise ValueError(f"Token exchange failed: {response.status}")

                token_data = await response.json()

                if "error" in token_data:
                    raise ValueError(f"Token error: {token_data['error_description']}")

                self.access_token = token_data.get("access_token")
                self.refresh_token = token_data.get("refresh_token")

                # Calculate expiration time
                expires_in = token_data.get("expires_in")
                if expires_in:
                    self.token_expires_at = time.time() + expires_in
                else:
                    # GitHub tokens typically don't expire, but set a far future date
                    self.token_expires_at = time.time() + (365 * 24 * 3600)  # 1 year

                return token_data

    async def test_token(self) -> Dict[str, Any]:
        """
        Test the access token by making a simple GitHub API call.

        Returns:
            User information from GitHub API
        """
        if not self.access_token:
            raise ValueError("No access token available")

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "MCP-Agent-OAuth-Demo/1.0"
        }

        async with aiohttp.ClientSession() as session:
            # Test with a simple user info call
            async with session.get("https://api.github.com/user", headers=headers) as response:
                if response.status != 200:
                    raise ValueError(f"Token test failed: {response.status}")

                user_data = await response.json()
                return user_data

    def get_token_for_mcp_agent(self) -> Dict[str, Any]:
        """
        Get token data in the format expected by MCP agent workflow_pre_auth.

        Returns:
            Token data dictionary for MCP agent
        """
        if not self.access_token:
            raise ValueError("No access token available")

        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "server_name": "github",
            "scopes": ["read:org", "public_repo"],
            "expires_at": self.token_expires_at,
            "authorization_server": "https://github.com/login/oauth/authorize",
            "token_type": "Bearer"
        }

    async def save_token_to_file(self, filename: str = "github_oauth_token.json"):
        """
        Save the token to a JSON file for later use.

        Args:
            filename: File to save token data
        """
        token_data = self.get_token_for_mcp_agent()

        with open(filename, 'w') as f:
            json.dump(token_data, f, indent=2)

        print(f"Token saved to {filename}")
        print("You can now use this token with the MCP agent workflow_pre_auth endpoint.")

    async def run_oauth_flow(self, scopes: list = None) -> Dict[str, Any]:
        """
        Run the complete OAuth flow interactively.

        Args:
            scopes: OAuth scopes to request

        Returns:
            Complete token data
        """
        print("Starting GitHub OAuth flow...")
        print("=" * 50)

        # Step 1: Generate authorization URL
        auth_url = self.get_authorization_url(scopes)
        print("\n1. Please visit this URL to authorize the application:")
        print(f"   {auth_url}")
        print("\n2. After authorization, you'll be redirected to a callback URL.")

        # Step 2: Start local server to handle callback
        callback_received = asyncio.Event()
        callback_data = {}

        async def handle_callback(request):
            nonlocal callback_data
            try:
                code = request.query.get('code')
                state = request.query.get('state')
                error = request.query.get('error')

                if error:
                    callback_data['error'] = error
                    callback_data['error_description'] = request.query.get('error_description', '')
                else:
                    callback_data['code'] = code
                    callback_data['state'] = state

                callback_received.set()

                # Return a simple success page
                html = """
                <html>
                <body>
                    <h2>OAuth Authorization Complete</h2>
                    <p>You can close this window and return to the terminal.</p>
                    <script>setTimeout(() => window.close(), 3000);</script>
                </body>
                </html>
                """
                return web.Response(text=html, content_type='text/html')

            except Exception as e:
                print(f"Error in callback handler: {e}")
                return web.Response(text=f"Error: {e}", status=500)

        # Start local server
        app = web.Application()
        app.router.add_get('/internal/oauth/callback', handle_callback)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, 'localhost', 8080)
        await site.start()

        print("\n3. Local callback server started on http://localhost:8080")
        print("   Opening browser to authorization URL...")

        # Open browser automatically
        try:
            webbrowser.open(auth_url)
        except Exception:
            print("   (Could not open browser automatically)")

        print("\n4. Waiting for authorization callback...")

        # Wait for callback with timeout
        try:
            await asyncio.wait_for(callback_received.wait(), timeout=300)  # 5 minute timeout
        except asyncio.TimeoutError:
            print("   Timeout waiting for authorization callback")
            await runner.cleanup()
            raise ValueError("OAuth flow timeout")

        await runner.cleanup()

        # Step 3: Handle callback result
        if 'error' in callback_data:
            raise ValueError(f"OAuth error: {callback_data['error']} - {callback_data.get('error_description', '')}")

        code = callback_data.get('code')
        state = callback_data.get('state')

        if not code:
            raise ValueError("No authorization code received")

        print("5. Authorization code received, exchanging for access token...")

        # Step 4: Exchange code for token
        await self.exchange_code_for_token(code, state)
        print("   ✓ Access token obtained successfully")

        # Step 5: Test the token
        print("6. Testing access token...")
        try:
            user_info = await self.test_token()
            username = user_info.get('login', 'unknown')
            print(f"   ✓ Token test successful - authenticated as: {username}")
        except Exception as e:
            print(f"   ⚠ Token test failed: {e}")

        return self.get_token_for_mcp_agent()


async def main():
    """
    Main interactive OAuth demonstration.
    """
    print("GitHub OAuth Demo for MCP Agent")
    print("=" * 40)

    # Check for environment variables
    client_id = os.getenv('GITHUB_CLIENT_ID')
    client_secret = os.getenv('GITHUB_CLIENT_SECRET')

    if not client_id or not client_secret:
        print("\nTo use this demo, you need to set up a GitHub OAuth App:")
        print("1. Go to GitHub Settings > Developer settings > OAuth Apps")
        print("2. Click 'New OAuth App'")
        print("3. Set Authorization callback URL to: http://localhost:8080/internal/oauth/callback")
        print("4. Set environment variables:")
        print("   export GITHUB_CLIENT_ID='your_client_id'")
        print("   export GITHUB_CLIENT_SECRET='your_client_secret'")
        print("\nAlternatively, you can pass them as command line arguments.")
        return

    try:
        # Create OAuth demo instance
        oauth_demo = GitHubOAuthDemo(client_id, client_secret)

        # Run the OAuth flow
        scopes = ["read:org", "public_repo", "user:email"]
        token_data = await oauth_demo.run_oauth_flow(scopes)

        print(token_data)

        print("\n" + "=" * 50)
        print("OAuth Flow Completed Successfully!")
        print("=" * 50)

        print("\nToken Details:")
        print(f"  Access Token: {token_data['access_token'][:20]}...")
        print(f"  Expires At: {time.ctime(token_data['expires_at'])}")
        print(f"  Scopes: {', '.join(token_data['scopes'])}")

        # Save token to file
        save_choice = input("\nSave token to file? (y/n): ").lower().strip()
        if save_choice in ['y', 'yes']:
            filename = input("Enter filename (default: github_oauth_token.json): ").strip()
            if not filename:
                filename = "github_oauth_token.json"
            await oauth_demo.save_token_to_file(filename)

        # Show usage instructions
        print("\n" + "=" * 50)
        print("Next Steps:")
        print("=" * 50)
        print("1. Use this token with the MCP agent workflow_pre_auth endpoint:")

        example_usage = {
            "workflow_name": "github_analysis_workflow",
            "tokens": [token_data]
        }
        print(f"   {json.dumps(example_usage, indent=2)}")

        print("\n2. Or configure it in your mcp_agent.secrets.yaml:")
        secrets_example = {
            "mcp": {
                "servers": {
                    "github": {
                        "auth": {
                            "oauth": {
                                "access_token": token_data['access_token'],
                                "refresh_token": token_data.get('refresh_token'),
                                "scopes": token_data['scopes']
                            }
                        }
                    }
                }
            }
        }
        print(f"   {json.dumps(secrets_example, indent=2)}")

    except Exception as e:
        print(f"\nOAuth flow failed: {e}")
        print("Please check your GitHub OAuth app configuration and try again.")


if __name__ == "__main__":
    asyncio.run(main())