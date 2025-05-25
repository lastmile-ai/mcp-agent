# LLM Provider Tests

This directory contains tests for the various LLM provider implementations in the MCP Agent library. The tests validate the core functionality of each provider's `AugmentedLLM` implementation.

## Test Coverage

The tests cover the following functionality:

- Basic text generation
- Structured output generation
- Message history handling
- Tool usage
- Error handling
- Type conversion between provider-specific types and MCP types
- Request parameter handling
- Model selection

## Running the Tests

### Prerequisites

Make sure you have installed all the required dependencies:

```bash
# Install required packages
uv sync --all-extras
```

### Running All Tests

To run all the LLM provider tests:

```bash
# From the project root
pytest tests/workflows/llm/

# Or with more detailed output
pytest tests/workflows/llm/ -v
```

### Running Specific Provider Tests

To run tests for a specific provider:

```bash
# OpenAI tests
pytest tests/workflows/llm/test_augmented_llm_openai.py -v

# Anthropic tests
pytest tests/workflows/llm/test_augmented_llm_anthropic.py -v
```

### Running a Specific Test

To run a specific test case:

```bash
pytest tests/workflows/llm/test_augmented_llm_openai.py::TestOpenAIAugmentedLLM::test_basic_text_generation -v
```

### Running with Coverage

To run tests with coverage reports:

```bash
# Generate coverage for all LLM provider tests
pytest tests/workflows/llm/ --cov=src/mcp_agent/workflows/llm

# Generate coverage for a specific provider
pytest --cov=src/mcp_agent/workflows/llm --cov-report=term tests/workflows/llm/test_augmented_llm_openai.py

# Generate an HTML coverage report
pytest --cov=src/mcp_agent/workflows/llm --cov-report=html tests/workflows/llm/test_augmented_llm_openai.py
```

## Adding New Provider Tests

When adding tests for a new provider:

1. Create a new test file following the naming convention: `test_augmented_llm_<provider>.py`
2. Use the existing tests as a template
3. Implement provider-specific test fixtures and helper methods
4. Make sure to cover all core functionality

## Notes on Mocking

The tests use extensive mocking to avoid making actual API calls to LLM providers. The key components that are mocked:

- Context
- Aggregator (for tool calls)
- Executor
- Response objects

This ensures tests can run quickly and without requiring API keys or network access.
