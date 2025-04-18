# MCP Education Agent

This example demonstrates how to use the MCP Agent framework with an educational scenario from the Intellagent project.

## Overview

The Education Agent acts as a tutor for children, helping them with homework by guiding them to find answers rather than providing direct solutions. The agent follows educational principles to promote learning:

- Encourages critical thinking
- Breaks problems into manageable steps
- Provides hints rather than answers
- Adapts to the child's level
- Uses positive reinforcement
- Promotes problem-solving strategies

## Setup

1. Clone both repositories if you haven't already:
   ```
   git clone https://github.com/your-org/mcp-agent.git
   git clone https://github.com/your-org/intellagent.git
   ```

2. Create your secrets file:
   ```
   cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
   ```

3. Edit `mcp_agent.secrets.yaml` and add your API keys.

## Running the Agent

### Interactive Mode

Run the education agent in interactive mode:

```
python main.py
```

This will start an interactive session where you can act as a student asking the educational agent for help with homework problems.

### Non-Interactive Demo Mode

For non-interactive environments (CI/CD pipelines, etc.), you can run the agent in demo mode with sample questions:

```
uv run python main.py
```

Or explicitly with:

```
python main.py --non-interactive
```

## Evaluation Metrics

This agent includes a comprehensive evaluation framework in the `evaluation_metrics` directory that measures:

### Fine-grained Progress Rate
- Tracks intermediate progress through predefined subgoals
- Maps agent responses to educational milestones
- Uses regex-based matching to evaluate adherence to pedagogical principles

### Grounding Accuracy
- Measures the agent's ability to map plans to executable actions
- Calculates the percentage of valid actions
- Tracks successful tool usage rates

### MCP-Specific Metrics
- Measures standardization in client-server communication
- Evaluates appropriate input parameters to tools
- Tests adaptability to changes in tool descriptions and parameters

### Task Completion
- Evaluates successful completion of educational tasks
- Provides performance breakdown for easy vs. hard problems
- Analyzes long-range interactions across multiple turns

### Visualization
- Generates progress trajectories 
- Creates heatmaps of subgoal completion
- Visualizes performance across different task difficulties

## Running Evaluations

To run a full evaluation of the education agent:

```
cd evaluation_metrics
./evaluate.py
```

Options:
- `--skip-eval`: Skip running the evaluation, just generate visualizations
- `--skip-vis`: Skip generating visualizations

The results are stored in `evaluation_metrics/results/` with visualizations in `evaluation_metrics/results/visualizations/`.

## Example Interactions

**Student**: "I need help with math. What's 5 × 7?"

**Tutor**: "I'd be happy to help you with this multiplication problem! Instead of just giving you the answer, let's think about how to solve it. Do you remember what multiplication means? It's like adding a number multiple times. So 5 × 7 means adding 5 seven times, or adding 7 five times. Can you try figuring out what 5 × 7 equals by breaking it down? Maybe start with 5 × 5 and then add two more groups of 5?"

**Student**: "I need help with my science homework. What causes the seasons on Earth?"

**Tutor**: "That's a great science question! Instead of just telling you the answer, let's explore this together. What do you already know about the Earth and the sun? Have you noticed anything about how the sun appears in the sky during different seasons? Think about how the Earth moves - does it just go around the sun, or does it do something else too? Try drawing a picture of the Earth and sun, and we can figure out what causes the seasons together!"