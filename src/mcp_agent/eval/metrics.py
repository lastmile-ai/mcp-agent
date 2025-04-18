"""
Core evaluation metrics for MCP Agents.

This module contains implementations of standardized metrics to evaluate
the performance of MCP agents across different scenarios (education, airline, retail, etc.)
"""

import re
import json
from typing import Dict, List, Any, Optional, Tuple, Union, Callable
from dataclasses import dataclass
import numpy as np
from enum import Enum

class TaskDifficulty(str, Enum):
    """Enum to represent task difficulty levels."""
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"

@dataclass
class SubGoal:
    """Class representing a subgoal within a task."""
    id: str
    description: str
    regex_pattern: Optional[str] = None
    matcher_function: Optional[Callable[[str], bool]] = None
    
    def is_matched(self, state: str) -> bool:
        """Check if the current state matches this subgoal."""
        if self.regex_pattern:
            return bool(re.search(self.regex_pattern, state, re.DOTALL))
        elif self.matcher_function:
            return self.matcher_function(state)
        return False

@dataclass
class Task:
    """Class representing a task with a set of subgoals."""
    id: str
    name: str
    description: str
    difficulty: TaskDifficulty
    subgoals: List[SubGoal]
    final_goal_description: str
    final_goal_regex: Optional[str] = None
    final_goal_matcher: Optional[Callable[[str], bool]] = None
    
    def is_completed(self, final_state: str) -> bool:
        """Check if the final state satisfies the completion criteria."""
        if self.final_goal_regex:
            return bool(re.search(self.final_goal_regex, final_state, re.DOTALL))
        elif self.final_goal_matcher:
            return self.final_goal_matcher(final_state)
        return False
    
    def progress_rate(self, states: List[str]) -> List[float]:
        """
        Calculate the fine-grained progress rate across a sequence of states.
        
        Returns a list of percentages indicating progress through subgoals.
        """
        progress = []
        
        for state in states:
            # Count matched subgoals
            matched = sum(1 for sg in self.subgoals if sg.is_matched(state))
            progress_pct = (matched / len(self.subgoals)) * 100
            progress.append(progress_pct)
            
        return progress

@dataclass
class ToolAction:
    """Represents a tool action performed by an agent."""
    tool_name: str
    params: Dict[str, Any]
    is_valid: bool = True
    error_message: Optional[str] = None
    timestamp: Optional[float] = None

@dataclass
class GroundingMetrics:
    """Metrics for measuring grounding accuracy."""
    
    @staticmethod
    def calculate_valid_actions_percentage(actions: List[ToolAction]) -> float:
        """Calculate percentage of valid actions."""
        if not actions:
            return 0.0
            
        valid_actions = sum(1 for action in actions if action.is_valid)
        return (valid_actions / len(actions)) * 100
    
    @staticmethod
    def calculate_tool_usage_success(actions: List[ToolAction], expected_tools: Dict[str, int]) -> Dict[str, float]:
        """
        Calculate success rate of using the correct tools.
        
        Args:
            actions: List of tool actions performed
            expected_tools: Dict mapping tool names to expected usage count
            
        Returns:
            Dict with tool names and success percentages
        """
        results = {}
        actual_usage = {}
        
        # Count actual tool usage
        for action in actions:
            actual_usage[action.tool_name] = actual_usage.get(action.tool_name, 0) + 1
        
        # Calculate success rates
        for tool, expected_count in expected_tools.items():
            actual_count = actual_usage.get(tool, 0)
            if expected_count == 0:
                # Tool shouldn't be used
                success_rate = 100.0 if actual_count == 0 else 0.0
            else:
                # Calculate how close the actual usage is to expected
                success_rate = min(100.0, (actual_count / expected_count) * 100)
            
            results[tool] = success_rate
            
        return results
    
    @staticmethod
    def calculate_correct_input_rate(actions: List[ToolAction], required_params: Dict[str, List[str]]) -> Dict[str, float]:
        """
        Calculate success rate of passing correct inputs to tools.
        
        Args:
            actions: List of tool actions
            required_params: Dict mapping tool names to lists of required parameter names
            
        Returns:
            Dict with tool names and input correctness percentages
        """
        results = {}
        
        # Group actions by tool
        tool_actions = {}
        for action in actions:
            if action.tool_name not in tool_actions:
                tool_actions[action.tool_name] = []
            tool_actions[action.tool_name].append(action)
        
        # Calculate correctness for each tool
        for tool, tool_required_params in required_params.items():
            if tool not in tool_actions or not tool_actions[tool]:
                results[tool] = 0.0
                continue
                
            tool_result = 0.0
            for action in tool_actions[tool]:
                # Check if all required params are present
                params_present = all(param in action.params for param in tool_required_params)
                if params_present:
                    tool_result += 1
            
            # Average over all actions for this tool
            results[tool] = (tool_result / len(tool_actions[tool])) * 100
            
        return results

