# Evaluator-Optimizer Workflow Example

This example demonstrates a sophisticated job cover letter refinement system that leverages the evaluator-optimizer pattern. The system generates a draft cover letter based on job description, company information, and candidate details. An evaluator agent then reviews the letter, provides a quality rating, and offers actionable feedback. This iterative cycle continues until the letter meets a predefined quality standard of "excellent".

## What's New in This Branch

- **Tool-based Architecture**: The workflow is now exposed as an MCP tool (`cover_letter_writer_tool`) that can be deployed and accessed remotely
- **Input Parameters**: The tool accepts three parameters:
  - `job_posting`: The job description and requirements
  - `candidate_details`: The candidate's background and qualifications
  - `company_information`: Company details (can be a URL for the agent to fetch)
- **Model Update**: Default model updated from `gpt-4o` to `gpt-4.1` for enhanced performance
- **Cloud Deployment Ready**: Full support for deployment to MCP Agent Cloud

To make things interesting, we specify the company information as a URL, expecting the agent to fetch it using the MCP 'fetch' server, and then using that information to generate the cover letter.

![Evaluator-optimizer workflow (Image credit: Anthropic)](https://www.anthropic.com/_next/image?url=https%3A%2F%2Fwww-cdn.anthropic.com%2Fimages%2F4zrzovbb%2Fwebsite%2F14f51e6406ccb29e695da48b17017e899a6119c7-2401x1000.png&w=3840&q=75)

---

```plaintext
┌───────────┐      ┌────────────┐
│ Optimizer │─────▶│  Evaluator │──────────────▶
│ Agent     │◀─────│  Agent     │ if(excellent)
└─────┬─────┘      └────────────┘  then out
      │
      ▼
┌────────────┐
│ Fetch      │
│ MCP Server │
└────────────┘
```

## `1` App set up

First, clone the repo and navigate to the workflow evaluator optimizer example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/workflows/workflow_evaluator_optimizer
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

## `2` Set up environment variables

Copy and configure your secrets and env variables:

```bash
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
```

Then open `mcp_agent.secrets.yaml` and add your API key for your preferred LLM provider. **Note: You only need to configure ONE API key** - either OpenAI or Anthropic, depending on which provider you want to use.

## (Optional) Configure tracing

In `mcp_agent.config.yaml`, you can set `otel` to `enabled` to enable OpenTelemetry tracing for the workflow.
You can [run Jaeger locally](https://www.jaegertracing.io/docs/2.5/getting-started/) to view the traces in the Jaeger UI.

## `3` Run locally

Run your MCP Agent app:

```bash
uv run main.py
```

## `4` [Beta] Deploy to the Cloud

Deploy your cover letter writer agent to MCP Agent Cloud for remote access and integration.

### Prerequisites

- MCP Agent Cloud account
- API keys configured in `mcp_agent.secrets.yaml`

### Deployment Steps

#### `a.` Log in to [MCP Agent Cloud](https://docs.mcp-agent.com/cloud/overview)

```bash
uv run mcp-agent login
```

#### `b.` Deploy your agent with a single command

```bash
uv run mcp-agent deploy cover-letter-writer
```

During deployment, you can select how you would like your secrets managed.

#### `c.` Connect to your deployed agent as an MCP server

Once deployed, you can connect to your agent through various MCP clients:

##### Claude Desktop Integration

Configure Claude Desktop to access your agent by updating `~/.claude-desktop/config.json`:

```json
{
  "cover-letter-writer": {
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
```

##### MCP Inspector

Use MCP Inspector to explore and test your agent:

```bash
npx @modelcontextprotocol/inspector
```

Configure the following settings in MCP Inspector:

| Setting            | Value                                                          |
| ------------------ | -------------------------------------------------------------- |
| **Transport Type** | SSE                                                            |
| **SSE URL**        | `https://[your-agent-server-id].deployments.mcp-agent.com/sse` |
| **Header Name**    | Authorization                                                  |
| **Bearer Token**   | your-mcp-agent-cloud-api-token                                 |

> [!TIP]
> Increase the request timeout in the Configuration settings since LLM calls may take longer than simple API calls.

##### Available Tools

Once connected to your deployed agent, you'll have access to:

**MCP Agent Cloud Default Tools:**

- `workflow-list`: List available workflows
- `workflow-run-list`: List execution runs of your agent
- `workflow-run`: Create a new workflow run
- `workflows-get_status`: Check agent run status
- `workflows-resume`: Resume a paused run
- `workflows-cancel`: Cancel a running workflow

**Your Agent's Tool:**

- `cover_letter_writer_tool`: Generate optimized cover letters with parameters:
  - `job_posting`: Job description and requirements
  - `candidate_details`: Candidate background and qualifications
  - `company_information`: Company details or URL to fetch

##### Monitoring Your Agent

After triggering a run, you'll receive a workflow metadata object:

```json
{
  "workflow_id": "cover-letter-writer-uuid",
  "run_id": "uuid",
  "execution_id": "uuid"
}
```

Monitor logs in real-time:

```bash
uv run mcp-agent cloud logger tail "cover-letter-writer" -f
```

Check run status using `workflows-get_status` to see the generated cover letter:

```json
{
  "result": {
    "id": "run-uuid",
    "name": "cover_letter_writer_tool",
    "status": "completed",
    "result": "{'kind': 'workflow_result', 'value': '[Your optimized cover letter]'}",
    "completed": true
  }
}
```
