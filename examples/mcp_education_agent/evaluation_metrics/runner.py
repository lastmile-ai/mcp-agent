"""
Evaluation runner for the MCP Education Agent.

This module runs a set of predefined educational tasks and evaluates
the agent's performance using the metrics defined in the metrics module.
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
    Visualization, create_education_evaluation_tasks
)

# Directory to store evaluation results
EVAL_RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
os.makedirs(EVAL_RESULTS_DIR, exist_ok=True)

class AgentEvaluator:
    """Evaluator for the Education Agent."""
    
    def __init__(self, agent_app: MCPApp, education_agent: Agent, llm):
        """Initialize the evaluator."""
        self.app = agent_app
        self.agent = education_agent
        self.llm = llm
        self.logger = agent_app.logger
        self.tasks = create_education_evaluation_tasks()
        
        # Storage for evaluation data
        self.responses: Dict[str, List[str]] = {}
        self.timestamps: Dict[str, List[float]] = {}
        self.final_states: Dict[str, str] = {}
        self.tool_actions: Dict[str, List[ToolAction]] = {}
        
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
            
            # Save task results
            results["tasks"][task_id] = {
                "name": task.name,
                "difficulty": task.difficulty,
                "progress_trajectory": progress_trajectory,
                "completion_time": self.timestamps[task_id][-1] - self.timestamps[task_id][0],
                "subgoals_matched": sum(1 for sg in task.subgoals if sg.is_matched(self.final_states[task_id])),
                "total_subgoals": len(task.subgoals),
                "is_completed": task.is_completed(self.final_states[task_id])
            }
            
            # Save visualization data
            Visualization.export_visualization_data(
                viz_data,
                os.path.join(EVAL_RESULTS_DIR, f"{task_id}_trajectory.json")
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
        
        # Overall results
        results["overall"] = {
            "total_tasks": len(self.tasks),
            "tasks_completed": sum(1 for status in completion_results.values() if status),
            "completion_rate": sum(1 for status in completion_results.values() if status) / len(completion_results) * 100,
            "difficulty_breakdown": {str(k): v for k, v in difficulty_breakdown.items()}
        }
        
        # Export the full evaluation results
        self._export_results(results)
        
        return results
    
    def _get_task_prompt(self, task: Task) -> str:
        """Get the appropriate prompt for a task."""
        if task.id == "math_problem":
            return "I'm stuck on this equation: 2x + 5 = 15. Can you help?"
        elif task.id == "science_explanation":
            return "Why does the moon change shape?"
        elif task.id == "writing_assistance":
            return "I need to write a story about dinosaurs."
        else:
            return f"I need help with {task.description}"
    
    def _export_results(self, results: Dict[str, Any]) -> None:
        """Export evaluation results to a JSON file."""
        timestamp = int(time.time())
        filename = os.path.join(EVAL_RESULTS_DIR, f"evaluation_{timestamp}.json")
        
        # Convert to JSON serializable format
        serializable_results = json.loads(json.dumps(results, default=lambda o: str(o)))
        
        with open(filename, "w") as f:
            json.dump(serializable_results, f, indent=2)
        
        self.logger.info(f"Evaluation results exported to {filename}")


async def run_education_agent_evaluation():
    """Run the education agent evaluation."""
    app = MCPApp(name="mcp_education_agent_evaluation")
    
    # Load the educational instructions
    EDUCATION_WIKI_PATH = "/home/ubuntu/mahtab/projects/intellagent/examples/education/input/wiki.md"
    
    with open(EDUCATION_WIKI_PATH, "r") as f:
        EDUCATION_INSTRUCTIONS = f.read()
    
    async with app.run() as agent_app:
        logger = agent_app.logger
        context = agent_app.context
        
        logger.info("Starting education agent evaluation")
        
        # Create the education agent
        education_agent = Agent(
            name="education_tutor",
            instruction=EDUCATION_INSTRUCTIONS,
            server_names=[]
        )
        
        async with education_agent:
            # Use either OpenAI or Anthropic model based on config
            if context.config.anthropic and context.config.anthropic.api_key:
                llm = await education_agent.attach_llm(AnthropicAugmentedLLM)
                logger.info("Using Anthropic model for education agent evaluation")
            else:
                llm = await education_agent.attach_llm(OpenAIAugmentedLLM)
                logger.info("Using OpenAI model for education agent evaluation")
            
            # Run the evaluation
            evaluator = AgentEvaluator(agent_app, education_agent, llm)
            results = await evaluator.run_all_tasks()
            
            # Log summary
            logger.info("Evaluation completed", data={
                "total_tasks": results["overall"]["total_tasks"],
                "completion_rate": f"{results['overall']['completion_rate']:.2f}%"
            })
            
            # Print summary
            print("\n=== Education Agent Evaluation Results ===")
            print(f"Total Tasks: {results['overall']['total_tasks']}")
            print(f"Tasks Completed: {results['overall']['tasks_completed']}")
            print(f"Completion Rate: {results['overall']['completion_rate']:.2f}%")
            print("\nDifficulty Breakdown:")
            for diff, rate in results["overall"]["difficulty_breakdown"].items():
                print(f"  {diff}: {rate:.2f}%")
            print("\nTask Details:")
            for task_id, task_data in results["tasks"].items():
                print(f"  {task_data['name']} ({task_id}):")
                print(f"    - Completed: {'Yes' if task_data['is_completed'] else 'No'}")
                print(f"    - Subgoals: {task_data['subgoals_matched']}/{task_data['total_subgoals']}")
                print(f"    - Time: {task_data['completion_time']:.2f}s")
            
            print(f"\nDetailed results saved to: {EVAL_RESULTS_DIR}")


if __name__ == "__main__":
    asyncio.run(run_education_agent_evaluation())