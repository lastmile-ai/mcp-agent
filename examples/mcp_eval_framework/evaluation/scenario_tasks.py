"""
Scenario-specific evaluation tasks for MCP Agents.

This module contains tasks for different scenarios (education, airline, retail, etc.)
"""

from typing import Dict, List, Any
from .metrics import Task, SubGoal, TaskDifficulty

def create_education_tasks() -> List[Task]:
    """Create evaluation tasks for the education scenario."""
    
    # Define subgoals and tasks for education scenarios
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
            SubGoal(
                id="guide_not_solve",
                description="Guide student through steps rather than solving directly",
                regex_pattern=r"(step|process|try|think)"
            ),
            SubGoal(
                id="encourage_participation",
                description="Encourage student participation in solving",
                regex_pattern=r"(what do you think|how would you|can you)"
            )
        ],
        final_goal_description="Successfully guide the student through solving the equation without giving the answer directly",
        final_goal_regex=r"(subtract.+5|isolate.+x|divide.+2)"
    )
    
    science_explanation_task = Task(
        id="science_explanation",
        name="Science Concept Explanation",
        description="Explain a scientific concept in an age-appropriate way",
        difficulty=TaskDifficulty.HARD,
        subgoals=[
            SubGoal(
                id="acknowledge_question",
                description="Acknowledge the student's question",
                regex_pattern=r"(great question|good question|interesting question)"
            ),
            SubGoal(
                id="explain_concept",
                description="Explain the moon phases concept correctly",
                regex_pattern=r"(phases|reflects|orbit|illuminated|new moon|full moon)"
            ),
            SubGoal(
                id="use_analogies",
                description="Use age-appropriate analogies or examples",
                regex_pattern=r"(like|similar|imagine|picture)"
            ),
            SubGoal(
                id="provide_visualization",
                description="Suggest visualization or drawing to aid understanding",
                regex_pattern=r"(draw|visualize|diagram|picture)"
            ),
            SubGoal(
                id="check_understanding",
                description="Check for student understanding",
                regex_pattern=r"(understand|make sense|follow|questions|curious)"
            )
        ],
        final_goal_description="Provide a comprehensive, age-appropriate explanation that encourages further inquiry",
        final_goal_regex=r"(waxing|waning|cycle|29\.5|month|reflect)"
    )
    
    writing_assistance_task = Task(
        id="writing_assistance",
        name="Creative Writing Assistance",
        description="Help a student with creative writing without doing the work for them",
        difficulty=TaskDifficulty.MEDIUM,
        subgoals=[
            SubGoal(
                id="acknowledge_task",
                description="Acknowledge the writing task",
                regex_pattern=r"(creative|story|dinosaurs|writing)"
            ),
            SubGoal(
                id="brainstorm_approach",
                description="Help brainstorm approach rather than giving content",
                regex_pattern=r"(brainstorm|ideas|think about|consider)"
            ),
            SubGoal(
                id="prompt_planning",
                description="Prompt student to plan story elements",
                regex_pattern=r"(character|setting|plot|theme|conflict)"
            ),
            SubGoal(
                id="ask_for_ideas",
                description="Ask for student's own ideas",
                regex_pattern=r"(what do you think|your ideas|you have in mind)"
            ),
            SubGoal(
                id="provide_structure",
                description="Provide structure without content",
                regex_pattern=r"(beginning|middle|end|introduction|conclusion)"
            ),
            SubGoal(
                id="encourage_creativity",
                description="Encourage personal creativity",
                regex_pattern=r"(creative|imagination|unique|own)"
            )
        ],
        final_goal_description="Guide student to develop their own story rather than providing one",
        final_goal_regex=r"(example|idea|spark|interest|develop)"
    )
    
    return [math_problem_task, science_explanation_task, writing_assistance_task]


