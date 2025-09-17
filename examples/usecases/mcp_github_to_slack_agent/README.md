# GitHub PRs to Slack Summary Agent

This application creates an MCP Agent that monitors GitHub pull requests and submits prioritized summaries to Slack. The agent uses a LLM to analyze PR information, prioritize issues, and create informative summaries.

## How It Works

1. The application connects to both GitHub and Slack via their respective MCP servers
2. The agent retrieves the last 10 pull requests from a specified GitHub repository
3. It analyzes each PR and prioritizes them based on importance factors:
   - PRs marked as high priority or urgent
   - PRs addressing security vulnerabilities
   - PRs fixing critical bugs
   - PRs blocking other work
   - PRs that have been open for a long time
4. The agent formats a professional summary of high-priority items
5. The summary is posted to the specified Slack channel

## Setup

### Prerequisites

- Python 3.10 or higher
- MCP Agent framework
- GitHub Copilot access (for cloud-based GitHub MCP server)
- [Slack MCP Server](https://github.com/korotovsky/slack-mcp-server/tree/master)
- Node.js and npm (for the Slack server)
- Access to a GitHub repository
- Access to a Slack workspace

### Getting a Slack Bot Token and Team ID

1. Head to [Slack API apps](https://api.slack.com/apps)

2. Create a **New App**

3. Click on the option to **Create from scratch**

4. In the app view, go to **OAuth & Permissions** on the left-hand navigation

5. Copy the **Bot User OAuth Token**
6. _[Optional] In OAuth & Permissions, add chat:write, users:read, im:history, chat:write.public to the Bot Token Scopes_

7. For **Team ID**, go to the browser and log into your workspace.
8. In the browser, take the **TEAM ID** from the url: `https://app.slack.com/client/TEAM_ID`

9. Add the **OAuth Token** and the **Team ID** to your `mcp_agent.secrets.yaml` file

10. _[Optional] Make sure to launch and install your Slack bot to your workspace. And, invite the new bot to the channel you want to interact with._

### Installation

1. Install dependencies:

```
uv sync --dev
```

2. Create a `mcp_agent.secrets.yaml` secrets file

3. Update the secrets file with your API keys and Tokens

### Usage

Run the application with:

```
uv run main.py --owner <github-owner> --repo <repository-name> --channel <slack-channel>
```

### [Beta] Deploy to the cloud

#### `a.` Log in to [MCP Agent Cloud](https://docs.mcp-agent.com/cloud/overview)

```bash
uv run mcp-agent login
```

During deployment, you can select how you would like your secrets managed.

#### `b.` Deploy your agent with a single command

```bash
uv run mcp-agent deploy my-first-agent
```

#### `c.` Connect to your deployed agent as an MCP server through any MCP client

##### Claude Desktop Integration

Configure Claude Desktop to access your agent servers by updating your `~/.claude-desktop/config.json`:

```json
"my-agent-server": {
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
```

##### MCP Inspector

Use MCP Inspector to explore and test your agent servers:

```bash
npx @modelcontextprotocol/inspector
```

Make sure to fill out the following settings:

| Setting          | Value                                                          |
| ---------------- | -------------------------------------------------------------- |
| _Transport Type_ | _SSE_                                                          |
| _SSE_            | _https://[your-agent-server-id].deployments.mcp-agent.com/sse_ |
| _Header Name_    | _Authorization_                                                |
| _Bearer Token_   | _your-mcp-agent-cloud-api-token_                               |

> [!TIP]
> In the Configuration, change the request timeout to a longer time period. Since your agents are making LLM calls, it is expected that it should take longer than simple API calls.

##### Trigger Agent Run on Cloud

Once you are connected to the MCP Agent on cloud, you will get a list of tools as follow:

- MCP Agent Cloud Default Tools:
  - workflow-list: list the workflow (you don't need this)
  - workflow-run-list: list the execution runs of your agent
  - workflow-run: create workflow run (you don't need this)
  - workflows-get_status: get your agent run's status
  - workflows-resume: signal workflow to pause run
  - workflows-cancel: signal workflow to cancel run
- Tool's that your agent expose:
  - github_to_slack: default of your tool name, input the parameters to trigger a workflow run

Once you run the agent, successful trigger will return a workflow_run metadata object, where you can find your run id to query status:

```json
{
  "workflow_id": "github_to_slack-uuid",
  "run_id": "uuid",
  "execution_id": "uuid"
}
```

If this command returns error, you can tail the agent logs to investigate:

```shell
uv run mcp-agent cloud logger tail "app_id" -f
```

When you agent run successfully finishes, you will see Slack message is posted by your agent and you will also be able to see the agent's text response by using `workflows-get_status`, which will return result like:

```json
{
  "result": {
    "id": "run-uuid",
    "name": "github_to_slack",
    "status": "completed",
    "running": false,
    "state": {
      "status": "completed",
      "metadata": {},
      "updated_at": 1757705891.842188,
      "error": null
    },
    "result": "{'kind': 'workflow_result', 'value': \"I'll help you complete this workflow. Let me start by retrieving the last 10 pull requests from the GitHub repository lastmile-.......",
    "completed": true,
    "error": null,
    "temporal": {
      "id": "github_to_slack-uuid",
      "workflow_id": "github_to_slack-uuid",
      "run_id": "uuid",
      "status": "xxxxx",
      "error": "xxxxx"
    }
  }
}
```
