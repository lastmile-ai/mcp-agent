"""
Tool Usage Evaluation Summary for MCP Agents.

This module analyzes tool usage evaluation results to provide 
insights and recommendations for agent improvements.
"""

import argparse
import glob
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any, Union

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ToolEvaluationAnalyzer:
    """Analyzer for tool usage evaluation results."""
    
    def __init__(self, examples_dir: Optional[Path] = None):
        """Initialize the tool evaluation analyzer.
        
        Args:
            examples_dir: Directory containing example evaluations
        """
        if examples_dir is None:
            # Default to project root/examples
            examples_dir = Path(__file__).parent.parent.parent.parent / "examples"
        
        self.examples_dir = examples_dir
        self.results_cache = {}
    
    def find_evaluation_files(self, example_name: str) -> List[Path]:
        """Find evaluation result files for an example.
        
        Args:
            example_name: Name of the example
            
        Returns:
            List of paths to evaluation result files
        """
        example_dir = self.examples_dir / example_name
        eval_dir = example_dir / "eval_results"
        
        if not eval_dir.exists():
            logger.warning(f"No evaluation directory found for {example_name}")
            return []
        
        # Find all JSON files in the eval directory
        eval_files = list(eval_dir.glob("*.json"))
        
        return eval_files
    
    def load_evaluation_results(self, file_path: Path) -> Dict[str, Any]:
        """Load evaluation results from a file.
        
        Args:
            file_path: Path to the evaluation results file
            
        Returns:
            Evaluation results as a dictionary
        """
        if file_path in self.results_cache:
            return self.results_cache[file_path]
        
        try:
            with open(file_path, 'r') as f:
                results = json.load(f)
                self.results_cache[file_path] = results
                return results
        except Exception as e:
            logger.error(f"Error loading results from {file_path}: {e}")
            return {}
    
    def analyze_tool_usage(self, example_name: str) -> Dict[str, Any]:
        """Analyze tool usage for an example.
        
        Args:
            example_name: Name of the example
            
        Returns:
            Analysis results as a dictionary
        """
        eval_files = self.find_evaluation_files(example_name)
        
        if not eval_files:
            logger.warning(f"No evaluation files found for {example_name}")
            return {
                "example_name": example_name,
                "status": "no_data"
            }
        
        # Group files by evaluation type
        tool_usage_evals = []
        specific_query_evals = []
        
        for file_path in eval_files:
            if "tool_usage_evaluation" in file_path.name:
                tool_usage_evals.append(file_path)
            elif "specific_queries_evaluation" in file_path.name:
                specific_query_evals.append(file_path)
        
        # Get the most recent of each type
        latest_tool_usage = max(tool_usage_evals, key=lambda p: p.stat().st_mtime) if tool_usage_evals else None
        latest_specific_query = max(specific_query_evals, key=lambda p: p.stat().st_mtime) if specific_query_evals else None
        
        # Load and analyze results
        tool_usage_results = self.load_evaluation_results(latest_tool_usage) if latest_tool_usage else {}
        specific_query_results = self.load_evaluation_results(latest_specific_query) if latest_specific_query else {}
        
        # Compile analysis
        analysis = {
            "example_name": example_name,
            "status": "analyzed",
            "available_tools": tool_usage_results.get("available_tools", []),
            "tool_usage_stats": {
                "used_tools": tool_usage_results.get("used_tools", []),
                "tool_usage_count": tool_usage_results.get("tool_usage_count", {}),
                "avg_processing_time": tool_usage_results.get("avg_processing_time", {})
            },
            "basic_selection_accuracy": tool_usage_results.get("selection_accuracy", 0),
            "specific_selection_accuracy": specific_query_results.get("selection_accuracy", 0),
            "basic_test_cases": tool_usage_results.get("test_cases", []),
            "specific_test_cases": specific_query_results.get("test_cases", [])
        }
        
        # Add improvement recommendations based on analysis
        analysis["recommendations"] = self._generate_recommendations(analysis)
        
        return analysis
    
    def _generate_recommendations(self, analysis: Dict[str, Any]) -> List[str]:
        """Generate improvement recommendations based on analysis.
        
        Args:
            analysis: Analysis results
            
        Returns:
            List of recommendation strings
        """
        recommendations = []
        
        # Check for selection accuracy issues
        basic_accuracy = analysis.get("basic_selection_accuracy", 0)
        specific_accuracy = analysis.get("specific_selection_accuracy", 0)
        
        if basic_accuracy < 0.7:
            recommendations.append(f"Improve tool selection for basic queries (current accuracy: {basic_accuracy:.2f})")
        
        if specific_accuracy < 0.7:
            recommendations.append(f"Improve tool selection for complex queries (current accuracy: {specific_accuracy:.2f})")
        
        # Check for specific test case failures
        specific_cases = analysis.get("specific_test_cases", [])
        failed_cases = [c for c in specific_cases if not c.get("correct", False)]
        
        for case in failed_cases:
            query = case.get("query", "")
            expected = case.get("expected_tool", "")
            selected = case.get("selected_tool", "")
            desc = case.get("description", "")
            
            recommendations.append(f"Improve handling of '{desc}' queries - expected '{expected}' but got '{selected}'")
        
        # Add general recommendations if no specific issues
        if not recommendations:
            available_tools = analysis.get("available_tools", [])
            if len(available_tools) > 1:
                recommendations.append("Consider adding more complex multi-tool scenarios for testing")
            else:
                recommendations.append("Consider expanding agent capabilities with additional tools")
        
        return recommendations
    
    def generate_summary_report(self, examples: List[str]) -> Dict[str, Any]:
        """Generate a summary report for multiple examples.
        
        Args:
            examples: List of example names
            
        Returns:
            Summary report as a dictionary
        """
        analyses = {}
        for example in examples:
            analyses[example] = self.analyze_tool_usage(example)
        
        # Calculate overall metrics
        overall_basic_accuracy = 0
        overall_specific_accuracy = 0
        count = 0
        
        for example, analysis in analyses.items():
            if analysis.get("status") == "analyzed":
                overall_basic_accuracy += analysis.get("basic_selection_accuracy", 0)
                overall_specific_accuracy += analysis.get("specific_selection_accuracy", 0)
                count += 1
        
        if count > 0:
            overall_basic_accuracy /= count
            overall_specific_accuracy /= count
        
        return {
            "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "examples_analyzed": count,
            "overall_basic_accuracy": overall_basic_accuracy,
            "overall_specific_accuracy": overall_specific_accuracy,
            "analyses": analyses
        }
    
    def export_summary_report(self, report: Dict[str, Any], output_dir: Optional[Path] = None) -> Path:
        """Export a summary report to a file.
        
        Args:
            report: Summary report dictionary
            output_dir: Directory to save the report
            
        Returns:
            Path to the saved report file
        """
        if output_dir is None:
            output_dir = self.examples_dir.parent / "reports"
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = report.get("timestamp", datetime.now().strftime("%Y%m%d_%H%M%S"))
        output_file = output_dir / f"tool_evaluation_summary_{timestamp}.json"
        
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"Summary report saved to: {output_file}")
        return output_file


