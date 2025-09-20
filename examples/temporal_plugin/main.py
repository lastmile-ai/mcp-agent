from mcp_agent.config import get_settings
from mcp_agent.app import MCPApp

# Load configuration from file
settings = get_settings("mcp_agent.config.yaml")

# Initialize the app to get context
app = MCPApp(name="mcp_basic_agent", settings=settings)
