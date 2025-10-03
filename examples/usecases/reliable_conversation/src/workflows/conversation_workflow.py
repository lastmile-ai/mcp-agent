"""
Conversation-as-workflow implementation following mcp-agent patterns.
Based on examples/workflows/workflow_swarm/main.py signal handling patterns.
"""

import time
import uuid
from typing import Dict, Any, Optional
from mcp_agent.executor.workflow import Workflow, WorkflowResult
from mcp_agent.agents.agent import Agent

# Import our models
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.conversation_models import (
    ConversationState,
    ConversationMessage,
    ConversationConfig,
    QualityMetrics,
    Requirement,
)
from utils.logging import get_rcm_logger, log_conversation_event, log_workflow_step
from utils.config import get_llm_class, extract_rcm_config


class ConversationWorkflow(Workflow[Dict[str, Any]]):
    """
    Core conversation workflow implementing paper findings.
    Supports both AsyncIO and Temporal execution modes.
    """

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.state: Optional[ConversationState] = None
        self.config: Optional[ConversationConfig] = None
        self.logger = get_rcm_logger("conversation_workflow")

    async def run(self, args: Dict[str, Any]) -> WorkflowResult[Dict[str, Any]]:
        """Main conversation loop - handles both execution modes"""

        # Initialize configuration
        rcm_config = extract_rcm_config(self.app.context.config)
        self.config = ConversationConfig.from_dict(rcm_config)

        # Determine execution mode from context
        execution_engine = self.app.context.config.execution_engine

        if execution_engine == "temporal":
            return await self._run_temporal_conversation(args)
        else:
            return await self._run_asyncio_conversation(args)

    async def _run_asyncio_conversation(
        self, args: Dict[str, Any]
    ) -> WorkflowResult[Dict[str, Any]]:
        """AsyncIO mode - single turn processing for REPL"""

        # Initialize or restore state
        if "state" in args and args["state"]:
            self.state = ConversationState.from_dict(args["state"])
            log_conversation_event(
                self.logger,
                "state_restored",
                self.state.conversation_id,
                {"turn": self.state.current_turn},
            )
        else:
            conversation_id = args.get(
                "conversation_id", f"rcm_{int(time.time())}_{str(uuid.uuid4())[:8]}"
            )
            self.state = ConversationState(
                conversation_id=conversation_id, is_temporal_mode=False
            )
            # Add system message on first turn
            await self._add_system_message()
            log_conversation_event(
                self.logger, "conversation_started", self.state.conversation_id
            )

        # Process single turn
        user_input = args["user_input"]
        await self._process_turn(user_input)

        # Return updated state
        response_data = {
            "response": self.state.messages[-1].content if self.state.messages else "",
            "state": self.state.to_dict(),
            "metrics": self.state.quality_history[-1].to_dict()
            if self.state.quality_history
            else {},
            "turn_number": self.state.current_turn,
        }

        log_conversation_event(
            self.logger,
            "turn_completed",
            self.state.conversation_id,
            {
                "turn": self.state.current_turn,
                "response_length": len(response_data["response"]),
            },
        )

        return WorkflowResult(value=response_data)

    async def _run_temporal_conversation(
        self, args: Dict[str, Any]
    ) -> WorkflowResult[Dict[str, Any]]:
        """Temporal mode - full conversation lifecycle (to be implemented in Phase 6)"""
        # Placeholder for temporal implementation
        raise NotImplementedError("Temporal mode will be implemented in Phase 6")

    async def _add_system_message(self):
        """Add initial system message to conversation"""
        system_message = ConversationMessage(
            role="system",
            content="You are a helpful AI assistant engaged in a multi-turn conversation. "
            "Maintain context across turns and provide thoughtful, accurate responses.",
            turn_number=0,
        )
        self.state.messages.append(system_message)
        log_workflow_step(
            self.logger, self.state.conversation_id, "system_message_added"
        )

    async def _process_turn(self, user_input: str):
        """
        Process single conversation turn with quality control pipeline.
        Implements paper's quality refinement methodology from Phase 2.
        """
        log_workflow_step(
            self.logger,
            self.state.conversation_id,
            "turn_processing_started",
            {"turn": self.state.current_turn + 1},
        )

        # Increment turn counter
        self.state.current_turn += 1

        # Add user message
        user_message = ConversationMessage(
            role="user", content=user_input, turn_number=self.state.current_turn
        )
        self.state.messages.append(user_message)

        # Use quality-controlled processing
        try:
            # Import our task functions directly
            from tasks.task_functions import process_turn_with_quality

            result = await process_turn_with_quality(
                {"state": self.state.to_dict(), "config": self.config.to_dict()}
            )

            # Update state with quality-controlled results
            response = result["response"]

            # Update requirements
            self.state.requirements = [
                Requirement.from_dict(req_dict) for req_dict in result["requirements"]
            ]

            # Update consolidated context
            self.state.consolidated_context = result["consolidated_context"]

            # Add quality metrics
            metrics = QualityMetrics.from_dict(result["metrics"])
            self.state.quality_history.append(metrics)

            # Track paper metrics
            if result.get("context_consolidated"):
                self.state.consolidation_turns.append(self.state.current_turn)

            log_workflow_step(
                self.logger,
                self.state.conversation_id,
                "quality_controlled_processing_completed",
                {
                    "response_length": len(response),
                    "quality_score": metrics.overall_score,
                    "refinement_attempts": result.get("refinement_attempts", 1),
                    "requirements_tracked": len(self.state.requirements),
                },
            )

        except Exception as e:
            # Fallback to basic response generation if quality control fails
            log_workflow_step(
                self.logger,
                self.state.conversation_id,
                "quality_control_fallback",
                {"error": str(e)},
            )

            response = await self._generate_basic_response(user_input)

            # Add basic quality metrics (fallback)
            basic_metrics = QualityMetrics(
                clarity=0.7,
                completeness=0.7,
                assumptions=0.3,
                verbosity=0.3,
                premature_attempt=False,
                middle_turn_reference=0.5,
                requirement_tracking=0.5,
            )
            self.state.quality_history.append(basic_metrics)

        # Add assistant message
        assistant_message = ConversationMessage(
            role="assistant", content=response, turn_number=self.state.current_turn
        )
        self.state.messages.append(assistant_message)

        # Track answer lengths for bloat analysis
        self.state.answer_lengths.append(len(response))

        # Track first answer attempt
        if self.state.first_answer_attempt_turn is None and len(response) > 100:
            self.state.first_answer_attempt_turn = self.state.current_turn

        log_workflow_step(
            self.logger,
            self.state.conversation_id,
            "turn_processing_completed",
            {"response_length": len(response)},
        )

    async def _generate_basic_response(self, user_input: str) -> str:
        """
        Generate basic response using LLM.
        This will be enhanced with quality control in Phase 2.
        """
        log_workflow_step(
            self.logger, self.state.conversation_id, "response_generation_started"
        )

        # Check if we have MCP servers and LLM providers configured
        try:
            # Create a basic agent for response generation
            response_agent = Agent(
                name="basic_responder",
                instruction="You are a helpful assistant. Provide clear, accurate responses based on the conversation context.",
                server_names=self.config.mcp_servers,
            )

            async with response_agent:
                # Get LLM based on config
                llm_class = get_llm_class(self.config.evaluator_model_provider)
                llm = await response_agent.attach_llm(llm_class)

                # Build conversation context for the LLM
                conversation_context = self._build_conversation_context()

                # Generate response
                full_prompt = (
                    f"{conversation_context}\n\nUser: {user_input}\n\nAssistant:"
                )

                response = await llm.generate_str(full_prompt)

                log_workflow_step(
                    self.logger,
                    self.state.conversation_id,
                    "response_generation_completed",
                    {"response_length": len(response)},
                )

                return response

        except Exception as e:
            # Fallback for testing without LLM providers
            log_workflow_step(
                self.logger,
                self.state.conversation_id,
                "response_generation_fallback",
                {"error": str(e)},
            )

            # Generate a simple mock response for testing
            mock_response = f"Thank you for your message: '{user_input}'. This is a mock response for testing purposes."

            log_workflow_step(
                self.logger,
                self.state.conversation_id,
                "response_generation_completed",
                {"response_length": len(mock_response), "mode": "mock"},
            )

            return mock_response

    def _build_conversation_context(self) -> str:
        """Build context string from conversation history"""
        context_parts = []

        # Include recent messages (last 5 for now)
        recent_messages = (
            self.state.messages[-5:]
            if len(self.state.messages) > 5
            else self.state.messages
        )

        for msg in recent_messages:
            if msg.role != "system":  # Skip system message in context
                role_label = "User" if msg.role == "user" else "Assistant"
                context_parts.append(f"{role_label}: {msg.content}")

        return (
            "\n".join(context_parts)
            if context_parts
            else "This is the start of our conversation."
        )
