# LinkedIn Candidate Search & CSV Export Tool

This tool uses playwright and filesystems MCP servers and automates searching LinkedIn for candidates matching specific criteria and exports their details to a CSV file.

## Overview

The script (`main_csv.py`) uses the Model Context Protocol (MCP) framework to:
1. Search LinkedIn for candidates based on user-provided criteria
2. Extract candidate profile information
3. Export qualified candidates to a CSV file

## Prerequisites

- Python 3.10
- Node.js (for Playwright)
- MCP Agent configuration files:
  - `mcp_agent.config.yaml`
  - `mcp_agent.secrets.yaml` (with LinkedIn credentials)

## Required MCP Servers

The tool uses two MCP servers:
1. **Playwright Server**: Handles browser automation for LinkedIn interaction
   - Command: `npx @playwright/mcp@latest`
2. **Filesystem Server**: Manages CSV file operations
   - Command: `npx @modelcontextprotocol/server-filesystem`

## Configuration

1. Set up `mcp_agent.config.yaml` with:
   - Server configurations for Playwright and Filesystem
   - Logging settings
   - Execution engine settings

2. Configure `mcp_agent.secrets.yaml` with:
   - LinkedIn credentials (username and password)
   - OpenAI API key
   - Filesystem paths

## Usage
uv run main.py --criteria "Python developers in San Francisco" --max-results 7 --output "/desktop/JOB.csv"
Run the script from the command line using: uv run main.py --criteria "THE POSITION YOU ARE LOOKING FOR" --max-results NUMBER OF MAX RESULTS --output "LOCATION OF SAVED RESULTS"