#!/usr/bin/env python3
"""
Generate a comprehensive evaluation report comparing multiple MCP agents.
"""

import os
import json
import glob
import argparse
from datetime import datetime
from typing import Dict, List, Any

def find_evaluation_results() -> Dict[str, List[str]]:
    """Find all evaluation results for agents."""
    results = {}
    base_dir = "examples"
    
    # Find all agent dirs with eval_results
    for agent_dir in os.listdir(base_dir):
        agent_path = os.path.join(base_dir, agent_dir)
        eval_dir = os.path.join(agent_path, "eval_results")
        
        if os.path.isdir(eval_dir):
            eval_files = glob.glob(os.path.join(eval_dir, "evaluation_*.json"))
            if eval_files:
                results[agent_dir] = eval_files
    
    return results

def load_evaluation_data(file_path: str) -> Dict[str, Any]:
    """Load evaluation data from a file."""
    with open(file_path, "r") as f:
        return json.load(f)

def generate_comparison_report(agent_results: Dict[str, List[str]], output_dir: str) -> str:
    """Generate a comparison report for all evaluated agents."""
    os.makedirs(output_dir, exist_ok=True)
    
    report_data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "agent_count": len(agent_results),
        "agents": {}
    }
    
    # Process each agent's most recent evaluation
    for agent_name, result_files in agent_results.items():
        # Sort by timestamp (newest first)
        result_files.sort(reverse=True)
        
        # Load the most recent evaluation
        most_recent = result_files[0]
        data = load_evaluation_data(most_recent)
        
        # Extract key metrics
        report_data["agents"][agent_name] = {
            "evaluation_file": most_recent,
            "timestamp": data.get("timestamp", "unknown"),
            "success_rate": data.get("metrics", {}).get("success_rate", 0),
            "avg_response_time": data.get("metrics", {}).get("avg_response_time", 0),
            "test_count": len(data.get("results", [])),
            "tool_usage_count": data.get("metrics", {}).get("tool_usage_count", 0)
        }
    
    # Calculate rankings
    agents_by_success = sorted(report_data["agents"].items(), 
                              key=lambda x: x[1]["success_rate"], 
                              reverse=True)
    
    agents_by_speed = sorted(report_data["agents"].items(), 
                            key=lambda x: x[1]["avg_response_time"])
    
    # Add rankings to the report
    report_data["rankings"] = {
        "by_success_rate": [a[0] for a in agents_by_success],
        "by_response_time": [a[0] for a in agents_by_speed]
    }
    
    # Save the report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = os.path.join(output_dir, f"comparison_report_{timestamp}.json")
    
    with open(report_file, "w") as f:
        json.dump(report_data, f, indent=2)
    
    # Generate a visualization data file
    vis_dir = os.path.join(output_dir, "visualizations")
    os.makedirs(vis_dir, exist_ok=True)
    
    vis_file = os.path.join(vis_dir, f"comparison_metrics_{timestamp}.json")
    
    visualization_data = {
        "agents": list(report_data["agents"].keys()),
        "success_rates": [a["success_rate"] for a in report_data["agents"].values()],
        "response_times": [a["avg_response_time"] for a in report_data["agents"].values()]
    }
    
    with open(vis_file, "w") as f:
        json.dump(visualization_data, f, indent=2)
    
    return report_file

def print_report_summary(report_file: str):
    """Print a summary of the comparison report."""
    with open(report_file, "r") as f:
        report = json.load(f)
    
    print("\n===== MCP Agent Evaluation Comparison =====")
    print(f"Generated: {report['timestamp']}")
    print(f"Agents Evaluated: {report['agent_count']}")
    
    print("\nSuccess Rate Ranking:")
    for i, agent in enumerate(report["rankings"]["by_success_rate"]):
        success_rate = report["agents"][agent]["success_rate"]
        print(f"{i+1}. {agent}: {success_rate:.2f}%")
    
    print("\nResponse Time Ranking (fastest first):")
    for i, agent in enumerate(report["rankings"]["by_response_time"]):
        response_time = report["agents"][agent]["avg_response_time"]
        print(f"{i+1}. {agent}: {response_time:.2f}s")
    
    print("\nDetailed Results:")
    for agent, metrics in report["agents"].items():
        print(f"\n{agent}:")
        print(f"  Success Rate: {metrics['success_rate']:.2f}%")
        print(f"  Avg Response Time: {metrics['avg_response_time']:.2f}s")
        print(f"  Test Cases: {metrics['test_count']}")
        print(f"  Tool Usage: {metrics['tool_usage_count']}")
    
    print(f"\nFull report saved to: {report_file}")

def main():
    parser = argparse.ArgumentParser(description="Generate a comparison report for evaluated MCP agents")
    parser.add_argument("--output", type=str, default="eval/reports",
                      help="Directory to save the comparison report")
    
    args = parser.parse_args()
    
    # Find all evaluation results
    agent_results = find_evaluation_results()
    
    if not agent_results:
        print("No evaluation results found. Run evaluations first.")
        return
    
    print(f"Found evaluation results for {len(agent_results)} agents.")
    
    # Generate the comparison report
    report_file = generate_comparison_report(agent_results, args.output)
    
    # Print the summary
    print_report_summary(report_file)

if __name__ == "__main__":
    main()