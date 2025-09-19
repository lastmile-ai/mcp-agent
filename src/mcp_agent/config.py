"""
Reading settings from environment variables and providing a settings object
for the application configuration.
"""

import sys
from io import StringIO
from pathlib import Path
from typing import Dict, List, Literal, Optional, Set
import threading
import warnings

from httpx import URL
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


from mcp_agent.agents.agent_spec import AgentSpec


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

    transport: Literal["stdio", "sse", "streamable_http", "websocket"] = "stdio"
    """The transport mechanism."""

    command: str | None = None
    """The command to execute the server (e.g. npx) in stdio mode."""

    args: List[str] = Field(default_factory=list)
    """The arguments for the server command in stdio mode."""

    url: str | None = None
    """The URL for the server for SSE, Streamble HTTP or websocket transport."""

    headers: Dict[str, str] | None = None
    """HTTP headers for SSE or Streamable HTTP requests."""

    http_timeout_seconds: int | None = None
    """
    HTTP request timeout in seconds for SSE or Streamable HTTP requests.

    Note: This is different from read_timeout_seconds, which 
    determines how long (in seconds) the client will wait for a new
    event before disconnecting
    """

    read_timeout_seconds: int | None = None
    """
    Timeout in seconds the client will wait for a new event before
    disconnecting from an SSE or Streamable HTTP server connection.
    """

    terminate_on_close: bool = True
    """
    For Streamable HTTP transport, whether to terminate the session on connection close.
    """

    auth: MCPServerAuthSettings | None = None
    """The authentication configuration for the server."""

    roots: List[MCPRootSettings] | None = None
    """Root directories this server has access to."""

    env: Dict[str, str] | None = None
    """Environment variables to pass to the server process."""

    allowed_tools: Set[str] | None = None
    """Set of tool names to allow from this server. If specified, only these tools will be exposed to agents. 
    Tool names should match exactly. [WARNING] Empty list will result LLM have no access to tools."""

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class MCPSettings(BaseModel):
    """Configuration for all MCP servers."""

    servers: Dict[str, MCPServerSettings] = Field(default_factory=dict)
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    @field_validator("servers", mode="before")
    def none_to_dict(cls, v):
        return {} if v is None else v


class VertexAIMixin(BaseModel):
    """Common fields for Vertex AI-compatible settings."""

    project: str | None = Field(
        default=None,
        validation_alias=AliasChoices("project", "PROJECT_ID", "GOOGLE_CLOUD_PROJECT"),
    )

    location: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "location", "LOCATION", "CLOUD_LOCATION", "GOOGLE_CLOUD_LOCATION"
        ),
    )

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class BedrockMixin(BaseModel):
    """Common fields for Bedrock-compatible settings."""

    aws_access_key_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("aws_access_key_id", "AWS_ACCESS_KEY_ID"),
    )

    aws_secret_access_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("aws_secret_access_key", "AWS_SECRET_ACCESS_KEY"),
    )

    aws_session_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("aws_session_token", "AWS_SESSION_TOKEN"),
    )

    aws_region: str | None = Field(
        default=None,
        validation_alias=AliasChoices("aws_region", "AWS_REGION"),
    )

    profile: str | None = Field(
        default=None,
        validation_alias=AliasChoices("profile", "AWS_PROFILE"),
    )

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class BedrockSettings(BaseSettings, BedrockMixin):
    """
    Settings for using Bedrock models in the MCP Agent application.
    """

    model_config = SettingsConfigDict(
        env_prefix="",
        extra="allow",
        arbitrary_types_allowed=True,
        env_file=".env",
        env_file_encoding="utf-8",
    )


class AnthropicSettings(BaseSettings, VertexAIMixin, BedrockMixin):
    """
    Settings for using Anthropic models in the MCP Agent application.
    """

    api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "api_key", "ANTHROPIC_API_KEY", "anthropic__api_key"
        ),
    )
    default_model: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "default_model", "ANTHROPIC_DEFAULT_MODEL", "anthropic__default_model"
        ),
    )
    provider: Literal["anthropic", "bedrock", "vertexai"] = Field(
        default="anthropic",
        validation_alias=AliasChoices(
            "provider", "ANTHROPIC_PROVIDER", "anthropic__provider"
        ),
    )
    base_url: str | URL | None = Field(default=None)

    model_config = SettingsConfigDict(
        env_prefix="ANTHROPIC_",
        extra="allow",
        arbitrary_types_allowed=True,
        env_file=".env",
        env_file_encoding="utf-8",
    )