@dataclass
class MCPSpecificMetrics:
    """Metrics specific to MCP agent evaluation."""
    
    @staticmethod
    def evaluate_tool_adaptability(
        actions_before: List[ToolAction], 
        actions_after: List[ToolAction], 
        tool_changes: Dict[str, Dict[str, Any]]
    ) -> float:
        """
        Evaluate how well the agent adapts to changes in tool specifications.
        
        Args:
            actions_before: Actions before tool specification changes
            actions_after: Actions after tool specification changes
            tool_changes: Dict describing changes made to tools
            
        Returns:
            Adaptability score (0-100)
        """
        if not actions_after or not tool_changes:
            return 0.0
            
        adaptability_scores = []
        
        for tool_name, changes in tool_changes.items():
            # Find actions that use this tool after changes
            tool_actions = [a for a in actions_after if a.tool_name == tool_name]
            
            if not tool_actions:
                continue
                
            # Check if each action reflects the changes
            for action in tool_actions:
                score = 100.0
                
                # Check parameter changes
                if 'params_added' in changes:
                    for param in changes['params_added']:
                        if param not in action.params:
                            score *= 0.5  # Penalize missing new parameters
                
                if 'params_removed' in changes:
                    for param in changes['params_removed']:
                        if param in action.params:
                            score *= 0.5  # Penalize using removed parameters
                
                adaptability_scores.append(score)
        
        if not adaptability_scores:
            return 0.0
            
        return sum(adaptability_scores) / len(adaptability_scores)
    
    @staticmethod
    def evaluate_server_communication_success(
        actions: List[ToolAction],
        expected_server_interactions: Dict[str, int]
    ) -> Dict[str, float]:
        """
        Evaluate success rate of server communications.
        
        Args:
            actions: List of tool actions
            expected_server_interactions: Dict mapping server names to expected interaction counts
            
        Returns:
            Dict with server names and interaction success rates
        """
        results = {}
        actual_interactions = {}
        
        # Count actual server interactions
        for action in actions:
            # Assuming server name is encoded in the tool name or params
            # This is a simplification - adapt to your actual data structure
            server_name = action.params.get("server_name", "unknown")
            actual_interactions[server_name] = actual_interactions.get(server_name, 0) + 1
        
        # Calculate success rates
        for server, expected_count in expected_server_interactions.items():
            actual_count = actual_interactions.get(server, 0)
            if expected_count == 0:
                success_rate = 100.0 if actual_count == 0 else 0.0
            else:
                success_rate = min(100.0, (actual_count / expected_count) * 100)
            
            results[server] = success_rate
            
        return results

@dataclass
class TaskCompletionMetrics:
    """Metrics for measuring task completion success."""
    
    @staticmethod
    def calculate_success_rate(tasks: List[Task], final_states: Dict[str, str]) -> Dict[str, bool]:
        """
        Calculate success rate for completed tasks.
        
        Args:
            tasks: List of tasks
            final_states: Dict mapping task IDs to final states
            
        Returns:
            Dict mapping task IDs to completion status
        """
        results = {}
        
        for task in tasks:
            if task.id in final_states:
                results[task.id] = task.is_completed(final_states[task.id])
            else:
                results[task.id] = False
                
        return results
    
    @staticmethod
    def breakdown_by_difficulty(
        tasks: List[Task], 
        completion_results: Dict[str, bool]
    ) -> Dict[TaskDifficulty, float]:
        """
        Break down task completion success by difficulty level.
        
        Args:
            tasks: List of tasks
            completion_results: Dict mapping task IDs to completion status
            
        Returns:
            Dict mapping difficulty levels to success percentages
        """
        results = {diff: {'count': 0, 'success': 0} for diff in TaskDifficulty}
        
        # Count tasks and successes by difficulty
        for task in tasks:
            results[task.difficulty]['count'] += 1
            if task.id in completion_results and completion_results[task.id]:
                results[task.difficulty]['success'] += 1
        
        # Calculate percentages
        percentages = {}
        for diff, counts in results.items():
            if counts['count'] > 0:
                percentages[diff] = (counts['success'] / counts['count']) * 100
            else:
                percentages[diff] = 0.0
                
        return percentages
    
    @staticmethod
    def calculate_turn_efficiency(
        tasks: List[Task],
        turns_per_task: Dict[str, int],
        completion_results: Dict[str, bool]
    ) -> Dict[str, float]:
        """
        Calculate turn efficiency for each task.
        
        Args:
            tasks: List of tasks
            turns_per_task: Dict mapping task IDs to number of turns taken
            completion_results: Dict mapping task IDs to completion status
            
        Returns:
            Dict mapping task IDs to efficiency scores
        """
        results = {}
        
        for task in tasks:
            if task.id not in turns_per_task or task.id not in completion_results:
                continue
                
            # Efficiency is inversely proportional to turns taken
            # Only consider completed tasks for efficiency
            if completion_results[task.id]:
                # Simplified efficiency model - can be customized
                # Assuming a baseline of expected turns based on difficulty
                expected_turns = {
                    TaskDifficulty.EASY: 3,
                    TaskDifficulty.MEDIUM: 5,
                    TaskDifficulty.HARD: 8
                }
                
                baseline = expected_turns.get(task.difficulty, 5)
                actual_turns = turns_per_task[task.id]
                
                # Higher is better, capped at 100%
                efficiency = min(100.0, (baseline / actual_turns) * 100)
                results[task.id] = efficiency
            else:
                results[task.id] = 0.0
                
        return results

@dataclass
class Visualization:
    """Utilities for visualizing evaluation metrics."""
    
    @staticmethod
    def generate_progress_trajectory(
        task: Task, 
        states: List[str],
        timestamps: List[float]
    ) -> Dict[str, Any]:
        """
        Generate data for visualizing progress trajectory.
        
        Args:
            task: The task
            states: List of agent states
            timestamps: List of timestamps corresponding to states
            
        Returns:
            Dict with trajectory data for visualization
        """
        progress_rates = task.progress_rate(states)
        
        return {
            'task_id': task.id,
            'task_name': task.name,
            'difficulty': task.difficulty,
            'timestamps': timestamps,
            'progress_rates': progress_rates,
            'subgoals': [sg.id for sg in task.subgoals]
        }
    
    @staticmethod
    def export_visualization_data(data: Dict[str, Any], filename: str) -> None:
        """Export data for visualization to a JSON file."""
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)