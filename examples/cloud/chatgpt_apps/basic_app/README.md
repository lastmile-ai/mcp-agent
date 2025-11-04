# ChatGPT App Example

This example demonstrates how to create an MCP Agent application with interactive UI widgets for OpenAI's ChatGPT Apps platform. It shows how to build a coin-flip widget that renders interactive UI components directly in the ChatGPT interface.

## Motivation

This example showcases the integration between mcp-agent and OpenAI's ChatGPT Apps SDK, specifically demonstrating:

- **Widget-based UI**: Creating interactive widgets that render in ChatGPT
- **Resource templates**: Serving HTML/JS/CSS as MCP resources
- **Tool invocation metadata**: Using OpenAI-specific metadata for tool behavior
- **Static asset serving**: Two approaches for serving client-side code (inline vs. deployed)

## Concepts Demonstrated

- Creating MCP tools with OpenAI widget metadata
- Serving interactive HTML/JS/CSS widgets through MCP resources
- Using `EmbeddedResource` to pass UI templates to ChatGPT
- Handling tool calls that return structured content for widget hydration
- Deploying web clients alongside MCP servers

## Components in this Example

1. **CoinFlipWidget**: A dataclass that encapsulates all widget metadata:
   - Widget identifier and title
   - Template URI (cached by ChatGPT)
   - Tool invocation state messages
   - HTML template content
   - Response text

> [!TIP]
> The widget HTML templates are heavily cached by OpenAI Apps. Use date-based URIs (like `ui://widget/coin-flip-10-22-2025-15-48.html`) to bust the cache when updating the widget.

2. **MCP Server**: FastMCP server configured for stateless HTTP with:

   - Tool registration (`coin-flip` tool)
   - Resource serving (HTML template)
   - Resource template registration
   - Custom request handlers for tools and resources

3. **Web Client**: A React application (in `web/` directory) that:
   - Renders an interactive coin flip interface
   - Hydrates with structured data from tool calls
   - Provides visual feedback for coin flip results

## Static Asset Serving Approaches

The example demonstrates two methods for serving the web client assets:

### Method 1: Inline Assets (Default)

Embeds the JavaScript and CSS directly into the HTML template. This approach:

- Works immediately for initial deployment
- Can lead to large HTML templates
- May have string escaping issues
- Best for initial development and testing

### Method 2: Deployed Assets (Recommended)

References static files from a deployed server URL:

- Smaller HTML templates
- Better performance with caching
- Requires initial deployment to get the server URL
- Best for production use
- NOTE: The deployed server will only serve static files from `web/build/static` or `web/dist/static`

## Prerequisites

- Python 3.10+
- [UV](https://github.com/astral-sh/uv) package manager
- Node.js and npm/yarn (for building the web client)

## Building the Web Client

Before running the server, you need to build the React web client:

```bash
cd web
yarn install
yarn build
cd ..
```

This creates optimized production assets in `web/build/static` that the server will serve.

## Test Locally

Install the dependencies:

```bash
uv pip install -r requirements.txt
```

Spin up the mcp-agent server locally with SSE transport:

```bash
uv run main.py
```

This will:

- Start the MCP server on port 8000
- Serve the web client at http://127.0.0.1:8000
- Serve static assets (JS/CSS) at http://127.0.0.1:8000/static

Use [MCP Inspector](https://github.com/modelcontextprotocol/inspector) to explore and test the server:

```bash
npx @modelcontextprotocol/inspector --transport sse --server-url http://127.0.0.1:8000/sse
```

In MCP Inspector:

- Click **Tools > List Tools** to see the `coin-flip` tool
- Click **Resources > List Resources** to see the widget HTML template
- Run the `coin-flip` tool to see the widget metadata and structured result

## Deploy to mcp-agent Cloud

You can deploy this MCP-Agent app as a hosted mcp-agent app in the Cloud.

1. In your terminal, authenticate into mcp-agent cloud by running:

```bash
uv run mcp-agent login
```

2. You will be redirected to the login page, create an mcp-agent cloud account through Google or Github

3. Set up your mcp-agent cloud API Key and copy & paste it into your terminal

```bash
uv run mcp-agent login
INFO: Directing to MCP Agent Cloud API login...
Please enter your API key =:
```

4. In your terminal, deploy the MCP app:

```bash
uv run mcp-agent deploy chatgpt-app --no-auth
```

Note the use of `--no-auth` flag here will allow unauthenticated access to this server using its URL.

The `deploy` command will bundle the app files and deploy them, producing a server URL of the form:
`https://<server_id>.deployments.mcp-agent.com`.

5. After deployment, update main.py:767 with your actual server URL:

```python
SERVER_URL = "https://<server_id>.deployments.mcp-agent.com"
```

6. Switch to using deployed assets (optional but recommended):

Update main.py:782 to use `DEPLOYED_HTML_TEMPLATE`:

```python
html=DEPLOYED_HTML_TEMPLATE,
```

Then bump the template uri:

```python
template_uri="ui://widget/coin-flip-<date-string>.html",
```

Then redeploy:

```bash
uv run mcp-agent deploy chatgpt-app --no-auth
```

## Using with OpenAI ChatGPT Apps

Once deployed, you can integrate this server with ChatGPT Apps:

1. In your OpenAI platform account, create a new ChatGPT App
2. Configure the app to connect to your deployed MCP server URL
3. The `coin-flip` tool will appear as an available action
4. When invoked, the widget will render in the ChatGPT interface with interactive UI

## Understanding Widget Metadata

The example uses OpenAI-specific metadata fields:

- `openai/outputTemplate`: URI pointing to the HTML template resource
- `openai/toolInvocation/invoking`: Message shown while tool is being called
- `openai/toolInvocation/invoked`: Message shown after tool completes
- `openai/widgetAccessible`: Indicates the tool can render a widget
- `openai/resultCanProduceWidget`: Indicates the result includes widget data

These metadata fields tell ChatGPT how to handle the tool and render the UI.

## Widget Hydration

When the `coin-flip` tool is called:

1. The server returns an `EmbeddedResource` containing the HTML template
2. The server includes `structuredContent` with the flip result (`{"flipResult": "heads"}`)
3. ChatGPT loads the HTML and executes the embedded JavaScript
4. The React app hydrates with the structured data and displays the result
5. The user can interact with the widget to flip again

## MCP Clients

Since the mcp-agent app is exposed as an MCP server, it can be used in any MCP client just like any other MCP server.

## Test Deployment

Use [MCP Inspector](https://github.com/modelcontextprotocol/inspector) to explore and test this server:

```bash
npx @modelcontextprotocol/inspector --transport sse --server-url https://<server_id>.deployments.mcp-agent.com/sse
```

Make sure Inspector is configured with the following settings:

| Setting          | Value                                               |
| ---------------- | --------------------------------------------------- |
| _Transport Type_ | _SSE_                                               |
| _SSE_            | _https://[server_id].deployments.mcp-agent.com/sse_ |

## Code Structure

- `main.py` - Defines the MCP server, widget metadata, and tool handlers
- `web/` - React web client for the coin flip widget
  - `web/src/` - React source code
  - `web/build/` - Production build output (generated)
  - `web/public/` - Static assets
- `mcp_agent.config.yaml` - App configuration (execution engine, name)
- `requirements.txt` - Python dependencies

## Additional Resources

- [OpenAI Apps SDK Documentation](https://developers.openai.com/apps-sdk/build/mcp-server)