class CohereSettings(BaseSettings):
    """
    Settings for using Cohere models in the MCP Agent application.
    """

    api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("api_key", "COHERE_API_KEY", "cohere__api_key"),
    )

    model_config = SettingsConfigDict(
        env_prefix="COHERE_",
        extra="allow",
        arbitrary_types_allowed=True,
        env_file=".env",
        env_file_encoding="utf-8",
    )


class OpenAISettings(BaseSettings):
    """
    Settings for using OpenAI models in the MCP Agent application.
    """

    api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("api_key", "OPENAI_API_KEY", "openai__api_key"),
    )

    reasoning_effort: Literal["low", "medium", "high"] = Field(
        default="medium",
        validation_alias=AliasChoices(
            "reasoning_effort", "OPENAI_REASONING_EFFORT", "openai__reasoning_effort"
        ),
    )
    base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "base_url", "OPENAI_BASE_URL", "openai__base_url"
        ),
    )

    user: str | None = Field(
        default=None,
        validation_alias=AliasChoices("user", "openai__user"),
    )

    default_headers: Dict[str, str] | None = None
    default_model: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "default_model", "OPENAI_DEFAULT_MODEL", "openai__default_model"
        ),
    )

    # NOTE: An http_client can be programmatically specified
    # and will be used by the OpenAI client. However, since it is
    # not a JSON-serializable object, it cannot be set via configuration.
    # http_client: Client | None = None

    model_config = SettingsConfigDict(
        env_prefix="OPENAI_",
        extra="allow",
        arbitrary_types_allowed=True,
        env_file=".env",
        env_file_encoding="utf-8",
    )


class AzureSettings(BaseSettings):
    """
    Settings for using Azure models in the MCP Agent application.
    """

    api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "api_key", "AZURE_OPENAI_API_KEY", "AZURE_AI_API_KEY", "azure__api_key"
        ),
    )

    endpoint: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "endpoint", "AZURE_OPENAI_ENDPOINT", "AZURE_AI_ENDPOINT", "azure__endpoint"
        ),
    )

    credential_scopes: List[str] | None = Field(
        default=["https://cognitiveservices.azure.com/.default"]
    )

    model_config = SettingsConfigDict(
        env_prefix="AZURE_",
        extra="allow",
        arbitrary_types_allowed=True,
        env_file=".env",
        env_file_encoding="utf-8",
    )


class GoogleSettings(BaseSettings, VertexAIMixin):
    """
    Settings for using Google models in the MCP Agent application.
    """

    api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "api_key", "GOOGLE_API_KEY", "GEMINI_API_KEY", "google__api_key"
        ),
    )

    vertexai: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "vertexai", "GOOGLE_VERTEXAI", "google__vertexai"
        ),
    )

    model_config = SettingsConfigDict(
        env_prefix="GOOGLE_",
        extra="allow",
        arbitrary_types_allowed=True,
        env_file=".env",
        env_file_encoding="utf-8",
    )


class VertexAISettings(BaseSettings, VertexAIMixin):
    """Standalone Vertex AI settings (for future use)."""

    model_config = SettingsConfigDict(
        env_prefix="VERTEXAI_",
        extra="allow",
        arbitrary_types_allowed=True,
        env_file=".env",
        env_file_encoding="utf-8",
    )


