# GitHub PRs to Slack Summary Agent

This application creates an MCP Agent that monitors GitHub pull requests and submits prioritized summaries to Slack. The agent uses a LLM to analyze PR information, prioritize issues, and create informative summaries.

## How It Works

1. The application connects to both GitHub and Slack via their respective MCP servers
2. The agent retrieves the latest pull requests from a specified GitHub repository
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
- [GitHub MCP Server](https://github.com/github/github-mcp-server))
- [Slack MCP Server](https://github.com/modelcontextprotocol/servers/tree/main/src/slack)
- Node.js and npm (this is for the Slack server)
- [Docker](https://www.docker.com/)
- Access to a GitHub repository
- Access to a Slack workspace

### Getting a Slack Bot Token and Team ID

1. Head to [Slack API apps](https://api.slack.com/apps)

2. Create a **New App**

3. Click on the option to **Create from scratch**

4. In the app view, go to **OAuth & Permissions** on the left-hand navigation

5. Copy the **Bot User OAuth Token**
   
6. *[Optional] In OAuth & Permissions, add chat:write, users:read, im:history, chat:write.public to the Bot Token Scopes*

7. For **Team ID**, go to the browser and log into your workspace.
   
8. In the browser, take the **TEAM ID** from the url: `https://app.slack.com/client/TEAM_ID`

9. Add the **OAuth Token** and the **Team ID** to your `mcp_agent.secrets.yaml` file

10. *[Optional] Make sure to launch and install your Slack bot to your workspace. And, invite the new bot to the channel you want to interact with.*

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
