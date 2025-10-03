"""
Custom exceptions for the mcp-agent library.
Enables user-friendly error handling for common issues.
"""


class MCPAgentError(Exception):
    """Base exception class for mcp-agent errors"""

    def __init__(self, message: str, details: str = ""):
        self.message = message
        self.details = details
        super().__init__(f"{message}\n\n{details}" if details else message)


class ServerConfigError(MCPAgentError):
    """Raised when there are issues with MCP server configuration
    Example: Server name referenced in agent.servers[] but not defined in config
    """

    def __init__(self, message: str, details: str = ""):
        super().__init__(message, details)


class AgentConfigError(MCPAgentError):
    """Raised when there are issues with Agent or Workflow configuration
    Example: Parallel fan-in references unknown agent
    """

    def __init__(self, message: str, details: str = ""):
        super().__init__(message, details)


class ProviderKeyError(MCPAgentError):
    """Raised when there are issues with LLM provider API keys
    Example: OpenAI/Anthropic key not configured but model requires it
    """

    def __init__(self, message: str, details: str = ""):
        super().__init__(message, details)


class ServerInitializationError(MCPAgentError):
    """Raised when a server fails to initialize properly."""

    def __init__(self, message: str, details: str = ""):
        super().__init__(message, details)


class ModelConfigError(MCPAgentError):
    """Raised when there are issues with LLM model configuration
    Example: Unknown model name in model specification string
    """

    def __init__(self, message: str, details: str = ""):
        super().__init__(message, details)


class CircularDependencyError(MCPAgentError):
    """Raised when we detect a Circular Dependency in the workflow"""

    def __init__(self, message: str, details: str = ""):
        super().__init__(message, details)


class PromptExitError(MCPAgentError):
    """Raised from enhanced_prompt when the user requests hard exits"""

    # TODO an exception for flow control :(
    def __init__(self, message: str, details: str = ""):
        super().__init__(message, details)
