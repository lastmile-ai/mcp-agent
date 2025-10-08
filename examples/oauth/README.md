# OAuth Examples

Two complementary scenarios demonstrate how OAuth integrates with MCP:

## interactive_tool

Shows the full authorization code flow for a synchronous tool. When the
client calls the tool, the server sends an `auth/request` message and the
client walks the user through the browser-based login. Subsequent tool calls
reuse the stored token.

## workflow_pre_auth

Demonstrates seeding tokens via the `workflows-pre-auth` tool before running
an asynchronous workflow. This is useful when workflows execute in the
background (e.g., Temporal) and cannot perform interactive authentication on
their own.
