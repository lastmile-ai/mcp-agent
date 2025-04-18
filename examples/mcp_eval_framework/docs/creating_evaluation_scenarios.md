# Creating Evaluation Scenarios for MCP Agents

This guide provides a detailed, step-by-step process for creating and implementing evaluation scenarios for MCP agents. It covers everything from defining the scenario to implementing tasks and metrics, with code examples.

## Table of Contents

1. [Overview of Evaluation Scenarios](#1-overview-of-evaluation-scenarios)
2. [Defining Your Scenario](#2-defining-your-scenario)
3. [Creating Scenario Instructions](#3-creating-scenario-instructions)
4. [Defining Evaluation Tasks](#4-defining-evaluation-tasks)
5. [Implementing the Scenario](#5-implementing-the-scenario)
6. [Running and Testing](#6-running-and-testing)
7. [Analyzing Results](#7-analyzing-results)
8. [Advanced Customization](#8-advanced-customization)

---

## 1. Overview of Evaluation Scenarios

### What Is an Evaluation Scenario?

An evaluation scenario consists of:

- **Domain**: A specific area where an agent provides assistance (education, airline, retail, etc.)
- **Instructions**: Guidelines that define the agent's role and behavior
- **Tasks**: Specific challenges designed to test the agent's capabilities
- **Metrics**: Measurements to evaluate the agent's performance

### Why Create Scenarios?

- **Standardized Evaluation**: Compare different agents on the same tasks
- **Performance Tracking**: Monitor improvements over time
- **Targeted Testing**: Focus on specific capabilities or challenges
- **Quality Assurance**: Ensure agents meet minimum performance standards

### Components of the Evaluation Framework

```
mcp_eval_framework/
├── main.py                     # Main agent runner
├── evaluation/                 # Evaluation framework
│   ├── metrics.py              # Core evaluation metrics
│   ├── scenario_tasks.py       # Task definitions by scenario
│   ├── runner.py               # Evaluation execution
│   ├── visualize.py            # Result visualization
│   └── evaluate.py             # Main evaluation script
```

---

## 2. Defining Your Scenario

### Step 2.1: Choose a Domain

Select a domain where an agent would provide value:

- **Education**: Tutoring, homework help, concept explanation
- **Customer Service**: Airline bookings, retail support, technical assistance
- **Healthcare**: Medical information, appointment scheduling, symptom checking
- **Finance**: Account management, investment advice, transaction support

### Step 2.2: Define Agent Role and Goals

Clearly articulate:

- **What is the agent's role?** (tutor, assistant, advisor, etc.)
- **What are the primary goals?** (educate, solve problems, provide information)
- **What are the constraints?** (don't solve problems directly, maintain policy compliance)

### Step 2.3: Identify Key Capabilities

List the specific capabilities you want to evaluate:

- **Knowledge**: Domain-specific information accuracy
- **Reasoning**: Problem-solving approach and logic
- **Communication**: Clarity, appropriateness, and helpfulness
- **Tool Usage**: Effective use of available tools and resources
- **Policy Adherence**: Following guidelines and constraints

### Code Example: Scenario Configuration

```python
# Add to SCENARIOS dictionary in main.py and runner.py
SCENARIOS = {
    # Existing scenarios...
    "retail_support": {
        "wiki_path": "/path/to/intellagent/examples/retail/input/wiki.md",
        "agent_name": "retail_assistant",
        "sample_questions": [
            "I need to return a defective product.",
            "What's your refund policy?",
            "When will my order be delivered?",
            "Do you have this item in a different size?",
            "I need to change my delivery address."
        ]
    },
}
```

---

## 3. Creating Scenario Instructions

### Step 3.1: Write Comprehensive Guidelines

Create a markdown file (`wiki.md`) containing:

- **Role Definition**: Clear statement of the agent's role
- **Goals and Principles**: What the agent should aim to achieve
- **Constraints**: What the agent should avoid
- **Domain Knowledge**: Essential information about the domain
- **Response Guidelines**: How the agent should structure responses
- **Examples**: Sample interactions demonstrating desired behavior

### Step 3.2: Format for Clarity

Organize the instructions for easy comprehension:

```markdown
# Retail Support Assistant

## Role and Purpose
You are a retail support assistant for an online clothing store. Your purpose is to help customers with their orders, returns, and product inquiries.

## Key Principles
1. Prioritize customer satisfaction
2. Provide accurate information about products and policies
3. Help resolve issues efficiently
4. Maintain a friendly, professional tone
5. Respect customer privacy

## Response Guidelines
- Greet customers politely
- Address their questions directly
- Ask clarifying questions when needed
- Provide specific, actionable information
- Reference store policies when applicable
- Offer alternatives when a request can't be fulfilled

## Returns and Refunds Policy
[Policy details...]

## Shipping Information
[Shipping details...]

## Examples
[Example interactions...]
```

### Step 3.3: Save in the Appropriate Location

Place your `wiki.md` file in the intellagent project structure:

```
/path/to/intellagent/examples/your_scenario/input/wiki.md
```

---

## 4. Defining Evaluation Tasks

### Step 4.1: Identify Key Tasks

List 3-5 representative tasks that cover different aspects of the scenario:

- **Retail Example**:
  - Processing a return request
  - Answering policy questions
  - Handling delivery issues
  - Providing product recommendations
  - Resolving a customer complaint

### Step 4.2: Assign Difficulty Levels

Categorize tasks by difficulty:

- **EASY**: Simple, straightforward requests
- **MEDIUM**: Moderate complexity, some considerations
- **HARD**: Complex situations with multiple factors

### Step 4.3: Break Down into Subgoals

For each task, identify 4-6 subgoals that represent progressive steps:

- **Return Processing Task**:
  1. Greet customer professionally
  2. Identify the return request
  3. Ask for order information
  4. Explain return policy
  5. Provide return instructions
  6. Confirm next steps

### Step 4.4: Define Completion Criteria

Determine how you'll verify task completion:

- **Regex Patterns**: Text patterns that indicate success
- **Custom Functions**: More complex logic for verification
- **Combined Criteria**: Multiple conditions that must be met

### Code Example: Task Definition

```python
def create_retail_tasks() -> List[Task]:
    """Create evaluation tasks for retail scenario."""
    
    return_task = Task(
        id="return_request",
        name="Return Request Processing",
        description="Help a customer process a return for a defective product",
        difficulty=TaskDifficulty.MEDIUM,
        subgoals=[
            SubGoal(
                id="greet_customer",
                description="Greet the customer professionally",
                regex_pattern=r"(hello|hi|welcome|greetings|assist)"
            ),
            SubGoal(
                id="identify_return",
                description="Identify the return request",
                regex_pattern=r"(return|defective|broken|not working|damaged)"
            ),
            SubGoal(
                id="request_order_info",
                description="Request order information",
                regex_pattern=r"(order|number|id|confirmation|details)"
            ),
            SubGoal(
                id="explain_policy",
                description="Explain the return policy",
                regex_pattern=r"(policy|30 day|days|window|process)"
            ),
            SubGoal(
                id="provide_instructions",
                description="Provide specific return instructions",
                regex_pattern=r"(label|package|box|send|mail|drop off)"
            )
        ],
        final_goal_description="Successfully guide the customer through the return process",
        final_goal_regex=r"(assist|help|process|return|refund)"
    )
    
    # Define more tasks...
    
    return [return_task, policy_task, delivery_task]
```

---

## 5. Implementing the Scenario

### Step 5.1: Add Tasks to the Framework

Create a function in `scenario_tasks.py`:

```python
def create_retail_tasks() -> List[Task]:
    """Create evaluation tasks for retail scenario."""
    
    # Task definitions...
    
    return [task1, task2, task3]
```

### Step 5.2: Register the Scenario Tasks

Update the `get_tasks_for_scenario` function:

```python
def get_tasks_for_scenario(scenario_name: str) -> List[Task]:
    """Get evaluation tasks for a specific scenario."""
    scenario_task_creators = {
        "education": create_education_tasks,
        "airline": create_airline_tasks,
        "retail": create_retail_tasks,  # Add your scenario
    }
    
    if scenario_name not in scenario_task_creators:
        raise ValueError(f"No tasks defined for scenario: {scenario_name}")
    
    return scenario_task_creators[scenario_name]()
```

### Step 5.3: Add Task Prompts

Update the `_get_task_prompt` method in `runner.py`:

```python
def _get_task_prompt(self, task: Task) -> str:
    """Get the appropriate prompt for a task."""
    # Retail scenario prompts
    retail_prompts = {
        "return_request": "I need to return a defective product that I bought last week.",
        "policy_question": "What's your refund policy for items on sale?",
        "delivery_issue": "My order was supposed to arrive yesterday but it hasn't."
    }
    
    # Select prompts based on scenario
    if self.scenario_name == "retail":
        return retail_prompts.get(task.id, f"I need help with {task.description}")
    # Other scenarios...
```

### Step 5.4: Update Configuration

Add scenario configuration to main files:

```python
# In main.py and runner.py
SCENARIOS = {
    # Existing scenarios...
    "retail": {
        "wiki_path": "/path/to/intellagent/examples/retail/input/wiki.md",
        "agent_name": "retail_assistant",
        # Sample questions...
    },
}
```

---

## 6. Running and Testing

### Step 6.1: Test Interactive Mode

Run your scenario interactively to check agent behavior:

```bash
./main.py --scenario retail
```

Interact with the agent and observe:
- Are responses aligned with scenario instructions?
- Does the agent handle questions appropriately?
- Are there any unexpected behaviors?

### Step 6.2: Run Initial Evaluation

Run an evaluation to get baseline metrics:

```bash
cd evaluation
./evaluate.py --scenarios retail --results-dir ../results
```

### Step 6.3: Debug and Refine

Based on initial results:

- **Adjust Task Definitions**: Modify subgoals or regex patterns
- **Refine Instructions**: Clarify or expand the wiki.md file
- **Tune Metrics**: Adjust how performance is measured if needed

### Code Example: Debugging Task

```python
# Example task refinement
# Before:
SubGoal(
    id="explain_policy",
    description="Explain the return policy",
    regex_pattern=r"(policy|30 day)"  # Too limited
)

# After:
SubGoal(
    id="explain_policy",
    description="Explain the return policy",
    regex_pattern=r"(policy|return window|days to return|refund policy|exchange policy)"
)
```

---

## 7. Analyzing Results

### Step 7.1: Review Metrics

Examine the evaluation results:

- **Overall Completion Rate**: What percentage of tasks were completed?
- **Subgoal Match Rate**: How many subgoals were achieved?
- **Difficulty Breakdown**: How did performance vary by difficulty?
- **Compare Scenarios**: How does this scenario compare to others?

### Step 7.2: Identify Patterns

Look for patterns in the results:

- **Common Failures**: Are there specific subgoals that are consistently missed?
- **Difficulty Impact**: Is there a significant drop in performance as difficulty increases?
- **Response Quality**: Beyond metrics, how is the qualitative experience?

### Step 7.3: Generate Visualizations

Use the visualization tools:

```bash
python evaluation/visualize.py --results-dir ../results/retail
```

Review the generated visualizations:
- Progress trajectories across tasks
- Success rates by difficulty
- Subgoal completion heatmaps

### Step 7.4: Document Findings

Create a summary of your findings:

```markdown
# Retail Scenario Evaluation Results

## Overview
- **Tasks**: 3 (1 Easy, 1 Medium, 1 Hard)
- **Overall Completion Rate**: 85%
- **Average Subgoal Match Rate**: 72%

## Key Findings
1. **Strong customer greeting**: All responses properly greeted the customer
2. **Policy explanation needs improvement**: Only 60% of responses explained policies clearly
3. **Delivery issues handled well**: 90% of delivery-related subgoals were met

## Recommendations
1. Improve policy explanation in the agent instructions
2. Add more examples of clear policy statements
3. Consider adding a dedicated policy tool
```

---

## 8. Advanced Customization

### Step 8.1: Custom Metrics

Add scenario-specific metrics:

```python
def calculate_customer_satisfaction_score(responses: List[str]) -> float:
    """Calculate a simulated customer satisfaction score based on response features."""
    satisfaction_indicators = [
        r"(thank you|thanks|appreciate)",  # Politeness
        r"(specific|exact|precise)",       # Specificity
        r"(option|alternative|choice)",    # Offering choices
        r"(follow up|check|confirm)",      # Follow-up offers
        r"(sorry|apologize|regret)"        # Appropriate apologies
    ]
    
    scores = []
    for response in responses:
        score = sum(1 for pattern in satisfaction_indicators 
                    if re.search(pattern, response, re.IGNORECASE))
        scores.append(min(100, (score / len(satisfaction_indicators)) * 100))
    
    return sum(scores) / len(scores) if scores else 0.0
```

### Step 8.2: Custom Matchers

Create more sophisticated subgoal matchers:

```python
def verify_correct_policy_citation(state: str) -> bool:
    """Verify that the correct policy is cited for the situation."""
    if "return" in state.lower() and "defective" in state.lower():
        # Should mention the defective item policy
        return "full refund" in state.lower() and "30 days" in state.lower()
    elif "return" in state.lower() and "change mind" in state.lower():
        # Should mention the change-of-mind policy
        return "store credit" in state.lower() and "14 days" in state.lower()
    return False

# Usage
SubGoal(
    id="cite_correct_policy",
    description="Cite the correct policy for the situation",
    matcher_function=verify_correct_policy_citation
)
```

### Step 8.3: Multi-agent Comparison

Compare different agent implementations:

```bash
# Run with different agents
./evaluate.py --scenarios retail --agent-model gpt-4 --results-dir ../results/retail_gpt4
./evaluate.py --scenarios retail --agent-model claude-3 --results-dir ../results/retail_claude
```

### Step 8.4: A/B Testing Scenario Variants

Test different instruction variants:

```bash
# Run with different instruction files
SCENARIOS = {
    "retail_a": {
        "wiki_path": "/path/to/intellagent/examples/retail/input/wiki_variant_a.md",
        "agent_name": "retail_assistant",
    },
    "retail_b": {
        "wiki_path": "/path/to/intellagent/examples/retail/input/wiki_variant_b.md",
        "agent_name": "retail_assistant",
    },
}

# Run evaluation
./evaluate.py --scenarios retail_a retail_b
```

## Conclusion

Creating effective evaluation scenarios is both an art and a science. The best scenarios:

1. **Represent realistic use cases** that the agent would encounter
2. **Test diverse capabilities** across different difficulty levels
3. **Provide clear metrics** that align with business objectives
4. **Enable fair comparison** between different agent implementations

By following this guide, you can create comprehensive evaluation scenarios that provide meaningful insights into agent performance and guide improvements over time.