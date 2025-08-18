# FastAPI WebSocket Example with MCP Agent

This example demonstrates how to integrate MCP Agent with FastAPI WebSocket connections to create a real-time chat application that supports multiple users with persistent sessions.

## Features

- 🚀 **FastAPI WebSocket Server**: Real-time bidirectional communication
- 👥 **Multi-user Support**: Individual sessions per user ID
- 🧠 **MCP Agent Integration**: Each user gets their own MCP agent instance
- 📁 **File System Access**: Agents can read/write files in the current directory
- 🌐 **Web Fetch Capabilities**: Agents can fetch content from URLs
- 🔄 **Session Management**: Automatic cleanup of inactive sessions
- 🎨 **Built-in Test Interface**: HTML page for testing WebSocket connections

## Project Structure

```
fastapi_websocket/
├── main.py                          # FastAPI server with WebSocket endpoints
├── session_manager.py               # User session management
├── websocket_client_async.py        # Improved async WebSocket client
├── mcp_agent.config.yaml            # MCP agent configuration
├── mcp_agent.secrets.yaml.example   # Example secrets file
├── requirements.txt                 # Dependencies
└── README.md                        # This file
```

## Setup

1. **Install dependencies**:
   ```bash
   uv pip install -r requirements.txt
   ```

2. **Set up API keys**:
   ```bash
   cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
   # Edit mcp_agent.secrets.yaml and add your OpenAI API key
   ```

3. **Create logs directory**:
   ```bash
   mkdir -p logs
   ```

## Running the Server

Start the FastAPI server:

```bash
uv run main.py
```

The server will start on `http://localhost:8000`

## Usage

### Web Interface

1. Open `http://localhost:8000` in your browser
2. Enter a user ID (or use the default "test_user")
3. Click "Connect" to establish WebSocket connection
4. Type messages and get AI responses in real-time

### API Endpoints

- `GET /`: HTML test interface
- `WebSocket /ws/{user_id}`: WebSocket endpoint for chat
- `GET /health`: Health check endpoint
- `GET /sessions`: List active sessions

### WebSocket Message Format

**Client to Server:**
```json
{
  "message": "Your message here"
}
```

**Server to Client:**
```json
{
  "message": "AI response here",
  "user_id": "user123",
  "session_id": "uuid-session-id"
}
```

**Error Response:**
```json
{
  "error": "Error message here"
}
```

## Python WebSocket Client

### Async Client
For better async handling, use the improved client:

```bash
uv run websocket_client_async.py
```

Or create your own client:

```python
import asyncio
import websockets
import json

async def client():
    uri = "ws://localhost:8000/ws/your_user_id"
    async with websockets.connect(uri) as websocket:
        # Send message
        await websocket.send(json.dumps({"message": "Hello, AI!"}))
        
        # Receive response
        response = await websocket.recv()
        data = json.loads(response)
        print(f"AI: {data['message']}")

asyncio.run(client())
```

## Session Management

- Each user ID gets a unique session with its own MCP agent
- Sessions are automatically cleaned up after 2 hours of inactivity
- Session cleanup runs every hour
- Each session maintains conversation history

## MCP Agent Capabilities

Each user session includes an MCP agent with:

- **Filesystem Access**: Read/write files in the current directory
- **Web Fetching**: Retrieve content from URLs
- **OpenAI Integration**: GPT-4o-mini for text generation
- **Tool Calling**: Automatic tool selection and execution

## Configuration

### MCP Agent Configuration (`mcp_agent.config.yaml`)

```yaml
execution_engine: asyncio
logger:
  transports: [console, file]
  level: debug

mcp:
  servers:
    fetch:
      command: "uvx"
      args: ["mcp-server-fetch"]
    filesystem:
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-filesystem"]

openai:
  default_model: "gpt-4o-mini"
```

### Secrets Configuration (`mcp_agent.secrets.yaml`)

```yaml
openai:
  api_key: "sk-your-openai-api-key-here"
```

## Examples

### Basic Chat
```
User: Hello, who are you?
AI: I'm an AI assistant with access to filesystem and web resources. I can help you with file operations, web searches, and general assistance.
```

### File Operations
```
User: List the files in the current directory
AI: [Lists files using filesystem tools]

User: Create a file called test.txt with "Hello World"
AI: [Creates the file using filesystem tools]
```

### Web Fetching
```
User: Get the content from https://example.com
AI: [Fetches and displays the content]
```

## Error Handling

The server includes comprehensive error handling:

- JSON parsing errors
- WebSocket connection errors
- MCP agent initialization errors
- Session management errors
- Tool execution errors

## Development

### Adding New Features

1. **New MCP Servers**: Add server configurations to `mcp_agent.config.yaml`
2. **Custom Tools**: Extend the agent initialization in `session_manager.py`
3. **Session Enhancements**: Modify the `UserSession` class
4. **API Endpoints**: Add new routes to `main.py`

### Testing

- Use the built-in web interface at `http://localhost:8000`
- Run the Python client: `uv run websocket_client_async.py`
- Test health endpoint: `curl http://localhost:8000/health`
- List sessions: `curl http://localhost:8000/sessions`

## Production Considerations

- Set up proper logging and monitoring
- Implement authentication and authorization
- Add rate limiting
- Use a production WSGI server
- Set up SSL/TLS for secure WebSocket connections
- Configure session persistence for scalability
- Add database storage for conversation history

## Troubleshooting

### Common Issues

1. **WebSocket Connection Failed**
   - Check if the server is running on port 8000
   - Verify firewall settings

2. **MCP Agent Initialization Error**
   - Ensure OpenAI API key is set in `mcp_agent.secrets.yaml`
   - Check if required MCP servers are installed

3. **Tool Execution Errors**
   - Verify MCP server installations: `uvx mcp-server-fetch` and `npx @modelcontextprotocol/server-filesystem`
   - Check file permissions for filesystem operations

4. **Session Management Issues**
   - Monitor logs for cleanup task errors
   - Check memory usage for large numbers of sessions

### Debug Mode

Run with debug logging:
```bash
uv run main.py --log-level debug
```

## License

This example is part of the MCP Agent project and follows the same license terms.