def main():
    """Main function to run the tool evaluation analyzer."""
    parser = argparse.ArgumentParser(description="Analyze tool usage evaluation results")
    parser.add_argument(
        "--examples", 
        nargs="+", 
        default=["mcp_basic_agent", "mcp_basic_azure_agent", "mcp_basic_google_agent", 
                "mcp_basic_ollama_agent", "mcp_basic_slack_agent", "mcp_researcher"],
        help="Names of examples to analyze (defaults to predefined list)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directory to save the summary report"
    )
    
    args = parser.parse_args()
    
    analyzer = ToolEvaluationAnalyzer()
    report = analyzer.generate_summary_report(args.examples)
    
    output_dir = Path(args.output_dir) if args.output_dir else None
    output_file = analyzer.export_summary_report(report, output_dir)
    
    # Print a concise summary to the console
    logger.info("Tool Evaluation Summary:")
    logger.info(f"Examples analyzed: {report['examples_analyzed']}")
    logger.info(f"Basic query accuracy: {report['overall_basic_accuracy']:.2f}")
    logger.info(f"Specific query accuracy: {report['overall_specific_accuracy']:.2f}")
    
    for example, analysis in report["analyses"].items():
        if analysis.get("status") == "analyzed":
            logger.info(f"\n{example}:")
            logger.info(f"  Basic accuracy: {analysis.get('basic_selection_accuracy', 0):.2f}")
            logger.info(f"  Specific accuracy: {analysis.get('specific_selection_accuracy', 0):.2f}")
            
            if analysis.get("recommendations"):
                logger.info("  Recommendations:")
                for rec in analysis.get("recommendations", []):
                    logger.info(f"    - {rec}")


if __name__ == "__main__":
    main()