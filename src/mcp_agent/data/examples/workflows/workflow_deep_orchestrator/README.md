# Deep Orchestrator Workflow Example

This example demonstrates the Deep Orchestrator workflow, an adaptive multi-agent system that dynamically plans, executes, and learns from complex tasks. Unlike the standard orchestrator, it features persistent memory, knowledge extraction, budget management, and intelligent replanning capabilities.

This particular example is an advanced student assignment grader that showcases all the Deep Orchestrator's features with full state visibility through a real-time monitoring dashboard.

<img width="1490" height="515" alt="image" src="https://github.com/user-attachments/assets/d69b81e0-0a04-40ef-912d-5516cf7c7ce8" />

<img width="1489" height="746" alt="image" src="https://github.com/user-attachments/assets/b6cfc75a-66e1-4a60-8457-75804e0dc74d" />

<img width="1489" height="814" alt="image" src="https://github.com/user-attachments/assets/bad5aa9c-e16e-4cd3-a4d4-47f8f399194a" />

## Key Features Demonstrated

- **Dynamic Agent Creation**: Automatically designs and spawns specialized agents for each task
- **Knowledge Accumulation**: Extracts and reuses insights across the entire workflow
- **Adaptive Replanning**: Monitors progress and adjusts strategy when objectives aren't met
- **Resource Management**: Tracks and enforces budgets for tokens, cost, and time
- **Parallel Execution**: Runs independent tasks concurrently for efficiency
- **Real-time Monitoring**: Live dashboard showing queue status, budget usage, and progress
- **Agent Caching**: Reuses dynamically created agents to reduce overhead
- **Policy Engine**: Smart decision-making for workflow control

## When to Use Deep Orchestrator

Use this workflow for:

- Complex research or analysis tasks requiring exploration and synthesis
- Long-running workflows that may need multiple iterations
- Tasks where you can't predict all subtasks upfront
- Scenarios requiring knowledge building across multiple steps
- Resource-constrained environments needing budget management

## Dashboard Overview

The live monitoring dashboard displays:

- **Task Queue**: Current, completed, and pending steps with task statuses
- **Current Plan**: Overview of all planned steps and their execution status
- **Memory**: Knowledge items extracted and stored during execution
- **Budget**: Real-time tracking of tokens, cost, and time usage
- **Policy Engine**: Failure tracking and execution decisions
- **Agent Cache**: Performance metrics for dynamic agent reuse

## `1` App Setup

First, clone the repo and navigate to the deep orchestrator example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/workflows/workflow_deep_orchestrator
```

Install `uv` (if you don't have it):

```bash
pip install uv
```

Sync `mcp-agent` project dependencies:

```bash
uv sync
```

Install requirements specific to this example:

```bash
uv pip install -r requirements.txt
```

## `2` Set up environment variables

Copy and configure your secrets and env variables:

```bash
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
```

Then open `mcp_agent.secrets.yaml` and add your API key for your preferred LLM.

## (Optional) Configure Tracing

In `mcp_agent.config.yaml`, you can set `otel` to `enabled` to enable OpenTelemetry tracing for the workflow.
You can [run Jaeger locally](https://www.jaegertracing.io/docs/2.5/getting-started/) to view the traces in the Jaeger UI.

## `3` Run the Example

Create a sample student story for grading:

```bash
echo "The sun was shining brightly as Sarah walked to school. She was excited about presenting her science project on renewable energy. Her teacher, Mr. Johnson, had been very supportive throughout the process. As she entered the classroom, she noticed her classmates were already setting up their projects. The room buzzed with nervous energy. Sarah took a deep breath and began unpacking her solar panel demonstration. Today was going to be a great day, she thought to herself." > short_story.md
```

Run the Deep Orchestrator example:

```bash
uv run main.py
```

## What the Example Does

The assignment grader will:

1. **Plan Comprehensively**: Create a detailed execution plan with multiple analysis steps
2. **Execute in Parallel**: Run grammar check, style analysis, and structure assessment concurrently
3. **Extract Knowledge**: Learn from each analysis step (e.g., common errors, style patterns)
4. **Adapt if Needed**: Replan if initial analysis is incomplete or new requirements emerge
5. **Synthesize Results**: Combine all findings into a comprehensive grading report
6. **Save Report**: Write the final graded report to `graded_report.md`

## Understanding the Output

The live dashboard shows:

- Real-time task execution with status indicators (✓ completed, ⟳ in progress, ✗ failed)
- Budget consumption across tokens, cost, and time dimensions
- Knowledge items being extracted and categorized
- Agent cache performance metrics
- Policy engine decisions and failure handling

After completion, you'll see:

- A preview of the grading report
- Execution statistics (time, iterations, tasks completed)
- Knowledge extracted during the analysis
- Total token usage and cost
- Created artifacts (graded_report.md)

## Configuration Options

You can modify the orchestrator configuration in `main.py`:

```python
orchestrator = DeepOrchestrator(
    max_iterations=25,          # Maximum workflow iterations
    max_replans=2,             # Maximum replanning attempts
    enable_filesystem=True,     # Enable persistent workspace
    enable_parallel=True,       # Enable parallel task execution
    max_task_retries=5,        # Retry failed tasks
)

# Budget limits
orchestrator.budget.max_tokens = 100000
orchestrator.budget.max_cost = 0.80
orchestrator.budget.max_time_minutes = 7
```

## Comparison with Standard Orchestrator

| Feature    | Standard Orchestrator     | Deep Orchestrator                 |
| ---------- | ------------------------- | --------------------------------- |
| Planning   | Fixed or simple iteration | Comprehensive + adaptive          |
| Memory     | In-context only           | Persistent + knowledge extraction |
| Agents     | Predefined only           | Dynamic creation + caching        |
| Execution  | Single pass               | Iterative until complete          |
| Monitoring | Basic logging             | Full state dashboard              |
| Budget     | None                      | Token/cost/time tracking          |

## Learn More

- [Deep Orchestrator Architecture](../../../src/mcp_agent/workflows/deep_orchestrator/README.md)
- [Multi-agent research system](https://www.anthropic.com/engineering/built-multi-agent-research-system) - Anthropic
- [Standard Orchestrator Example](../workflow_orchestrator_worker/README.md)
