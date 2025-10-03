.PHONY: sync
sync:
	uv sync --all-extras --all-packages --group dev

# Linter and Formatter
.PHONY: format
format: 
	uv run scripts/format.py

.PHONY: lint
lint: 
	uv run scripts/lint.py --fix

# Tests
.PHONY: tests
tests: 
	uv run pytest 

.PHONY: coverage
coverage:
	uv run coverage run --omit="src/mcp_agent/cli/**" -m pytest tests -m "not integration"
	uv run coverage xml -o coverage.xml
	uv run coverage report -m --fail-under=80

.PHONY: coverage-report
coverage-report:
	uv run coverage run --omit="src/mcp_agent/cli/**" -m pytest tests
	uv run coverage html

.PHONY: schema
schema:
	uv run scripts/gen_schema.py

.PHONY: prompt
prompt:
	rm -f prompt.md
	uv run scripts/promptify.py -x "**/src/mcp_agent/cli/**" -x "**/src/mcp_agent/utils/**" -x "**/src/mcp_agent/tracing/**" -x "**/src/mcp_agent/executor/temporal/**" -x "**/src/mcp_agent/core/**" -x "**/src/mcp_agent/logging/**" -x "**/scripts/**" -x "**/tests/**" -x "**/.github/**" -x "**/dist/**" -x "**/examples/mcp*" -x "**/data/**" -x "*.jsonl" -x "**/schema/" -x CONTRIBUTING.md