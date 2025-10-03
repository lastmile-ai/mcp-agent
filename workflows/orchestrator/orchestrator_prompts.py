TASK_RESULT_TEMPLATE = """Task: {task_description}
Result: {task_result}"""

STEP_RESULT_TEMPLATE = """Step: {step_description}
Step Subtasks:
{tasks_str}"""

PLAN_RESULT_TEMPLATE = """Plan Objective: {plan_objective}

Progress So Far (steps completed):
{steps_str}

Plan Current Status: {plan_status}
Plan Current Result: {plan_result}"""

FULL_PLAN_PROMPT_TEMPLATE = """You are tasked with orchestrating a plan to complete an objective.
You can analyze results from the previous steps already executed to decide if the objective is complete.
Your plan must be structured in sequential steps, with each step containing independent parallel subtasks.

Objective: {objective}

{plan_result}

If the previous results achieve the objective, return is_complete=True.
Otherwise, generate remaining steps needed.

You have access to the following MCP Servers (which are collections of tools/functions),
and Agents (which are collections of servers):

Agents:
{agents}

Generate a plan with all remaining steps needed.
Steps are sequential, but each Step can have parallel subtasks.
For each Step, specify a description of the step and independent subtasks that can run in parallel.
For each subtask specify:
    1. Clear description of the task that an LLM can execute  
    2. Name of 1 Agent (ONLY using the available agents specified) OR List of MCP server names to use for the task
    
Return your response in the following JSON structure:
    {{
        "steps": [
            {{
                "description": "Description of step 1",
                "tasks": [
                    {{
                        "description": "Description of task 1",
                        "agent": "agent_name"  # For AgentTask
                    }},
                    {{
                        "description": "Description of task 2", 
                        "agent": "agent_name2"
                    }}
                ]
            }}
        ],
        "is_complete": false
    }}

You must respond with valid JSON only, with no triple backticks. No markdown formatting.
No extra text. Do not wrap in ```json code fences."""

ITERATIVE_PLAN_PROMPT_TEMPLATE = """You are tasked with determining only the next step in a plan
needed to complete an objective. You must analyze the current state and progress from previous steps 
to decide what to do next.

A Step must be sequential in the plan, but can have independent parallel subtasks. Only return a single Step.

Objective: {objective}

{plan_result}
    
If the previous results achieve the objective, return is_complete=True.
Otherwise, generate the next Step.

You have access to the following MCP Servers (which are collections of tools/functions),
and Agents (which are collections of servers):

Agents:
{agents}

Generate the next step, by specifying a description of the step and independent subtasks that can run in parallel:
For each subtask specify:
    1. Clear description of the task that an LLM can execute  
    2. Name of 1 Agent (ONLY using the available agents specified) OR List of MCP server names to use for the task

Return your response in the following JSON structure:
    {{
    
        "description": "Description of step 1",
        "tasks": [
            {{
                "description": "Description of task 1",
                "agent": "agent_name"  # For AgentTask
            }}
        ],
        "is_complete": false
    }}

You must respond with valid JSON only, with no triple backticks. No markdown formatting.
No extra text. Do not wrap in ```json code fences."""

TASK_PROMPT_TEMPLATE = """You are part of a larger workflow to achieve the objective: {objective}.
Your job is to accomplish only the following task: {task}.

Results so far that may provide helpful context:
{context}"""

SYNTHESIZE_STEP_PROMPT_TEMPLATE = """Synthesize the results of these parallel tasks into a cohesive result:
{step_result}"""

SYNTHESIZE_PLAN_PROMPT_TEMPLATE = """Synthesize the results of executing all steps in the plan into a cohesive result:
{plan_result}"""
