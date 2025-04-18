# MCP Agent Evaluation Framework

This framework provides tools for evaluating MCP agents across different usage scenarios.

## Tool Usage Evaluation Framework

A new evaluation framework specifically focused on tool usage has been added to evaluate how effectively MCP agents select and use tools based on user queries.

### Quick Start

```bash
# Run evaluation on specific agents
uv run -m mcp_agent.eval.test_tool_usage --examples mcp_basic_agent mcp_researcher

# Run specific query evaluations
uv run -m mcp_agent.eval.test_specific_queries

# Generate summary analysis
uv run -m mcp_agent.eval.tool_evaluation_summary
```

### What's Evaluated

The tool usage framework evaluates:

1. **Tool Selection Accuracy**: How well agents choose the appropriate tool for tasks
2. **Processing Time**: Execution time for each tool
3. **Response to Complex Queries**: Performance with complex, multi-intent queries
4. **Multi-Tool Capabilities**: Ability to use multiple tools for a single task

### Evaluation Metrics

- **Basic Selection Accuracy**: Percentage of times the agent selects the correct tool for basic queries
- **Specific Selection Accuracy**: Percentage of times the agent selects the correct tool for complex queries
- **Tool Usage Count**: Frequency of each tool's use

### Understanding Results

Results are stored in three types of files:

1. **Basic Tool Usage**: `tool_usage_evaluation_*.json` 
2. **Specific Queries**: `specific_queries_evaluation_*.json`
3. **Summary Report**: `tool_evaluation_summary_*.json`

#### Interpreting Metrics

- **High basic/specific accuracy (>0.8)**: Agent reliably selects correct tools
- **Basic < Specific accuracy**: Agent handles complex queries better than basic ones
- **Specific < Basic accuracy**: Agent struggles with complex multi-intent queries

#### Recommendations

The summary report provides agent-specific recommendations such as:
- Improving tool selection for basic queries
- Enhancing multi-tool coordination
- Adding support for complex query patterns

### Extending Evaluation

To add new test queries:

1. Modify `_create_challenging_query()` in `test_specific_queries.py`
2. Add test cases specific to agent capabilities
3. Run the evaluation again

### Example Results

```
Examples analyzed: 6
Basic query accuracy: 0.60
Specific query accuracy: 0.96

mcp_researcher:
  Basic accuracy: 0.25
  Specific accuracy: 0.75
  Recommendations:
    - Improve tool selection for basic queries (current accuracy: 0.25)
    - Improve handling of 'Research with explicit Python requirement' queries
```

## Original Metrics Framework

The original evaluation framework measures agent performance using:

- **Progress Rate**: How effectively an agent makes progress through subgoals
- **Grounding Accuracy**: How accurately an agent uses tools and references facts
- **Task Completion**: Whether the agent successfully completes the task
- **Turn Efficiency**: How efficiently the agent completes tasks (fewer turns is better)

## Simple Agent Tester

A simplified agent tester is also available for quick evaluations:

```bash
# Run the test_agent.py script with the agent name
python -m src.mcp_agent.eval.test_agent --agent mcp_basic_slack_agent
```

This will:

1. Run a series of standard test queries against the agent
2. Measure response times and quality metrics
3. Store results in the agent's eval_results directory
4. Generate visualization data

## Output Structure

Results are stored in the agent's directory under `eval_results/`:

```
examples/mcp_basic_slack_agent/eval_results/
├── evaluation_20250416_123456.json     # Detailed evaluation results
└── visualizations/                     # Visualization data
    └── metrics_20250416_123456.json    # Metrics for visualization
```

## Framework Structure

- `evaluate.py`: Main script for comprehensive evaluations
- `metrics.py`: Core evaluation metrics definitions
- `tool_usage_evaluation.py`: Tool usage evaluation metrics and utilities
- `tool_usage_listener.py`: Event listener for capturing tool usage
- `run_tool_usage_evaluation.py`: Runner for tool usage evaluations
- `test_tool_usage.py`: Test script for running tool usage evaluations
- `test_specific_queries.py`: Test script for running specific query evaluations
- `tool_evaluation_summary.py`: Tool usage evaluation summary and analysis

## Extending the Framework

The evaluation framework can be extended with:

- Additional metrics and measurements
- Domain-specific test cases
- Integration with other evaluation tools
- Custom visualization generators

## Original Evaluation Criteria

The original MCP agent evaluation framework measures:

1. **Response Time**: How long the agent takes to respond to queries (lower is better)
2. **Success Rate**: If responses contain expected keywords/content (higher is better)
3. **Response Length**: Character count of responses for verbosity analysis
4. **Tool Usage Count**: Number of times the agent uses tools to complete tasks
