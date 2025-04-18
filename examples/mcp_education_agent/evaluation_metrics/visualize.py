"""
Visualization utilities for MCP Education Agent evaluation results.
"""

import os
import json
import glob
from typing import Dict, List, Any, Optional
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from matplotlib.colors import LinearSegmentedColormap

# Directory to store evaluation results
EVAL_RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
VISUALIZATIONS_DIR = os.path.join(EVAL_RESULTS_DIR, "visualizations")
os.makedirs(VISUALIZATIONS_DIR, exist_ok=True)


def load_latest_evaluation() -> Dict[str, Any]:
    """Load the latest evaluation results."""
    eval_files = glob.glob(os.path.join(EVAL_RESULTS_DIR, "evaluation_*.json"))
    if not eval_files:
        raise FileNotFoundError("No evaluation results found")
    
    # Sort by modification time to get latest
    latest_file = max(eval_files, key=os.path.getmtime)
    
    with open(latest_file, 'r') as f:
        return json.load(f)


def load_trajectory_data(task_id: str) -> Dict[str, Any]:
    """Load trajectory data for a specific task."""
    trajectory_files = glob.glob(os.path.join(EVAL_RESULTS_DIR, f"{task_id}_trajectory.json"))
    if not trajectory_files:
        raise FileNotFoundError(f"No trajectory data found for task {task_id}")
    
    # Sort by modification time to get latest
    latest_file = max(trajectory_files, key=os.path.getmtime)
    
    with open(latest_file, 'r') as f:
        return json.load(f)


def plot_progress_trajectories() -> None:
    """Plot progress trajectories for all tasks."""
    results = load_latest_evaluation()
    
    fig, ax = plt.subplots(figsize=(12, 8))
    
    for task_id, task_data in results["tasks"].items():
        try:
            trajectory_data = load_trajectory_data(task_id)
            
            # Calculate relative timestamps
            timestamps = trajectory_data.get("timestamps", [])
            if timestamps:
                timestamps = [t - timestamps[0] for t in timestamps]
            
            progress_rates = trajectory_data.get("progress_rates", [])
            
            # Plot the trajectory
            ax.plot(
                timestamps, 
                progress_rates, 
                marker='o', 
                label=f"{task_data['name']} ({task_id})"
            )
        except FileNotFoundError:
            continue
    
    ax.set_xlabel("Time (seconds)")
    ax.set_ylabel("Progress Rate (%)")
    ax.set_title("Task Progress Trajectories")
    ax.legend()
    ax.grid(True)
    
    # Save the figure
    plt.tight_layout()
    plt.savefig(os.path.join(VISUALIZATIONS_DIR, "progress_trajectories.png"), dpi=300)
    plt.close()


def plot_difficulty_breakdown() -> None:
    """Plot task success rates broken down by difficulty."""
    results = load_latest_evaluation()
    
    difficulty_breakdown = results["overall"].get("difficulty_breakdown", {})
    
    difficulties = list(difficulty_breakdown.keys())
    rates = list(difficulty_breakdown.values())
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    bar_colors = ['green' if d.lower() == 'easy' else 'orange' for d in difficulties]
    
    ax.bar(difficulties, rates, color=bar_colors)
    ax.set_xlabel("Task Difficulty")
    ax.set_ylabel("Success Rate (%)")
    ax.set_title("Task Success Rates by Difficulty")
    ax.set_ylim(0, 100)
    
    # Add data labels
    for i, v in enumerate(rates):
        ax.text(i, v + 3, f"{v:.1f}%", ha='center')
    
    plt.tight_layout()
    plt.savefig(os.path.join(VISUALIZATIONS_DIR, "difficulty_breakdown.png"), dpi=300)
    plt.close()


def plot_subgoal_heatmap() -> None:
    """Plot a heatmap showing subgoal completion across tasks."""
    results = load_latest_evaluation()
    
    subgoal_data = {}
    
    # Collect subgoal matching data for each task
    for task_id, task_data in results["tasks"].items():
        try:
            trajectory_data = load_trajectory_data(task_id)
            subgoals = trajectory_data.get("subgoals", [])
            final_state = results["tasks"][task_id].get("final_state", "")
            
            # Check which subgoals were matched
            matched_subgoals = {}
            for sg_id in subgoals:
                # This is a simplification - in reality would need task's subgoal objects
                matched_subgoals[sg_id] = 1.0 if sg_id in final_state else 0.0
            
            subgoal_data[task_data["name"]] = matched_subgoals
        except FileNotFoundError:
            continue
    
    if not subgoal_data:
        print("No subgoal data available for heatmap")
        return
    
    # Create a matrix for the heatmap
    task_names = list(subgoal_data.keys())
    all_subgoals = set()
    for matched in subgoal_data.values():
        all_subgoals.update(matched.keys())
    all_subgoals = sorted(list(all_subgoals))
    
    # Create the matrix
    matrix = np.zeros((len(task_names), len(all_subgoals)))
    for i, task in enumerate(task_names):
        for j, sg in enumerate(all_subgoals):
            matrix[i, j] = subgoal_data[task].get(sg, 0.0)
    
    # Create the heatmap
    fig, ax = plt.subplots(figsize=(12, 8))
    sns.heatmap(
        matrix, 
        annot=True, 
        fmt=".1f", 
        cmap="YlGnBu", 
        xticklabels=all_subgoals, 
        yticklabels=task_names
    )
    
    ax.set_title("Subgoal Completion Heatmap")
    plt.tight_layout()
    plt.savefig(os.path.join(VISUALIZATIONS_DIR, "subgoal_heatmap.png"), dpi=300)
    plt.close()


def plot_task_completion_times() -> None:
    """Plot the completion times for each task."""
    results = load_latest_evaluation()
    
    task_names = []
    completion_times = []
    difficulties = []
    
    for task_id, task_data in results["tasks"].items():
        task_names.append(task_data["name"])
        completion_times.append(task_data["completion_time"])
        difficulties.append(task_data["difficulty"])
    
    # Set up colormap for different difficulties
    colors = ['green' if d.lower() == 'easy' else 'orange' for d in difficulties]
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Sort by completion time
    sorted_indices = np.argsort(completion_times)
    sorted_names = [task_names[i] for i in sorted_indices]
    sorted_times = [completion_times[i] for i in sorted_indices]
    sorted_colors = [colors[i] for i in sorted_indices]
    
    ax.barh(sorted_names, sorted_times, color=sorted_colors)
    ax.set_xlabel("Completion Time (seconds)")
    ax.set_title("Task Completion Times")
    
    # Add a legend for difficulties
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='green', label='Easy'),
        Patch(facecolor='orange', label='Hard')
    ]
    ax.legend(handles=legend_elements)
    
    plt.tight_layout()
    plt.savefig(os.path.join(VISUALIZATIONS_DIR, "completion_times.png"), dpi=300)
    plt.close()


def generate_all_visualizations() -> None:
    """Generate all visualizations."""
    try:
        print("Generating progress trajectory visualization...")
        plot_progress_trajectories()
        
        print("Generating difficulty breakdown visualization...")
        plot_difficulty_breakdown()
        
        print("Generating subgoal heatmap visualization...")
        plot_subgoal_heatmap()
        
        print("Generating task completion times visualization...")
        plot_task_completion_times()
        
        print(f"All visualizations saved to {VISUALIZATIONS_DIR}")
    except Exception as e:
        print(f"Error generating visualizations: {e}")


if __name__ == "__main__":
    generate_all_visualizations()