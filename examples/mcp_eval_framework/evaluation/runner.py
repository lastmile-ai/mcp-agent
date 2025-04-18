"""
Evaluation runner for MCP Agents.

This module runs a set of predefined tasks for different scenarios
and evaluates the agent's performance using the metrics defined in the metrics module.
"""

import asyncio
import json
import time
import os
from typing import Dict, List, Any, Optional, Tuple

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.llm_selector import ModelPreferences
from mcp_agent.workflows.llm.augmented_llm_anthropic import AnthropicAugmentedLLM
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

from .metrics import (
    Task, ToolAction, 
    GroundingMetrics, MCPSpecificMetrics, TaskCompletionMetrics,
    Visualization
)
from .scenario_tasks import get_tasks_for_scenario

# Dictionary of scenarios with their configurations
SCENARIOS = {
    "education": {
        "wiki_path": "/home/ubuntu/mahtab/projects/intellagent/examples/education/input/wiki.md",
        "agent_name": "education_tutor",
    },
    "airline": {
        "wiki_path": "/home/ubuntu/mahtab/projects/intellagent/examples/airline/input/wiki.md",
        "agent_name": "airline_assistant",
    },
}

class AgentEvaluator:
    """Evaluator for MCP Agents across different scenarios."""
    
    def __init__(
        self, 
        agent_app: MCPApp, 
        scenario_agent: Agent, 
        llm, 
        scenario_name: str,
        results_dir: str
    ):
        """Initialize the evaluator."""
        self.app = agent_app
        self.agent = scenario_agent
        self.llm = llm
        self.scenario_name = scenario_name
        self.logger = agent_app.logger
        self.tasks = get_tasks_for_scenario(scenario_name)
        self.results_dir = results_dir
        
        # Storage for evaluation data
        self.responses: Dict[str, List[str]] = {}
        self.timestamps: Dict[str, List[float]] = {}
        self.final_states: Dict[str, str] = {}
        self.tool_actions: Dict[str, List[ToolAction]] = {}
        self.turns_per_task: Dict[str, int] = {}
        
    async def run_task(self, task: Task) -> None:
        """Run a single task and record data for evaluation."""
        task_id = task.id
        self.responses[task_id] = []
        self.timestamps[task_id] = []
        self.tool_actions[task_id] = []
        
        # Get the appropriate prompt for this task type
        prompt = self._get_task_prompt(task)
        
        self.logger.info(f"Running task: {task.name} (ID: {task.id})")
        
        start_time = time.time()
        self.timestamps[task_id].append(start_time)
        
        # Call the LLM to handle the task
        result = await self.llm.generate_str(
            message=prompt,
            request_params=RequestParams(
                modelPreferences=ModelPreferences(
                    intelligencePriority=0.8,
                    speedPriority=0.2,
                ),
            ),
        )
        
        # Record the response and timestamp
        self.responses[task_id].append(result)
        end_time = time.time()
        self.timestamps[task_id].append(end_time)
        
        # Store final state for completion evaluation
        self.final_states[task_id] = result
        
        # Record turn count (1 for single-turn evaluation)
        self.turns_per_task[task_id] = 1
        
        # Log completion
        self.logger.info(f"Task {task.id} completed in {end_time - start_time:.2f}s")
    
    async def run_all_tasks(self) -> Dict[str, Any]:
        """Run all tasks and return evaluation results."""
        for task in self.tasks:
            await self.run_task(task)
        
        return self.evaluate_results()
    
    def evaluate_results(self) -> Dict[str, Any]:
        """Evaluate the performance based on recorded data."""
        results = {
            "scenario": self.scenario_name,
            "tasks": {},
            "overall": {}
        }
        
        # Process task-specific evaluations
        for task in self.tasks:
            task_id = task.id
            
            # Skip tasks that weren't run
            if task_id not in self.responses:
                continue
            
            # Calculate progress rate for this task
            progress_trajectory = task.progress_rate(self.responses[task_id])
            
            # Generate visualization data
            viz_data = Visualization.generate_progress_trajectory(
                task=task,
                states=self.responses[task_id],
                timestamps=self.timestamps[task_id]
            )
            
            # Count matched subgoals
            subgoals_matched = sum(1 for sg in task.subgoals if sg.is_matched(self.final_states[task_id]))
            
            # Save task results
            results["tasks"][task_id] = {
                "name": task.name,
                "difficulty": task.difficulty,
                "progress_trajectory": progress_trajectory,
                "completion_time": self.timestamps[task_id][-1] - self.timestamps[task_id][0],
                "subgoals_matched": subgoals_matched,
                "total_subgoals": len(task.subgoals),
                "subgoal_match_rate": (subgoals_matched / len(task.subgoals)) * 100,
                "is_completed": task.is_completed(self.final_states[task_id]),
                "turns_taken": self.turns_per_task.get(task_id, 0)
            }
            
            # Save visualization data
            os.makedirs(os.path.join(self.results_dir, "visualizations"), exist_ok=True)
            Visualization.export_visualization_data(
                viz_data,
                os.path.join(self.results_dir, "visualizations", f"{task_id}_trajectory.json")
            )
        
        # Calculate overall metrics
        completion_results = {
            task_id: data["is_completed"]
            for task_id, data in results["tasks"].items()
        }
        
        # Breakdown by difficulty
        difficulty_breakdown = TaskCompletionMetrics.breakdown_by_difficulty(
            self.tasks, completion_results
        )
        
        # Calculate turn efficiency
        turn_efficiency = TaskCompletionMetrics.calculate_turn_efficiency(
            self.tasks, self.turns_per_task, completion_results
        )
        
        # Overall results
        results["overall"] = {
            "total_tasks": len(self.tasks),
            "tasks_completed": sum(1 for status in completion_results.values() if status),
            "completion_rate": sum(1 for status in completion_results.values() if status) / len(completion_results) * 100,
            "difficulty_breakdown": {str(k): v for k, v in difficulty_breakdown.items()},
            "average_subgoal_match_rate": sum(task["subgoal_match_rate"] for task in results["tasks"].values()) / len(results["tasks"]),
            "turn_efficiency": {task_id: efficiency for task_id, efficiency in turn_efficiency.items()}
        }
        
        # Export the full evaluation results
        self._export_results(results)
        
        return results
    
    def _get_task_prompt(self, task: Task) -> str:
        """Get the appropriate prompt for a task based on scenario and task ID."""
        # Education scenario prompts
        education_prompts = {
            "math_problem": "I'm stuck on this equation: 2x + 5 = 15. Can you help?",
            "science_explanation": "Why does the moon change shape?",
            "writing_assistance": "I need to write a story about dinosaurs."
        }
        
        # Airline scenario prompts
        airline_prompts = {
            "flight_change": "I need to change my flight from New York to Los Angeles tomorrow.",
            "baggage_policy": "What's your baggage policy for international flights?",
            "delay_compensation": "My flight was delayed by 3 hours. Am I eligible for compensation?"
        }
        
        # Select the appropriate prompt based on scenario
        if self.scenario_name == "education":
            return education_prompts.get(task.id, f"I need help with {task.description}")
        elif self.scenario_name == "airline":
            return airline_prompts.get(task.id, f"I need help with {task.description}")
        else:
            return f"I need help with {task.description}"
    
    def _export_results(self, results: Dict[str, Any]) -> None:
        """Export evaluation results to a JSON file."""
        timestamp = int(time.time())
        filename = os.path.join(self.results_dir, f"{self.scenario_name}_evaluation_{timestamp}.json")
        
        # Convert to JSON serializable format
        serializable_results = json.loads(json.dumps(results, default=lambda o: str(o)))
        
        with open(filename, "w") as f:
            json.dump(serializable_results, f, indent=2)
        
        self.logger.info(f"Evaluation results exported to {filename}")


