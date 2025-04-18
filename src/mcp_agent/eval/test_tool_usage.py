"""
Test script for running tool usage evaluations on MCP agent examples.

Usage:
    python -m mcp_agent.eval.test_tool_usage [--examples EXAMPLE [EXAMPLE ...]]
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import List, Optional

from .run_tool_usage_evaluation import ToolEvaluationRunner


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def run_evaluations(examples: Optional[List[str]] = None) -> None:
    """Run evaluations for specified examples.
    
    Args:
        examples: List of example names to evaluate
    """
    # If no examples specified, auto-discover all examples
    if not examples:
        base_dir = Path(__file__).parent.parent.parent.parent
        examples_dir = base_dir / "examples"
        
        # Find all directories that have a config file
        examples = []
        for item in examples_dir.iterdir():
            if item.is_dir() and (item / "mcp_agent.config.yaml").exists():
                examples.append(item.name)
        
        if not examples:
            logger.error("No examples found with mcp_agent.config.yaml files")
            return
    
    examples_to_evaluate = examples
    logger.info(f"Running evaluations for examples: {examples_to_evaluate}")
    
    # Create runner
    base_dir = Path(__file__).parent.parent.parent.parent
    runner = ToolEvaluationRunner(base_dir)
    
    # Run evaluations
    results = []
    success_map = {}  # Map example name to result path
    success_count = 0
    failure_count = 0
    
    for example in examples_to_evaluate:
        try:
            logger.info(f"Evaluating example: {example}")
            result = await runner.run_evaluation(example)
            
            if result:
                success_map[example] = result
                success_count += 1
                logger.info(f"Successfully evaluated {example}")
            else:
                failure_count += 1
                logger.error(f"Failed to evaluate {example}")
        except Exception as e:
            failure_count += 1
            logger.error(f"Error evaluating {example}: {e}")
    
    # Print summary
    logger.info("Evaluation Summary:")
    logger.info(f"Total examples: {len(examples_to_evaluate)}")
    logger.info(f"Successful: {success_count}")
    logger.info(f"Failed: {failure_count}")
    logger.info(f"Results saved to individual example directories:")
    
    for example, result in success_map.items():
        logger.info(f"  - {example}: {result}")


def main():
    """Main function to run the test script."""
    parser = argparse.ArgumentParser(description="Test tool usage evaluations for MCP agent examples")
    parser.add_argument(
        "--examples", 
        nargs="+", 
        help="Names of examples to evaluate (defaults to predefined list)"
    )
    
    args = parser.parse_args()
    
    asyncio.run(run_evaluations(args.examples))


if __name__ == "__main__":
    main()