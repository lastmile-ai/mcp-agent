"""
Logging utilities for Reliable Conversation Manager.
Follows mcp-agent logging patterns.
"""

from mcp_agent.logging.logger import get_logger
from typing import Dict, Any, Optional


def get_rcm_logger(name: str):
    """Get logger with RCM-specific formatting"""
    logger = get_logger(f"rcm.{name}")
    return logger


def log_conversation_event(
    logger, event_type: str, conversation_id: str, data: Optional[Dict[str, Any]] = None
):
    """Log conversation-specific events with consistent formatting"""
    log_data = {
        "event_type": event_type,
        "conversation_id": conversation_id,
        **(data or {}),
    }
    logger.info(f"Conversation event: {event_type}", data=log_data)


def log_quality_metrics(
    logger, conversation_id: str, turn_number: int, metrics: Dict[str, Any]
):
    """Log quality metrics for analysis"""
    log_data = {
        "conversation_id": conversation_id,
        "turn_number": turn_number,
        "metrics": metrics,
    }
    logger.info("Quality metrics recorded", data=log_data)


def log_workflow_step(
    logger, conversation_id: str, step: str, details: Optional[Dict[str, Any]] = None
):
    """Log workflow execution steps for debugging"""
    log_data = {
        "conversation_id": conversation_id,
        "workflow_step": step,
        **(details or {}),
    }
    logger.debug(f"Workflow step: {step}", data=log_data)
