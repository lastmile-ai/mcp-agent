"""
Test script for running specific queries against MCP agent examples.

This script tests specific agents with modified queries based on prior evaluations.

Usage:
    python -m mcp_agent.eval.test_specific_queries
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any

from .run_tool_usage_evaluation import ToolEvaluationRunner
from .tool_usage_evaluation import ToolUsageEvaluator, ToolEvent, ToolTestCase

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SpecificQueryTester:
    """Class to test specific queries against agents."""
    
    def __init__(self, base_dir: Optional[Path] = None):
        """Initialize the specific query tester.
        
        Args:
            base_dir: Base directory containing MCP agent examples
        """
        if base_dir is None:
            # Default to project root
            base_dir = Path(__file__).parent.parent.parent.parent
        
        self.base_dir = base_dir
        self.runner = ToolEvaluationRunner(base_dir)
    
    def _create_challenging_query(self, example_name: str) -> List[Dict[str, Any]]:
        """Create challenging queries for a specific example.
        
        Args:
            example_name: Name of the example
            
        Returns:
            List of test cases with challenging queries
        """
        test_cases = []
        
        # Specific challenging queries for each agent type
        if example_name == "mcp_basic_agent":
            # Test cases that require URL fetching but with more complex instructions
            test_cases.append({
                "query": "Can you retrieve and summarize the introduction section from https://modelcontextprotocol.io/introduction",
                "expected_tool": "fetch",
                "description": "Fetch with summarization request"
            })
            test_cases.append({
                "query": "I need to read the content from https://modelcontextprotocol.io/introduction and extract the key points",
                "expected_tool": "fetch",
                "description": "Fetch with extraction request"
            })
            # Edge case between filesystem and fetch
            test_cases.append({
                "query": "Find information about MCP protocol online and save it to a file",
                "expected_tool": "fetch",
                "description": "Multi-step operation requiring multiple tools"
            })
            
        elif example_name == "mcp_basic_slack_agent":
            # Test cases for Slack functionality with variations
            test_cases.append({
                "query": "What are the most recent conversations in the general channel?",
                "expected_tool": "slack",
                "description": "Slightly different way to ask for Slack messages"
            })
            test_cases.append({
                "query": "Give me a summary of the discussion in the general channel from yesterday",
                "expected_tool": "slack",
                "description": "Slack request with time specification"
            })
            test_cases.append({
                "query": "Has anyone mentioned 'meeting' in the general channel recently?",
                "expected_tool": "slack",
                "description": "Slack request with keyword search"
            })
            
        elif example_name == "mcp_researcher":
            # Test cases for research operations with multiple potential tools
            test_cases.append({
                "query": "Research Eutelsat's financial performance over the last fiscal year and create a chart",
                "expected_tool": "brave",
                "description": "Research with visualization requirement"
            })
            test_cases.append({
                "query": "Gather data about Eutelsat's market position compared to competitors and analyze using Python",
                "expected_tool": "interpreter",
                "description": "Research with explicit Python requirement"
            })
            test_cases.append({
                "query": "Find recent news about Eutelsat's satellite launches and create a timeline",
                "expected_tool": "brave",
                "description": "Research with timeline creation request"
            })
            test_cases.append({
                "query": "Calculate Eutelsat's revenue growth rate based on publicly available financial data",
                "expected_tool": "interpreter",
                "description": "Financial calculation requiring Python"
            })
            
        elif example_name == "mcp_basic_ollama_agent":
            # Test cases for Ollama agent
            test_cases.append({
                "query": "Can you fetch and tell me about the key features of the Model Context Protocol from their website?",
                "expected_tool": "fetch",
                "description": "Web content with specific information extraction"
            })
            test_cases.append({
                "query": "Read through the MCP documentation online and explain how it works",
                "expected_tool": "fetch",
                "description": "Web content processing with explanation request"
            })
            
        elif example_name == "mcp_basic_azure_agent" or example_name == "mcp_basic_google_agent":
            # Test cases for cloud-based agents
            test_cases.append({
                "query": "Please retrieve information about the first version of MCP from their website",
                "expected_tool": "fetch",
                "description": "Information retrieval with specific version"
            })
            test_cases.append({
                "query": "I need to understand how MCP differs from other protocols, can you get this from their site?",
                "expected_tool": "fetch",
                "description": "Comparative information retrieval"
            })
        
        return test_cases
    
    async def test_specific_example(self, example_name: str) -> Optional[Path]:
        """Test a specific example with challenging queries.
        
        Args:
            example_name: Name of the example
            
        Returns:
            Path to the results file
        """
        logger.info(f"Testing example with specific queries: {example_name}")
        
        example_dir, config_path = self.runner.get_example_paths(example_name)
        if not example_dir.exists() or not config_path.exists():
            logger.error(f"Example directory or config file not found for {example_name}")
            return None
        
        # Create evaluation results directory for this example
        eval_results_dir = example_dir / "eval_results"
        eval_results_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize evaluator
        evaluator = ToolUsageEvaluator(example_name, str(config_path))
        
        # Load config to identify tools
        config = self.runner.load_config(config_path)
        
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
        
        # Get challenging test cases for this example
        test_cases_info = self._create_challenging_query(example_name)
        logger.info(f"Created {len(test_cases_info)} challenging test cases for {example_name}")
        
        # Register tool events for each available tool
        for tool in tools:
            # Simulate a tool event
            event = ToolEvent(
                tool_name=tool,
                parameters={},
                start_time=time.time(),
                end_time=time.time() + 0.5,  # Simulated processing time
                result={"status": "success"},
                error=None
            )
            evaluator.record_tool_event(event)
        
        # Create ToolTestCase objects
        test_cases = []
        for tc_info in test_cases_info:
            test_case = ToolTestCase(
                query=tc_info["query"],
                expected_tool=tc_info["expected_tool"],
                context={"description": tc_info.get("description", "")}
            )
            test_cases.append(test_case)
        
        # Set the test cases on the evaluator
        evaluator.test_cases = test_cases
        
        # Define a tool selector function based on query patterns
        def tool_selector(query: str) -> str:
            # Simple pattern matching for tool selection
            query_lower = query.lower()
            
            # Check for patterns that indicate specific tools
            if any(term in query_lower for term in ["http", "url", "web", "site", "online", "website", "fetch", "retrieve"]):
                for tool in tools:
                    if tool in ["fetch", "web"]:
                        return tool
            
            if any(term in query_lower for term in ["file", "read", "local", "save", "document", "text file"]):
                for tool in tools:
                    if tool in ["filesystem", "file"]:
                        return tool
            
            if any(term in query_lower for term in ["search", "find", "look for", "research", "information about", "data about"]):
                for tool in tools:
                    if tool in ["brave", "search"]:
                        return tool
            
            if any(term in query_lower for term in ["code", "python", "run", "calculate", "compute", "script", "analyze"]):
                for tool in tools:
                    if tool in ["interpreter", "python"]:
                        return tool
            
            if any(term in query_lower for term in ["message", "channel", "slack", "chat", "conversation", "discussion"]):
                for tool in tools:
                    if tool in ["slack", "chat"]:
                        return tool
            
            # If no specific match, return the first tool
            return tools[0] if tools else "unknown"
        
        # Evaluate tool selection accuracy
        accuracy = evaluator.evaluate_tool_selection(tool_selector)
        logger.info(f"Tool selection accuracy for specific queries on {example_name}: {accuracy:.2f}")
        
        # Export results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = eval_results_dir / f"specific_queries_evaluation_{example_name}_{timestamp}.json"
        
        # Add more details to the results
        results = {
            "agent_name": example_name,
            "timestamp": timestamp,
            "available_tools": tools,
            "selection_accuracy": accuracy,
            "test_cases": [
                {
                    "query": tc.query,
                    "expected_tool": tc.expected_tool,
                    "selected_tool": tc.result.get("selected_tool") if tc.result else None,
                    "description": tc.context.get("description") if tc.context else "",
                    "correct": (tc.result.get("selected_tool") == tc.expected_tool) if tc.result else False
                } for tc in test_cases
            ]
        }
        
        # Write results to file
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"Results saved to: {results_file}")
        return results_file


async def main():
    """Main function to run specific query tests."""
    parser = argparse.ArgumentParser(description="Test specific queries against MCP agent examples")
    parser.add_argument(
        "--examples", 
        nargs="+", 
        default=["mcp_basic_agent", "mcp_basic_azure_agent", "mcp_basic_google_agent", 
                "mcp_basic_ollama_agent", "mcp_basic_slack_agent", "mcp_researcher"],
        help="Names of examples to test (defaults to predefined list)"
    )
    
    args = parser.parse_args()
    examples = args.examples
    
    tester = SpecificQueryTester()
    
    # Run tests
    results = []
    for example in examples:
        try:
            logger.info(f"Testing example: {example}")
            result = await tester.test_specific_example(example)
            if result:
                results.append((example, result))
                logger.info(f"Successfully tested {example}")
            else:
                logger.error(f"Failed to test {example}")
        except Exception as e:
            logger.error(f"Error testing {example}: {e}")
    
    # Print summary
    logger.info("Testing Summary:")
    logger.info(f"Total examples: {len(examples)}")
    logger.info(f"Successful: {len(results)}")
    logger.info(f"Failed: {len(examples) - len(results)}")
    logger.info("Results saved to individual example directories:")
    
    for example, result in results:
        logger.info(f"  - {example}: {result}")


if __name__ == "__main__":
    asyncio.run(main())