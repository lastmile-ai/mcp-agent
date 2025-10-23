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

Install the g-search-mcp server (from https://github.com/jae-jae/g-search-mcp):

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
