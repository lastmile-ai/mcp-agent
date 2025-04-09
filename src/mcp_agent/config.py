"""
Reading settings from environment variables and providing a settings object
for the application configuration.
"""

from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class MCPServerAuthSettings(BaseModel):
    """Represents authentication configuration for a server."""

    api_key: str | None = None

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class MCPRootSettings(BaseModel):
    """Represents a root directory configuration for an MCP server."""

    uri: str
    """The URI identifying the root. Must start with file://"""

    name: Optional[str] = None
    """Optional name for the root."""

    server_uri_alias: Optional[str] = None
    """Optional URI alias for presentation to the server"""

    @field_validator("uri", "server_uri_alias")
    @classmethod
    def validate_uri(cls, v: str) -> str:
        """Validate that the URI starts with file:// (required by specification 2024-11-05)"""
        if not v.startswith("file://"):
            raise ValueError("Root URI must start with file://")
        return v

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class MCPServerSettings(BaseModel):
    """
    Represents the configuration for an individual server.
    """

    # TODO: saqadri - server name should be something a server can provide itself during initialization
    name: str | None = None
    """The name of the server."""

    # TODO: saqadri - server description should be something a server can provide itself during initialization
    description: str | None = None
    """The description of the server."""

    transport: Literal["stdio", "sse", "websocket"] = "stdio"
    """The transport mechanism."""

    command: str | None = None
    """The command to execute the server (e.g. npx)."""

    args: List[str] | None = None
    """The arguments for the server command."""

    read_timeout_seconds: int | None = None
    """The timeout in seconds for the server connection."""

    url: str | None = None
    """The URL for the server (e.g. for SSE transport)."""

    auth: MCPServerAuthSettings | None = None
    """The authentication configuration for the server."""

    headers: Dict[str, str] | None = None
    """HTTP headers for sse or websocket requests."""

    roots: Optional[List[MCPRootSettings]] = None
    """Root directories this server has access to."""

    env: Dict[str, str] | None = None
    """Environment variables to pass to the server process."""


class MCPSettings(BaseModel):
    """Configuration for all MCP servers."""

    servers: Dict[str, MCPServerSettings] = {}
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class AnthropicSettings(BaseModel):
    """
    Settings for using Anthropic models in the MCP Agent application.
    """

    api_key: str | None = None

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class BedrockSettings(BaseModel):
    """
    Settings for using Bedrock models in the MCP Agent application.
    """

    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_session_token: str | None = None
    aws_region: str | None = None
    profile: str | None = None

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class CohereSettings(BaseModel):
    """
    Settings for using Cohere models in the MCP Agent application.
    """

    api_key: str | None = None

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class OpenAISettings(BaseModel):
    """
    Settings for using OpenAI models in the MCP Agent application.
    """

    api_key: str | None = None
    reasoning_effort: Literal["low", "medium", "high"] = "medium"

    base_url: str | None = None

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class AzureSettings(BaseModel):
    """
    Settings for using Azure models in the MCP Agent application.
    """

    api_key: str

    endpoint: str

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class TemporalSettings(BaseModel):
    """
    Temporal settings for the MCP Agent application.
    """

    host: str
    namespace: str = "default"
    task_queue: str
    api_key: str | None = None


class UsageTelemetrySettings(BaseModel):
    """
    Settings for usage telemetry in the MCP Agent application.
    Anonymized usage metrics are sent to a telemetry server to help improve the product.
    """

    enabled: bool = True
    """Enable usage telemetry in the MCP Agent application."""

    enable_detailed_telemetry: bool = False
    """If enabled, detailed telemetry data, including prompts and agents, will be sent to the telemetry server."""


class OpenTelemetrySettings(BaseModel):
    """
    OTEL settings for the MCP Agent application.
    """

    enabled: bool = True

    service_name: str = "mcp-agent"
    service_instance_id: str | None = None
    service_version: str | None = None

    otlp_endpoint: str | None = None
    """OTLP endpoint for OpenTelemetry tracing"""

    console_debug: bool = False
    """Log spans to console"""

    sample_rate: float = 1.0
    """Sample rate for tracing (1.0 = sample everything)"""


class LogPathSettings(BaseModel):
    """
    Settings for configuring log file paths with dynamic elements like timestamps or session IDs.
    """

    path_pattern: str = "logs/mcp-agent-{unique_id}.jsonl"
    """
    Path pattern for log files with a {unique_id} placeholder.
    The placeholder will be replaced according to the unique_id setting.
    Example: "logs/mcp-agent-{unique_id}.jsonl"
    """

    unique_id: Literal["timestamp", "session_id"] = "timestamp"
    """
    Type of unique identifier to use in the log filename:
    - timestamp: Uses the current time formatted according to timestamp_format
    - session_id: Generates a UUID for the session
    """

    timestamp_format: str = "%Y%m%d_%H%M%S"
    """
    Format string for timestamps when unique_id is set to "timestamp".
    Uses Python's datetime.strftime format.
    """


