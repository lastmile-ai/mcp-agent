# MCP Slack agent example

This example shows a "slack" Agent which has access to the ['slack'](https://github.com/modelcontextprotocol/servers/tree/main/src/slack) and 'filesystem' MCP servers.

You can use it to perform read/write actions on your Slack, as well as on your filesystem, including combination actions such as writing slack messages to disk or reading files and sending them over slack.

```plaintext
┌──────────────┐      ┌──────────────┐
│ Slack Finder │──┬──▶│  Slack       │
│    Agent     │  │   │  MCP Server  │
└──────────────┘  │   └──────────────┘
                  │   ┌──────────────┐
                  └──▶│  Filesystem  │
                      │  MCP Server  │
                      └──────────────┘
```

## `1` App set up

First, clone the repo and navigate to the slack agent example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/usecases/mcp_basic_slack_agent
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

## `2` Set up Slack Bot Token and Team ID

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

## `2.1` Set up secrets and environment variables

Copy and configure your secrets and env variables:

```bash
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
```

Then open `mcp_agent.secrets.yaml` and add your api key for your preferred LLM and `token` / `team id` for your Slack MCP server.

Example configuration:

```yaml
openai:
  api_key: openai_api_key

anthropic:
  api_key: anthropic_api_key

mcp:
  servers:
    slack:
    env:
      SLACK_BOT_TOKEN: "xoxb-your-bot-token"
      SLACK_TEAM_ID: "T01234567"
```

## `3` Run locally

Run your MCP Agent app:

```bash
uv run main.py
```
