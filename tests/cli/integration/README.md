# Integration Tests

This directory contains integration tests that require external dependencies, such as a running API server or other services.

## Running Integration Tests

By default, these tests are skipped. To run them:

```bash
pytest -m integration
```

## Testing Philosophy

Integration tests in this directory should:

1. **Test True Integration**: These tests should verify the interaction between multiple components or with external services.
2. **Be Environment Aware**: Tests should handle missing dependencies gracefully by skipping rather than failing.
3. **Clearly Document Dependencies**: Each test should clearly state its external dependencies.

## Markers

- `integration`: Marks tests that require external dependencies. These are skipped by default.

## Deprecated Markers

- `mock`: This marker has been removed as mock-based tests should be regular unit tests without special markers.

## Fixtures

Common fixtures are defined in `conftest.py` and include:

- `real_api_credentials` - Retrieves real API credentials for testing
- `mock_api_credentials` - Provides mock credentials for dry-run tests
- `setup_test_env_vars` - Sets up environment variables for testing

## Test Structure

The integration tests are organized as follows:

1. **API Client Integration**: Tests real API client interaction with the API service
2. **Deploy Command Integration**: Tests end-to-end deploy functionality with real configurations
3. **MCP Agent Configs**: Tests processing of realistic agent configurations