class LoggerSettings(BaseModel):
    """
    Logger settings for the MCP Agent application.
    """

    # Original transport configuration (kept for backward compatibility)
    type: Literal["none", "console", "file", "http"] = "console"

    transports: List[Literal["none", "console", "file", "http"]] = []
    """List of transports to use (can enable multiple simultaneously)"""

    level: Literal["debug", "info", "warning", "error"] = "info"
    """Minimum logging level"""

    progress_display: bool = False
    """Enable or disable the progress display"""

    path: str = "mcp-agent.jsonl"
    """Path to log file, if logger 'type' is 'file'."""

    # Settings for advanced log path configuration
    path_settings: LogPathSettings | None = None
    """
    Save log files with more advanced path semantics, like having timestamps or session id in the log name.
    """

    batch_size: int = 100
    """Number of events to accumulate before processing"""

    flush_interval: float = 2.0
    """How often to flush events in seconds"""

    max_queue_size: int = 2048
    """Maximum queue size for event processing"""

    # HTTP transport settings
    http_endpoint: str | None = None
    """HTTP endpoint for event transport"""

    http_headers: dict[str, str] | None = None
    """HTTP headers for event transport"""

    http_timeout: float = 5.0
    """HTTP timeout seconds for event transport"""


class Settings(BaseSettings):
    """
    Settings class for the MCP Agent application.
    """

    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
        nested_model_default_partial_update=True,
    )  # Customize the behavior of settings here

    mcp: MCPSettings | None = MCPSettings()
    """MCP config, such as MCP servers"""

    execution_engine: Literal["asyncio", "temporal"] = "asyncio"
    """Execution engine for the MCP Agent application"""

    temporal: TemporalSettings | None = None
    """Settings for Temporal workflow orchestration"""

    anthropic: AnthropicSettings | None = None
    """Settings for using Anthropic models in the MCP Agent application"""

    bedrock: BedrockSettings | None = None
    """Settings for using Bedrock models in the MCP Agent application"""

    cohere: CohereSettings | None = None
    """Settings for using Cohere models in the MCP Agent application"""

    openai: OpenAISettings | None = None
    """Settings for using OpenAI models in the MCP Agent application"""

    azure: AzureSettings | None = None
    """Settings for using Azure models in the MCP Agent application"""

    otel: OpenTelemetrySettings | None = OpenTelemetrySettings()
    """OpenTelemetry logging settings for the MCP Agent application"""

    logger: LoggerSettings | None = LoggerSettings()
    """Logger settings for the MCP Agent application"""

    usage_telemetry: UsageTelemetrySettings | None = UsageTelemetrySettings()
    """Usage tracking settings for the MCP Agent application"""

    @classmethod
    def find_config(cls) -> Path | None:
        """Find the config file in the current directory or parent directories."""
        return cls._find_config(["mcp-agent.config.yaml", "mcp_agent.config.yaml"])

    @classmethod
    def find_secrets(cls) -> Path | None:
        """Find the secrets file in the current directory or parent directories."""
        return cls._find_config(["mcp-agent.secrets.yaml", "mcp_agent.secrets.yaml"])

    @classmethod
    def _find_config(cls, filenames: List[str]) -> Path | None:
        """Find the config file of one of the possible names in the current directory or parent directories."""
        current_dir = Path.cwd()

        # Check current directory and parent directories
        while current_dir != current_dir.parent:
            for filename in filenames:
                config_path = current_dir / filename
                if config_path.exists():
                    return config_path
            current_dir = current_dir.parent

        return None


# Global settings object
_settings: Settings | None = None


def get_settings(config_path: str | None = None) -> Settings:
    """Get settings instance, automatically loading from config file if available."""

    def deep_merge(base: dict, update: dict) -> dict:
        """Recursively merge two dictionaries, preserving nested structures."""
        merged = base.copy()
        for key, value in update.items():
            if (
                key in merged
                and isinstance(merged[key], dict)
                and isinstance(value, dict)
            ):
                merged[key] = deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged

    global _settings
    if _settings:
        return _settings

    import yaml  # pylint: disable=C0415

    merged_settings = {}

    # Determine the config file to use
    if config_path:
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
    else:
        config_file = Settings.find_config()

    # If we found a config file, load it
    if config_file and config_file.exists():
        with open(config_file, "r", encoding="utf-8") as f:
            yaml_settings = yaml.safe_load(f) or {}
            merged_settings = yaml_settings

        # Try to find secrets in the same directory as the config file
        config_dir = config_file.parent
        secrets_found = False
        for secrets_filename in ["mcp-agent.secrets.yaml", "mcp_agent.secrets.yaml"]:
            secrets_file = config_dir / secrets_filename
            if secrets_file.exists():
                with open(secrets_file, "r", encoding="utf-8") as f:
                    yaml_secrets = yaml.safe_load(f) or {}
                    merged_settings = deep_merge(merged_settings, yaml_secrets)
                secrets_found = True
                break

        # If no secrets were found in the config directory, fall back to discovery
        if not secrets_found:
            secrets_file = Settings.find_secrets()
            if secrets_file and secrets_file.exists():
                with open(secrets_file, "r", encoding="utf-8") as f:
                    yaml_secrets = yaml.safe_load(f) or {}
                    merged_settings = deep_merge(merged_settings, yaml_secrets)

        _settings = Settings(**merged_settings)
        return _settings

    # No valid config found anywhere
    _settings = Settings()
    return _settings
