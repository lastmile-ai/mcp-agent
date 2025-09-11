import sys

from mcp_agent.cli.main import app


GO_OPTIONS = {
    "--npx",
    "--uvx",
    "--stdio",
    "--url",
    "--model",
    "--models",
    "--instruction",
    "-i",
    "--message",
    "-m",
    "--prompt-file",
    "-p",
    "--servers",
    "--auth",
    "--name",
    "--config-path",
    "-c",
    "--script",
}

KNOWN = {
    "go",
    "check",
    "chat",
    "dev",
    "invoke",
    "serve",
    "init",
    "quickstart",
    "config",
    "keys",
    "models",
    "server",
    "build",
    "logs",
    "doctor",
    "configure",
    "cloud",
}


def main():
    if len(sys.argv) > 1:
        first = sys.argv[1]
        if first not in KNOWN:
            for i, arg in enumerate(sys.argv[1:], 1):
                if arg in GO_OPTIONS or any(
                    arg.startswith(opt + "=") for opt in GO_OPTIONS
                ):
                    sys.argv.insert(i, "go")
                    break
    app()


if __name__ == "__main__":
    main()
