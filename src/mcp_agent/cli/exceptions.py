"""Custom exceptions for MCP Agent Cloud CLI."""


class CLIError(Exception):
    """Exception for expected CLI errors that should show clean user-facing messages."""

    def __init__(self, message: str, exit_code: int = 1, retriable: bool = True):
        super().__init__(message)
        self.exit_code = exit_code
        self.retriable = retriable
