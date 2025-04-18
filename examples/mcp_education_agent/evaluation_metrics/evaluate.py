#!/usr/bin/env python3
"""
Main evaluation script for MCP Education Agent.

This script brings together the metrics, runner, and visualization
modules to perform a complete evaluation of the education agent.
"""

import asyncio
import argparse
import os
import json
import sys

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation_metrics.runner import run_education_agent_evaluation
from evaluation_metrics.visualize import generate_all_visualizations


async def main():
    """Run the evaluation and generate visualizations."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Evaluate MCP Education Agent")
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
    if not args.skip_eval:
        print("Running MCP Education Agent evaluation...")
        await run_education_agent_evaluation()
        print("Evaluation complete!")
    
    # Generate visualizations
    if not args.skip_vis:
        print("\nGenerating visualizations...")
        generate_all_visualizations()
        print("Visualization generation complete!")


if __name__ == "__main__":
    asyncio.run(main())