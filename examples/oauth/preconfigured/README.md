# OAuth MCP Agent Example

This example demonstrates how to build MCP agents that use OAuth authentication to access OAuth-protected MCP servers, specifically showing integration with the GitHub MCP server.

## 📋 Overview

This example includes:

- **Basic OAuth Integration** - Connect to OAuth-protected MCP servers
- **GitHub Organization Search** - Use the `search_orgs` tool from GitHub MCP server
- **Workflow Pre-Authorization** - Demonstrate the new `workflow_pre_auth` endpoint
- **Interactive OAuth Flow** - Complete OAuth setup and token management
- **Production-Ready Configuration** - Comprehensive config with security best practices

## 🚀 Quick Start

### 1. Prerequisites

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install GitHub MCP server
uvx install github-mcp-server

# Optional: Install additional MCP servers
npm install -g @modelcontextprotocol/server-filesystem
uvx install mcp-server-fetch
```

### 2. Set Up GitHub OAuth App

1. Go to [GitHub Settings → Developer settings → OAuth Apps](https://github.com/settings/applications/new)
2. Click **"New OAuth App"**
3. Fill in the details:
   - **Application name**: `MCP Agent OAuth Example`
   - **Homepage URL**: `https://github.com/yourusername/your-repo`
   - **Authorization callback URL**: `http://localhost:8080/oauth/callback`
4. Click **"Register application"**
5. Copy the **Client ID** and generate a **Client Secret**

### 3. Configure Secrets

```bash
# Copy the secrets template
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml

# Edit with your credentials
nano mcp_agent.secrets.yaml
```

Add your GitHub OAuth app credentials:

```yaml
mcp:
  servers:
    github:
      auth:
        oauth:
          client_id: "your_github_oauth_app_client_id_here"
          client_secret: "your_github_oauth_app_client_secret_here"
          access_token: "your_github_access_token_here"  # Optional: skip OAuth flow
```

### 4. Run the Examples

#### Basic OAuth Example
```bash
python main.py
```

#### Interactive OAuth Setup
```bash
python oauth_demo.py
```

#### Workflow with Pre-Authorization
```bash
python workflow_example.py
```

## 📁 File Structure

```
examples/oauth/
├── README.md                      # This file
├── main.py                        # Basic OAuth MCP agent
├── workflow_example.py            # Workflow with pre-auth demo
├── oauth_demo.py                  # Interactive OAuth flow
├── mcp_agent.config.yaml          # Agent configuration
├── mcp_agent.secrets.yaml.example # Secrets template
└── requirements.txt               # Python dependencies
```

## 🔐 Authentication Methods

### Method 1: OAuth Flow (Recommended)

Full OAuth 2.0 flow with refresh tokens:

1. **Run Interactive Setup**:
   ```bash
   GITHUB_CLIENT_ID=your_id GITHUB_CLIENT_SECRET=your_secret python oauth_demo.py
   ```

2. **Follow Browser Flow**: Authorize the application in your browser

3. **Token Storage**: Tokens are automatically stored for reuse

### Method 2: Personal Access Token (Development)

For development and testing, you can use a GitHub Personal Access Token:

