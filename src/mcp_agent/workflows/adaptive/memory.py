"""
Memory management for Adaptive Workflow

This module provides:
1. Storage abstraction for different backends
2. Pattern tracking for adaptive learning
3. Simple, extensible design
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from collections import defaultdict
import json
from pathlib import Path

from mcp_agent.logging.logger import get_logger
from mcp_agent.workflows.adaptive.models import (
    ExecutionMemory,
    TaskType,
)

logger = get_logger(__name__)


class MemoryBackend(ABC):
    """Abstract base class for memory storage backends"""

    @abstractmethod
    async def save(self, execution_id: str, memory: ExecutionMemory) -> None:
        """Save execution memory"""
        pass

    @abstractmethod
    async def load(self, execution_id: str) -> Optional[ExecutionMemory]:
        """Load execution memory"""
        pass

    @abstractmethod
    async def delete(self, execution_id: str) -> None:
        """Delete execution memory"""
        pass

    @abstractmethod
    async def list_executions(self) -> Dict[str, Dict[str, Any]]:
        """List all executions with basic info"""
        pass

    @abstractmethod
    async def save_pattern(
        self, pattern_key: str, pattern_data: Dict[str, Any]
    ) -> None:
        """Save a learned pattern"""
        pass

    @abstractmethod
    async def load_patterns(self, pattern_type: str) -> Dict[str, Any]:
        """Load patterns of a specific type"""
        pass


class InMemoryBackend(MemoryBackend):
    """In-memory storage backend (default)"""

    def __init__(self):
        self._storage: Dict[str, ExecutionMemory] = {}
        self._patterns: Dict[str, Dict[str, Any]] = defaultdict(dict)

    async def save(self, execution_id: str, memory: ExecutionMemory) -> None:
        """Save execution memory in memory"""
        self._storage[execution_id] = memory.model_copy(deep=True)
        logger.debug(f"Saved execution {execution_id} to memory")

    async def load(self, execution_id: str) -> Optional[ExecutionMemory]:
        """Load execution memory from memory"""
        if execution_id in self._storage:
            return self._storage[execution_id].model_copy(deep=True)
        return None

    async def delete(self, execution_id: str) -> None:
        """Delete execution memory from memory"""
        if execution_id in self._storage:
            del self._storage[execution_id]
            logger.debug(f"Deleted execution {execution_id} from memory")

    async def list_executions(self) -> Dict[str, Dict[str, Any]]:
        """List all executions in memory"""
        executions = {}
        for execution_id, memory in self._storage.items():
            executions[execution_id] = {
                "objective": memory.objective,
                "task_type": memory.task_type.value if memory.task_type else None,
                "start_time": memory.start_time.isoformat(),
                "iterations": memory.iterations,
                "total_cost": memory.total_cost,
            }
        return executions

    async def save_pattern(
        self, pattern_key: str, pattern_data: Dict[str, Any]
    ) -> None:
        """Save a learned pattern"""
        pattern_type = pattern_key.split(":", 1)[0]
        self._patterns[pattern_type][pattern_key] = pattern_data

    async def load_patterns(self, pattern_type: str) -> Dict[str, Any]:
        """Load patterns of a specific type"""
        return dict(self._patterns.get(pattern_type, {}))


class FileSystemBackend(MemoryBackend):
    """File system storage backend for persistence"""

    def __init__(self, base_path: str = ".adaptive_memory"):
        self.base_path = Path(base_path)
        self.executions_path = self.base_path / "executions"
        self.patterns_path = self.base_path / "patterns"

        # Create directories
        self.executions_path.mkdir(parents=True, exist_ok=True)
        self.patterns_path.mkdir(parents=True, exist_ok=True)

    async def save(self, execution_id: str, memory: ExecutionMemory) -> None:
        """Save execution memory to file"""
        file_path = self.executions_path / f"{execution_id}.json"
        with open(file_path, "w") as f:
            json.dump(memory.model_dump(mode="json"), f, indent=2, default=str)
        logger.debug(f"Saved execution {execution_id} to {file_path}")

    async def load(self, execution_id: str) -> Optional[ExecutionMemory]:
        """Load execution memory from file"""
        file_path = self.executions_path / f"{execution_id}.json"
        if file_path.exists():
            try:
                with open(file_path, "r") as f:
                    data = json.load(f)
                return ExecutionMemory(**data)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to load execution {execution_id}: {e}")
                return None
        return None

    async def delete(self, execution_id: str) -> None:
        """Delete execution memory file"""
        file_path = self.executions_path / f"{execution_id}.json"
        if file_path.exists():
            file_path.unlink()
            logger.debug(f"Deleted execution {execution_id}")

    async def list_executions(self) -> Dict[str, Dict[str, Any]]:
        """List all executions from files"""
        executions = {}
        for file_path in self.executions_path.glob("*.json"):
            execution_id = file_path.stem
            try:
                memory = await self.load(execution_id)
                if memory:
                    executions[execution_id] = {
                        "objective": memory.objective,
                        "task_type": memory.task_type.value
                        if memory.task_type
                        else None,
                        "start_time": memory.start_time.isoformat(),
                        "iterations": memory.iterations,
                        "total_cost": memory.total_cost,
                    }
            except Exception as e:
                logger.warning(f"Failed to load execution {execution_id}: {e}")
        return executions

    async def save_pattern(
        self, pattern_key: str, pattern_data: Dict[str, Any]
    ) -> None:
        """Save a learned pattern to file"""
        pattern_type = pattern_key.split(":", 1)[0]
        file_path = self.patterns_path / f"{pattern_type}.json"

        # Load existing patterns
        patterns = {}
        if file_path.exists():
            with open(file_path, "r") as f:
                patterns = json.load(f)

        # Update with new pattern
        patterns[pattern_key] = pattern_data

        # Save back
        with open(file_path, "w") as f:
            json.dump(patterns, f, indent=2, default=str)

    async def load_patterns(self, pattern_type: str) -> Dict[str, Any]:
        """Load patterns from file"""
        file_path = self.patterns_path / f"{pattern_type}.json"
        if file_path.exists():
            with open(file_path, "r") as f:
                return json.load(f)
        return {}


class AdaptiveMemory:
    """
    Lightweight adaptive memory that learns from executions
    without rigid categorization or complex strategies
    """

    def __init__(self, backend: MemoryBackend):
        self.backend = backend
        # Simple in-memory cache for current session
        self.session_patterns = {
            "successful_approaches": defaultdict(list),
            "tool_effectiveness": defaultdict(lambda: defaultdict(float)),
            "failure_patterns": defaultdict(list),
        }

    async def learn_from_execution(self, memory: ExecutionMemory) -> None:
        """Learn patterns from a completed execution"""
        if not memory.task_type:
            return

        task_type = memory.task_type.value

        # Track successful approaches
        for i, synthesis in enumerate(memory.research_history):
            # Extract what worked from synthesis
            approach_key = f"{task_type}:iteration_{i}"

            # Find which subagent results contributed to this synthesis
            relevant_results = [
                r for r in memory.subagent_results if r.success and r.findings
            ]

            if relevant_results:
                pattern = {
                    "task_type": task_type,
                    "objective_snippet": memory.objective[:100],
                    "successful_aspects": [r.aspect_name for r in relevant_results],
                    "synthesis": synthesis[:500],  # First 500 chars
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

                self.session_patterns["successful_approaches"][task_type].append(
                    pattern
                )
                await self.backend.save_pattern(approach_key, pattern)

        # Track tool effectiveness
        for result in memory.subagent_results:
            if result.success and hasattr(result, "tools_used"):
                for tool in getattr(result, "tools_used", []):
                    self.session_patterns["tool_effectiveness"][task_type][tool] += 1

    async def suggest_approach(
        self, objective: str, task_type: Optional[TaskType] = None
    ) -> Optional[Dict[str, Any]]:
        """Suggest approach based on past successful patterns"""
        if not task_type:
            return None

        # Look for similar objectives in successful patterns
        task_patterns = self.session_patterns["successful_approaches"].get(
            task_type.value, []
        )

        if not task_patterns:
            # Try loading from backend
            stored_patterns = await self.backend.load_patterns(task_type.value)
            task_patterns = list(stored_patterns.values())

        if not task_patterns:
            return None

        # Simple similarity: find patterns with overlapping keywords
        objective_lower = objective.lower()
        objective_words = set(objective_lower.split())

        best_match = None
        best_score = 0

        for pattern in task_patterns:
            pattern_words = set(pattern["objective_snippet"].lower().split())
            overlap = len(objective_words & pattern_words)

            if overlap > best_score:
                best_score = overlap
                best_match = pattern

        if best_match and best_score > 2:  # At least 3 common words
            return {
                "suggested_aspects": best_match["successful_aspects"],
                "similar_objective": best_match["objective_snippet"],
                "confidence": min(best_score / len(objective_words), 1.0),
            }

        return None

    def get_effective_tools(self, task_type: TaskType) -> List[str]:
        """Get tools that have been effective for this task type"""
        tool_scores = self.session_patterns["tool_effectiveness"].get(
            task_type.value, {}
        )

        # Sort by effectiveness (usage count)
        sorted_tools = sorted(tool_scores.items(), key=lambda x: x[1], reverse=True)

        # Return top tools
        return [tool for tool, score in sorted_tools if score > 0]


class MemoryManager:
    """
    Memory manager for Adaptive Workflow V2
    Combines storage and adaptive learning
    """

    def __init__(
        self, backend: Optional[MemoryBackend] = None, enable_learning: bool = True
    ):
        """
        Initialize memory manager

        Args:
            backend: Storage backend to use (defaults to InMemoryBackend)
            enable_learning: Whether to enable adaptive learning
        """
        self.backend = backend or InMemoryBackend()
        self.enable_learning = enable_learning
        self.adaptive_memory = AdaptiveMemory(self.backend) if enable_learning else None

    async def save_memory(self, memory: ExecutionMemory) -> None:
        """Save execution memory and learn patterns"""
        await self.backend.save(memory.execution_id, memory)

        # Learn from this execution if enabled
        if self.enable_learning and self.adaptive_memory:
            await self.adaptive_memory.learn_from_execution(memory)

    async def load_memory(self, execution_id: str) -> Optional[ExecutionMemory]:
        """Load execution memory"""
        return await self.backend.load(execution_id)

    async def delete_memory(self, execution_id: str) -> None:
        """Delete execution memory"""
        await self.backend.delete(execution_id)

    async def list_executions(self) -> Dict[str, Dict[str, Any]]:
        """List all stored executions with basic info"""
        return await self.backend.list_executions()

    async def suggest_approach(
        self, objective: str, task_type: Optional[TaskType] = None
    ) -> Optional[Dict[str, Any]]:
        """Get suggestions based on past executions"""
        if self.adaptive_memory:
            return await self.adaptive_memory.suggest_approach(objective, task_type)
        return None

    def get_effective_tools(self, task_type: TaskType) -> List[str]:
        """Get tools that work well for this task type"""
        if self.adaptive_memory:
            return self.adaptive_memory.get_effective_tools(task_type)
        return []
