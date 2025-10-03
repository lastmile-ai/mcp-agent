#!/usr/bin/env python3
"""
Improved WebSocket client using aioconsole for non-blocking input.
Install with: pip install aioconsole
"""

import asyncio
import json
import sys
import websockets
from datetime import datetime

try:
    import aioconsole
except ImportError:
    print("❌ aioconsole not found. Install with: pip install aioconsole")
    sys.exit(1)


class AsyncWebSocketClient:
    """Async WebSocket client with non-blocking input."""

    def __init__(self, user_id: str, host: str = "localhost", port: int = 8000):
        self.user_id = user_id
        self.host = host
        self.port = port
        self.uri = f"ws://{host}:{port}/ws/{user_id}"
        self.websocket = None
        self.running = False

    async def connect(self):
        """Connect to the WebSocket server."""
        try:
            self.websocket = await websockets.connect(self.uri)
            print(f"✅ Connected to WebSocket server as user: {self.user_id}")
            return True
        except Exception as e:
            print(f"❌ Failed to connect: {e}")
            return False

    async def disconnect(self):
        """Disconnect from the WebSocket server."""
        if self.websocket:
            await self.websocket.close()
            print("👋 Disconnected from WebSocket server")

    async def send_message(self, message: str):
        """Send a message to the server."""
        if not self.websocket:
            print("❌ Not connected to server")
            return

        try:
            await self.websocket.send(json.dumps({"message": message}))
            print(f"📤 Sent: {message}")
        except Exception as e:
            print(f"❌ Error sending message: {e}")

    async def listen_for_messages(self):
        """Listen for incoming messages from the server."""
        while self.running and self.websocket:
            try:
                response = await self.websocket.recv()
                data = json.loads(response)

                timestamp = datetime.now().strftime("%H:%M:%S")
                if "error" in data:
                    print(f"\n🔴 [{timestamp}] Error: {data['error']}")
                else:
                    print(f"\n🤖 [{timestamp}] AI: {data.get('message', 'No message')}")

                # Re-prompt for user input
                print("💬 You: ", end="", flush=True)

            except websockets.exceptions.ConnectionClosed:
                print("\n🔌 Connection closed by server")
                break
            except Exception as e:
                print(f"\n❌ Error in message listener: {e}")
                break

    async def handle_user_input(self):
        """Handle user input asynchronously."""
        print("💬 You: ", end="", flush=True)

        while self.running:
            try:
                user_input = await aioconsole.ainput("")
                user_input = user_input.strip()

                if user_input.lower() in ["quit", "exit"]:
                    print("👋 Goodbye!")
                    self.running = False
                    break

                if user_input.lower() == "help":
                    self.show_help()
                    print("💬 You: ", end="", flush=True)
                    continue

                if user_input:
                    await self.send_message(user_input)

                print("💬 You: ", end="", flush=True)

            except (EOFError, KeyboardInterrupt):
                print("\n🛑 Interrupted by user")
                self.running = False
                break

    async def interactive_chat(self):
        """Run an interactive chat session."""
        if not await self.connect():
            return

        print("\n🚀 Starting interactive chat session")
        print("💡 Type 'quit' or 'exit' to disconnect")
        print("💡 Type 'help' for available commands")
        print("=" * 50)

        self.running = True

        # Start both tasks concurrently
        try:
            await asyncio.gather(
                self.listen_for_messages(),
                self.handle_user_input(),
                return_exceptions=True,
            )
        finally:
            self.running = False
            await self.disconnect()

    def show_help(self):
        """Show available commands."""
        print("\n📋 Available commands:")
        print("  help          - Show this help message")
        print("  quit/exit     - Disconnect and exit")
        print("  Ctrl+C        - Interrupt and exit")
        print("\n💡 Example messages to try:")
        print("  - Hello, who are you?")
        print("  - List the files in the current directory")
        print("  - Create a file called test.txt with 'Hello World'")
        print("  - Get the content from https://httpbin.org/json")
        print("  - What's the current time?")


async def main():
    """Main function to run the WebSocket client."""
    # Get user ID from command line or use default
    user_id = sys.argv[1] if len(sys.argv) > 1 else "test_user"

    # Create client
    client = AsyncWebSocketClient(user_id)

    # Run interactive chat
    await client.interactive_chat()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)
