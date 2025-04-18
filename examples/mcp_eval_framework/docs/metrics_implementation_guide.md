# MCP Agent Evaluation Metrics Implementation Guide

This guide provides detailed explanations of how each evaluative metric in the MCP Agent Evaluation Framework was implemented, how they work, and how they can be extended.

## Table of Contents

1. [Fine-grained Progress Rate](#1-fine-grained-progress-rate)
2. [Grounding Accuracy](#2-grounding-accuracy)
3. [MCP-Specific Metrics](#3-mcp-specific-metrics)
4. [Task Completion Metrics](#4-task-completion-metrics)
5. [Turn Efficiency](#5-turn-efficiency)
6. [Extending the Metrics](#6-extending-the-metrics)

---

## 1. Fine-grained Progress Rate

### Purpose
To track intermediate progress through predefined subgoals for each task, providing insight into the agent's trajectory toward completing a task.

### Implementation Details

#### Key Components
- `SubGoal` class: Represents an individual milestone within a task
- `Task` class: Contains multiple subgoals that represent progressive steps 
- `progress_rate()` method: Calculates the percentage of matched subgoals

#### Code Implementation

```python
@dataclass
class SubGoal:
    """Class representing a subgoal within a task."""
    id: str
    description: str
    regex_pattern: Optional[str] = None
    matcher_function: Optional[Callable[[str], bool]] = None
    
    def is_matched(self, state: str) -> bool:
        """Check if the current state matches this subgoal."""
        if self.regex_pattern:
            return bool(re.search(self.regex_pattern, state, re.DOTALL))
        elif self.matcher_function:
            return self.matcher_function(state)
        return False

@dataclass
class Task:
    """Class representing a task with a set of subgoals."""
    id: str
    name: str
    description: str
    difficulty: TaskDifficulty
    subgoals: List[SubGoal]
    final_goal_description: str
    final_goal_regex: Optional[str] = None
    final_goal_matcher: Optional[Callable[[str], bool]] = None
    
    def progress_rate(self, states: List[str]) -> List[float]:
        """Calculate the fine-grained progress rate across states."""
        progress = []
        
        for state in states:
            # Count matched subgoals
            matched = sum(1 for sg in self.subgoals if sg.is_matched(state))
            progress_pct = (matched / len(self.subgoals)) * 100
            progress.append(progress_pct)
            
        return progress
```

#### How It Works
1. **Subgoal Definition**: Each task contains multiple subgoals, each with a regex pattern or matcher function
2. **State Matching**: For each agent response (state), we check if it matches each subgoal
3. **Progress Calculation**: We calculate the percentage of subgoals that have been matched
4. **Progress Trajectory**: By applying this across a sequence of agent responses, we get a trajectory

#### Scenario Example - Education

```python
math_problem_task = Task(
    id="math_problem",
    name="Math Problem Solving",
    description="Help a student solve a math equation",
    difficulty=TaskDifficulty.EASY,
    subgoals=[
        SubGoal(
            id="greet_student",
            description="Greet the student appropriately",
            regex_pattern=r"(hello|hi|greetings|welcome)"
        ),
        SubGoal(
            id="identify_problem",
            description="Identify the math problem correctly",
            regex_pattern=r"(equation|2x \+ 5 = 15)"
        ),
        # More subgoals...
    ],
    final_goal_description="Successfully guide the student through solving the equation",
    final_goal_regex=r"(subtract.+5|isolate.+x|divide.+2)"
)
```

---

## 2. Grounding Accuracy

### Purpose
To measure the agent's ability to map plans to executable actions, evaluating how well the agent interacts with available tools.

### Implementation Details

#### Key Components
- `ToolAction` class: Represents a tool action performed by an agent
- `GroundingMetrics` class: Contains methods to calculate various grounding metrics
- `calculate_valid_actions_percentage()`: Measures the percentage of valid actions
- `calculate_tool_usage_success()`: Evaluates correct tool usage
- `calculate_correct_input_rate()`: Checks if correct parameters are provided

#### Code Implementation

```python
@dataclass
class ToolAction:
    """Represents a tool action performed by an agent."""
    tool_name: str
    params: Dict[str, Any]
    is_valid: bool = True
    error_message: Optional[str] = None
    timestamp: Optional[float] = None

@dataclass
class GroundingMetrics:
    """Metrics for measuring grounding accuracy."""
    
    @staticmethod
    def calculate_valid_actions_percentage(actions: List[ToolAction]) -> float:
        """Calculate percentage of valid actions."""
        if not actions:
            return 0.0
            
        valid_actions = sum(1 for action in actions if action.is_valid)
        return (valid_actions / len(actions)) * 100
    
    @staticmethod
    def calculate_tool_usage_success(actions: List[ToolAction], 
                                    expected_tools: Dict[str, int]) -> Dict[str, float]:
        """Calculate success rate of using the correct tools."""
        results = {}
        actual_usage = {}
        
        # Count actual tool usage
        for action in actions:
            actual_usage[action.tool_name] = actual_usage.get(action.tool_name, 0) + 1
        
        # Calculate success rates
        for tool, expected_count in expected_tools.items():
            actual_count = actual_usage.get(tool, 0)
            if expected_count == 0:
                # Tool shouldn't be used
                success_rate = 100.0 if actual_count == 0 else 0.0
            else:
                # Calculate how close the actual usage is to expected
                success_rate = min(100.0, (actual_count / expected_count) * 100)
            
            results[tool] = success_rate
            
        return results
    
    @staticmethod
    def calculate_correct_input_rate(actions: List[ToolAction], 
                                    required_params: Dict[str, List[str]]) -> Dict[str, float]:
        """Calculate success rate of passing correct inputs to tools."""
        results = {}
        
        # Group actions by tool
        tool_actions = {}
        for action in actions:
            if action.tool_name not in tool_actions:
                tool_actions[action.tool_name] = []
            tool_actions[action.tool_name].append(action)
        
        # Calculate correctness for each tool
        for tool, tool_required_params in required_params.items():
            if tool not in tool_actions or not tool_actions[tool]:
                results[tool] = 0.0
                continue
                
            tool_result = 0.0
            for action in tool_actions[tool]:
                # Check if all required params are present
                params_present = all(param in action.params for param in tool_required_params)
                if params_present:
                    tool_result += 1
            
            # Average over all actions for this tool
            results[tool] = (tool_result / len(tool_actions[tool])) * 100
            
        return results
```

#### How It Works
1. **Action Recording**: Each tool action performed by the agent is recorded
2. **Valid Actions**: We calculate what percentage of actions were valid (didn't result in errors)
3. **Tool Usage**: We compare actual tool usage against expected usage
4. **Parameter Correctness**: We check if the required parameters were provided for each tool

#### Scenario Example - Airline

For an airline booking scenario, we might evaluate:
- Did the agent use the correct flight search tool?
- Did it provide all required parameters (origin, destination, date)?
- Did it handle error cases appropriately?

---

## 3. MCP-Specific Metrics

### Purpose
To evaluate standardization in client-server communication and test the core value proposition of the MCP protocol.

### Implementation Details

#### Key Components
- `MCPSpecificMetrics` class: Contains methods specific to MCP functionality
- `evaluate_tool_adaptability()`: Measures how well the agent adapts to tool changes
- `evaluate_server_communication_success()`: Assesses server interactions

#### Code Implementation

```python
@dataclass
class MCPSpecificMetrics:
    """Metrics specific to MCP agent evaluation."""
    
    @staticmethod
    def evaluate_tool_adaptability(
        actions_before: List[ToolAction], 
        actions_after: List[ToolAction], 
        tool_changes: Dict[str, Dict[str, Any]]
    ) -> float:
        """Evaluate how well the agent adapts to changes in tool specifications."""
        if not actions_after or not tool_changes:
            return 0.0
            
        adaptability_scores = []
        
        for tool_name, changes in tool_changes.items():
            # Find actions that use this tool after changes
            tool_actions = [a for a in actions_after if a.tool_name == tool_name]
            
            if not tool_actions:
                continue
                
            # Check if each action reflects the changes
            for action in tool_actions:
                score = 100.0
                
                # Check parameter changes
                if 'params_added' in changes:
                    for param in changes['params_added']:
                        if param not in action.params:
                            score *= 0.5  # Penalize missing new parameters
                
                if 'params_removed' in changes:
                    for param in changes['params_removed']:
                        if param in action.params:
                            score *= 0.5  # Penalize using removed parameters
                
                adaptability_scores.append(score)
        
        if not adaptability_scores:
            return 0.0
            
        return sum(adaptability_scores) / len(adaptability_scores)
    
    @staticmethod
    def evaluate_server_communication_success(
        actions: List[ToolAction],
        expected_server_interactions: Dict[str, int]
    ) -> Dict[str, float]:
        """Evaluate success rate of server communications."""
        results = {}
        actual_interactions = {}
        
        # Count actual server interactions
        for action in actions:
            server_name = action.params.get("server_name", "unknown")
            actual_interactions[server_name] = actual_interactions.get(server_name, 0) + 1
        
        # Calculate success rates
        for server, expected_count in expected_server_interactions.items():
            actual_count = actual_interactions.get(server, 0)
            if expected_count == 0:
                success_rate = 100.0 if actual_count == 0 else 0.0
            else:
                success_rate = min(100.0, (actual_count / expected_count) * 100)
            
            results[server] = success_rate
            
        return results
```

#### How It Works
1. **Tool Adaptability**: We compare agent behavior before and after tool specification changes
2. **Change Detection**: We check if the agent correctly adapts to added/removed parameters
3. **Server Communication**: We track interactions with different servers
4. **Success Rate Calculation**: We compare actual server interactions against expected counts

#### Scenario Example - Tool Change
If a flight search tool changes from requiring:
```
{origin: "NYC", destination: "LAX"}
```
to:
```
{departureAirport: "NYC", arrivalAirport: "LAX", flexible: true}
```

We would evaluate if the agent correctly adapts to the new parameter names and adds the new parameter.

---

## 4. Task Completion Metrics

### Purpose
To measure overall effectiveness in completing tasks, with breakdown by difficulty level.

### Implementation Details

#### Key Components
- `TaskCompletionMetrics` class: Contains methods for task completion evaluation
- `calculate_success_rate()`: Determines if tasks were successfully completed
- `breakdown_by_difficulty()`: Provides success rates by difficulty level

#### Code Implementation

```python
@dataclass
class TaskCompletionMetrics:
    """Metrics for measuring task completion success."""
    
    @staticmethod
    def calculate_success_rate(tasks: List[Task], final_states: Dict[str, str]) -> Dict[str, bool]:
        """Calculate success rate for completed tasks."""
        results = {}
        
        for task in tasks:
            if task.id in final_states:
                results[task.id] = task.is_completed(final_states[task.id])
            else:
                results[task.id] = False
                
        return results
    
    @staticmethod
    def breakdown_by_difficulty(
        tasks: List[Task], 
        completion_results: Dict[str, bool]
    ) -> Dict[TaskDifficulty, float]:
        """Break down task completion success by difficulty level."""
        results = {diff: {'count': 0, 'success': 0} for diff in TaskDifficulty}
        
        # Count tasks and successes by difficulty
        for task in tasks:
            results[task.difficulty]['count'] += 1
            if task.id in completion_results and completion_results[task.id]:
                results[task.difficulty]['success'] += 1
        
        # Calculate percentages
        percentages = {}
        for diff, counts in results.items():
            if counts['count'] > 0:
                percentages[diff] = (counts['success'] / counts['count']) * 100
            else:
                percentages[diff] = 0.0
                
        return percentages
```

#### How It Works
1. **Final State Evaluation**: We check if the agent's final response satisfies the completion criteria
2. **Task Grouping**: Tasks are categorized by difficulty level (EASY, MEDIUM, HARD)
3. **Success Counting**: We count how many tasks were completed in each difficulty category
4. **Percentage Calculation**: We calculate success percentages for each difficulty level

#### Scenario Example - Education vs. Airline
This allows us to compare:
- Do agents perform better on education tasks vs. airline tasks?
- Are EASY tasks consistently completed while HARD tasks fail?
- Which scenario has the highest overall completion rate?

---

## 5. Turn Efficiency

### Purpose
To analyze how efficiently the agent completes tasks compared to expected baselines.

### Implementation Details

#### Key Components
- `calculate_turn_efficiency()` method in `TaskCompletionMetrics`
- Expected turn counts based on task difficulty
- Efficiency score calculation

#### Code Implementation

```python
@staticmethod
def calculate_turn_efficiency(
    tasks: List[Task],
    turns_per_task: Dict[str, int],
    completion_results: Dict[str, bool]
) -> Dict[str, float]:
    """Calculate turn efficiency for each task."""
    results = {}
    
    for task in tasks:
        if task.id not in turns_per_task or task.id not in completion_results:
            continue
            
        # Efficiency is inversely proportional to turns taken
        # Only consider completed tasks for efficiency
        if completion_results[task.id]:
            # Simplified efficiency model - can be customized
            # Assuming a baseline of expected turns based on difficulty
            expected_turns = {
                TaskDifficulty.EASY: 3,
                TaskDifficulty.MEDIUM: 5,
                TaskDifficulty.HARD: 8
            }
            
            baseline = expected_turns.get(task.difficulty, 5)
            actual_turns = turns_per_task[task.id]
            
            # Higher is better, capped at 100%
            efficiency = min(100.0, (baseline / actual_turns) * 100)
            results[task.id] = efficiency
        else:
            results[task.id] = 0.0
            
    return results
```

#### How It Works
1. **Turn Counting**: We count how many conversational turns it takes to complete a task
2. **Baseline Definition**: We define expected turn counts based on task difficulty
3. **Efficiency Calculation**: We calculate efficiency as a ratio of expected to actual turns
4. **Completion Filter**: Only completed tasks receive an efficiency score

#### Scenario Example - Conversation Flow
For a flight booking task, we might expect:
- EASY task (basic inquiry): 3 turns
- MEDIUM task (flight booking): 5 turns
- HARD task (complex change with special requirements): 8 turns

If an agent completes a MEDIUM task in 4 turns, it gets an efficiency score of min(100, (5/4)*100) = 100%

---

## 6. Extending the Metrics

### Adding New Metrics

To add a new metric to the framework:

1. **Define the Metric Class**: Create a new class or method in `metrics.py`
2. **Implement Calculation Logic**: Add methods to calculate the metric
3. **Collect Required Data**: Modify the `AgentEvaluator` class to collect needed data
4. **Add to Results**: Include the metric in the evaluation results
5. **Visualize**: Add visualization in `visualize.py` if applicable

### Example: Adding Response Time Metrics

```python
@dataclass
class ResponseTimeMetrics:
    """Metrics for measuring agent response times."""
    
    @staticmethod
    def calculate_average_response_time(tasks: List[Task], 
                                       response_times: Dict[str, List[float]]) -> Dict[str, float]:
        """Calculate average response time for each task."""
        results = {}
        
        for task in tasks:
            if task.id in response_times and response_times[task.id]:
                results[task.id] = sum(response_times[task.id]) / len(response_times[task.id])
            else:
                results[task.id] = 0.0
                
        return results
    
    @staticmethod
    def calculate_response_time_by_difficulty(
        tasks: List[Task], 
        response_times: Dict[str, List[float]]
    ) -> Dict[TaskDifficulty, float]:
        """Calculate average response time by difficulty level."""
        difficulty_times = {diff: [] for diff in TaskDifficulty}
        
        for task in tasks:
            if task.id in response_times and response_times[task.id]:
                difficulty_times[task.difficulty].extend(response_times[task.id])
        
        return {
            diff: (sum(times) / len(times) if times else 0.0) 
            for diff, times in difficulty_times.items()
        }
```

### Creating Custom Matcher Functions

For more complex subgoal matching beyond regex patterns:

```python
def contains_numerical_value(state: str) -> bool:
    """Check if the response contains a numerical value."""
    return bool(re.search(r'\d+(\.\d+)?', state))

def mentions_specific_entity(state: str, entity: str) -> bool:
    """Check if the response mentions a specific entity."""
    return entity.lower() in state.lower()

# Usage
SubGoal(
    id="provides_numerical_answer",
    description="Provides a numerical answer",
    matcher_function=contains_numerical_value
)

SubGoal(
    id="mentions_new_york",
    description="Mentions New York in the response",
    matcher_function=lambda state: mentions_specific_entity(state, "New York")
)
```

### Scenario-Specific Customization

Different scenarios may require custom metrics or adaptations:

```python
# Education-specific metrics
def calculate_pedagogical_score(responses: List[str]) -> float:
    """Calculate how well responses follow pedagogical principles."""
    pedagogical_patterns = [
        r"(why.+think|how.+approach|what.+understand)",  # Socratic questioning
        r"(try.+yourself|attempt|practice)",             # Encouraging practice
        r"(excellent|great job|well done)",              # Positive reinforcement
        r"(step.+step|first.+then|finally)",             # Structured guidance
    ]
    
    scores = []
    for response in responses:
        score = sum(1 for pattern in pedagogical_patterns 
                    if re.search(pattern, response, re.IGNORECASE))
        scores.append(min(100, (score / len(pedagogical_patterns)) * 100))
    
    return sum(scores) / len(scores) if scores else 0.0

# Airline-specific metrics
def calculate_policy_accuracy(responses: List[str], policy_keywords: Dict[str, List[str]]) -> float:
    """Calculate how accurately airline policies are represented."""
    policy_scores = []
    
    for policy, keywords in policy_keywords.items():
        for response in responses:
            if any(keyword.lower() in response.lower() for keyword in keywords):
                # Found response mentioning this policy
                # More sophisticated checking could be implemented here
                policy_scores.append(100.0)
                break
        else:
            policy_scores.append(0.0)
    
    return sum(policy_scores) / len(policy_scores) if policy_scores else 0.0
```

## Conclusion

This guide covers the implementation details of the core metrics in the MCP Agent Evaluation Framework. By understanding how these metrics work, you can:

1. **Customize metrics** for your specific scenarios
2. **Extend the framework** with new metrics
3. **Interpret results** more effectively
4. **Compare agents** across different settings

The metrics system is designed to be modular and extensible, allowing for easy adaptation to new scenarios and requirements.