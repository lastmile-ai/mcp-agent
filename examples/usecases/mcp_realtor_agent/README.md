# MCP Research & Analysis Agent Framework

This example demonstrates a universal research and analysis agent framework that can be adapted for any domain expertise. The system combines MCP server architecture with automatic elicitation for personalized data collection and analysis. Simply replace the agent instructions and API integrations to create specialized research workflows for finance, healthcare, legal, marketing, real estate, or any other field requiring data collection, quality verification, and report generation.

## Features

This research framework provides:

1. **Custom MCP Server Integration**: Pluggable API servers with domain-specific data sources and automatic elicitation
2. **Interactive Elicitation**: Automatic prompts for user preferences, analysis criteria, and domain-specific requirements
3. **Quality Control**: EvaluatorOptimizer ensures comprehensive research meets excellence standards
4. **Multi-Source Data**: Combines domain APIs with web search fallback for complete coverage
5. **Expert Analysis**: Domain-specific insights, calculations, and personalized recommendations
6. **Professional Reports**: Generates comprehensive markdown reports with actionable insights

**Adaptable to any domain**: Change the agent instructions, MCP server, and API integrations to create research agents for finance, healthcare, legal research, market analysis, academic research, or any other expertise area.

```plaintext
┌──────────────┐      ┌────────────────────┐      ┌──────────────────┐
│ Orchestrator ├─────▶│ Research Quality   ├─────▶│ Domain Research  │
│ Workflow     │      │ Controller         │      │ Agent            │
└──────────────┘      └────────────────────┘      └──────────────────┘
       │                        │                          │
       │                        ▼                          ▼
       │                 ┌─────────────┐      ┌──────────────────────┐
       │                 │ Research    │      │ Custom MCP Server    │◀──┐
       │                 │ Quality     │      │ with Elicitation     │   │
       │                 │ Evaluator   │      │ (Domain-Specific)    │   │
       │                 └─────────────┘      └──────────────────────┘   │
       │                                               │                 │
       │                                               ▼                 │
       │                                      ┌──────────────────┐       │
       │                                      │ Domain API       │       │
       │                                      │ (Finance/Health/ │       │
       │                                      │  Legal/etc.)     │       │
       │                                      └──────────────────┘       │
       │                                               │                 │
       │                                               ▼                 │
       │                                      ┌──────────────────┐       │
       │                                      │ Web Search       ├───────┘
       │                                      │ Fallback         │
       │                                      └──────────────────┘
       │
       │            ┌──────────────────┐
       └───────────▶│ Supplementary    │
       │            │ Research Agent   │
       │            └──────────────────┘
       │            ┌──────────────────┐
       └───────────▶│ Domain Analysis  │
       │            │ Agent            │
       │            └──────────────────┘
       │            ┌──────────────────┐
       └────────── ▶│ Report Writer    │
                    │ Agent            │
                    └──────────────────┘
```

## Architecture

### Custom MCP Server
- **Domain-specific FastMCP server** with relevant API integrations
- **Automatic elicitation** for user preferences, analysis criteria, and domain requirements
- **API fallback handling** with structured error responses when domain APIs are unavailable
- **Real data integration** from industry-specific sources

### Agent Workflow
- **Research Quality Controller**: EvaluatorOptimizer component that ensures high-quality data collection
- **Supplementary Research Agent**: Adds web search data to complement domain APIs
- **Domain Analysis Agent**: Provides specialized analysis with domain-specific calculations
- **Report Writer**: Creates comprehensive markdown reports with findings and recommendations

## Use Cases & Examples

The agent will ask domain-relevant questions like:

* **Real Estate**: Property types, budget range, investment goals
* **Finance**: Portfolio size, risk tolerance, investment timeline  
* **Healthcare**: Patient demographics, symptoms, treatment history
* **Legal**: Case type, jurisdiction, legal precedents needed

Reports are saved with expert analysis and actionable recommendations for your specific domain.

## `1` App Setup

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/usecases/mcp_research_agent
uv init
uv sync
uv add mcp-agent fastmcp aiohttp
npm install -g g-search-mcp
npm install -g @modelcontextprotocol/server-filesystem
```

## `2` Set up API keys and configuration

### Get Domain API Key
1. Sign up for your domain-specific API service
2. Get API credentials from the provider dashboard

### Configure secrets
```bash
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
```

Add your API keys to `mcp_agent.secrets.yaml`:
```yaml
openai:
  api_key: "sk-your-openai-api-key"

environment:
  DOMAIN_API_KEY: "your-domain-specific-api-key"
  # Examples:
  # RENTSPIDER_API_KEY: "real-estate-api-key"
  # BLOOMBERG_API_KEY: "finance-api-key"
  # PUBMED_API_KEY: "healthcare-api-key"
```

### Configure MCP servers
Update `mcp_agent.config.yaml` for your domain:
```yaml
mcp:
  servers:
    domain_api:
      command: "python3"
      args: ["domain_server.py"]  # Your custom MCP server
      description: "Domain-specific API server with elicitation"
      env:
        DOMAIN_API_KEY: "${DOMAIN_API_KEY}"
    
    g-search:
      command: "npx"
      args: ["-y", "g-search-mcp"]
      description: "Web search for supplementary research"
    
    filesystem:
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-filesystem", "."]
      description: "File system operations for saving reports"
```

## `3` Customize for your domain

### Create your MCP server
Copy and modify the example server:
```bash
cp rentspider_server.py your_domain_server.py
# Update API endpoints, elicitation schemas, and data processing
```

### Update agent instructions
Modify `main.py` agent instructions for your domain:
```python
domain_research_agent = Agent(
    name="domain_researcher",
    instruction=f"""You are a world-class {YOUR_DOMAIN} researcher.
    
    Use domain-specific tools to gather data:
    1. Call get_domain_data for {LOCATION/ENTITY}
    2. Call analyze_domain_metrics for analysis
    3. If API fails, use web search fallback
    
    Focus on {DOMAIN_SPECIFIC_METRICS}...
    """,
    server_names=["domain_api", "g-search", "fetch"],
)
```

## `4` Run the analysis

```bash
# Run with domain-specific parameters
uv run main.py "Your Analysis Target"
uv run main.py "Austin, TX"          # Real estate
uv run main.py "AAPL portfolio"      # Finance
uv run main.py "diabetes treatment"  # Healthcare
uv run main.py "contract dispute"    # Legal
```

## Interactive Experience

The system automatically prompts for domain-relevant preferences through elicitation:

- **Real Estate**: Budget, property types, investment goals, market timeframes
- **Finance**: Asset allocation, risk tolerance, performance metrics, investment strategy  
- **Healthcare**: Patient demographics, symptoms, treatment preferences
- **Legal**: Case type, jurisdiction, research scope, strategy focus

## Quick Customization

### Create Domain MCP Server
```python
from mcp.server.fastmcp import FastMCP
from mcp.server.elicitation import AcceptedElicitation

@mcp.tool()
async def get_domain_data(query: str, ctx: Context) -> str:
    result = await ctx.elicit(message=f"Configure analysis:", schema=DomainPreferences)
    return domain_api_call(result.data)
```

### Update Agent Instructions
```python
instruction = f"""You are a {DOMAIN} expert. Use domain tools with elicitation, 
fallback to web search if APIs fail. Focus on {DOMAIN_GOALS}."""
```

## Key Features

- **API Fallback**: Graceful degradation to web search when domain APIs unavailable
- **Quality Control**: EvaluatorOptimizer ensures research standards
- **Professional Reports**: Domain-specific insights with actionable recommendations  
- **Multi-Domain**: Easily extend to finance, healthcare, legal, marketing, etc.