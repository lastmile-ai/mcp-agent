from mcp_agent.app import MCPApp

app = MCPApp(name="hello_world")


@app.tool()
def hello_world() -> str:
    """A simple tool that returns 'Hello, World!'"""
    return "Hello, World!"
