"""
Tool Usage Listener for MCP Agents.

This module provides a ToolUsageListener that can be attached to an agent
to capture real tool usage data during execution.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from ..logging.events import Event
from ..logging.listeners import EventListener
from .tool_usage_evaluation import ToolUsageEvaluator, ToolEvent


logger = logging.getLogger(__name__)


class ToolUsageListener(EventListener):
    """Event listener that captures tool usage events for evaluation."""
    
    def __init__(self, agent_name: str, config_path: Optional[str] = None):
        """Initialize the tool usage listener.
        
        Args:
            agent_name: Name of the agent being evaluated
            config_path: Path to the agent's config file
        """
        super().__init__()
        self.agent_name = agent_name
        self.evaluator = ToolUsageEvaluator(agent_name, config_path)
    
    def on_event(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """Process an event.
        
        Args:
            event_type: Type of the event
            event_data: Event data
        """
        if event_type == "tool_call":
            # Convert event_data to ToolEvent
            try:
                tool_event = ToolEvent(
                    tool_name=event_data.get("tool_name", "unknown"),
                    parameters=event_data.get("parameters", {}),
                    start_time=event_data.get("timestamp", 0),
                    end_time=event_data.get("end_timestamp"),
                    result=event_data.get("result"),
                    error=event_data.get("error")
                )
                self.evaluator.record_tool_event(tool_event)
                logger.debug(f"Recorded tool event: {tool_event.tool_name}")
            except Exception as e:
                logger.error(f"Error processing tool event: {e}")
    
    def export_results(self, output_dir: Path) -> Path:
        """Export evaluation results to a file.
        
        Args:
            output_dir: Directory to save the results
            
        Returns:
            Path to the saved results file
        """
        return self.evaluator.export_results(output_dir)


def attach_tool_usage_listener(
    agent_instance: Any, 
    agent_name: str, 
    config_path: Optional[str] = None
) -> ToolUsageListener:
    """Attach a tool usage listener to an agent.
    
    Args:
        agent_instance: The agent instance to attach the listener to
        agent_name: Name of the agent
        config_path: Path to the agent's config file
        
    Returns:
        The attached listener
    """
    listener = ToolUsageListener(agent_name, config_path)
    
    # Try different ways to attach the listener based on agent implementation
    if hasattr(agent_instance, "add_event_listener"):
        agent_instance.add_event_listener(listener)
    elif hasattr(agent_instance, "logger") and hasattr(agent_instance.logger, "add_listener"):
        agent_instance.logger.add_listener(listener)
    elif hasattr(agent_instance, "event_bus") and hasattr(agent_instance.event_bus, "subscribe"):
        agent_instance.event_bus.subscribe(listener)
    else:
        logger.warning(f"Could not attach listener to agent {agent_name}. Monitoring will not work.")
    
    return listener