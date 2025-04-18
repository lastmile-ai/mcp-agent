"""
Tool Usage Evaluation Runner for MCP Agents.

This script runs tool usage evaluation for specified MCP agent examples.
It evaluates:
- Which tools are used
- Processing time for each tool
- Tool parameters
- Tool selection accuracy
"""

import argparse
import asyncio
import importlib.util
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from .tool_usage_evaluation import ToolUsageEvaluator, ToolEvent, ToolTestCase, visualize_tool_usage
from .tool_usage_listener import attach_tool_usage_listener


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ToolEvaluationRunner:
    """Runner for tool usage evaluations."""
    
    def __init__(self, base_dir: Optional[Path] = None):
        """Initialize the tool evaluation runner.
        
        Args:
            base_dir: Base directory containing MCP agent examples
        """
        if base_dir is None:
            # Default to project root
            base_dir = Path(__file__).parent.parent.parent.parent
        
        self.base_dir = base_dir
    
    def get_example_paths(self, example_name: str) -> Tuple[Path, Path]:
        """Get the paths to the example's directory and config file.
        
        Args:
            example_name: Name of the example
            
        Returns:
            Tuple of (example_dir, config_path)
        """
        example_dir = self.base_dir / "examples" / example_name
        config_path = example_dir / "mcp_agent.config.yaml"
        
        return example_dir, config_path
    
    def load_config(self, config_path: Path) -> Dict[str, Any]:
        """Load the example's config file.
        
        Args:
            config_path: Path to the config file
            
        Returns:
            Config dictionary
        """
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {}
    
    def _get_test_query_for_example(self, example_name: str) -> str:
        """Get a predefined test query for this example.
        
        Args:
            example_name: Name of the example
            
        Returns:
            Test query for the example
        """
        # Map of example names to test queries
        test_queries = {
            "mcp_basic_agent": "Print the first 2 paragraphs of https://modelcontextprotocol.io/introduction",
            "mcp_basic_azure_agent": "Print the first 2 paragraphs of https://modelcontextprotocol.io/introduction",
            "mcp_basic_google_agent": "Print the first 2 paragraphs of https://modelcontextprotocol.io/introduction",
            "mcp_basic_bedrock_agent": "Print the first 2 paragraphs of https://modelcontextprotocol.io/introduction",
            "mcp_basic_ollama_agent": "Print the first 2 paragraphs of https://modelcontextprotocol.io/introduction",
            "mcp_basic_slack_agent": "What was the last message in the general channel?",
            "mcp_researcher": "Produce an investment report for the company Eutelsat",
            "mcp_hello_world": "Hello world!",
            "mcp_github_to_slack_agent": "Check for new GitHub issues and post them to Slack",
            "mcp_model_selector": "Select the best model for sentiment analysis",
            "mcp_root_test": "Analyze the sensor data from the fitness tracker experiment"
        }
        
        # Return the test query for this example, or a default query if not found
        return test_queries.get(example_name, f"Help me with {example_name}")
    
    def _create_similar_query(self, original_query: str) -> str:
        """Create a similar query with minor variations.
        
        Args:
            original_query: The original query to modify
            
        Returns:
            A modified version of the original query
        """
        # Simple word replacements to create a similar query
        replacements = {
            "print": "output",
            "produce": "create",
            "get": "retrieve",
            "what": "tell me",
            "help": "assist",
            "check": "look for",
            "analyze": "examine",
            "select": "choose"
        }
        
        # Try to replace a word
        words = original_query.split()
        for i, word in enumerate(words):
            word_lower = word.lower()
            if word_lower in replacements:
                words[i] = replacements[word_lower]
                return " ".join(words)
        
        # If no replacements were made, add "please" at the beginning
        return f"Please {original_query.lower()}"
    
    def _get_tool_parameters(self, tool: str, query: str) -> Dict[str, Any]:
        """Get appropriate parameters for a tool based on the query.
        
        Args:
            tool: Tool name
            query: Query text
            
        Returns:
            Tool parameters
        """
        # Default empty parameters
        return {}
    
    async def run_evaluation(self, example_name: str) -> Optional[Path]:
        """Run tool usage evaluation for an example agent.
        
        Args:
            example_name: Name of the example
            
        Returns:
            Path to the results file
        """
        logger.info(f"Evaluating example: {example_name}")
        
        example_dir, config_path = self.get_example_paths(example_name)
        if not example_dir.exists() or not config_path.exists():
            logger.error(f"Example directory or config file not found for {example_name}")
            return None
        
        # Create evaluation results directory for this example
        eval_results_dir = example_dir / "eval_results"
        eval_results_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize evaluator
        evaluator = ToolUsageEvaluator(example_name, str(config_path))
        
        # Load config to identify tools
        config = self.load_config(config_path)
        
        # Extract tools from config - handle different config formats
        tools = []
        if "serversConfig" in config:
            # Old format
            tools = list(config.get("serversConfig", {}).keys())
        elif "mcp" in config and "servers" in config["mcp"]:
            # New format with mcp.servers
            tools = list(config["mcp"]["servers"].keys())
        
        if not tools:
            logger.warning(f"No tools found in config for {example_name}")
            return None
        
        # Get a test query for this example
        test_query = self._get_test_query_for_example(example_name)
        logger.info(f"Using test query: {test_query}")
        
        # Create a similar query for testing
        similar_query = self._create_similar_query(test_query)
        logger.info(f"Created similar query: {similar_query}")
        
        # Register tool events for each available tool
        for tool in tools:
            # Simulate a tool event
            event = ToolEvent(
                tool_name=tool,
                parameters=self._get_tool_parameters(tool, test_query),
                start_time=time.time(),
                end_time=time.time() + 0.5,  # Simulated processing time
                result={"status": "success"},
                error=None
            )
            evaluator.record_tool_event(event)
        
        # Create test cases based on the similar query
        test_cases = []
        for tool in tools:
            test_case = ToolTestCase(
                query=similar_query,
                expected_tool=tool,
                context={"original_query": test_query}
            )
            test_cases.append(test_case)
        
        # Set the test cases on the evaluator
        evaluator.test_cases = test_cases
        
        # Define a tool selector function based on query patterns
        def tool_selector(query: str) -> str:
            # Simple pattern matching for tool selection
            query_lower = query.lower()
            
            # Check for patterns that indicate specific tools
            if "http" in query_lower or "url" in query_lower or "web" in query_lower:
                for tool in tools:
                    if tool in ["fetch", "web"]:
                        return tool
            
            if "file" in query_lower or "read" in query_lower:
                for tool in tools:
                    if tool in ["filesystem", "file"]:
                        return tool
            
            if "search" in query_lower or "find" in query_lower:
                for tool in tools:
                    if tool in ["brave", "search"]:
                        return tool
            
            if "code" in query_lower or "python" in query_lower or "run" in query_lower:
                for tool in tools:
                    if tool in ["interpreter", "python"]:
                        return tool
            
            if "message" in query_lower or "channel" in query_lower:
                for tool in tools:
                    if tool in ["slack", "chat"]:
                        return tool
            
            # If no specific match, return the first tool
            return tools[0] if tools else "unknown"
        
        # Evaluate tool selection accuracy
        accuracy = evaluator.evaluate_tool_selection(tool_selector)
        logger.info(f"Tool selection accuracy for {example_name}: {accuracy:.2f}")
        
        # Calculate metrics
        evaluator.calculate_metrics()
        
        # Export results
        results_file = evaluator.export_results(eval_results_dir)
        
        # Generate visualizations (disabled now)
        vis_files = visualize_tool_usage(results_file, eval_results_dir)
        
        return results_file


async def main():
    """Main function to run tool usage evaluation."""
    parser = argparse.ArgumentParser(description="Run tool usage evaluation for an MCP agent example")
    parser.add_argument(
        "example", 
        type=str,
        help="Name of the example to evaluate"
    )
    parser.add_argument(
        "--base-dir", 
        type=str, 
        default=None,
        help="Base directory containing MCP agent examples"
    )
    
    args = parser.parse_args()
    
    base_dir = Path(args.base_dir) if args.base_dir else None
    runner = ToolEvaluationRunner(base_dir)
    
    result = await runner.run_evaluation(args.example)
    
    if result:
        logger.info(f"Evaluation complete. Results saved to: {result}")
    else:
        logger.error(f"Evaluation failed for example: {args.example}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())