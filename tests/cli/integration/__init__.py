"""Integration tests for the MCP Agent Cloud SDK.

This package contains tests that verify the MCP Agent Cloud SDK components
work together correctly.

The tests are organized with markers:
- `integration`: All tests in this directory have this marker
- `mock`: Tests that use a mock backend and work without external dependencies
- `api`: Tests that require a real API connection

To run mock tests (no API needed):
    pytest -m "integration and mock" -v

To run API tests (requires web app):
    pytest -m "integration and api" -v

To run all integration tests:
    pytest -m integration -v
"""