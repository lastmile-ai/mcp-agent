# mcp_playwright_Linkedin_example

This example demonstrates how to build an MCP Agent that uses Playwright to automate LinkedIn interactions and reports results to Slack. The agent logs into LinkedIn, performs searches based on your criteria, scrapes profiles, and then posts summaries directly into your Slack channel.

## How It Works

1. **Connect to MCP Servers**  
   - Playwright MCP server for browser automation  
   - Slack MCP server for messaging  
2. **Authenticate**  
   - Log in to LinkedIn with your credentials  
   - Authenticate your Slack bot  
3. **Perform Search**  
   - Load your `sample_search_criteria.yaml`  
   - Execute LinkedIn search for profiles matching title, location, skills, etc.  
4. **Scrape & Summarize**  
   - Navigate to each profile result  
   - Extract name, headline, location, and experience snippets  
   - Format into a neat summary  
5. **Post to Slack**  
   - Bundle summaries up to `max_results`  
   - Send a single or threaded message to your Slack channel  

## Setup

### Prerequisites

- Node.js (v16+) and npm  
- Python 3.10 or higher  
- Docker (optional, for containerized runs)  
- MCP Agent framework  
- [Playwright MCP Server](https://www.npmjs.com/package/@playwright/mcp)  
- [Slack MCP Server](https://github.com/modelcontextprotocol/servers/tree/main/src/slack)  

### Configuration Files

- **`mcp_agent.config.yaml`**: Defines your MCP servers and logger settings   
- **`mcp_agent.secrets.yaml`**: Stores your LinkedIn and Slack credentials   
- **`sample_search_criteria.yaml`**: Specifies LinkedIn search parameters and Slack channel   

### Getting Your Tokens

#### LinkedIn Credentials

1. Create or use an existing LinkedIn account  
2. Note down your **username** and **password**  
3. Add them under the `playwright.env` section in `mcp_agent.secrets.yaml`

#### Slack Bot Token & Team ID

1. Go to [Slack API apps](https://api.slack.com/apps)  
2. **Create New App** → **From scratch**  
3. Under **OAuth & Permissions**, add scopes:  
   - `chat:write`  
   - `users:read`  
   - `im:history`  
4. Install the app to your workspace and grab the **Bot User OAuth Token**  
5. Find your **Team ID** in your workspace URL: `https://app.slack.com/client/TEAM_ID`  
6. Add both values under the `slack.env` section in `mcp_agent.secrets.yaml`

## Installation

1. Clone this repo  
2. Install Python dependencies:  
   ```bash
   pip install -r requirements.txt