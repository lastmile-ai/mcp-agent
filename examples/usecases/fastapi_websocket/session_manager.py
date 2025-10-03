import asyncio
import os
import uuid
from typing import Dict, Optional
from datetime import datetime

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM


class UserSession:
    """Represents a user session with MCP agent integration."""

    def __init__(self, user_id: str, session_id: str):
        self.user_id = user_id
        self.session_id = session_id
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.message_history = []

        # MCP agent components
        self.mcp_app: Optional[MCPApp] = None
        self.agent_app = None
        self.agent: Optional[Agent] = None
        self.llm = None

    async def initialize(self):
        """Initialize the MCP agent for this session."""
        try:
            # Create MCP app for this session
            self.mcp_app = MCPApp(name=f"mcp_websocket_session_{self.user_id}")

            # Start the MCP app
            self.agent_app = await self.mcp_app.run().__aenter__()

            # Get context and logger
            context = self.agent_app.context
            logger = self.agent_app.logger

            # Add current directory to filesystem server args
            context.config.mcp.servers["filesystem"].args.extend([os.getcwd()])

            # Create agent with access to filesystem and fetch servers
            self.agent = Agent(
                name=f"websocket_agent_{self.user_id}",
                instruction=f"""You are an AI assistant for user {self.user_id} with access to filesystem and web resources.
                You can help with file operations, web searches, and general assistance.
                Always be helpful, accurate, and concise in your responses.""",
                server_names=["fetch", "filesystem"],
            )

            # Initialize the agent
            await self.agent.__aenter__()

            # Attach LLM to the agent
            self.llm = await self.agent.attach_llm(OpenAIAugmentedLLM)

            logger.info(f"Session initialized for user {self.user_id}")

        except Exception as e:
            if self.agent_app:
                await self.agent_app.__aexit__(None, None, None)
            raise e

    async def process_message(self, message: str) -> str:
        """Process a user message through the MCP agent."""
        try:
            # Update last activity
            self.last_activity = datetime.now()

            # Add to message history
            self.message_history.append(
                {
                    "role": "user",
                    "content": message,
                    "timestamp": self.last_activity.isoformat(),
                }
            )

            # Process through LLM
            if not self.llm:
                return "Error: Agent not initialized"

            response = await self.llm.generate_str(message=message)

            # Add response to history
            self.message_history.append(
                {
                    "role": "assistant",
                    "content": response,
                    "timestamp": datetime.now().isoformat(),
                }
            )

            return response

        except Exception as e:
            error_msg = f"Error processing message: {str(e)}"
            self.message_history.append(
                {
                    "role": "error",
                    "content": error_msg,
                    "timestamp": datetime.now().isoformat(),
                }
            )
            return error_msg

    async def cleanup(self):
        """Clean up the session resources."""
        try:
            if self.agent:
                await self.agent.__aexit__(None, None, None)
            if self.agent_app:
                await self.agent_app.__aexit__(None, None, None)
        except Exception as e:
            print(f"Error during session cleanup for user {self.user_id}: {e}")


class SessionManager:
    """Manages user sessions for the WebSocket server."""

    def __init__(self):
        self.sessions: Dict[str, UserSession] = {}
        self.cleanup_interval = 3600  # Clean up inactive sessions every hour
        self.max_inactive_time = 7200  # Remove sessions inactive for 2 hours

    async def initialize(self):
        """Initialize the session manager."""
        # Start cleanup task
        asyncio.create_task(self._cleanup_task())

    async def get_or_create_session(self, user_id: str) -> UserSession:
        """Get existing session or create a new one for the user."""
        if user_id in self.sessions:
            session = self.sessions[user_id]
            session.last_activity = datetime.now()
            return session

        # Create new session
        session_id = str(uuid.uuid4())
        session = UserSession(user_id, session_id)

        try:
            await session.initialize()
            self.sessions[user_id] = session
            return session
        except Exception as e:
            await session.cleanup()
            raise Exception(f"Failed to create session for user {user_id}: {str(e)}")

    async def cleanup_session(self, user_id: str):
        """Clean up a specific user session."""
        if user_id in self.sessions:
            session = self.sessions[user_id]
            await session.cleanup()
            del self.sessions[user_id]

    async def cleanup(self):
        """Clean up all sessions."""
        cleanup_tasks = []
        for user_id, session in self.sessions.items():
            cleanup_tasks.append(session.cleanup())

        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)

        self.sessions.clear()

    async def _cleanup_task(self):
        """Background task to clean up inactive sessions."""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)

                current_time = datetime.now()
                inactive_users = []

                for user_id, session in self.sessions.items():
                    time_since_activity = (
                        current_time - session.last_activity
                    ).total_seconds()
                    if time_since_activity > self.max_inactive_time:
                        inactive_users.append(user_id)

                # Clean up inactive sessions
                for user_id in inactive_users:
                    print(f"Cleaning up inactive session for user: {user_id}")
                    await self.cleanup_session(user_id)

            except Exception as e:
                print(f"Error in cleanup task: {e}")

    def get_session_info(self, user_id: str) -> Optional[dict]:
        """Get session information for a user."""
        if user_id not in self.sessions:
            return None

        session = self.sessions[user_id]
        return {
            "user_id": session.user_id,
            "session_id": session.session_id,
            "created_at": session.created_at.isoformat(),
            "last_activity": session.last_activity.isoformat(),
            "message_count": len(session.message_history),
        }