def create_airline_tasks() -> List[Task]:
    """Create evaluation tasks for the airline scenario."""
    
    flight_change_task = Task(
        id="flight_change",
        name="Flight Change Request",
        description="Help a customer change their flight",
        difficulty=TaskDifficulty.MEDIUM,
        subgoals=[
            SubGoal(
                id="greet_customer",
                description="Greet the customer professionally",
                regex_pattern=r"(hello|hi|welcome|greetings|assist)"
            ),
            SubGoal(
                id="identify_request",
                description="Correctly identify the flight change request",
                regex_pattern=r"(change|reschedule|different flight|new flight)"
            ),
            SubGoal(
                id="request_booking_info",
                description="Request necessary booking information",
                regex_pattern=r"(booking|reference|confirmation|number|details)"
            ),
            SubGoal(
                id="explain_policy",
                description="Explain the flight change policy",
                regex_pattern=r"(policy|fee|charge|cost|process)"
            ),
            SubGoal(
                id="provide_options",
                description="Provide alternative flight options",
                regex_pattern=r"(alternative|option|available|different time)"
            )
        ],
        final_goal_description="Successfully assist the customer with changing their flight while adhering to airline policies",
        final_goal_regex=r"(assist|help|change|reschedule|process)"
    )
    
    baggage_info_task = Task(
        id="baggage_policy",
        name="Baggage Policy Information",
        description="Explain baggage policy for international flights",
        difficulty=TaskDifficulty.EASY,
        subgoals=[
            SubGoal(
                id="acknowledge_query",
                description="Acknowledge the baggage policy query",
                regex_pattern=r"(baggage|luggage|policy|question|inquiry)"
            ),
            SubGoal(
                id="specify_international",
                description="Specifically address international flights",
                regex_pattern=r"(international|abroad|overseas|foreign)"
            ),
            SubGoal(
                id="explain_weight_limits",
                description="Explain weight limitations",
                regex_pattern=r"(weight|kg|pounds|maximum|limit)"
            ),
            SubGoal(
                id="explain_dimensions",
                description="Explain dimension restrictions",
                regex_pattern=r"(dimensions|size|length|width|height)"
            ),
            SubGoal(
                id="explain_fees",
                description="Explain applicable fees",
                regex_pattern=r"(fee|cost|charge|price|payment)"
            )
        ],
        final_goal_description="Provide accurate and comprehensive information about international baggage policies",
        final_goal_regex=r"(allow|carry|check|bring|international|baggage|luggage)"
    )
    
    compensation_task = Task(
        id="delay_compensation",
        name="Flight Delay Compensation",
        description="Handle a compensation request for a delayed flight",
        difficulty=TaskDifficulty.HARD,
        subgoals=[
            SubGoal(
                id="express_empathy",
                description="Express empathy for the delay inconvenience",
                regex_pattern=r"(sorry|apologize|understand|inconvenience|frustration)"
            ),
            SubGoal(
                id="clarify_delay_info",
                description="Clarify details about the delay",
                regex_pattern=r"(how long|duration|hours|3 hours|when|what time)"
            ),
            SubGoal(
                id="explain_compensation_policy",
                description="Explain the compensation policy accurately",
                regex_pattern=r"(compensation|policy|eligible|qualify|threshold)"
            ),
            SubGoal(
                id="explain_process",
                description="Explain how to file a compensation claim",
                regex_pattern=r"(claim|process|form|submit|file|request)"
            ),
            SubGoal(
                id="provide_timeframe",
                description="Provide a timeframe for resolution",
                regex_pattern=r"(timeframe|timeline|how long|process time|days|weeks)"
            ),
            SubGoal(
                id="offer_alternatives",
                description="Offer alternative forms of immediate assistance",
                regex_pattern=r"(voucher|accommodation|meal|hotel|rebook)"
            )
        ],
        final_goal_description="Thoroughly explain the compensation process while showing empathy and providing immediate assistance options",
        final_goal_regex=r"(compensation|eligible|delay|assistance|claim)"
    )
    
    return [flight_change_task, baggage_info_task, compensation_task]


def get_tasks_for_scenario(scenario_name: str) -> List[Task]:
    """Get evaluation tasks for a specific scenario."""
    scenario_task_creators = {
        "education": create_education_tasks,
        "airline": create_airline_tasks,
    }
    
    if scenario_name not in scenario_task_creators:
        raise ValueError(f"No tasks defined for scenario: {scenario_name}")
    
    return scenario_task_creators[scenario_name]()