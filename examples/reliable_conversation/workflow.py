from mcp_agent.executor.workflow import Workflow, WorkflowResult
from mcp_agent.executor.workflow_signal import Signal
from typing import Dict, Any, Optional
import asyncio

from .app import rcm_app, SYSTEM_PROMPT
from .models import (
    ConversationState,
    Message,
    ConversationConfig,
    QualityMetrics,
    Requirement,
)
from .tasks.process_turn import process_turn_with_quality


@rcm_app.workflow
class ConversationWorkflow(Workflow[Dict[str, Any]]):
    """
    Conversation-as-workflow implementation supporting both AsyncIO and Temporal.
    Implements paper's findings through LLM-based quality control.
    """

    def __init__(self, name: str = None, context=None, **kwargs):
        super().__init__(name=name, context=context, **kwargs)
        self.conversation_state: Optional[ConversationState] = None
        self.config: Optional[ConversationConfig] = None

    @rcm_app.workflow_run
    async def run(self, args: Dict[str, Any]) -> WorkflowResult[Dict[str, Any]]:
        """
        Main conversation loop - handles both execution modes.
        AsyncIO: Processes single turn, returns immediately
        Temporal: Long-running conversation with signals
        """

        # Initialize configuration
        self.config = ConversationConfig(**args.get("config", {}))

        # Determine execution mode - default to asyncio if no context
        execution_engine = "asyncio"
        if (
            hasattr(self, "context")
            and self.context
            and hasattr(self.context, "config")
        ):
            execution_engine = getattr(
                self.context.config, "execution_engine", "asyncio"
            )

        if execution_engine == "temporal":
            return await self._run_temporal_conversation(args)
        else:
            return await self._run_asyncio_turn(args)

    async def _run_temporal_conversation(
        self, args: Dict[str, Any]
    ) -> WorkflowResult[Dict[str, Any]]:
        """Long-running Temporal conversation with signals and durability."""

        # Initialize conversation state
        self.conversation_state = ConversationState(
            conversation_id=args["conversation_id"], is_temporal_mode=True
        )

        # Add system message
        await self._add_system_message()

        try:
            # Main conversation loop - runs until ended
            while True:
                # Wait for user input or control signals
                signal_result = await self._wait_for_signals()

                if signal_result["type"] == "user_input":
                    await self._process_turn(signal_result["data"]["user_input"])
                elif signal_result["type"] == "pause":
                    await self._handle_pause()
                elif signal_result["type"] == "end":
                    break

        except Exception as e:
            # Log error and save state for recovery
            await self._handle_error(e)
            raise

        return WorkflowResult(
            value={
                "conversation_id": self.conversation_state.conversation_id,
                "final_state": self.conversation_state.model_dump(),
                "total_turns": self.conversation_state.current_turn,
            }
        )

    async def _run_asyncio_turn(
        self, args: Dict[str, Any]
    ) -> WorkflowResult[Dict[str, Any]]:
        """Single turn processing for AsyncIO mode."""

        # Reconstruct or initialize state
        if "state" in args:
            self.conversation_state = ConversationState(**args["state"])
        else:
            self.conversation_state = ConversationState(
                conversation_id=args.get("conversation_id", f"conv-{self.id}"),
                is_temporal_mode=False,
            )
            await self._add_system_message()

        # Process the turn
        user_input = args["user_input"]
        await self._process_turn(user_input)

        # Return response and updated state
        last_message = self.conversation_state.messages[-1]
        return WorkflowResult(
            value={
                "response": last_message.content,
                "state": self.conversation_state.model_dump(),
                "metrics": self.conversation_state.quality_history[-1].model_dump()
                if self.conversation_state.quality_history
                else {},
                "turn_number": self.conversation_state.current_turn,
            }
        )

    async def _process_turn(self, user_input: str):
        """Process a single conversation turn with quality control."""

        # Add user message
        self.conversation_state.current_turn += 1
        self.conversation_state.messages.append(
            Message(
                role="user",
                content=user_input,
                turn_number=self.conversation_state.current_turn,
            )
        )

        # Execute turn processing with quality refinement
        # For now, call the task directly - executor.execute() expects a callable, not a string
        result = await process_turn_with_quality(
            {
                "state": self.conversation_state.model_dump(),
                "config": self.config.model_dump(),
            }
        )

        # Update state with results
        self.conversation_state.messages.append(
            Message(
                role="assistant",
                content=result["response"],
                turn_number=self.conversation_state.current_turn,
            )
        )

        # Update tracked information
        self.conversation_state.requirements = [
            Requirement(**r) for r in result["requirements"]
        ]
        self.conversation_state.consolidated_context = result["consolidated_context"]
        self.conversation_state.quality_history.append(
            QualityMetrics(**result["metrics"])
        )
        self.conversation_state.answer_lengths.append(len(result["response"]))

        # Track consolidation and first attempts
        if result.get("context_consolidated"):
            self.conversation_state.consolidation_turns.append(
                self.conversation_state.current_turn
            )

        if (
            result["metrics"]["premature_attempt"]
            and self.conversation_state.first_answer_attempt_turn is None
        ):
            self.conversation_state.first_answer_attempt_turn = (
                self.conversation_state.current_turn
            )

    async def _wait_for_signals(self) -> Dict[str, Any]:
        """Wait for user input or control signals (Temporal mode)."""
        try:
            # Wait for any signal with timeout
            signal = await asyncio.wait_for(
                self.context.executor.signal_bus.wait_for_signal(
                    Signal(name="conversation_input", workflow_id=self.id)
                ),
                timeout=3600,  # 1 hour timeout
            )

            return {"type": signal.name, "data": signal.data}

        except asyncio.TimeoutError:
            # Conversation timed out
            return {"type": "end", "data": None}

    async def _add_system_message(self):
        """Add system message if first turn."""
        if not self.conversation_state.messages:
            self.conversation_state.messages.append(
                Message(role="system", content=SYSTEM_PROMPT, turn_number=0)
            )

    async def _handle_pause(self):
        """Handle conversation pause (Temporal mode)."""
        self.conversation_state.is_paused = True

        # Wait for resume signal
        await self.context.executor.signal_bus.wait_for_signal(
            Signal(name="resume", workflow_id=self.id)
        )

        self.conversation_state.is_paused = False

    async def _handle_error(self, error: Exception):
        """Handle workflow errors with state preservation."""
        error_info = {
            "error": str(error),
            "conversation_state": self.conversation_state.model_dump(),
            "workflow_id": self.id,
            "turn_number": self.conversation_state.current_turn,
        }

        # Log error for debugging
        await self.context.executor.execute("log_conversation_error", error_info)
