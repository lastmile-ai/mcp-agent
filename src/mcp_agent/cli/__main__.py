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
    # Curated top-level commands
    "init",
    "quickstart",
    "config",
    "doctor",
    "deploy",
    "login",
    "whoami",
    "logout",
    "cloud",
    # Umbrella group
    "dev",
}


def main():
    if len(sys.argv) > 1:
        first = sys.argv[1]
        # Back-compat: allow `mcp-agent go ...`
        if first == "go":
            sys.argv.insert(1, "dev")
        elif first not in KNOWN:
            for i, arg in enumerate(sys.argv[1:], 1):
                if arg in GO_OPTIONS or any(
                    arg.startswith(opt + "=") for opt in GO_OPTIONS
                ):
                    # Route bare chat-like invocations to dev go (legacy behavior)
                    sys.argv.insert(i, "dev")
                    sys.argv.insert(i + 1, "go")
                    break
    app()


if __name__ == "__main__":
    main()
