# MCP Financial Analyzer with Google Search

This MCP Agent app uses an orchestrator with smart data verification to coordinate specialized agents that generate comprehensive financial reports for companies.

```plaintext
┌──────────────┐      ┌──────────────┐
│              │      │  G-Search    │
│  Orchestrator│──┬──▶│  MCP Server  │
│  (manages    │  │   └──────────────┘
│   agents)    │  │   ┌──────────────┐
│              │  ├──▶│  Fetch       │
└──┬─────┬─────┘  │   │  MCP Server  │
   │     │        │   └──────────────┘
   │     │        │   ┌──────────────┐
   │     │        └──▶│  Filesystem  │
   │     │            │  MCP Server  │
   │     │            └──────────────┘
   ▼     ▼     ▼    ▼         
┌─────┐ ┌─────┐ ┌─────┐ ┌─────────┐
│Find │ │Veri-│ │Anal-│ │Report   │
│Agent│ │fier │ │yst  │ │Writer   │
│     │ │Agent│ │     │ │         │
└─────┘ └─────┘ └─────┘ └─────────┘
```

## `1` App set up

First, clone the repo and navigate to the financial analyzer example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/mcp_financial_analyzer
```

Install the UV tool (if you don't have it) to manage dependencies:

```bash
pip install uv
# inside the example:
uv pip install -r requirements.txt
```

Install the g-search-mcp server:

```bash
npm install -g g-search-mcp
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

The program will:
1. Use Google Search to find current stock price and financial data
2. Verify the completeness of the data before proceeding
3. Collect additional information for any missing data points
4. Analyze the financial data and generate a professional report
5. Save the report to the `company_reports` directory

## How It Works

The financial analyzer uses a smart verification process instead of blind retries:

1. **Finder Agent**: Uses Google Search to gather financial data with precise instructions
2. **Verifier Agent**: Checks if the data is complete and flags specific missing information
3. **Targeted Improvement**: Collects additional data only for the missing items
4. **Analyst Agent**: Evaluates the financial metrics and identifies key trends
5. **Report Writer**: Compiles findings into a well-structured markdown report

This approach ensures high-quality reports by focusing on data completeness rather than simply retrying on failure.

## Customizing the Analysis

You can modify the agent instructions in `main.py` to focus on different aspects of financial analysis:

- Add specific financial metrics to the finder agent instructions
- Change the verification criteria in the verifier agent
- Customize the report format and content in the writer agent

## Deploy your MCP Agent app

Coming soon
