"""
Visualization utilities for MCP Agent evaluation results.
"""

import os
import json
import glob
from typing import Dict, List, Any, Optional
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from matplotlib.colors import LinearSegmentedColormap

def load_evaluation_results(results_dir: str, scenario: Optional[str] = None) -> Dict[str, Any]:
    """
    Load the latest evaluation results.
    
    Args:
        results_dir: Directory containing evaluation results
        scenario: Optional scenario name to filter results
        
    Returns:
        Dict containing evaluation results
    """
    # Define the pattern to search for
    if scenario:
        pattern = os.path.join(results_dir, f"{scenario}_evaluation_*.json")
    else:
        pattern = os.path.join(results_dir, "*_evaluation_*.json")
    
    # Find all matching files
    eval_files = glob.glob(pattern)
    if not eval_files:
        raise FileNotFoundError(f"No evaluation results found matching: {pattern}")
    
    # Sort by modification time to get latest
    latest_file = max(eval_files, key=os.path.getmtime)
    
    with open(latest_file, 'r') as f:
        return json.load(f)

def load_trajectory_data(results_dir: str, task_id: str) -> Dict[str, Any]:
    """
    Load trajectory data for a specific task.
    
    Args:
        results_dir: Directory containing visualization data
        task_id: Task ID to load trajectory for
        
    Returns:
        Dict containing trajectory data
    """
    viz_dir = os.path.join(results_dir, "visualizations")
    trajectory_files = glob.glob(os.path.join(viz_dir, f"{task_id}_trajectory.json"))
    
    if not trajectory_files:
        raise FileNotFoundError(f"No trajectory data found for task {task_id}")
    
    # Sort by modification time to get latest
    latest_file = max(trajectory_files, key=os.path.getmtime)
    
    with open(latest_file, 'r') as f:
        return json.load(f)

def plot_progress_trajectories(results_dir: str, output_file: str) -> None:
    """
    Plot progress trajectories for all tasks.
    
    Args:
        results_dir: Directory containing evaluation results
        output_file: Path to save the plot
    """
    results = load_evaluation_results(results_dir)
    
    fig, ax = plt.subplots(figsize=(12, 8))
    
    for task_id, task_data in results["tasks"].items():
        try:
            trajectory_data = load_trajectory_data(results_dir, task_id)
            
            # Calculate relative timestamps
            timestamps = trajectory_data.get("timestamps", [])
            if timestamps:
                timestamps = [float(t) - float(timestamps[0]) for t in timestamps]
            
            progress_rates = trajectory_data.get("progress_rates", [])
            
            # Convert progress rates from string if needed
            progress_rates = [float(p) if isinstance(p, str) else p for p in progress_rates]
            
            # Plot the trajectory
            ax.plot(
                timestamps, 
                progress_rates, 
                marker='o', 
                label=f"{task_data['name']} ({task_id})"
            )
        except (FileNotFoundError, KeyError) as e:
            print(f"Error loading trajectory data for task {task_id}: {e}")
            continue
    
    ax.set_xlabel("Time (seconds)")
    ax.set_ylabel("Progress Rate (%)")
    ax.set_title(f"{results.get('scenario', 'Scenario')} Task Progress Trajectories")
    ax.legend()
    ax.grid(True)
    
    # Save the figure
    plt.tight_layout()
    plt.savefig(output_file, dpi=300)
    plt.close()

def plot_difficulty_breakdown(results_dir: str, output_file: str) -> None:
    """
    Plot task success rates broken down by difficulty.
    
    Args:
        results_dir: Directory containing evaluation results
        output_file: Path to save the plot
    """
    results = load_evaluation_results(results_dir)
    
    difficulty_breakdown = results["overall"].get("difficulty_breakdown", {})
    
    difficulties = list(difficulty_breakdown.keys())
    rates = [float(difficulty_breakdown[d]) for d in difficulties]
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Set colors based on difficulty
    bar_colors = []
    for d in difficulties:
        if "easy" in d.lower():
            bar_colors.append('green')
        elif "medium" in d.lower():
            bar_colors.append('blue')
        else:
            bar_colors.append('orange')
    
    ax.bar(difficulties, rates, color=bar_colors)
    ax.set_xlabel("Task Difficulty")
    ax.set_ylabel("Success Rate (%)")
    ax.set_title(f"{results.get('scenario', 'Scenario')} Success Rates by Difficulty")
    ax.set_ylim(0, 100)
    
    # Add data labels
    for i, v in enumerate(rates):
        ax.text(i, v + 3, f"{v:.1f}%", ha='center')
    
    plt.tight_layout()
    plt.savefig(output_file, dpi=300)
    plt.close()

