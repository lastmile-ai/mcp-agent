import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn
from contextlib import asynccontextmanager

from session_manager import SessionManager


# Global session manager
session_manager = SessionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events for the FastAPI application."""
    # Startup
    await session_manager.initialize()
    yield
    # Shutdown
    await session_manager.cleanup()


app = FastAPI(title="MCP Agent WebSocket Server", lifespan=lifespan)


@app.get("/")
async def get():
    """Serve a simple HTML page for testing WebSocket connections."""
    return HTMLResponse("""
<!DOCTYPE html>
<html>
<head>
    <title>MCP Agent WebSocket Test</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        #messages { border: 1px solid #ccc; height: 400px; overflow-y: auto; padding: 10px; margin: 10px 0; }
        #userInput { width: 70%; padding: 10px; }
        #sendBtn { padding: 10px 20px; }
        .message { margin: 5px 0; padding: 5px; border-radius: 3px; }
        .user { background-color: #e3f2fd; }
        .assistant { background-color: #f1f8e9; }
        .system { background-color: #fff3e0; }
    </style>
</head>
<body>
    <h1>MCP Agent WebSocket Test</h1>
    <div>
        <label for="userId">User ID:</label>
        <input type="text" id="userId" value="test_user" />
        <button onclick="connect()">Connect</button>
        <button onclick="disconnect()">Disconnect</button>
        <span id="status">Disconnected</span>
    </div>
    <div id="messages"></div>
    <div>
        <input type="text" id="userInput" placeholder="Type your message..." onkeypress="handleKeyPress(event)" />
        <button id="sendBtn" onclick="sendMessage()">Send</button>
    </div>

    <script>
        let ws = null;
        let userId = 'test_user';

        function connect() {
            userId = document.getElementById('userId').value || 'test_user';
            ws = new WebSocket(`ws://localhost:8000/ws/${userId}`);
            
            ws.onopen = function(event) {
                document.getElementById('status').textContent = 'Connected';
                addMessage('system', 'Connected to WebSocket server');
            };
            
            ws.onmessage = function(event) {
                const data = JSON.parse(event.data);
                addMessage('assistant', data.message);
            };
            
            ws.onclose = function(event) {
                document.getElementById('status').textContent = 'Disconnected';
                addMessage('system', 'Disconnected from WebSocket server');
            };
            
            ws.onerror = function(error) {
                addMessage('system', 'WebSocket error: ' + error);
            };
        }

        function disconnect() {
            if (ws) {
                ws.close();
            }
        }

        function sendMessage() {
            const input = document.getElementById('userInput');
            const message = input.value.trim();
            if (message && ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({message: message}));
                addMessage('user', message);
                input.value = '';
            }
        }

        function handleKeyPress(event) {
            if (event.key === 'Enter') {
                sendMessage();
            }
        }

        function addMessage(type, message) {
            const messagesDiv = document.getElementById('messages');
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${type}`;
            messageDiv.textContent = `${type.toUpperCase()}: ${message}`;
            messagesDiv.appendChild(messageDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }
    </script>
</body>
</html>
    """)


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """WebSocket endpoint for user sessions."""
    await websocket.accept()

    try:
        # Get or create user session
        user_session = await session_manager.get_or_create_session(user_id)

        # Send welcome message
        await websocket.send_text(
            json.dumps(
                {
                    "message": f"Welcome! You are connected as user: {user_id}",
                    "user_id": user_id,
                    "session_id": user_session.session_id,
                }
            )
        )

        while True:
            try:
                # Receive message from client
                data = await websocket.receive_text()
                message_data = json.loads(data)
                user_message = message_data.get("message", "")

                if not user_message:
                    continue

                # Process message through MCP agent
                response = await user_session.process_message(user_message)

                # Send response back to client
                await websocket.send_text(
                    json.dumps(
                        {
                            "message": response,
                            "user_id": user_id,
                            "session_id": user_session.session_id,
                        }
                    )
                )

            except WebSocketDisconnect:
                break
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"error": "Invalid JSON format"}))
            except Exception as e:
                await websocket.send_text(
                    json.dumps({"error": f"An error occurred: {str(e)}"})
                )

    except Exception as e:
        await websocket.send_text(json.dumps({"error": f"Session error: {str(e)}"}))
    finally:
        # Clean up session if needed
        await session_manager.cleanup_session(user_id)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "active_sessions": len(session_manager.sessions)}


@app.get("/sessions")
async def list_sessions():
    """List active sessions."""
    return {
        "active_sessions": list(session_manager.sessions.keys()),
        "total_sessions": len(session_manager.sessions),
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
