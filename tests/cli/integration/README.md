# Integration Tests

This directory contains integration tests that verify the MCP Agent Cloud SDK components work together correctly.

## Test Organization

The tests are organized with two markers:

- `integration`: All tests in this directory have this marker
- `mock`: Tests that use a mock backend and work without external dependencies
- `api`: Tests that require a real API connection

## Running Tests

### Mock Tests (No API needed)

Run mock integration tests (fast, works offline):

```bash
pytest -m "integration and mock" -v
```

### API Tests (Web App Required)

These tests need a running web app:

1. Ensure the proto files are properly generated
   - Current issue: Missing `@mcpac/proto/mcpac/api/secrets/v1/secrets_api_service_pb`
   - Make sure the proto generation steps have been completed

2. Start the web app: `cd www && pnpm run webdev`

3. Set a valid API token:
   ```bash
   export MCP_API_TOKEN="valid-test-token-for-your-environment"
   ```
   - The token must be valid for JWT decoding with your web app's NEXTAUTH_SECRET
   - Current issue: "Error decoding API token JWEInvalid: Invalid Compact JWE"

4. Run the tests: `pytest -m "integration and api" -v`

If you're seeing 500 errors from the API endpoints, check for:
- Missing proto files (need to run proto generation)
- Invalid API token (need to set MCP_API_TOKEN to a valid value)
- Other issues in the web app logs

### All Integration Tests

Run all integration tests (will skip API tests if API is unreachable):

```bash
pytest -m integration -v
```

## Test Files

- `test_secrets_integration.py`: Tests for the CLI's ability to process secrets with mock client
- `test_api_client_integration.py`: Tests for the API client with a real API connection
- `conftest.py`: Common fixtures for integration tests

## Design Principles

1. **Mock tests**: Should always pass without external dependencies
2. **API tests**: Will be skipped if API is unavailable
3. **Clear separation**: Tests should clearly indicate whether they need real connections
4. **Realistic fixtures**: Use real configuration files from the fixtures directory