# Human interactions in Temporal

This example demonstrates how to implement human interactions in an MCP running as a Temporal workflow. 
Human input can be used for approvals or data entry.
In this case, we ask a human to provide their name, so we can create a personalised greeting.

## Set up

First, clone the repo and navigate to the human_input example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/human_input/temporal
```

Install `uv` (if you don’t have it):

```bash
pip install uv
```

## Set up api keys

In `mcp_agent.secrets.yaml`, set your OpenAI `api_key`.

## Setting Up Temporal Server

Before running this example, you need to have a Temporal server running:

1. Install the Temporal CLI by following the instructions at: https://docs.temporal.io/cli/

2. Start a local Temporal server:
   ```bash
   temporal server start-dev
   ```

This will start a Temporal server on `localhost:7233` (the default address configured in `mcp_agent.config.yaml`).

You can use the Temporal Web UI to monitor your workflows by visiting `http://localhost:8233` in your browser.

## Run locally

In three separate terminal windows, run the following:

```bash
# this runs the mcp app
uv run main.py
```

```bash
# this runs the temporal worker that will execute the workflows
uv run worker.py
```

```bash
# this runs the client
uv run client.py
```

You will be prompted for input after the agent makes the initial tool call.

## Details

Notice how in `main.py` the `human_input_callback` is set to `elicitation_input_callback`.
This makes sure that human input is sought via elicitation.
In `client.py`, on the other hand, it is set to `console_elicitation_callback`.
This way, the client will prompt for input in the console whenever an upstream request for human input is made.

The following diagram shows the components involved and the flow of requests and responses.

```plaintext
┌──────────┐
│   LLM    │
│          │
└──────────┘
     ▲
     │
     1
     │
     ▼
┌──────────┐       ┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│ Temporal │───2──▶│   MCP App    │◀──3──▶│    Client    │◀──4──▶│     User     │
│  worker  │◀──5───│              │       │              │       │ (via console)│
└──────────┘       └──────────────┘       └──────────────┘       └──────────────┘
```

In the diagram,
- (1) uses the tool calling mechanism to call a system-provided tool for human input,
- (2) uses a HTTPS request to tell the MCP App that the workflow wants to make a request,
- (3) uses the MCP protocol for sending the request to the client and receiving the response,
- (4) uses a console prompt to get the input from the user, and
- (5) uses a Temporal signal to send the response back to the workflow.
