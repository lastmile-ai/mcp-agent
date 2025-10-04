# MCP Financial Analyzer with Google Search

This example demonstrates a financial analysis Agent application that uses an orchestrator with smart data verification to coordinate specialized agents for generating comprehensive financial reports on companies.

https://github.com/user-attachments/assets/d6049e1b-1afc-4f5d-bebf-ed9aece9acfc

## How It Works

1. **Orchestrator**: Coordinates the entire workflow, managing the flow of data between agents and ensuring each step completes successfully
2. **Research Agent & Research Evaluator**: Work together in a feedback loop where the Research Agent collects data and the Research Evaluator assesses its quality
3. **EvaluatorOptimizer** (Research Quality Controller): Manages the feedback loop, evaluating outputs and directing the Research Agent to improve data until reaching EXCELLENT quality rating
4. **Analyst Agent**: Analyzes the verified data to identify key financial insights
5. **Report Writer**: Creates a professional markdown report saved to the filesystem

This approach ensures high-quality reports by focusing on data verification before proceeding with analysis. The Research Agent and Research Evaluator iterate until the EvaluatorOptimizer determines the data meets quality requirements.

```plaintext
┌──────────────┐      ┌──────────────────┐      ┌────────────────────┐
│ Orchestrator │─────▶│ Research Quality │─────▶│      Research      │◀─┐
│   Workflow   │      │    Controller    │      │        Agent       │  │
└──────────────┘      └──────────────────┘      └────────────────────┘  │
       │                                                   │            │
       │                                                   │            │
       │                                                   ▼            │
       │                                        ┌────────────────────┐  │
       │                                        │ Research Evaluator ├──┘
       │                                        │        Agent       │
       │                                        └────────────────────┘
       │             ┌─────────────────┐
       └────────────▶│  Analyst Agent  │
       │             └─────────────────┘
       │             ┌─────────────────┐
       └────────────▶│  Report Writer  │
                     │      Agent      │
                     └─────────────────┘
```

## `1` App set up

First, clone the repo and navigate to the financial analyzer example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/usecases/mcp_financial_analyzer
```

Install `uv` (if you don’t have it):

```bash
pip install uv
```

Sync `mcp-agent` project dependencies:

```bash
uv sync
```

Install requirements specific to this example:

```bash
uv pip install -r requirements.txt
```

## `2` Set up secrets and environment variables

Copy and configure your secrets:

```bash
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
```

Then open `mcp_agent.secrets.yaml` and add your API key for your preferred LLM (OpenAI):

```yaml
openai:
  api_key: "YOUR_OPENAI_API_KEY"
```

## `3` Run locally

Run your MCP Agent app with a company name:

```bash
uv run main.py "Apple"
```

Or run with a different company:

```bash
uv run main.py "Microsoft"
```

## `4` [Beta] Deploy to MCP Agent Cloud

### Prerequisites
This agent is already cloud-compatible with the `@app.tool` decorator and uses only the `fetch` server for web data collection.

### Step 1: Login to MCP Agent Cloud

```bash
uv run mcp-agent login
```

### Step 2: Deploy your agent

```bash
uv run mcp-agent deploy financial-analyzer
```

During deployment, you'll be prompted to configure secrets. You'll see two options for the OpenAI API key:

#### For OpenAI API Key:
```
Select secret type for 'openai.api_key'
1: Deployment Secret: The secret value will be stored securely and accessible to the deployed application runtime.
2: User Secret: No secret value will be stored. The 'configure' command must be used to create a configured application with this secret.
```

**Recommendation:**
- Choose **Option 1** if you're deploying for personal use and want immediate functionality
- Choose **Option 2** if you're sharing this agent publicly and want users to provide their own OpenAI API keys

### Step 3: Connect to your deployed agent

Once deployed, you'll receive a deployment URL like: `https://[your-agent-server-id].deployments.mcp-agent.com`

#### Claude Desktop Integration

Configure Claude Desktop to access your agent by updating your `~/.claude-desktop/config.json`:

```json
{
  "mcpServers": {
    "financial-analyzer": {
      "command": "/path/to/npx",
      "args": [
        "mcp-remote",
        "https://[your-agent-server-id].deployments.mcp-agent.com/sse",
        "--header",
        "Authorization: Bearer ${BEARER_TOKEN}"
      ],
      "env": {
        "BEARER_TOKEN": "your-mcp-agent-cloud-api-token"
      }
    }
  }
}
```

#### MCP Inspector

Test your deployed agent using MCP Inspector:

```bash
npx @modelcontextprotocol/inspector
```

Configure the inspector with these settings:

| Setting | Value |
|---------|-------|
| Transport Type | SSE |
| SSE URL | `https://[your-agent-server-id].deployments.mcp-agent.com/sse` |
| Header Name | Authorization |
| Bearer Token | your-mcp-agent-cloud-api-token |

**💡 Tip:** Increase the request timeout in the Configuration since LLM calls take longer than simple API calls.

### Available Tools

Once deployed, your agent will expose the `analyze_stock` tool, which:
- Takes a company name as input (e.g., "Apple", "Microsoft")
- Conducts comprehensive financial research using web search
- Performs quality evaluation and improvement loops to ensure data accuracy
- Generates professional investment analysis with bull/bear cases
- Returns a complete financial report as formatted text

### Example Usage

After deployment, you can use the agent through Claude Desktop or MCP Inspector:

```
Please analyze Meta's financial performance and investment outlook.
```

The agent will automatically:
1. Research Tesla's current stock price, earnings, and recent news
2. Evaluate data quality and improve if needed
3. Analyze the financial data for investment insights
4. Generate a comprehensive report with recommendations
