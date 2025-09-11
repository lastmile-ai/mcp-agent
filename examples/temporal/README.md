# Temporal Workflow Examples

This collection of examples demonstrates how to use [Temporal](https://temporal.io/) as the execution engine for MCP Agent workflows. Temporal is a microservice orchestration platform that helps developers build and operate reliable applications at scale. These examples showcase various workflow patterns and use cases.

## Motivation

`mcp-agent` supports both `asyncio` and `temporal` execution modes. These can be configured
simply by changing the `execution_engine` property in the `mcp_agent.config.yaml`.

The main reason for using Temporal is for durable execution -- workflows can be long running,
they can be paused, resumed, retried, and Temporal provides those capabilities.
The same can be accomplished in-memory/in-proc via asyncio, but we recommend using
a workflow orchestration backend for production `mcp-agent` deployments.

## Overview

These examples showcase:

- Defining workflows using MCP Agent's workflow decorators
- Running workflows using Temporal as the execution engine
- Setting up a Temporal worker to process workflow tasks
- Various workflow patterns: basic, parallel processing, routing, orchestration, and evaluator-optimizer

## Prerequisites

- Python 3.10+
- [UV](https://github.com/astral-sh/uv) package manager
- A running Temporal server (see setup instructions below)

## Setting Up Temporal Server

Before running these examples, you need to have a Temporal server running. The easiest way to get started is using the Temporal CLI:

1. Install the Temporal CLI by following the instructions at: https://docs.temporal.io/cli/

2. Start a local Temporal server:
   ```bash
   temporal server start-dev
   ```

This will start a Temporal server on `localhost:7233` (the default address configured in `mcp_agent.config.yaml`).

You can also use the Temporal Web UI to monitor your workflows by visiting `http://localhost:8233` in your browser.

## Configuration

The examples use the configuration in `mcp_agent.config.yaml`, which includes:

- Temporal server address: `localhost:7233`
- Namespace: `default`
- Task queue: `mcp-agent`
- Maximum concurrent activities: 10

## Running the Examples

To run any of these examples, you'll need to:

1. Install the required dependencies:

   ```bash
   uv pip install -r requirements.txt
   ```

2. Start the Temporal server (as described above)

3. In a separate terminal, start the worker:

   ```bash
   uv run run_worker.py
   ```

   The worker will register all workflows with Temporal and wait for tasks to execute.

4. In another terminal, run any of the example workflow scripts:
   ```bash
   uv run basic.py
   # OR
   uv run evaluator_optimizer.py
   # OR
   uv run orchestrator.py
   # OR
   uv run parallel.py
   # OR
   uv run router.py
   ```

## Example Workflows

### Basic Workflow (`basic.py`)

A simple example that demonstrates the fundamentals of using Temporal with MCP Agent:

- Creates a basic finder agent that can access the filesystem and fetch web content
- Takes a request to fetch web content and processes it using an LLM
- Demonstrates the core workflow execution pattern

### Evaluator-Optimizer Workflow (`evaluator_optimizer.py`)

An example showcasing a workflow that iteratively improves content based on evaluation:

- Uses an optimizer agent to generate a cover letter based on job posting and candidate details
- Uses an evaluator agent to assess the quality of the generated content
- Iteratively refines the content until it meets quality requirements
- Demonstrates how to implement feedback loops in workflows

### Orchestrator Workflow (`orchestrator.py`)

A more complex example that demonstrates how to orchestrate multiple agents:

- Uses the @app.async_tool decorator instead of explicit workflow/run definitions
- Uses a combination of finder, writer, proofreader, fact-checker and style enforcer agents
- Orchestrates these agents to collaboratively complete a task
- Dynamically plans each step of the workflow
- Processes a short story and generates a feedback report

### Parallel Workflow (`parallel.py`)

Demonstrates how to execute tasks in parallel:

- Processes a short story using multiple specialized agents
- Runs proofreader, fact-checker, and style enforcer agents in parallel
- Combines all results using a grader agent
- Shows how to implement a fan-out/fan-in processing pattern

### Router Workflow (`router.py`)

Demonstrates intelligent routing of requests to appropriate agents or functions:

- Uses LLM-based routing to direct requests to the most appropriate handler
- Routes between agents, functions, and servers based on request content
- Shows multiple routing approaches and capabilities
- Demonstrates how to handle complex decision-making in workflows

## Project Structure

- `main.py`: Core application configuration
- `run_worker.py`: Worker setup script for running Temporal workers
- `basic.py`, `evaluator_optimizer.py`, `orchestrator.py`, `parallel.py`, `router.py`: Different workflow examples
- `short_story.md`: Sample content used by the workflow examples
- `graded_report.md`: Output file for the orchestrator and parallel workflows

## How It Works

### Workflow Definition

Workflows are defined using the `@app.workflow` and `@app.workflow_run` decorators:

```python
@app.workflow
class SimpleWorkflow(Workflow[str]):
    @app.workflow_run
    async def run(self, input_data: str) -> WorkflowResult[str]:
        # Workflow logic here
        return WorkflowResult(value=result)
```

### Worker Setup

The worker is set up in `run_worker.py` using the `create_temporal_worker_for_app` function:

```python
async def main():
    async with create_temporal_worker_for_app(app) as worker:
        await worker.run()
```

### Workflow Execution

Workflows are executed by starting them with the executor and waiting for the result:

```python
async def main():
    async with app.run() as agent_app:
        executor: TemporalExecutor = agent_app.executor
        handle = await executor.start_workflow("WorkflowName", input_data)
        result = await handle.result()
        print(result)
```

## Additional Resources

- [Temporal Documentation](https://docs.temporal.io/)
- [MCP Agent Documentation](https://github.com/lastmile-ai/mcp-agent)
