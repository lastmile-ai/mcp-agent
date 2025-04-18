#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
from typing import List, Optional
import json
from datetime import datetime

def get_agent_directories() -> List[str]:
    """Get all agent directories in the examples folder."""
    agent_dirs = []
    examples_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")
    
    for item in os.listdir(examples_dir):
        item_path = os.path.join(examples_dir, item)
        if os.path.isdir(item_path) and item.startswith("mcp_"):
            # Check if it has a main.py or equivalent entry point
            if os.path.exists(os.path.join(item_path, "main.py")):
                agent_dirs.append(item)
    
    return agent_dirs

def run_evaluation(agent_name: str, scenario: str, output_dir: Optional[str] = None) -> str:
    """Run evaluation for a specific agent and scenario."""
    if output_dir is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join("eval", "results", agent_name, timestamp)
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Import the runner to set up the agent and run the evaluation
    from eval.runner import EvaluationRunner
    from eval.scenario_tasks import get_scenario_tasks
    
    # Get the appropriate tasks for the scenario
    scenario_tasks = get_scenario_tasks(scenario)
    if not scenario_tasks:
        print(f"Error: Unknown scenario '{scenario}'")
        return ""
    
    # Set up the agent path
    agent_path = os.path.join("examples", agent_name)
    
    # Run the evaluation
    runner = EvaluationRunner(agent_path=agent_path, scenario_name=scenario)
    results = runner.run_evaluation(scenario_tasks)
    
    # Save results
    results_file = os.path.join(output_dir, f"{scenario}_evaluation_{timestamp}.json")
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)
    
    # Generate visualizations
    from eval.visualize import generate_visualizations
    visualizations_dir = os.path.join(output_dir, "visualizations")
    os.makedirs(visualizations_dir, exist_ok=True)
    generate_visualizations(results, visualizations_dir)
    
    return results_file

def main():
    parser = argparse.ArgumentParser(description="Run evaluations on MCP agents")
    parser.add_argument("--agent", type=str, help="Specific agent to evaluate (default: all)")
    parser.add_argument("--scenario", type=str, choices=["airline", "education"], 
                        default="airline", help="Evaluation scenario")
    parser.add_argument("--output", type=str, help="Output directory for evaluation results")
    
    args = parser.parse_args()
    
    # Get list of agents to evaluate
    if args.agent:
        agent_list = [args.agent]
    else:
        agent_list = get_agent_directories()
        print(f"Found {len(agent_list)} agents: {', '.join(agent_list)}")
    
    # Run evaluations
    for agent in agent_list:
        print(f"Evaluating {agent} on {args.scenario} scenario...")
        try:
            results_file = run_evaluation(agent, args.scenario, args.output)
            if results_file:
                print(f"Evaluation completed. Results saved to {results_file}")
            else:
                print(f"Evaluation failed for {agent}")
        except Exception as e:
            print(f"Error evaluating {agent}: {str(e)}")
    
if __name__ == "__main__":
    main()