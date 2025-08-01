# Adaptive Workflow Tests

This directory contains tests for the Adaptive Workflow implementation.

## Test Structure

- `conftest.py` - Pytest fixtures and mock objects for testing
- `test_adaptive_workflow.py` - Main test suite for the Adaptive Workflow

## Test Coverage

### TestAdaptiveWorkflowInit
- Tests workflow initialization with default and custom parameters
- Verifies all configuration options are properly set

### TestAdaptiveWorkflowTaskAnalysis  
- Tests task type detection (research vs action vs hybrid)
- Tests complexity estimation functionality
- Verifies LLM-based analysis integration

### TestAdaptiveWorkflowExecution
- Tests basic workflow execution flow
- Tests resource limit enforcement (time, cost, iterations, subagents)
- Tests parallel vs sequential task execution

### TestAdaptiveWorkflowMemory
- Tests memory management initialization
- Tests memory compression functionality
- Verifies workflow state persistence

### TestAdaptiveWorkflowLearning
- Tests learning system initialization
- Tests task complexity estimation based on patterns
- Verifies learning can be disabled

### TestAdaptiveWorkflowIntegration
- End-to-end workflow execution tests
- Integration between all workflow components
- Full pipeline validation with mocked dependencies

## Running Tests

From the project root:

```bash
# Run all adaptive workflow tests
pytest tests/workflows/adaptive/

# Run with coverage
pytest tests/workflows/adaptive/ --cov=mcp_agent.workflows.adaptive

# Run specific test class
pytest tests/workflows/adaptive/test_adaptive_workflow.py::TestAdaptiveWorkflowInit

# Run with verbose output
pytest tests/workflows/adaptive/ -v
```

## Mock Architecture

The tests use comprehensive mocking to isolate the workflow logic:

- `MockAugmentedLLM` - Mocks LLM interactions
- `mock_context` - Provides mock execution context
- `mock_llm_factory` - Factory for creating mock LLMs
- `mock_workflow` - Pre-configured workflow instance for testing

This allows testing of the workflow orchestration logic without requiring actual LLM calls or MCP server connections.