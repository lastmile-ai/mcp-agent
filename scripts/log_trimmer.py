# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pyperclip",
#     "tiktoken",
#     "typer",
# ]
# ///

import re
import pyperclip
import tiktoken
import typer
from pathlib import Path

app = typer.Typer()


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


PATTERNS = [
    r'\{"level":"DEBUG","timestamp":.*,"namespace":"mcp_agent\.tracing\.token_counter.+',
    r"'tools':.+",
    r'"timestamp":"[^"]*"',
]


@app.command()
def clean(file: Path = typer.Argument(..., help="Path to the file to clean")):
    """
    Remove specific debug and timestamp lines from a file and copy result to clipboard.
    """
    content = file.read_text()

    for pattern in PATTERNS:
        content = re.sub(pattern, "", content)

    pyperclip.copy(content)

    token_count = count_tokens(content)

    typer.echo("✅ Cleaned content copied to clipboard.")
    typer.echo(f"🧠 Estimated tokens (gpt-4o): {token_count}")

    typer.echo("Cleaned content copied to clipboard.")


if __name__ == "__main__":
    app()
