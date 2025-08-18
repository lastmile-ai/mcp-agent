# MCP Marketing Content Agent

This example demonstrates a marketing content creation agent that learns your brand voice and generates platform-optimized content using an evaluation-driven approach with persistent memory for continuous improvement.

## How It Works

1. **Content Creator Agent**: Expert marketer that generates 2 distinct content variations using different strategic approaches (data-driven vs narrative)
2. **Quality Evaluator Agent**: Selective CMO that rates content against strict brand standards and quality criteria  
3. **Content Quality System** (EvaluatorOptimizerLLM): Manages the creation-evaluation feedback loop, ensuring content meets EXCELLENT quality standards before presenting to user
4. **Memory Manager Agent**: Stores user feedback and choices for continuous learning and improvement
5. **Context Assembly**: Automatically gathers brand voice, content samples, and company documentation to inform content creation

This approach ensures high-quality, on-brand content by focusing on evaluation-driven creation and learning from user preferences over time.

```plaintext
┌──────────────┐      ┌───────────────────┐      ┌─────────────────┐
│ User Request │─────▶│ Content Quality   │─────▶│ Content Creator │◀─┐
│ + Feedback   │      │ Evaluator         │      │ Agent           │  │
└──────────────┘      └───────────────────┘      └─────────────────┘  │
       │                                                   │          │
       │                                                   │          │
       │                                                   ▼          │
       │                                        ┌─────────────────┐   │
       │                                        │ Quality Control ├───┘
       │                                        │ Agent           │
       │                                        └─────────────────┘
       │             ┌─────────────────┐
       └────────────▶│ Memory Manager  │
                     └─────────────────┘
```

## `1` App set up

First, clone the repo and navigate to the marketing content agent example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/usecases/mcp_marketing_assistant_agent
```

Install `uv` (if you don't have it):

```bash
pip install uv
```

Sync `mcp-agent` project dependencies:

```bash
uv sync
```

Install the required MCP servers:

```bash
npm install -g @modelcontextprotocol/server-memory
pip install markitdown-mcp
```

## `2` Set up secrets and configuration

Copy and configure your secrets:

```bash
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
```

Then open `mcp_agent.secrets.yaml` and add your OpenAI API key:

```yaml
openai:
  api_key: "YOUR_OPENAI_API_KEY"
```

Configure your brand voice in `company_config.yaml`:


## `3` Add content samples

Create directories for your content:

```bash
mkdir -p content_samples posts company_docs
```

Add your existing content to train the agent:
- `content_samples/`: Add social media posts, blog content (supports .md, .txt, .pdf, .docx, .html)
- `company_docs/`: Add brand guidelines, company info
- `posts/`: Where generated content will be saved

## `4` Run locally

Generate a LinkedIn post:

```bash
uv run main.py "Write a linkedin post about our new feature"
```

Create a Twitter thread:

```bash
uv run main.py "Create a twitter thread about our latest release"
```

Generate an email announcement:

```bash
uv run main.py "Draft an email about our upcoming webinar link to event page"
```

The agent will present you with two content variations, learn from your choice, and continuously improve based on your feedback.