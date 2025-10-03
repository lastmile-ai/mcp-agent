"""
Custom log formatter for improved readability of RCM logs.
Handles message content formatting and unwrapping.
"""

import json
import re
import logging
from typing import Dict, Any, Optional
from datetime import datetime


def format_message_content(content: str, max_line_length: int = 100) -> str:
    """Format message content for better readability"""
    if not content:
        return content

    # Handle JSON strings in content
    try:
        if content.strip().startswith("{") and content.strip().endswith("}"):
            parsed = json.loads(content)
            return json.dumps(parsed, indent=2)
    except Exception:
        pass

    # Handle code blocks - preserve them as is
    if "```" in content:
        return content

    # For regular text, unwrap lines but preserve intentional breaks
    lines = content.split("\n")
    formatted_lines = []

    for line in lines:
        line = line.strip()
        if not line:
            formatted_lines.append("")
            continue

        # Split long lines at sentence boundaries
        if len(line) > max_line_length:
            sentences = re.split(r"(?<=[.!?])\s+", line)
            current_line = ""

            for sentence in sentences:
                if len(current_line + sentence) <= max_line_length:
                    current_line += sentence + " "
                else:
                    if current_line:
                        formatted_lines.append(current_line.strip())
                    current_line = sentence + " "

            if current_line:
                formatted_lines.append(current_line.strip())
        else:
            formatted_lines.append(line)

    return "\n".join(formatted_lines)


def format_log_data(data: Dict[str, Any]) -> str:
    """Format log data for better readability"""
    if not data:
        return ""

    # Special handling for common RCM data structures
    if "messages" in data and isinstance(data["messages"], list):
        formatted_data = data.copy()
        formatted_messages = []

        for msg in data["messages"]:
            if isinstance(msg, dict) and "content" in msg:
                formatted_msg = msg.copy()
                formatted_msg["content"] = format_message_content(msg["content"])
                formatted_messages.append(formatted_msg)
            else:
                formatted_messages.append(msg)

        formatted_data["messages"] = formatted_messages
        return json.dumps(formatted_data, indent=2)

    # Handle other structured data
    try:
        return json.dumps(data, indent=2)
    except Exception:
        return str(data)


def extract_key_info(log_record) -> Dict[str, Any]:
    """Extract key information from log records for summary display"""
    key_info = {}

    # Extract logger name components
    logger_parts = log_record.name.split(".")
    if len(logger_parts) > 1:
        key_info["component"] = logger_parts[-1]
        key_info["module"] = ".".join(logger_parts[:-1])

    # Extract message type
    message = log_record.getMessage()
    if "Chat in progress" in message:
        key_info["event_type"] = "LLM_CALL_START"
    elif "Chat finished" in message:
        key_info["event_type"] = "LLM_CALL_END"
    elif "OpenAI ChatCompletion response" in message:
        key_info["event_type"] = "LLM_RESPONSE"
    elif "Conversation event:" in message:
        key_info["event_type"] = "CONVERSATION_EVENT"
    elif "Quality evaluation completed" in message:
        key_info["event_type"] = "QUALITY_EVAL"
    elif "Requirements extracted" in message:
        key_info["event_type"] = "REQUIREMENTS"
    elif "Context consolidated" in message:
        key_info["event_type"] = "CONTEXT_CONSOLIDATION"
    elif "Response generated" in message:
        key_info["event_type"] = "RESPONSE_GENERATED"

    return key_info


def create_readable_summary(message: str, record: logging.LogRecord) -> Optional[str]:
    """Create a readable summary for key log events"""
    key_info = extract_key_info(record)
    event_type = key_info.get("event_type")

    if not event_type:
        return None

    # Create emoji-based summaries for different event types
    if event_type == "LLM_CALL_START":
        component = key_info.get("component", "unknown")
        return f"🤖 LLM CALL START: {component}"

    elif event_type == "LLM_CALL_END":
        return "✅ LLM CALL END"

    elif event_type == "LLM_RESPONSE":
        # Try to extract key info from the message
        if "total_tokens" in message:
            tokens_match = re.search(r'total_tokens["\']:\s*(\d+)', message)
            if tokens_match:
                tokens = tokens_match.group(1)
                return f"📊 LLM RESPONSE: {tokens} tokens used"
        return "📊 LLM RESPONSE: received"

    elif event_type == "CONVERSATION_EVENT":
        return "🔄 CONVERSATION EVENT"

    elif event_type == "QUALITY_EVAL":
        # Try to extract quality score
        score_match = re.search(r'overall_score["\']:\s*([\d.]+)', message)
        if score_match:
            score = float(score_match.group(1))
            return f"⭐ QUALITY EVAL: {score:.2f}"
        return "⭐ QUALITY EVAL: completed"

    elif event_type == "REQUIREMENTS":
        return "📋 REQUIREMENTS: extracted"

    elif event_type == "CONTEXT_CONSOLIDATION":
        return "🔄 CONTEXT: consolidated"

    elif event_type == "RESPONSE_GENERATED":
        return "💬 RESPONSE: generated"

    return None


class ReadableFormatter(logging.Formatter):
    """Custom formatter for improved log readability with unwrapped messages"""

    def __init__(self, show_summaries: bool = True, max_line_length: int = 120):
        super().__init__()
        self.show_summaries = show_summaries
        self.max_line_length = max_line_length

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with improved readability"""
        # Get basic info
        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S.%f")[:-3]
        level = record.levelname
        name = (
            record.name.split(".")[-1] if "." in record.name else record.name
        )  # Just the last component

        # Get the formatted message
        formatted_msg = record.getMessage()

        # Format message content to unwrap lines and improve readability
        formatted_msg = format_message_content(formatted_msg, self.max_line_length)

        # Create readable summary for key events
        summary = None
        if self.show_summaries:
            summary = create_readable_summary(formatted_msg, record)

        # Build the final log line
        if summary:
            return f"[{timestamp}] {level:8} {name:15} | {summary}\n{' ' * 42}| {formatted_msg}"
        else:
            return f"[{timestamp}] {level:8} {name:15} | {formatted_msg}"
