"""
Tool Usage Evaluation Runner for MCP Agents.

This script runs tool usage evaluations for specified MCP agents, including:
- mcp_basic_azure
- mcp_basic_agent
- mcp_basic_google_agent
- mcp_basic_ollama_agent
- mcp_basic_slack_agent
- mcp_researcher
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Any, Union

import yaml

# Add parent directory to path to allow importing from mcp_agent
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mcp_agent.logging.events import ToolEvent
from mcp_agent.mcp.mcp_agent_client_session import MCPAgentClientSession
from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM

from .tool_usage_evaluation import ToolUsageEvaluator, visualize_tool_usage


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ToolUsageRunner:
    """Runner for tool usage evaluations."""
    
    def __init__(self, base_dir: Path):
        """Initialize the tool usage runner.
        
        Args:
            base_dir: Base directory containing MCP agent examples
        """
        self.base_dir = base_dir
        self.results_dir = base_dir / "eval_results" / "tool_usage"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        # List of agents to evaluate
        self.agents = [
            "mcp_basic_azure_agent",
            "mcp_basic_agent",
            "mcp_basic_google_agent",
            "mcp_basic_ollama_agent",
            "mcp_basic_slack_agent",
            "mcp_researcher"
        ]
        
        # Test queries that exercise different tools
        self.test_queries = {
            "fetch": [
                "Get information from this website: https://example.com",
                "What's on this webpage? https://anthropic.com",
                "Can you summarize the content at https://github.com/anthropics/anthropic-sdk-python"
            ],
            "filesystem": [
                "Read the file at /tmp/data.txt",
                "What's in the document README.md?",
                "Show me the contents of requirements.txt"
            ],
            "brave": [
                "Search for information about large language models",
                "Find the latest news about AI safety",
                "Look up papers on reinforcement learning"
            ],
            "interpreter": [
                "Run this Python code: print(sum(range(10)))",
                "Execute a function to calculate fibonacci numbers",
                "Use Python to analyze this data: [1, 2, 3, 4, 5]"
            ],
            "slack": [
                "What are the recent messages in the #general channel?",
                "Send a message to the team about the meeting",
                "Check if there are any new DMs"
            ]
        }
    
    def get_agent_paths(self, agent_name: str) -> Tuple[Path, Path]:
        """Get the paths to the agent's directory and config file.
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            Tuple of (agent_dir, config_path)
        """
        agent_dir = self.base_dir / "examples" / agent_name
        config_path = agent_dir / "mcp_agent.config.yaml"
        
        return agent_dir, config_path
    
    def load_config(self, config_path: Path) -> Dict[str, Any]:
        """Load the agent's config file.
        
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
    
    async def run_evaluation(self, agent_name: str) -> Optional[Path]:
        """Run tool usage evaluation for an agent.
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            Path to the results file
        """
        logger.info(f"Evaluating agent: {agent_name}")
        
        agent_dir, config_path = self.get_agent_paths(agent_name)
        if not agent_dir.exists() or not config_path.exists():
            logger.error(f"Agent directory or config file not found for {agent_name}")
            return None
        
        # Initialize evaluator
        evaluator = ToolUsageEvaluator(agent_name, str(config_path))
        
        # Load config to identify tools
        config = self.load_config(config_path)
        
        # Extract tools from config
        tools = []
        if "serversConfig" in config:
            tools = list(config.get("serversConfig", {}).keys())
        
        # Simulate tool events for evaluation
        # In a real implementation, you would:
        # 1. Instantiate and run the agent
        # 2. Intercept actual tool events during execution
        # 3. Record them using evaluator.record_tool_event()
        
        # For now, we'll use simulated events
        for tool in tools:
            if tool in self.test_queries:
                for query_idx, query in enumerate(self.test_queries[tool]):
                    # Simulate a tool event
                    event = ToolEvent(
                        tool_name=tool,
                        parameters={"query": query} if tool == "brave" else 
                                  {"url": "https://example.com"} if tool == "fetch" else
                                  {"path": "/tmp/data.txt"} if tool == "filesystem" else
                                  {"code": "print('Hello World')"} if tool == "interpreter" else
                                  {},
                        start_time=time.time(),
                        end_time=time.time() + (query_idx + 1) * 0.5,  # Simulated processing time
                        result={"status": "success", "data": f"Simulated result for {tool}"},
                        error=None if query_idx < 2 else f"Simulated error for {tool}"
                    )
                    evaluator.record_tool_event(event)
        
        # Generate test cases for tool selection evaluation
        test_cases = evaluator.generate_test_cases()
        
        # Simulate LLM tool selection (in real implementation, this would use the agent's LLM)
        def mock_llm_selector(query: str) -> str:
            # Simple mock selector that picks based on keywords
            if "URL" in query.upper() or "website" in query.lower() or "webpage" in query.lower():
                return "fetch"
            elif "file" in query.lower() or "document" in query.lower() or "contents" in query.lower():
                return "filesystem"
            elif "search" in query.lower() or "information about" in query.lower() or "find" in query.lower():
                return "brave"
            elif "code" in query.lower() or "Python" in query.lower() or "execute" in query.lower():
                return "interpreter"
            elif "slack" in query.lower() or "message" in query.lower() or "channel" in query.lower():
                return "slack"
            else:
                # Default to the first available tool
                return tools[0] if tools else "unknown"
        
        # Evaluate tool selection accuracy
        accuracy = evaluator.evaluate_tool_selection(mock_llm_selector)
        logger.info(f"Tool selection accuracy for {agent_name}: {accuracy:.2f}")
        
        # Calculate metrics
        evaluator.calculate_metrics()
        
        # Export results
        results_file = evaluator.export_results(self.results_dir)
        
        # Generate visualizations
        vis_files = visualize_tool_usage(results_file, self.results_dir)
        logger.info(f"Visualizations generated: {list(vis_files.keys())}")
        
        return results_file
    
    async def run_all(self, agents: Optional[List[str]] = None) -> List[Path]:
        """Run evaluations for all specified agents.
        
        Args:
            agents: List of agent names to evaluate (defaults to all)
            
        Returns:
            List of paths to results files
        """
        if agents is None:
            agents = self.agents
        
        results = []
        for agent_name in agents:
            result = await self.run_evaluation(agent_name)
            if result:
                results.append(result)
        
        return results


async def main():
    """Main function to run tool usage evaluations."""
    parser = argparse.ArgumentParser(description="Run tool usage evaluations for MCP agents")
    parser.add_argument(
        "--agents", 
        nargs="+", 
        help="Names of agents to evaluate (defaults to predefined list)"
    )
    parser.add_argument(
        "--base-dir", 
        type=str, 
        default=str(Path(__file__).parent.parent.parent.parent),
        help="Base directory containing MCP agent examples"
    )
    
    args = parser.parse_args()
    
    runner = ToolUsageRunner(Path(args.base_dir))
    results = await runner.run_all(args.agents)
    
    logger.info(f"Evaluation complete. Results saved to: {runner.results_dir}")
    for result in results:
        logger.info(f"  - {result}")


if __name__ == "__main__":
    asyncio.run(main())