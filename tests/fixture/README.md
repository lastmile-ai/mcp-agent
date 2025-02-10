# Test Fixtures

This directory contains test fixtures used for verifying event processing and display functionality.

## Files

- `mcp_basic_agent_20250131_205604.jsonl`: Log file containing events from a basic agent run, including "final response" events from both OpenAI and Anthropic endpoints
- `expected_output.txt`: Expected formatted output when processing the log file through event_summary.py

## Updating Fixtures

If you need to update these fixtures (e.g., when changing event processing logic), you can:

1. Run an example to generate a new log file:
   ```bash
   cd examples/mcp_basic_agent
   rm -f mcp-agent.jsonl  # Start with a clean log file
   uv run python main.py "What is the timestamp in different timezones?"
   cp mcp-agent.jsonl ../../tests/fixture/mcp_basic_agent_20250131_205604.jsonl
   ```

2. Use the utility method to update expected output:
   ```python
   from tests.test_event_progress import update_test_fixtures
   update_test_fixtures()
   ```

The test file will verify that event processing produces consistent output matching these fixtures.

Note: Always start with a clean log file (`rm -f mcp-agent.jsonl`) before generating new fixtures, as the logger appends to existing files.