def plot_subgoal_heatmap(results_dir: str, output_file: str) -> None:
    """
    Plot a heatmap showing subgoal completion across tasks.
    
    Args:
        results_dir: Directory containing evaluation results
        output_file: Path to save the plot
    """
    results = load_evaluation_results(results_dir)
    
    # Prepare data for heatmap
    tasks = []
    subgoals = set()
    task_subgoal_data = {}
    
    # Extract task and subgoal data
    for task_id, task_data in results["tasks"].items():
        try:
            trajectory_data = load_trajectory_data(results_dir, task_id)
            sg_list = trajectory_data.get("subgoals", [])
            
            # Add to set of all subgoals
            subgoals.update(sg_list)
            
            # Get the task name for better display
            task_name = task_data["name"]
            tasks.append(task_name)
            
            # Extract subgoal completion data
            # For simplicity, we'll use the subgoal match rate to estimate individual subgoal completion
            # In a real implementation, you would track each subgoal's completion separately
            sg_match_rate = float(task_data["subgoal_match_rate"]) / 100.0
            task_subgoal_data[task_name] = {sg: sg_match_rate for sg in sg_list}
            
        except (FileNotFoundError, KeyError) as e:
            print(f"Error processing subgoal data for task {task_id}: {e}")
            continue
    
    if not task_subgoal_data:
        print("No subgoal data available for heatmap")
        return
    
    # Convert to sorted lists for consistent ordering
    tasks = sorted(tasks)
    subgoals = sorted(list(subgoals))
    
    # Create the heatmap matrix
    matrix = np.zeros((len(tasks), len(subgoals)))
    for i, task in enumerate(tasks):
        for j, sg in enumerate(subgoals):
            matrix[i, j] = task_subgoal_data.get(task, {}).get(sg, 0.0)
    
    # Create the heatmap
    fig, ax = plt.subplots(figsize=(max(12, len(subgoals)), max(8, len(tasks))))
    
    # Create the heatmap with appropriate size
    sns.heatmap(
        matrix, 
        annot=True, 
        fmt=".2f", 
        cmap="YlGnBu", 
        xticklabels=subgoals, 
        yticklabels=tasks
    )
    
    ax.set_title(f"{results.get('scenario', 'Scenario')} Subgoal Completion Heatmap")
    plt.tight_layout()
    plt.savefig(output_file, dpi=300)
    plt.close()

def plot_turn_efficiency(results_dir: str, output_file: str) -> None:
    """
    Plot turn efficiency for each task.
    
    Args:
        results_dir: Directory containing evaluation results
        output_file: Path to save the plot
    """
    results = load_evaluation_results(results_dir)
    
    turn_efficiency = results["overall"].get("turn_efficiency", {})
    
    if not turn_efficiency:
        print("No turn efficiency data available")
        return
    
    # Get task names instead of IDs for better display
    task_names = {}
    for task_id, task_data in results["tasks"].items():
        task_names[task_id] = task_data["name"]
    
    task_ids = list(turn_efficiency.keys())
    names = [task_names.get(tid, tid) for tid in task_ids]
    efficiency_values = [float(turn_efficiency[tid]) for tid in task_ids]
    
    # Sort by efficiency
    sorted_indices = np.argsort(efficiency_values)
    sorted_names = [names[i] for i in sorted_indices]
    sorted_values = [efficiency_values[i] for i in sorted_indices]
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Plot horizontal bar chart
    bars = ax.barh(sorted_names, sorted_values, color='purple')
    
    ax.set_xlabel("Turn Efficiency (%)")
    ax.set_title(f"{results.get('scenario', 'Scenario')} Task Turn Efficiency")
    ax.set_xlim(0, 100)
    
    # Add data labels
    for i, bar in enumerate(bars):
        width = bar.get_width()
        ax.text(width + 2, bar.get_y() + bar.get_height()/2, f"{sorted_values[i]:.1f}%", va='center')
    
    plt.tight_layout()
    plt.savefig(output_file, dpi=300)
    plt.close()

def generate_visualizations(results_dir: str, output_dir: Optional[str] = None):
    """
    Generate all visualizations for evaluation results.
    
    Args:
        results_dir: Directory containing evaluation results
        output_dir: Directory to save visualizations (defaults to results_dir/visualizations)
    """
    # Set default output directory if not specified
    if output_dir is None:
        output_dir = os.path.join(results_dir, "visualizations")
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        # Load evaluation results to get scenario name
        results = load_evaluation_results(results_dir)
        scenario = results.get("scenario", "scenario")
        
        print(f"Generating visualizations for {scenario} evaluation...")
        
        # Generate various visualizations
        plot_progress_trajectories(
            results_dir, 
            os.path.join(output_dir, f"{scenario}_progress_trajectories.png")
        )
        
        plot_difficulty_breakdown(
            results_dir, 
            os.path.join(output_dir, f"{scenario}_difficulty_breakdown.png")
        )
        
        plot_subgoal_heatmap(
            results_dir, 
            os.path.join(output_dir, f"{scenario}_subgoal_heatmap.png")
        )
        
        plot_turn_efficiency(
            results_dir, 
            os.path.join(output_dir, f"{scenario}_turn_efficiency.png")
        )
        
        print(f"Visualizations saved to: {output_dir}")
        
    except Exception as e:
        print(f"Error generating visualizations: {e}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate visualizations for evaluation results")
    parser.add_argument(
        "--results-dir", 
        type=str, 
        default="./results",
        help="Directory containing evaluation results"
    )
    parser.add_argument(
        "--output-dir", 
        type=str, 
        default=None,
        help="Directory to save visualizations (defaults to results_dir/visualizations)"
    )
    
    args = parser.parse_args()
    
    generate_visualizations(args.results_dir, args.output_dir)