class SubagentSettings(BaseModel):
    """
    Settings for discovering and loading project/user subagents (AgentSpec files).
    Supports common formats like Claude Code subagents.
    """

    enabled: bool = True
    """Enable automatic subagent discovery and loading."""

    search_paths: List[str] = Field(
        default_factory=lambda: [
            ".claude/agents",
            "~/.claude/agents",
            ".mcp-agent/agents",
            "~/.mcp-agent/agents",
        ]
    )
    """Ordered list of directories to scan. Earlier entries take precedence on name conflicts (project before user)."""

    pattern: str = "**/*.*"
    """Glob pattern within each directory to match files (YAML/JSON/Markdown supported)."""

    definitions: List[AgentSpec] = Field(default_factory=list)
    """Inline AgentSpec definitions directly in config."""

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class TemporalSettings(BaseModel):
    """
    Temporal settings for the MCP Agent application.
    """

    host: str
    namespace: str = "default"
    api_key: str | None = None
    tls: bool = False
    task_queue: str
    max_concurrent_activities: int | None = None
    timeout_seconds: int | None = 60
    rpc_metadata: Dict[str, str] | None = None
    id_reuse_policy: Literal[
        "allow_duplicate",
        "allow_duplicate_failed_only",
        "reject_duplicate",
        "terminate_if_running",
    ] = "allow_duplicate"

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class UsageTelemetrySettings(BaseModel):
    """
    Settings for usage telemetry in the MCP Agent application.
    Anonymized usage metrics are sent to a telemetry server to help improve the product.
    """

    enabled: bool = True
    """Enable usage telemetry in the MCP Agent application."""

    enable_detailed_telemetry: bool = False
    """If enabled, detailed telemetry data, including prompts and agents, will be sent to the telemetry server."""

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class TracePathSettings(BaseModel):
    """
    Settings for configuring trace file paths with dynamic elements like timestamps or session IDs.
    """

    path_pattern: str = "traces/mcp-agent-trace-{unique_id}.jsonl"
    """
    Path pattern for trace files with a {unique_id} placeholder.
    The placeholder will be replaced according to the unique_id setting.
    Example: "traces/mcp-agent-trace-{unique_id}.jsonl"
    """

    unique_id: Literal["timestamp", "session_id"] = "timestamp"
    """
    Type of unique identifier to use in the trace filename:
    """

    timestamp_format: str = "%Y%m%d_%H%M%S"
    """
    Format string for timestamps when unique_id is set to "timestamp".
    Uses Python's datetime.strftime format.
    """

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class TraceOTLPSettings(BaseModel):
    """
    Settings for OTLP exporter in OpenTelemetry.
    """

    endpoint: str | None = None
    """OTLP endpoint for exporting traces."""

    headers: Dict[str, str] | None = None
    """Optional headers for OTLP exporter."""

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class OpenTelemetrySettings(BaseModel):
    """
    OTEL settings for the MCP Agent application.
    """

    enabled: bool = False

    exporters: List[Literal["console", "file", "otlp"]] = []
    """List of exporters to use (can enable multiple simultaneously)"""

    service_name: str = "mcp-agent"
    service_instance_id: str | None = None
    service_version: str | None = None

    sample_rate: float = 1.0
    """Sample rate for tracing (1.0 = sample everything)"""

    otlp_settings: TraceOTLPSettings | None = None
    """OTLP settings for OpenTelemetry tracing. Required if using otlp exporter."""

    path: str | None = None
    """
    Direct path for trace file. If specified, this takes precedence over path_settings.
    Useful for test scenarios where you want full control over the trace file location.
    """

    # Settings for advanced trace path configuration for file exporter
    path_settings: TracePathSettings | None = None
    """
    Save trace files with more advanced path semantics, like having timestamps or session id in the trace name.
    Ignored if 'path' is specified.
    """

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


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

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


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

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


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

    mcp: MCPSettings | None = Field(default_factory=MCPSettings)
    """MCP config, such as MCP servers"""

    execution_engine: Literal["asyncio", "temporal"] = "asyncio"
    """Execution engine for the MCP Agent application"""

    temporal: TemporalSettings | None = None
    """Settings for Temporal workflow orchestration"""

    anthropic: AnthropicSettings | None = Field(default_factory=AnthropicSettings)
    """Settings for using Anthropic models in the MCP Agent application"""

    bedrock: BedrockSettings | None = Field(default_factory=BedrockSettings)
    """Settings for using Bedrock models in the MCP Agent application"""

    cohere: CohereSettings | None = Field(default_factory=CohereSettings)
    """Settings for using Cohere models in the MCP Agent application"""

    openai: OpenAISettings | None = Field(default_factory=OpenAISettings)
    """Settings for using OpenAI models in the MCP Agent application"""

    azure: AzureSettings | None = Field(default_factory=AzureSettings)
    """Settings for using Azure models in the MCP Agent application"""

    google: GoogleSettings | None = Field(default_factory=GoogleSettings)
    """Settings for using Google models in the MCP Agent application"""

    otel: OpenTelemetrySettings | None = OpenTelemetrySettings()
    """OpenTelemetry logging settings for the MCP Agent application"""

    logger: LoggerSettings | None = LoggerSettings()
    """Logger settings for the MCP Agent application"""

    usage_telemetry: UsageTelemetrySettings | None = UsageTelemetrySettings()
    """Usage tracking settings for the MCP Agent application"""

    agents: SubagentSettings | None = SubagentSettings()
    """Settings for defining and loading subagents for the MCP Agent application"""

    def __eq__(self, other):  # type: ignore[override]
        if not isinstance(other, Settings):
            return NotImplemented
        # Compare by full JSON dump to avoid differences in internal field-set tracking
        return self.model_dump(mode="json") == other.model_dump(mode="json")

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
        """Find a file by name in current, parents, and `.mcp-agent` subdirs, with home fallback.

        Search order:
          - For each directory from CWD -> root:
              - <dir>/<filename>
              - <dir>/.mcp-agent/<filename>
          - Home-level fallback:
              - ~/.mcp-agent/<filename>
        Returns the first match found.
        """
        current_dir = Path.cwd()

        # Check current directory and parent directories (direct and .mcp-agent subdir)
        while True:
            for filename in filenames:
                direct = current_dir / filename
                if direct.exists():
                    return direct

                mcp_dir = current_dir / ".mcp-agent" / filename
                if mcp_dir.exists():
                    return mcp_dir

            if current_dir == current_dir.parent:
                break
            current_dir = current_dir.parent

        # Home directory fallback
        try:
            home = Path.home()
            for filename in filenames:
                home_file = home / ".mcp-agent" / filename
                if home_file.exists():
                    return home_file
        except Exception:
            pass

        return None


