# Contributing

We welcome **all** kinds of contributions - bug fixes, big features, docs, examples and more. _You don't need to be an AI expert
or even a Python developer to help out._

## Checklist

Contributions are made through
[pull requests](https://help.github.com/articles/using-pull-requests/).

Before sending a pull request, make sure to do the following:

- Fork the repo, and create a feature branch prefixed with `feature/`
- [Lint, typecheck, and format](#code-quality) your code
- [Add examples](#examples)
- (Ideal) [Add tests](#testing)

_Please reach out to the mcp-agent maintainers before starting work on a large
contribution._ Get in touch at
[GitHub issues](https://github.com/lastmile-ai/mcp-agent/issues)
or [on Discord](https://lmai.link/discord/mcp-agent).

## Prerequisites

To build mcp-agent, you'll need the following installed:

- Install [uv](https://docs.astral.sh/uv/), which we use for Python package management
- Install [Python](https://www.python.org/) >= 3.10. (You may already it installed. To see your version, use `python -V` at the command line.)

  If you don't, install it using `uv python install 3.10`

- Install dev dependencies using:
  ```bash
  make sync
  ```
  This will sync all packages with extras and dev dependencies.

## Development Commands

We provide a [Makefile](./Makefile) with common development commands:

### Code Quality

**Note**: Lint and format are also run as part of the precommit hook defined in [.pre-commit-config.yaml](./.pre-commit-config.yaml).

**Format:**

```bash
make format
```

**Lint:**

This autofixes linter errors as well:

```bash
make lint
```

### Testing

**Run tests:**

```bash
make tests
```

**Run tests with coverage:**

```bash
make coverage
```

**Generate HTML coverage report:**

```bash
make coverage-report
```

### Generate Schema

If you make changes to [config.py](./src/mcp_agent/config.py), please also run the schema generator to update the [mcp-agent.config.schema.json](./schema/mcp-agent.config.schema.json):

```bash
make schema
```

## Scripts

There are several useful scripts in the `scripts/` directory that can be invoked via `uv run scripts/<script>.py [ARGS]`

### promptify.py

**Generates prompt.md file for LLMs**. Very helpful in leverage LLMs to help develop `mcp-agent`.

You can use the Makefile command for a quick generation with sensible defaults:

```bash
make prompt
```

Or run it directly with custom arguments:

```bash
uv run scripts/promptify.py -i "**/agents/**" -i "**/context.py" -x "**/app.py"
```

Use `-i REGEX` to include only specific files, and `-x REGEX` to exclude certain files.

**Note:** There's also an existing `LLMS.txt` file in the repository root that you can use directly as a prompt for LLMs.

## Examples

We use the examples for end-to-end testing. We'd love for you to add Python unit [tests](./tests) for new functionality going forward.

At minimum, for any new feature or provider integration (e.g. additional LLM support), you should add example usage in the [`examples`](./examples/) directory.

### Running Examples

All examples are in the `examples/` directory, organized by category (basic, mcp, usecases, etc.). Each example has its own README with specific instructions.

**General pattern for running examples:**

1. Navigate to the example directory:

   ```bash
   cd examples/basic/mcp_basic_agent
   ```

2. Install dependencies:

   ```bash
   uv pip install -r requirements.txt
   ```

3. Configure secrets (if needed):

   ```bash
   cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
   # Edit mcp_agent.secrets.yaml with your API keys
   ```

4. Run the example:
   ```bash
   uv run main.py
   ```

**Quick Examples:**

- **Basic Agent** (`examples/basic/mcp_basic_agent/`) - A "finder" agent with filesystem and fetch capabilities
- **Researcher** (`examples/usecases/mcp_researcher/`) - Research assistant with search, web fetch, and Python interpreter

Each example includes a README explaining its purpose, architecture, and specific setup requirements.

## Editor settings

If you use vscode, you might find the following `settings.json` useful. We've added them to the [.vscode](./.vscode) directory along with recommended extensions

```json
{
  "editor.formatOnSave": true,
  "editor.defaultFormatter": "esbenp.prettier-vscode",
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true,
    "editor.rulers": []
  },
  "yaml.schemas": {
    "https://raw.githubusercontent.com/lastmile-ai/mcp-agent/main/schema/mcp-agent.config.schema.json": [
      "mcp-agent.config.yaml",
      "mcp_agent.config.yaml",
      "mcp-agent.secrets.yaml",
      "mcp_agent.secrets.yaml"
    ]
  }
}
```

## Thank you

If you are considering contributing, or have already done so, **thank you**. This project is meant to streamline AI application development, and we need all the help we can get! Happy building.
