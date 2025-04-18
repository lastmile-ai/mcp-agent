# MCP Agent Evaluation Framework

This framework provides a comprehensive solution for running and evaluating MCP agents across different scenarios (education, airline, retail, etc.), with standardized metrics and visualizations.

## Overview

The MCP Agent Evaluation Framework:

1. **Runs different scenario agents** with a unified interface
2. **Evaluates agent performance** using standardized metrics
3. **Generates visualizations** to help analyze results
4. **Supports multiple scenarios** with a consistent approach

## Metrics Evaluated

The framework evaluates several key metrics:

### Fine-grained Progress Rate
- **What**: Tracks intermediate progress through predefined subgoals for each task
- **How**: Maps agent responses to task-specific milestones using regex patterns
- **Why**: Provides insight into the agent's trajectory toward completing a task

### Grounding Accuracy
- **What**: Measures the agent's ability to map plans to executable actions
- **How**: Calculates the percentage of valid tool actions and correct parameter usage
- **Why**: Evaluates how well the agent interacts with available tools

### MCP-Specific Metrics
- **What**: Evaluates standardization in client-server communication
- **How**: Tracks successful tool usage and adaptation to tool specification changes
- **Why**: Tests the core value proposition of the MCP protocol

### Task Completion
- **What**: Measures successful completion rates across different tasks
- **How**: Provides performance breakdown for easy, medium, and hard tasks
- **Why**: Evaluates the agent's ultimate effectiveness

### Turn Efficiency
- **What**: Analyzes how efficiently the agent completes tasks
- **How**: Compares the actual number of turns with expected baseline
- **Why**: Evaluates the agent's ability to solve problems efficiently

## Setup

1. Clone the repository:
   ```
   git clone https://github.com/your-org/mcp-agent.git
   ```

2. Navigate to the evaluation framework:
   ```
   cd mcp-agent/examples/mcp_eval_framework
   ```

3. Create your secrets file:
   ```
   cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
   ```

4. Edit `mcp_agent.secrets.yaml` and add your API keys.

5. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

## Running the Agent

### Interactive Mode

Run a specific scenario agent interactively:

```bash
./main.py --scenario education
```

Available scenarios: education, airline

### Non-Interactive Demo Mode

Run sample questions in non-interactive mode:

```bash
./main.py --scenario airline --non-interactive
```

Or with uv run:

```bash
uv run python main.py --scenario airline
```

## Running Evaluations

To evaluate agent performance across scenarios:

```bash
cd evaluation
./evaluate.py --scenarios education airline --results-dir ../results
```

Options:
- `--scenarios`: Space-separated list of scenarios to evaluate (default: education)
- `--results-dir`: Directory to save results (default: ./results)
- `--skip-eval`: Skip running the evaluation, just generate visualizations
- `--skip-vis`: Skip generating visualizations

## Step-by-Step Guide: Creating Evaluation Scenarios for MCP Agent

This guide walks you through the process of creating and testing evaluation scenarios for MCP agents using the evaluation framework.

### 1. Define Your Scenario

**Step 1.1: Identify the scenario domain**
- Choose a domain where an agent can provide assistance (education, airline, retail, etc.)
- Determine the primary purpose of the agent (tutoring, customer service, recommendation, etc.)

**Step 1.2: Collect domain knowledge**
- Gather relevant domain knowledge and terminology
- Identify common user queries and expected agent responses
- Understand domain-specific policies or guidelines the agent should follow

### 2. Create Scenario Instructions

**Step 2.1: Write scenario instructions**
- Create a markdown file with detailed instructions for the agent
- Define the agent's role, goals, and constraints
- Include domain-specific knowledge and guidelines
- Example: Create `/path/to/intellagent/examples/your_scenario/input/wiki.md`

**Step 2.2: Define sample user queries**
- Create a list of representative user queries for the scenario
- Ensure coverage of different aspects of the domain
- Include a range of easy to complex queries

### 3. Define Evaluation Tasks

**Step 3.1: Identify key tasks**
- Determine 3-5 specific tasks the agent should be able to handle
- Ensure tasks vary in complexity (easy, medium, hard)
- Make tasks measurable and specific

**Step 3.2: Break tasks into subgoals**
- For each task, identify 4-6 subgoals that represent progressive steps
- Define regex patterns to detect each subgoal in agent responses
- Define criteria for overall task completion

**Step 3.3: Implement task definitions**
- Add your scenario tasks to `scenario_tasks.py`:

```python
def create_your_scenario_tasks() -> List[Task]:
    """Create evaluation tasks for your scenario."""
    
    task1 = Task(
        id="task1_id",
        name="Task 1 Name",
        description="Description of Task 1",
        difficulty=TaskDifficulty.EASY,
        subgoals=[
            SubGoal(
                id="subgoal1",
                description="Description of subgoal 1",
                regex_pattern=r"(word1|word2|phrase1)"
            ),
            # Add more subgoals...
        ],
        final_goal_description="Description of what completion looks like",
        final_goal_regex=r"(completion|pattern|here)"
    )
    
    # Define more tasks...
    
    return [task1, task2, task3]
```

**Step 3.4: Register your scenario tasks**
- Update the `get_tasks_for_scenario` function:

