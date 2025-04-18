"""
Tool Usage Evaluation Framework for MCP Agents.

This module provides specialized evaluation metrics focusing on tool usage:
- Tool selection appropriateness
- Processing time for each tool
- Parameter correctness
- Tool selection accuracy for similar queries
"""

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union, Callable

from .metrics import MCPSpecificMetrics, ToolAction


@dataclass
class ToolEvent:
    """Event for tool usage by agents."""
    
    tool_name: str
    parameters: Dict[str, Any]
    start_time: float
    end_time: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class ToolUsageMetrics:
    """Metrics related to tool usage by agents."""
    
    # Tool selection metrics
    available_tools: List[str] = field(default_factory=list)
    used_tools: List[str] = field(default_factory=list)
    tool_usage_count: Dict[str, int] = field(default_factory=dict)
    
    # Timing metrics
    tool_processing_times: Dict[str, List[float]] = field(default_factory=dict)
    avg_processing_time: Dict[str, float] = field(default_factory=dict)
    
    # Parameter metrics
    tool_parameters: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    parameter_errors: Dict[str, List[str]] = field(default_factory=dict)
    
    # Selection accuracy
    selection_tests: List[Dict[str, Any]] = field(default_factory=list)
    selection_accuracy: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to a dictionary for serialization.
        
        Returns:
            Dictionary representation of the metrics
        """
        return {
            "available_tools": self.available_tools,
            "used_tools": self.used_tools,
            "tool_usage_count": self.tool_usage_count,
            "avg_processing_time": self.avg_processing_time,
            "parameter_errors": self.parameter_errors,
            "selection_accuracy": self.selection_accuracy,
        }


@dataclass
class ToolTestCase:
    """Test case for evaluating tool selection."""
    
    query: str
    expected_tool: str
    context: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None


class ToolUsageEvaluator:
    """Evaluator for tool usage metrics."""
    
    def __init__(self, agent_name: str, config_path: Optional[str] = None):
        """Initialize the tool usage evaluator.
        
        Args:
            agent_name: Name of the agent being evaluated
            config_path: Path to the agent's config file
        """
        self.agent_name = agent_name
        self.config_path = config_path
        self.metrics = ToolUsageMetrics()
        self.tool_events: List[ToolEvent] = []
        self.test_cases: List[ToolTestCase] = []
        
        # Load available tools from config if provided
        if config_path:
            self._load_available_tools()
    
    def _load_available_tools(self) -> None:
        """Load available tools from the agent's config file."""
        try:
            with open(self.config_path, 'r') as f:
                # Try loading as YAML first (most configs are YAML)
                import yaml
                config = yaml.safe_load(f)
                
                # Extract tools from config based on format
                tools = []
                if "serversConfig" in config:
                    # Old format
                    tools = list(config.get("serversConfig", {}).keys())
                elif "mcp" in config and "servers" in config["mcp"]:
                    # New format with mcp.servers
                    tools = list(config["mcp"]["servers"].keys())
                elif "tools" in config:
                    # Generic tools list
                    tools = list(config.get("tools", []))
                
                self.metrics.available_tools = tools
        except Exception as e:
            print(f"Error loading config: {e}")
    
    def record_tool_event(self, event: ToolEvent) -> None:
        """Record a tool usage event.
        
        Args:
            event: The tool event to record
        """
        self.tool_events.append(event)
        
        # Update tool usage metrics
        tool_name = event.tool_name
        
        # Count usage
        if tool_name not in self.metrics.tool_usage_count:
            self.metrics.tool_usage_count[tool_name] = 0
        self.metrics.tool_usage_count[tool_name] += 1
        
        if tool_name not in self.metrics.used_tools:
            self.metrics.used_tools.append(tool_name)
        
        # Track parameters
        if tool_name not in self.metrics.tool_parameters:
            self.metrics.tool_parameters[tool_name] = []
        self.metrics.tool_parameters[tool_name].append(event.parameters)
        
        # Track processing time
        processing_time = event.end_time - event.start_time if event.end_time else 0
        if tool_name not in self.metrics.tool_processing_times:
            self.metrics.tool_processing_times[tool_name] = []
        self.metrics.tool_processing_times[tool_name].append(processing_time)
        
        # Track errors
        if event.error:
            if tool_name not in self.metrics.parameter_errors:
                self.metrics.parameter_errors[tool_name] = []
            self.metrics.parameter_errors[tool_name].append(event.error)
    
    def generate_test_cases(self, num_cases: int = 5) -> List[ToolTestCase]:
        """Generate test cases for tool selection based on recorded events.
        
        Args:
            num_cases: Number of test cases to generate
            
        Returns:
            List of test cases
        """
        test_cases = []
        
        # Group events by tool
        tool_events = {}
        for event in self.tool_events:
            if event.tool_name not in tool_events:
                tool_events[event.tool_name] = []
            tool_events[event.tool_name].append(event)
        
        # Generate test cases for each tool (limited by num_cases)
        for tool_name, events in tool_events.items():
            count = min(len(events), max(1, num_cases // len(tool_events)))
            for i in range(count):
                event = events[i]
                # Create a similar but slightly modified query based on the event
                query = self._create_similar_query(event)
                test_case = ToolTestCase(
                    query=query,
                    expected_tool=tool_name,
                    context={"original_parameters": event.parameters}
                )
                test_cases.append(test_case)
        
        self.test_cases = test_cases
        return test_cases
    
    def _create_similar_query(self, event: ToolEvent) -> str:
        """Create a similar query based on the event.
        
        Args:
            event: The tool event to base the query on
            
        Returns:
            A similar query string
        """
        # This is a simplified version - in a real implementation, you'd want to:
        # 1. Use the LLM to generate a similar but distinct query
        # 2. Ensure the query is appropriate for the tool
        # 3. Keep the intent the same but vary the wording
        
        tool_name = event.tool_name
        
        if tool_name == "fetch":
            return f"Can you get information from this URL: {event.parameters.get('url', 'https://example.com')}"
        elif tool_name == "filesystem":
            return f"Please read the file at {event.parameters.get('path', '/path/to/file.txt')}"
        elif tool_name == "brave":
            return f"Search for information about {event.parameters.get('query', 'machine learning')}"
        elif tool_name == "interpreter":
            return f"Run this Python code: {event.parameters.get('code', 'print(1+1)')}"
        elif tool_name == "slack":
            return "What are the recent messages in the slack channel?"
        else:
            return f"Use the {tool_name} tool to complete this task"
    
    def calculate_metrics(self) -> ToolUsageMetrics:
        """Calculate metrics based on recorded events.
        
        Returns:
            Updated metrics
        """
        # Calculate average processing time per tool
        for tool_name, times in self.metrics.tool_processing_times.items():
            if times:
                self.metrics.avg_processing_time[tool_name] = sum(times) / len(times)
        
        return self.metrics
    
    def evaluate_tool_selection(self, llm_selector: Callable[[str], str]) -> float:
        """Evaluate tool selection accuracy using test cases.
        
        Args:
            llm_selector: Function that takes a query and returns a selected tool
            
        Returns:
            Selection accuracy as a fraction
        """
        if not self.test_cases:
            self.generate_test_cases()
        
        correct = 0
        for test_case in self.test_cases:
            selected_tool = llm_selector(test_case.query)
            test_case.result = {"selected_tool": selected_tool}
            
            if selected_tool == test_case.expected_tool:
                correct += 1
        
        accuracy = correct / len(self.test_cases) if self.test_cases else 0
        self.metrics.selection_accuracy = accuracy
        return accuracy
    
    def export_results(self, output_dir: Path) -> Path:
        """Export evaluation results to a file.
        
        Args:
            output_dir: Directory to save the results
            
        Returns:
            Path to the saved results file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"tool_usage_evaluation_{self.agent_name}_{timestamp}.json"
        
        # Update metrics before exporting
        self.calculate_metrics()
        
        # Convert test cases to dictionaries
        test_cases_dict = []
        for tc in self.test_cases:
            test_cases_dict.append({
                "query": tc.query,
                "expected_tool": tc.expected_tool,
                "result": tc.result
            })
        
        # Prepare results for export
        results = {
            "agent_name": self.agent_name,
            "timestamp": timestamp,
            "available_tools": self.metrics.available_tools,
            "used_tools": self.metrics.used_tools,
            "tool_usage_count": self.metrics.tool_usage_count,
            "avg_processing_time": self.metrics.avg_processing_time,
            "parameter_errors": self.metrics.parameter_errors,
            "selection_accuracy": self.metrics.selection_accuracy,
            "test_cases": test_cases_dict
        }
        
        # Create directory if it doesn't exist
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Write results to file
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        return output_file


def visualize_tool_usage(results_file: Path, output_dir: Path) -> Dict[str, Path]:
    """Generate visualizations for tool usage evaluation.
    
    Args:
        results_file: Path to the results JSON file
        output_dir: Directory to save visualizations
        
    Returns:
        Dictionary mapping visualization names to their file paths
    """
    # Return empty dict as visualizations are currently disabled
    return {}
    
    # # Load results
    # with open(results_file, 'r') as f:
    #     results = json.load(f)
    # 
    # # Create visualizations directory
    # vis_dir = output_dir / "visualizations"
    # vis_dir.mkdir(parents=True, exist_ok=True)
    # 
    # # Generate visualization data
    # timestamp = results.get("timestamp", datetime.now().strftime("%Y%m%d_%H%M%S"))
    # vis_files = {}
    # 
    # # Tool usage frequency visualization
    # if "tool_usage_count" in results and results["tool_usage_count"]:
    #     usage_data = {
    #         "title": f"Tool Usage Frequency - {results['agent_name']}",
    #         "labels": list(results["tool_usage_count"].keys()),
    #         "data": list(results["tool_usage_count"].values()),
    #         "type": "bar"
    #     }
    #     usage_file = vis_dir / f"tool_usage_frequency_{timestamp}.json"
    #     with open(usage_file, 'w') as f:
    #         json.dump(usage_data, f, indent=2)
    #     vis_files["usage_frequency"] = str(usage_file)
    # 
    # # Processing time visualization
    # if "avg_processing_time" in results and results["avg_processing_time"]:
    #     time_data = {
    #         "title": f"Average Tool Processing Time - {results['agent_name']}",
    #         "labels": list(results["avg_processing_time"].keys()),
    #         "data": list(results["avg_processing_time"].values()),
    #         "type": "bar"
    #     }
    #     time_file = vis_dir / f"tool_processing_time_{timestamp}.json"
    #     with open(time_file, 'w') as f:
    #         json.dump(time_data, f, indent=2)
    #     vis_files["processing_time"] = str(time_file)
    # 
    # # Selection accuracy visualization
    # if "selection_accuracy" in results and "test_cases" in results:
    #     accuracy_data = {
    #         "title": f"Tool Selection Accuracy - {results['agent_name']}",
    #         "accuracy": results["selection_accuracy"],
    #         "test_cases": results["test_cases"],
    #         "type": "gauge"
    #     }
    #     accuracy_file = vis_dir / f"tool_selection_accuracy_{timestamp}.json"
    #     with open(accuracy_file, 'w') as f:
    #         json.dump(accuracy_data, f, indent=2)
    #     vis_files["selection_accuracy"] = str(accuracy_file)
    # 
    # # Summary visualization
    # summary_data = {
    #     "title": f"Tool Usage Summary - {results['agent_name']}",
    #     "timestamp": timestamp,
    #     "metrics": {
    #         "tools_available": len(results.get("available_tools", [])),
    #         "tools_used": len(results.get("used_tools", [])),
    #         "selection_accuracy": results.get("selection_accuracy", 0),
    #     },
    #     "type": "summary"
    # }
    # summary_file = vis_dir / f"tool_usage_summary_{timestamp}.json"
    # with open(summary_file, 'w') as f:
    #     json.dump(summary_data, f, indent=2)
    # vis_files["summary"] = str(summary_file)
    # 
    # return vis_files