1. Go to [GitHub Settings → Developer settings → Personal access tokens](https://github.com/settings/tokens)
2. Generate a token with scopes: `read:org`, `public_repo`, `user:email`
3. Configure in `mcp_agent.secrets.yaml`:

```yaml
mcp:
  servers:
    github:
      auth:
        api_key: "ghp_your_personal_access_token_here"
```

## 🔄 Workflow Pre-Authorization

The `workflow_pre_auth` endpoint allows you to pre-store OAuth tokens for workflows:

### 1. Start MCP Agent Server

```bash
mcp-agent server --config mcp_agent.config.yaml
```

### 2. Pre-Authorize Tokens

```bash
curl -X POST http://localhost:8080/tools/workflows-pre-auth \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_name": "github_analysis_workflow",
    "tokens": [
      {
        "access_token": "your_github_access_token",
        "refresh_token": "your_refresh_token",
        "server_name": "github",
        "scopes": ["read:org", "public_repo"],
        "authorization_server": "https://github.com/login/oauth/authorize"
      }
    ]
  }'
```

### 3. Run Workflow

```bash
curl -X POST http://localhost:8080/tools/workflows-run \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_name": "analyze_github_ecosystem",
    "run_parameters": {
      "focus_areas": ["AI/ML", "cloud", "security"],
      "include_details": true
    }
  }'
```

## 🛠 Examples Explained

### main.py - Basic OAuth Integration

Demonstrates:
- Connecting to GitHub MCP server with OAuth
- Using the `search_orgs` tool
- Error handling and token management
- Both single-use and persistent connections

Key features:
```python
async with gen_client("github", server_registry=context.server_registry) as github_client:
    result = await github_client.call_tool("search_orgs", {
        "query": "microsoft",
        "perPage": 10,
        "sort": "best-match"
    })
```

### workflow_example.py - Advanced Workflow

Demonstrates:
- Custom agent (`GitHubOrganizationAnalyzer`)
- Workflow with `@app.async_tool` decorator
- Pre-authorization token usage
- Comprehensive GitHub ecosystem analysis

Key features:
```python
@app.async_tool
async def analyze_github_ecosystem(
    app_ctx: Context,
    focus_areas: List[str],
    include_details: bool = True
) -> Dict[str, Any]:
    # Uses pre-authorized tokens automatically
    analyzer = GitHubOrganizationAnalyzer(context=app_ctx)
    return await analyzer.analyze_organizations(queries, include_details)
```

### oauth_demo.py - Interactive OAuth Setup

Demonstrates:
- Complete OAuth 2.0 flow
- Local callback server
- Token testing and validation
- Token persistence

Key features:
- Automatic browser opening
- CSRF protection with state parameter
- Token testing with GitHub API
- Export tokens for MCP agent use

## ⚙ Configuration Details

### OAuth Configuration

```yaml
oauth:
  token_store:
    backend: memory  # or 'redis' for production
    refresh_leeway_seconds: 60
  flow_timeout_seconds: 300
  callback_base_url: http://localhost:8080

mcp:
  servers:
    github:
      auth:
        oauth:
          enabled: true
          scopes: ["read:org", "public_repo", "user:email"]
          authorization_server: "https://github.com/login/oauth/authorize"
          resource: "https://api.github.com"
```

### GitHub Scopes Required

| Scope | Purpose | Required |
|-------|---------|----------|
| `read:org` | Search organizations | ✅ Yes |
| `public_repo` | Access public repositories | ✅ Yes |
| `user:email` | User information | ⚠ Recommended |
| `repo` | Private repositories | ❌ Optional |

## 🔧 Production Deployment

### Redis Token Storage

For production with multiple processes:

```yaml
oauth:
  token_store:
    backend: redis
    redis_url: "redis://localhost:6379"
    redis_prefix: "mcp_agent:oauth_tokens"
```

### Environment Variables

```bash
export GITHUB_CLIENT_ID="your_client_id"
export GITHUB_CLIENT_SECRET="your_client_secret"
export REDIS_URL="redis://localhost:6379"
export OPENAI_API_KEY="your_openai_key"
```

### Security Best Practices

1. **Never commit secrets** - Use `.gitignore` for `mcp_agent.secrets.yaml`
2. **Rotate tokens regularly** - Set up token refresh workflows
3. **Minimal scopes** - Only request necessary permissions
4. **Secure storage** - Use Redis or encrypted storage in production
5. **HTTPS callbacks** - Use HTTPS URLs for production OAuth callbacks

## 🐛 Troubleshooting

### Common Issues

#### OAuth Flow Fails
```
Error: OAuth error: access_denied
```
**Solution**: Check callback URL matches OAuth app configuration

#### Token Test Fails
```
Error: Token test failed: 401
```
**Solution**: Verify token scopes and GitHub app permissions

#### MCP Server Connection Fails
```
Error: GitHub MCP server not found
```
**Solution**: Install GitHub MCP server with `uvx install github-mcp-server`

#### Import Errors
```
ImportError: No module named 'mcp_agent'
```
**Solution**: Install with `pip install mcp-agent[oauth]`

### Debug Mode

Enable detailed logging:

```yaml
logger:
  level: debug
  debug_oauth: true
```

### Testing Tokens

Test your GitHub token manually:

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" https://api.github.com/user
```

## 📚 Advanced Usage

### Multiple OAuth Providers

```yaml
mcp:
  servers:
    github:
      auth:
        oauth:
          client_id: "github_client_id"
          # ... GitHub config

    slack:
      auth:
        oauth:
          client_id: "slack_client_id"
          # ... Slack config
```

### Custom Token Refresh

```python
async def refresh_github_token(old_token: str) -> str:
    # Custom token refresh logic
    async with aiohttp.ClientSession() as session:
        # ... refresh implementation
        return new_token
```

### Workflow Chaining

```python
@app.async_tool
async def multi_step_analysis(app_ctx: Context, orgs: List[str]):
    # Step 1: Search organizations
    github_results = await search_organizations(orgs)

    # Step 2: Analyze with different service
    analysis = await analyze_with_ai(github_results)

    # Step 3: Store results
    await store_results(analysis)

    return analysis
```

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch
3. Add tests for new functionality
4. Ensure all examples work
5. Submit a pull request

## 📄 License

This example is part of the MCP Agent project and follows the same license terms.

## 🔗 Related Resources

- [MCP Agent Documentation](../../README.md)
- [GitHub MCP Server](https://github.com/github/github-mcp-server)
- [OAuth 2.0 Specification](https://tools.ietf.org/html/rfc6749)
- [GitHub OAuth Apps](https://docs.github.com/en/developers/apps/building-oauth-apps)
- [Model Context Protocol](https://modelcontextprotocol.io)

---

For questions or issues with this example, please check the [main repository issues](../../issues) or create a new issue with the `oauth-example` label.