```python
def get_tasks_for_scenario(scenario_name: str) -> List[Task]:
    """Get evaluation tasks for a specific scenario."""
    scenario_task_creators = {
        "education": create_education_tasks,
        "airline": create_airline_tasks,
        "your_scenario": create_your_scenario_tasks,  # Add your scenario
    }
    
    if scenario_name not in scenario_task_creators:
        raise ValueError(f"No tasks defined for scenario: {scenario_name}")
    
    return scenario_task_creators[scenario_name]()
```

### 4. Set Up the Agent Runner

**Step 4.1: Add scenario configuration**
- Update the `SCENARIOS` dictionary in `main.py` and `runner.py`:

```python
SCENARIOS = {
    "education": {
        "wiki_path": "/path/to/intellagent/examples/education/input/wiki.md",
        "agent_name": "education_tutor",
        "sample_questions": [
            "Question 1?",
            "Question 2?",
            # More sample questions...
        ]
    },
    "your_scenario": {
        "wiki_path": "/path/to/intellagent/examples/your_scenario/input/wiki.md",
        "agent_name": "your_scenario_assistant",
        "sample_questions": [
            "Question 1?",
            "Question 2?",
            # More sample questions...
        ]
    },
}
```

**Step 4.2: Define task prompts**
- Update the `_get_task_prompt` method in `runner.py` to include prompts for your tasks:

```python
def _get_task_prompt(self, task: Task) -> str:
    """Get the appropriate prompt for a task based on scenario and task ID."""
    # Your scenario prompts
    your_scenario_prompts = {
        "task1_id": "Your specific prompt for task 1",
        "task2_id": "Your specific prompt for task 2",
        "task3_id": "Your specific prompt for task 3"
    }
    
    # Select the appropriate prompt based on scenario
    if self.scenario_name == "your_scenario":
        return your_scenario_prompts.get(task.id, f"I need help with {task.description}")
    # Other scenarios...
```

### 5. Test Your Scenario

**Step 5.1: Run the agent interactively**
- Test your scenario in interactive mode:
```bash
./main.py --scenario your_scenario
```

**Step 5.2: Check the agent behavior**
- Interact with the agent and check if it follows the scenario instructions
- Try different queries and evaluate the responses manually

**Step 5.3: Run the evaluation**
- Evaluate your scenario using the evaluation framework:
```bash
cd evaluation
./evaluate.py --scenarios your_scenario --results-dir ../results
```

**Step 5.4: Analyze the results**
- Review the evaluation results and visualizations
- Check task completion rates, subgoal match rates, and other metrics
- Identify areas for improvement

### 6. Refine Your Scenario

**Step 6.1: Adjust task definitions**
- Refine regex patterns for more accurate subgoal detection
- Adjust task difficulty levels if needed
- Add or remove subgoals based on observed agent behavior

**Step 6.2: Update scenario instructions**
- Clarify or expand instructions in your wiki.md file
- Add more examples or guidelines if the agent is struggling with specific aspects

**Step 6.3: Re-run evaluations**
- Re-run the evaluation to see if your changes improved performance
- Compare results with previous runs

### 7. Document Your Scenario

**Step 7.1: Create a scenario README**
- Document the purpose and scope of your scenario
- List the evaluation tasks and their criteria
- Provide example interactions and expected outcomes

**Step 7.2: Share findings**
- Document interesting findings from your evaluation
- Note any unique challenges or opportunities for your specific scenario
- Share best practices for creating effective agents in your domain

## Framework Structure

```
mcp_eval_framework/
├── main.py                      # Main agent runner
├── mcp_agent.config.yaml        # Agent configuration
├── mcp_agent.secrets.yaml       # API keys (create from example)
├── mcp_agent.secrets.yaml.example  # Example secrets file
├── requirements.txt             # Package dependencies
├── evaluation/                  # Evaluation framework
│   ├── __init__.py              # Package initialization
│   ├── metrics.py               # Core evaluation metrics
│   ├── scenario_tasks.py        # Task definitions by scenario
│   ├── runner.py                # Evaluation runner
│   ├── visualize.py             # Visualization utilities
│   └── evaluate.py              # Main evaluation script
├── results/                     # Evaluation results (created when run)
│   ├── education/               # Results for education scenario
│   │   ├── visualizations/      # Visualizations for education scenario
│   │   └── education_evaluation_*.json  # Evaluation results
│   └── airline/                 # Results for airline scenario
│       ├── visualizations/      # Visualizations for airline scenario  
│       └── airline_evaluation_*.json  # Evaluation results
```

## Example Output

The evaluation generates several visualizations:

1. **Progress Trajectories**: Shows how the agent progresses through subgoals over time
2. **Difficulty Breakdown**: Shows completion rates by task difficulty
3. **Subgoal Heatmap**: Shows which subgoals are completed across different tasks
4. **Turn Efficiency**: Shows how efficiently tasks are completed (turns taken vs. expected)

## Contributing

To add a new scenario:

1. Create scenario instructions in the intellagent project
2. Define scenario tasks in `scenario_tasks.py`
3. Register the scenario in `SCENARIOS` dictionaries
4. Add task prompts to the `_get_task_prompt` method
5. Test and refine

## Future Improvements

- Multi-turn conversations for more realistic evaluation
- Tool usage tracking for better MCP-specific metrics
- Comparative evaluation between different model sizes
- Agent self-evaluation capabilities