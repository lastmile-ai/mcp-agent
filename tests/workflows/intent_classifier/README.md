# Intent Classifier Tests

This directory contains tests for the intent classifier functionality in the MCP Agent.

## Overview

The intent classifier is responsible for determining user intentions from natural language inputs. The tests ensure that:

1. Classifiers initialize correctly
2. Classification produces expected results
3. Different embedding models work as expected
4. Error cases are properly handled


## Mock Strategy

The tests use mock embedding and LLM models to avoid making actual API calls to external services like OpenAI or Cohere. This makes the tests:

- Faster to run
- Not dependent on API keys or network connectivity
- Deterministic in their behavior

## Running Tests

Run all intent classifier tests:

```bash
pytest tests/workflows/intent_classifier/
```

Run a specific test file:

```bash
pytest tests/workflows/intent_classifier/test_intent_classifier_embedding_openai.py
```

Run a specific test:

```bash
pytest tests/workflows/intent_classifier/test_intent_classifier_embedding_openai.py::TestOpenAIEmbeddingIntentClassifier::test_initialization
```

## Test Structure

The tests follow a standard structure:

1. **Setup**: Create mocks, fixtures, and initialize the component under test
2. **Exercise**: Call the method being tested
3. **Verify**: Assert that the results match expectations
4. **Cleanup**: (handled automatically by pytest)

## Adding New Tests

When adding tests for new intent classifier implementations:

1. Create a new test file `test_intent_classifier_[type]_[provider].py`
2. Use the common fixtures from `conftest.py` where appropriate
3. Create custom mocks for any service-specific dependencies
4. Implement tests covering initialization, classification, and error handling

## Key Test Cases

For all intent classifier implementations, ensure testing covers:

- Basic initialization
- Classification with different top_k values
- Classification with different input texts
- Error handling for edge cases
- Performance with large number of intents (if applicable)
