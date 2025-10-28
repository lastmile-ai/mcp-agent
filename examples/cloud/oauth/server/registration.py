import requests
import json

# Authorization server URL. This can either be the MCP Agent Clound authorization server (as currently configured),
# or your own.
auth_server_url = "https://auth.mcp-agent.com"
redirect_uris = [
    # These are the redirect URIs for MCP Inspector. Replace with your app's URIs.
    "http://localhost:6274/oauth/callback",
    "http://localhost:6274/oauth/callback/debug",
]
client_name = "My Python Application"

# Fetch the registration endpoint dynamically from the .well-known/oauth-authorization-server details
well_known_url = f"{auth_server_url}/.well-known/oauth-authorization-server"
response = requests.get(well_known_url)

if response.status_code == 200:
    well_known_details = response.json()
    registration_endpoint = well_known_details.get("registration_endpoint")
    if not registration_endpoint:
        raise ValueError("Registration endpoint not found in .well-known details")
else:
    raise ValueError(f"Failed to fetch .well-known details: {response.status_code}")


# Client registration request
registration_request = {
    "client_name": client_name,
    "redirect_uris": redirect_uris,
    "grant_types": ["authorization_code", "refresh_token"],
    "scope": "mcp",
    # use client_secret_basic when testing with MCP Inspector
    "token_endpoint_auth_method": "client_secret_basic",
}

print(f"Registering client at: {registration_endpoint}")

# Register the client
response = requests.post(
    registration_endpoint,
    json=registration_request,
    headers={"Content-Type": "application/json"},
)

if response.status_code in [200, 201]:
    client_info = response.json()
    print("Client registered successfully!")
    print(json.dumps(client_info, indent=2))

    # Save credentials for later use
    print("\n=== Save these credentials ===")
    print(f"Client ID: {client_info['client_id']}")
    print(f"Client Secret: {client_info['client_secret']}")
else:
    print(f"Registration failed with status {response.status_code}")
    print(response.text)
