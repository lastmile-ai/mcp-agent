"""
Temporary file to hold the OpenTelemetry semantic conventions for Gen AI and MCP Attributes which are currently
incubating and not yet part of the official OpenTelemetry specification.
See https://github.com/open-telemetry/opentelemetry-python/blob/main/opentelemetry-semantic-conventions/src/opentelemetry/semconv/_incubating/attributes/gen_ai_attributes.py
, https://opentelemetry.io/docs/specs/semconv/attributes-registry/gen-ai/,
and https://github.com/open-telemetry/semantic-conventions/issues/2043
TODO: Remove this file once the Gen AI semantic conventions are officially released.
"""

GEN_AI_AGENT_DESCRIPTION = "gen_ai.agent.description"
"""
Free-form description of the GenAI agent provided by the application.
"""

GEN_AI_AGENT_ID = "gen_ai.agent.id"
"""
The unique identifier of the GenAI agent.
"""

GEN_AI_AGENT_NAME = "gen_ai.agent.name"
"""
Human-readable name of the GenAI agent provided by the application.
"""

GEN_AI_OPENAI_REQUEST_SERVICE_TIER = "gen_ai.openai.request.service_tier"
"""
The service tier requested. May be a specific tier, default, or auto.
"""

GEN_AI_OPENAI_RESPONSE_SERVICE_TIER = "gen_ai.openai.response.service_tier"
"""
The service tier used for the response.
"""

GEN_AI_OPENAI_RESPONSE_SYSTEM_FINGERPRINT = "gen_ai.openai.response.system_fingerprint"
"""
A fingerprint to track any eventual change in the Generative AI environment.
"""

GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
"""
The name of the operation being performed.
Note: If one of the predefined values applies, but specific system uses a different name it's RECOMMENDED to document it in the semantic conventions for specific GenAI system and use system-specific name in the instrumentation. If a different name is not documented, instrumentation libraries SHOULD use applicable predefined value.
"""

GEN_AI_OUTPUT_TYPE = "gen_ai.output.type"
"""
Represents the content type requested by the client.
Note: This attribute SHOULD be used when the client requests output of a specific type. The model may return zero or more outputs of this type.
This attribute specifies the output modality and not the actual output format. For example, if an image is requested, the actual output could be a URL pointing to an image file.
Additional output format details may be recorded in the future in the `gen_ai.output.{type}.*` attributes.
"""

GEN_AI_REQUEST_CHOICE_COUNT = "gen_ai.request.choice.count"
"""
The target number of candidate completions to return.
"""

GEN_AI_REQUEST_ENCODING_FORMATS = "gen_ai.request.encoding_formats"
"""
The encoding formats requested in an embeddings operation, if specified.
Note: In some GenAI systems the encoding formats are called embedding types. Also, some GenAI systems only accept a single format per request.
"""

GEN_AI_REQUEST_FREQUENCY_PENALTY = "gen_ai.request.frequency_penalty"
"""
The frequency penalty setting for the GenAI request.
"""

GEN_AI_REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"
"""
The maximum number of tokens the model generates for a request.
"""

GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
"""
The name of the GenAI model a request is being made to.
"""

GEN_AI_REQUEST_PRESENCE_PENALTY = "gen_ai.request.presence_penalty"
"""
The presence penalty setting for the GenAI request.
"""

GEN_AI_REQUEST_SEED = "gen_ai.request.seed"
"""
Requests with same seed value more likely to return same result.
"""

GEN_AI_REQUEST_STOP_SEQUENCES = "gen_ai.request.stop_sequences"
"""
List of sequences that the model will use to stop generating further tokens.
"""

GEN_AI_REQUEST_TEMPERATURE = "gen_ai.request.temperature"
"""
The temperature setting for the GenAI request.
"""

GEN_AI_REQUEST_TOP_K = "gen_ai.request.top_k"
"""
The top_k sampling setting for the GenAI request.
"""

GEN_AI_REQUEST_TOP_P = "gen_ai.request.top_p"
"""
The top_p sampling setting for the GenAI request.
"""

GEN_AI_RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons"
"""
Array of reasons the model stopped generating tokens, corresponding to each generation received.
"""

GEN_AI_RESPONSE_ID = "gen_ai.response.id"
"""
The unique identifier for the completion.
"""

GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
"""
The name of the model that generated the response.
"""

GEN_AI_SYSTEM = "gen_ai.system"
"""
The Generative AI product as identified by the client or server instrumentation.
Note: The `gen_ai.system` describes a family of GenAI models with specific model identified
by `gen_ai.request.model` and `gen_ai.response.model` attributes.

The actual GenAI product may differ from the one identified by the client.
Multiple systems, including Azure OpenAI and Gemini, are accessible by OpenAI client
libraries. In such cases, the `gen_ai.system` is set to `openai` based on the
instrumentation's best knowledge, instead of the actual system. The `server.address`
attribute may help identify the actual system in use for `openai`.

For custom model, a custom friendly name SHOULD be used.
If none of these options apply, the `gen_ai.system` SHOULD be set to `_OTHER`.
"""

GEN_AI_TOKEN_TYPE = "gen_ai.token.type"
"""
The type of token being counted.
"""

GEN_AI_TOOL_CALL_ID = "gen_ai.tool.call.id"
"""
The tool call identifier.
"""

GEN_AI_TOOL_DESCRIPTION = "gen_ai.tool.description"
"""
The tool description.
"""

GEN_AI_TOOL_NAME = "gen_ai.tool.name"
"""
Name of the tool utilized by the agent.
"""

GEN_AI_TOOL_TYPE = "gen_ai.tool.type"
"""
Type of the tool utilized by the agent.
Note: Extension: A tool executed on the agent-side to directly call external APIs, bridging the gap between the agent and real-world systems.
  Agent-side operations involve actions that are performed by the agent on the server or within the agent's controlled environment.
Function: A tool executed on the client-side, where the agent generates parameters for a predefined function, and the client executes the logic.
  Client-side operations are actions taken on the user's end or within the client application.
Datastore: A tool used by the agent to access and query structured or unstructured external data for retrieval-augmented tasks or knowledge updates.
"""

GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
"""
The number of tokens used in the GenAI input (prompt).
"""

GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
"""
The number of tokens used in the GenAI response (completion).
"""

MCP_METHOD_NAME = "mcp.method.name"
"""
The name of the request or notification method
e.g. notifications/cancelled; initialize; notifications/initialized
"""

MCP_PROMPT_NAME = "mcp.prompt.name"
"""
The name of the prompt or prompt template provided in the request or response
e.g. analyze-code
"""

MCP_REQUEST_ARGUMENT_KEY = "mcp.request.argument"
"""
Usage-format: f'MCP_REQUEST_ARGUMENT_KEY.{argument_KEY}'
Additional arguments passed to the request within params object. <key> being the normalized
argument name (lowercase), the value being the argument value.
e.g. f'{MCP_REQUEST_ARGUMENT_KEY}.location'="Seattle, WA"
"""

MCP_REQUEST_ID = "mcp.request.id"
"""
This is a unique identifier for the request.
"""

MCP_RESOURCE_URI = "mcp.resource.uri"
"""
The value of the resource uri.
e.g. postgres://database/customers/schema; file://home/user/documents/report.pdf
"""

MCP_SESSION_ID = "mcp.session.id"
"""
Identifies MCP session.
"""

MCP_TOOL_NAME = "mcp.tool.name"
"""
The name of the tool provided in the request
e.g. fetch; filesystem
"""