class PreloadSettings(BaseSettings):
    """
    Class for preloaded settings of the MCP Agent application.
    """

    model_config = SettingsConfigDict(env_prefix="mcp_app_settings_")

    preload: str | None = None
    """ A literal YAML string to interpret as a serialized Settings model.
    For example, the value given by `pydantic_yaml.to_yaml_str(settings)`.
    Env Var: `MCP_APP_SETTINGS_PRELOAD`.
    """

    preload_strict: bool = False
    """ Whether to perform strict parsing of the preload string.
    If true, failures in parsing will raise an exception.
    If false (default), failures in parsing will fall through to the default
    settings loading.
    Env Var: `MCP_APP_SETTINGS_PRELOAD_STRICT`.
    """


# Global settings object
_settings: Settings | None = None


def _clear_global_settings():
    """
    Convenience for testing - clear the global memoized settings.
    """
    global _settings
    _settings = None


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

    preload_settings = PreloadSettings()
    preload_config = preload_settings.preload
    if preload_config:
        try:
            # Write to an intermediate buffer to force interpretation as literal data and not a file path
            buf = StringIO()
            buf.write(preload_config)
            buf.seek(0)
            yaml_settings = yaml.safe_load(buf) or {}

            # Preload is authoritative: construct from YAML directly (no env overlay)
            return Settings(**yaml_settings)
        except Exception as e:
            if preload_settings.preload_strict:
                raise ValueError(
                    "MCP App Preloaded Settings value failed validation"
                ) from e
            # TODO: Decide the right logging call here - I'm cautious that it's in a very central scope
            print(
                f"MCP App Preloaded Settings value failed validation: {e}",
                file=sys.stderr,
            )

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

    # Thread-safety advisory: warn when using global singleton from non-main thread
    if (
        threading.current_thread() is not threading.main_thread()
        and config_path is None
    ):
        warnings.warn(
            "get_settings() returned the global Settings singleton on a non-main thread. "
            "In multithreaded environments, prefer passing a Settings instance explicitly to MCPApp("
            "settings=...) or provide a per-thread config_path to avoid cross-thread coupling.",
            stacklevel=2,
        )
    return _settings
