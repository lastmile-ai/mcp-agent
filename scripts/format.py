# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "ruff",
#     "typer",
# ]
# ///

import subprocess
import sys
import typer
from rich import print


def main(path: str = None):
    try:
        command = ["ruff", "format"]

        if path:
            command.append(path)

        # Run `ruff` and pipe output to the terminal
        process = subprocess.run(
            command,
            check=True,
            stdout=sys.stdout,  # Redirect stdout to the terminal
            stderr=sys.stderr,  # Redirect stderr to the terminal
        )
        sys.exit(process.returncode)  # Exit with the same code as the command
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")  # Log the error in a user-friendly way
        sys.exit(e.returncode)  # Exit with the error code from the command
    except FileNotFoundError:
        print(
            "Error: `ruff` command not found. Make sure it's installed in the environment."
        )
        sys.exit(1)


if __name__ == "__main__":
    typer.run(main)
