# Timer App - ChatGPT App Example

![timer-app](https://github.com/user-attachments/assets/7a526501-84c8-4ef5-b784-4b3948790db2)

This example demonstrates how to create an MCP Agent application with interactive UI widgets for OpenAI's ChatGPT Apps platform. It shows how to build a countdown timer widget that renders interactive UI components directly in the ChatGPT interface.

**SSE Endpoint to try out! -**  `https://timer.demos.mcp-agent.com/sse`

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

1. **TimerWidget**: A dataclass that encapsulates all widget metadata:
   - Widget identifier and title
   - Template URI (cached by ChatGPT)
   - Tool invocation state messages
   - HTML template content
   - Response text

> [!TIP]
> The widget HTML templates are heavily cached by OpenAI Apps. Use date-based URIs (like `ui://widget/timer-10-30-2025-12-00.html`) to bust the cache when updating the widget.

2. **MCP Server**: FastMCP server configured for stateless HTTP with:

   - Tool registration (`timer` tool with hours, minutes, seconds, and optional message parameters)
   - Resource serving (HTML template)
   - Resource template registration
   - Custom request handlers for tools and resources

3. **Web Client**: A React application (in `web/` directory) that:
   - Renders an interactive countdown timer interface with hours, minutes, and seconds
   - Displays an optional custom message below the timer (e.g., "Meeting starts soon!")
   - Hydrates with structured data from tool calls
   - Provides Start and Reset controls
   - Shows visual completion indicator with "Time's up!" message
   - Notifies ChatGPT when the timer completes
   - Uses shadcn/ui components for consistent styling

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

This creates optimized production assets in `web/build/` that the server will serve.

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

- Click **Tools > List Tools** to see the `timer` tool
- Click **Resources > List Resources** to see the widget HTML template
- Run the `timer` tool with parameters (e.g., `{"hours": 0, "minutes": 5, "seconds": 0, "message": "Coffee break!"}`) to see the widget metadata and structured result

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
template_uri="ui://widget/timer-<date-string>.html",
```

Then redeploy:

```bash
uv run mcp-agent deploy chatgpt-app --no-auth
```

## Using with OpenAI ChatGPT Apps

Once deployed, you can integrate this server with ChatGPT Apps:

1. In your OpenAI platform account, create a new ChatGPT App
2. Configure the app to connect to your deployed MCP server URL
3. The `timer` tool will appear as an available action
4. When invoked with time parameters (hours, minutes, seconds), the widget will render in the ChatGPT interface with an interactive countdown timer
5. Users can click Start to begin the countdown and Reset to reset the timer

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

- `main.py` - Defines the MCP server, widget metadata, and tool handlers for the timer
- `web/` - React web client for the countdown timer widget
  - `web/src/components/Timer.tsx` - Main timer component with countdown logic
  - `web/src/components/ui/` - shadcn/ui components (Card, Button)
  - `web/src/components/App.tsx` - Root app component
  - `web/src/utils/types.ts` - TypeScript type definitions
  - `web/build/` - Production build output (generated)
  - `web/public/` - Static assets
- `mcp_agent.config.yaml` - App configuration (execution engine, name)
- `requirements.txt` - Python dependencies

## Additional Resources

- [OpenAI Apps SDK Documentation](https://developers.openai.com/apps-sdk/build/mcp-server)
