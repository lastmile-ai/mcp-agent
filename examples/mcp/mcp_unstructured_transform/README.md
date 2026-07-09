# MCP Agent: Document parsing with Unstructured Transform

This example shows an [`mcp-agent`](https://github.com/lastmile-ai/mcp-agent)
agent that connects to **Unstructured's hosted Transform MCP server** to turn
documents into clean, structured output.

Transform MCP turns any file into agent-ready data with a single MCP call — no
separate ingestion pipeline to wire up. Drop in a PDF, invoice, spreadsheet,
scan, or email and it can **partition, enrich, chunk, and embed** the content
(returned as markdown, Element JSON, HTML, or plain text), with tables and
layout kept intact — ready for RAG, vector stores, or agent memory. It handles
PDFs, DOCX, PPTX, XLSX, HTML, EML, images, and 60+ file types in all. This
example uses the simplest slice of that: parse a file to clean markdown.

```plaintext
┌──────────┐      ┌──────────────────┐      ┌───────────────────────────┐
│   User   │─────▶│  document_parser │─────▶│  Unstructured Transform   │
│  request │      │      (agent)     │◀─────│   MCP server (hosted)     │
└──────────┘      └──────────────────┘      └───────────────────────────┘
```

## What it does

`main.py` spins up a `document_parser` agent whose only server is
`unstructured_transform`. It hands the agent a public PDF URL and asks for
Markdown. The agent calls the server's tools to do the work:

- `transform_files` — parse a file (public `https://` URL or an uploaded ref)
- `check_transform_status` — poll the resulting job
- `get_transform_results` — fetch the finished output
- `request_file_upload_url` — for local files: mint a signed upload URL, `PUT`
  the bytes, then pass the returned `u10d://file/<id>` ref to `transform_files`

The sample uses a public URL so it runs without an upload step.

## `1` Setup

Install dependencies (from this directory):

```bash
uv pip install -r requirements.txt
```

The only credential you provide by hand is an **LLM provider key** for the agent
itself (OpenAI is the default in `mcp_agent.config.yaml`) — the same key every
`mcp-agent` example uses. The Transform server needs **no API key**: it signs you
in through the browser on first run (step 3).

## `2` Configure secrets

Copy the example secrets file and add your LLM provider key:

```bash
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
```

Set `openai.api_key` (or `anthropic.api_key`). That's the only secret — there is
no Unstructured credential to paste. `mcp_agent.secrets.yaml` is gitignored.

## `3` Run

```bash
uv run main.py
```

On the **first** run, `mcp-agent` opens your browser to **Unstructured's sign-in
page** (`transform.unstructured.io`). Sign in — or sign up; Unstructured is free
to start, with 15,000 pages a month — and approve access. The returned tokens
are cached locally, so later runs don't prompt again. Then the agent lists the Transform server's tools,
submits the file, polls the job, and prints the parsed Markdown.

> **How the keyless auth works:** `mcp_agent.config.yaml` configures OAuth
> against the Transform server (`https://mcp.transform.unstructured.io/` — the
> root path is the MCP endpoint; there is no `/mcp` suffix). The `client_id`
> there is a **public** OAuth client (PKCE, no secret), so it ships safely in the
> repo and needs no per-user registration. If you'd rather skip the browser
> flow, the server also accepts an Unstructured API key as a `Bearer` token via
> a request header.

## Parsing your own files

- **Public URL:** change `SAMPLE_FILE_URL` in `main.py` to any reachable
  `https://` file.
- **Local file:** ask the agent to parse a path — it will call
  `request_file_upload_url`, upload the bytes, and transform the returned ref.

## Learn more

- Unstructured Platform: https://unstructured.io
- Unstructured docs: https://docs.unstructured.io
- mcp-agent: https://github.com/lastmile-ai/mcp-agent