async def run_scenario_evaluation(scenario_name: str, results_dir: str):
    """Run the evaluation for a specific scenario."""
    # Validate scenario
    if scenario_name not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario_name}. Available scenarios: {', '.join(SCENARIOS.keys())}")
    
    scenario = SCENARIOS[scenario_name]
    app = MCPApp(name=f"mcp_{scenario_name}_evaluation")
    
    # Load the scenario instructions
    with open(scenario["wiki_path"], "r") as f:
        instructions = f.read()
    
    # Create results directory
    os.makedirs(results_dir, exist_ok=True)
    
    async with app.run() as agent_app:
        logger = agent_app.logger
        context = agent_app.context
        
        logger.info(f"Starting {scenario_name} scenario evaluation")
        
        # Create the scenario agent
        scenario_agent = Agent(
            name=scenario["agent_name"],
            instruction=instructions,
            server_names=[]
        )
        
        async with scenario_agent:
            # Use either OpenAI or Anthropic model based on config
            if context.config.anthropic and context.config.anthropic.api_key:
                llm = await scenario_agent.attach_llm(AnthropicAugmentedLLM)
                logger.info(f"Using Anthropic model for {scenario_name} agent evaluation")
            else:
                llm = await scenario_agent.attach_llm(OpenAIAugmentedLLM)
                logger.info(f"Using OpenAI model for {scenario_name} agent evaluation")
            
            # Run the evaluation
            evaluator = AgentEvaluator(
                agent_app, 
                scenario_agent, 
                llm, 
                scenario_name, 
                results_dir
            )
            results = await evaluator.run_all_tasks()
            
            # Log summary
            logger.info("Evaluation completed", data={
                "scenario": scenario_name,
                "total_tasks": results["overall"]["total_tasks"],
                "completion_rate": f"{results['overall']['completion_rate']:.2f}%"
            })
            
            # Print summary
            print(f"\n=== {scenario_name.title()} Agent Evaluation Results ===")
            print(f"Total Tasks: {results['overall']['total_tasks']}")
            print(f"Tasks Completed: {results['overall']['tasks_completed']}")
            print(f"Completion Rate: {results['overall']['completion_rate']:.2f}%")
            print(f"Average Subgoal Match Rate: {results['overall']['average_subgoal_match_rate']:.2f}%")
            print("\nDifficulty Breakdown:")
            for diff, rate in results["overall"]["difficulty_breakdown"].items():
                print(f"  {diff}: {rate:.2f}%")
            print("\nTask Details:")
            for task_id, task_data in results["tasks"].items():
                print(f"  {task_data['name']} ({task_id}):")
                print(f"    - Completed: {'Yes' if task_data['is_completed'] else 'No'}")
                print(f"    - Subgoals: {task_data['subgoals_matched']}/{task_data['total_subgoals']} ({task_data['subgoal_match_rate']:.2f}%)")
                print(f"    - Time: {task_data['completion_time']:.2f}s")
            
            print(f"\nDetailed results saved to: {results_dir}")
            
            return results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run evaluation for a specific scenario")
    parser.add_argument(
        "--scenario", 
        type=str, 
        default="education",
        choices=SCENARIOS.keys(),
        help=f"Scenario to evaluate. Available options: {', '.join(SCENARIOS.keys())}"
    )
    parser.add_argument(
        "--results-dir", 
        type=str, 
        default="./results",
        help="Directory to save evaluation results"
    )
    
    args = parser.parse_args()
    
    asyncio.run(run_scenario_evaluation(args.scenario, args.results_dir))