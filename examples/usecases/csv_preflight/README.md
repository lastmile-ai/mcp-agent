# Give an mcp-agent a deterministic CSV preflight tool

A useful first step in an import workflow is checking whether a file satisfies a
known contract. For example, duplicate invoice IDs, an impossible calendar date,
or an amount of `NaN` should produce a repeatable answer. An LLM does not need to
make that decision.

This example exposes a small Python validator as an MCP tool, connects it to an
`Agent`, and calls it directly. The complete round trip works without a model API
key: the server is a local subprocess and the transport is stdio. This gives you
a way to test tool discovery, argument validation, result handling, and process
cleanup before adding model-driven orchestration.

The fixture data is synthetic. This example validates a file; it does not import
invoices, modify files, or send the CSV to a model.

## Run it

Use Python 3.10 or newer. From this directory, create an isolated environment:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1` instead. The
client uses `sys.executable` to launch the server with the same environment, so a
second Python installation on your PATH does not silently change server
dependencies. The server path and default fixture path are resolved relative to
`main.py`, not your shell's current directory.

Expected standard output:

```json
{
  "ok": true,
  "rows_read": 2,
  "error_count": 0,
  "errors": [],
  "errors_truncated": false
}
```

Now run the deliberately invalid fixture:

```sh
python main.py invalid.csv
```

It returns `ok: false` and three errors on record 3: a duplicate `invoice_id`, a
non-finite `amount`, and an invalid `invoice_date`. Its process exit status is 1.
An unreadable input or failure to obtain a report exits with status 2; a valid
report exits with status 0. Passing your own path reads that file on the client
and supplies its text to the local server.

## 1. Make the data contract explicit

The accepted header is exactly:

```csv
invoice_id,amount,invoice_date
```

The validator requires that order, rejects missing or extra columns, trims cell
whitespace, and treats invoice IDs as case-sensitive text. Every nonempty record
must have an ID, a finite decimal amount, and a real date in `YYYY-MM-DD` format.
IDs must be unique within this file. It does not check a database for existing
IDs. Negative amounts are allowed for credit entries, and no currency, precision,
or accounting rules are implied.

`Decimal` handles the amount check without converting amounts to binary floats.
Its parser can also accept special values such as `NaN` and `Infinity`, so
`is_finite()` is essential. A date must pass both a format check and
`date.fromisoformat()`; the format alone cannot reject February 30.

The CSV parser supports quoted fields, embedded newlines, CRLF, and an optional
UTF-8 BOM. Truly blank records are ignored; a header-only file passes with zero
rows. Error record numbers count parsed CSV records, including blank records,
with the header as record 1. They are not physical line numbers when a quoted
field spans multiple lines. Record 0 identifies a whole-input error, such as
malformed quoting or the input size limit.

The input is limited to 64,000 characters. The CLI reads at most 64,001 characters
so an oversized file can be rejected without loading the complete file.
The report includes at most 20
error details plus the total count and a truncation flag. It returns no cell
values or transformed invoice records. A larger import workflow should use
streaming or batches with an explicitly defined cross-batch uniqueness policy.

## 2. Expose the function over MCP

`server.py` registers the validator with the Python MCP SDK's `FastMCP`:

```python
from mcp.server.fastmcp import FastMCP
from validator import validate_csv

server = FastMCP("csv-preflight", log_level="WARNING")
server.tool()(validate_csv)

if __name__ == "__main__":
    server.run(transport="stdio")
```

The `csv_text: str` annotation becomes part of the tool's input schema. Passing
an integer produces an MCP tool error, while a well-formed tool call containing
invalid invoice data returns an ordinary report with `ok: false`. These are
different outcomes: one means the tool could not fulfill the request; the other
means it successfully evaluated the data and found problems.

Keep protocol traffic on stdout. Diagnostic output from a stdio server belongs
on stderr; an unrelated `print()` on stdout can break a client connection.

## 3. Let mcp-agent manage the connection

`make_app()` supplies programmatic `Settings`, registering the subprocess under
the server name `csv`. Logging and usage/trace telemetry are disabled for this
local example. You do not need a YAML configuration or a secrets file.

Inside the running application, the client uses the ordinary Agent interface:

```python
async with (
    app.run(),
    Agent(
        name="invoice_checker",
        instruction="Use validate_csv to check invoice data. Do not import or modify it.",
        server_names=["csv"],
        context=app.context,
    ) as agent,
):
    result = await agent.call_tool("validate_csv", {"csv_text": csv_text})
```

The application context is passed explicitly. The context managers own the
connection lifecycle and close the server when the work finishes. The tool name
is unambiguous because this agent connects to only one server.

No LLM is attached, so the instruction is descriptive here: it does not enforce
the validator's rules. Python code defines both the checks and the direct tool
call. If you later attach an augmented LLM, the same tool is available to that
model, but validation should still be performed by the deterministic function.
Provider calls and their costs are outside this example.

## 4. Separate transport failure from a negative result

`check_csv()` first checks `result.isError`. It only interprets the returned JSON
as a validation report after the MCP call succeeds, and it requires a Boolean
`ok` field. It does not convert a tool failure into a successful import decision.

The report intentionally stops before a database write. A real importer needs
its own transaction, duplicate handling against stored data, and domain checks.
Passing this preflight means only that the documented file-level rules passed.

## Verify the complete path

From this directory, run:

```sh
python -m unittest -v
```

Six unit tests cover the CSV contract, decimal/date edges, ID normalization,
report bounds, and fixtures. Two integration tests launch the actual local MCP
server: they discover the tool, reject an incorrectly typed argument, and compare
both fixture reports with the validator's direct result. No provider key or mock
MCP transport is used. A CLI regression test checks that an oversized file is
rejected by the size limit without reading an invalid UTF-8 tail beyond that limit.

Validated on Python 3.12.4/macOS with mcp-agent source commit
`f62d849350816588b1c6294e7914bbe4d8b84072` (0.2.6) and MCP SDK 1.30.0. All nine tests also pass in a fresh
environment installed from this example’s requirements, using the published
mcp-agent 0.2.6 package. The example
requirements keep MCP below version 2 because this server uses the SDK 1.x
FastMCP API. Other platforms and Python versions have not been exercised here.

References:

- [Agent API](https://docs.mcp-agent.com/mcp-agent-sdk/core-components/agents)
- [Application configuration](https://docs.mcp-agent.com/mcp-agent-sdk/core-components/configuring-your-application)
- [Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk)

This tutorial and its implementation were prepared with OpenAI Codex assistance;
the reported checks were executed locally. It is a learning example, not a claim
of production accounting validation or prior client work.
