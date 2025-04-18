# 🌐 Browser Console Agent

A command-line application that lets you interact with websites using natural language through the Model Context Protocol (MCP).

![browser agent](https://andrew-dev-s3.s3.us-east-1.amazonaws.com/browser-agent.gif)

## Features

- **Natural Language Control**: Navigate and interact with websites using conversational commands
- **Continuous Browser Session**: Keep the same browser context across multiple queries
- **Real-time Website Analysis**: Extract information, analyze content, and take screenshots
- **Interactive Console Interface**: Simple terminal-based interface for browsing the web

## Requirements

- Python 3.13+
- Node.js and npm (for the MCP Puppeteer server)
- OpenAI API key

## Installation

1. Install using `uv`:
   ```bash
   uv pip install .
   ```

2. Make sure Node.js and npm are installed:
   ```bash
   node --version
   npm --version
   ```

3. Configure your API keys in `mcp_agent.secrets.yaml`:
   ```yaml
   openai:
     api_key: your-openai-api-key
   ```

## Usage

1. Run the console app:
   ```bash
   uv run console_agent.py [URL]
   ```
   If no URL is provided, it defaults to the Wikipedia page for large language models.

2. Type commands to interact with the webpage or select numbered options
3. Type `exit` or `quit` to end the session

## Example Commands

- "Summarize the content on this page"
- "Click on the 'Documentation' link"
- "Fill out the contact form with this information..."
- "Find all links on this page"
- "Navigate to the pricing page"
- "Extract the main headings from this article"
- "Take a screenshot of the current page"

## How It Works

The Browser Console Agent uses:
- **MCP Agent**: Agent frameowkr for Model Context Protocol servers
- **Puppeteer Server**: Provides browser automation capabilities
- **OpenAI**: Powers natural language understanding and generation

The app maintains a continuous browser session, allowing you to:
1. Browse websites with natural language commands
2. Maintain cookies and session state between queries
3. Navigate through websites as if you were using them directly

## Troubleshooting

- Make sure Node.js and npm are properly installed
- Check that your OpenAI API key is correctly configured in `mcp_agent.secrets.yaml`
- If you encounter issues with the Puppeteer server, ensure you have a compatible browser installed
