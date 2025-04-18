#!/usr/bin/env python3
"""
Main evaluation script for MCP Agents.

This script brings together the runner and visualization modules
to perform a complete evaluation of MCP agents across different scenarios.
"""

import asyncio
import argparse
import os
import json
import sys
from typing import List, Optional

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation.runner import SCENARIOS, run_scenario_evaluation
from evaluation.visualize import generate_visualizations


async def main(
    scenarios: List[str], 
    results_dir: str, 
    skip_eval: bool = False, 
    skip_vis: bool = False
):
    """
    Run the evaluation and generate visualizations for specified scenarios.
    
    Args:
        scenarios: List of scenario names to evaluate
        results_dir: Directory to store evaluation results
        skip_eval: Skip running the evaluation, just generate visualizations
        skip_vis: Skip generating visualizations
    """
    # Validate scenarios
    available_scenarios = list(SCENARIOS.keys())
    for scenario in scenarios:
        if scenario not in available_scenarios:
            print(f"Warning: Unknown scenario '{scenario}'. Available scenarios: {', '.join(available_scenarios)}")
            return
    
    # Create base results directory
    os.makedirs(results_dir, exist_ok=True)
    
    # Process each scenario
    for scenario in scenarios:
        # Create scenario-specific results directory
        scenario_results_dir = os.path.join(results_dir, scenario)
        os.makedirs(scenario_results_dir, exist_ok=True)
        
        # Run the evaluation
        if not skip_eval:
            print(f"\nRunning evaluation for the {scenario} scenario...")
            await run_scenario_evaluation(scenario, scenario_results_dir)
            print(f"Evaluation for {scenario} scenario complete!")
        
        # Generate visualizations
        if not skip_vis:
            print(f"\nGenerating visualizations for {scenario} scenario...")
            generate_visualizations(scenario_results_dir)
            print(f"Visualization generation for {scenario} scenario complete!")


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Evaluate MCP Agents across different scenarios")
    
    parser.add_argument(
        "--scenarios", 
        type=str,
        nargs="+",
        default=["education"],
        choices=SCENARIOS.keys(),
        help=f"Scenarios to evaluate. Available options: {', '.join(SCENARIOS.keys())}"
    )
    
    parser.add_argument(
        "--results-dir", 
        type=str, 
        default="./results",
        help="Base directory to save evaluation results"
    )
    
    parser.add_argument(
        "--skip-eval", 
        action="store_true", 
        help="Skip running the evaluation, just generate visualizations"
    )
    
    parser.add_argument(
        "--skip-vis", 
        action="store_true", 
        help="Skip generating visualizations"
    )
    
    args = parser.parse_args()
    
    # Run the evaluation
    asyncio.run(main(args.scenarios, args.results_dir, args.skip_eval, args.skip_vis))