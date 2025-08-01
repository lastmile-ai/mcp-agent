"""
Tests for Adaptive Workflow V2 Memory Management
"""

import pytest
from datetime import datetime, timezone

from mcp_agent.workflows.adaptive.memory import (
    MemoryManager,
    InMemoryBackend,
    FileSystemBackend,
    AdaptiveMemory,
)
from mcp_agent.workflows.adaptive.models import (
    ExecutionMemory,
    TaskType,
    SubagentResult,
)


class TestInMemoryBackend:
    """Tests for in-memory storage backend"""

    @pytest.mark.asyncio
    async def test_save_and_load(self):
        """Test basic save and load operations"""
        backend = InMemoryBackend()

        memory = ExecutionMemory(
            execution_id="test-123",
            objective="Test objective",
            task_type=TaskType.RESEARCH,
            iterations=5,
            total_cost=10.0,
        )

        # Save
        await backend.save("test-123", memory)

        # Load
        loaded = await backend.load("test-123")
        assert loaded is not None
        assert loaded.execution_id == "test-123"
        assert loaded.iterations == 5

        # Load non-existent
        assert await backend.load("non-existent") is None

    @pytest.mark.asyncio
    async def test_delete(self):
        """Test deletion"""
        backend = InMemoryBackend()

        memory = ExecutionMemory(
            execution_id="test-456", objective="Test", task_type=TaskType.ACTION
        )

        await backend.save("test-456", memory)
        assert await backend.load("test-456") is not None

        await backend.delete("test-456")
        assert await backend.load("test-456") is None

    @pytest.mark.asyncio
    async def test_list_executions(self):
        """Test listing executions"""
        backend = InMemoryBackend()

        # Save multiple executions
        for i in range(3):
            memory = ExecutionMemory(
                execution_id=f"test-{i}",
                objective=f"Objective {i}",
                task_type=TaskType.RESEARCH,
                iterations=i,
            )
            await backend.save(f"test-{i}", memory)

        # List
        executions = await backend.list_executions()
        assert len(executions) == 3
        assert "test-0" in executions
        assert executions["test-1"]["iterations"] == 1

    @pytest.mark.asyncio
    async def test_pattern_storage(self):
        """Test pattern storage and retrieval"""
        backend = InMemoryBackend()

        # Save patterns
        pattern1 = {"approach": "web_search", "success": True}
        pattern2 = {"approach": "code_analysis", "success": False}

        await backend.save_pattern("research:pattern1", pattern1)
        await backend.save_pattern("research:pattern2", pattern2)
        await backend.save_pattern("action:pattern1", {"approach": "file_edit"})

        # Load patterns by type
        research_patterns = await backend.load_patterns("research")
        assert len(research_patterns) == 2
        assert "research:pattern1" in research_patterns

        action_patterns = await backend.load_patterns("action")
        assert len(action_patterns) == 1


class TestFileSystemBackend:
    """Tests for filesystem storage backend"""

    @pytest.mark.asyncio
    async def test_save_and_load(self, tmp_path):
        """Test basic save and load with filesystem"""
        backend = FileSystemBackend(str(tmp_path / "test_memory"))

        memory = ExecutionMemory(
            execution_id="fs-test-123",
            objective="Filesystem test",
            task_type=TaskType.HYBRID,
            start_time=datetime.now(timezone.utc),
        )

        # Save
        await backend.save("fs-test-123", memory)

        # Verify file exists
        file_path = tmp_path / "test_memory" / "executions" / "fs-test-123.json"
        assert file_path.exists()

        # Load
        loaded = await backend.load("fs-test-123")
        assert loaded is not None
        assert loaded.objective == "Filesystem test"

    @pytest.mark.asyncio
    async def test_persistence_across_instances(self, tmp_path):
        """Test that data persists across backend instances"""
        path = str(tmp_path / "persistent_memory")

        # First instance saves
        backend1 = FileSystemBackend(path)
        memory = ExecutionMemory(
            execution_id="persist-test",
            objective="Test persistence",
            task_type=TaskType.ACTION,
        )
        await backend1.save("persist-test", memory)

        # Second instance loads
        backend2 = FileSystemBackend(path)
        loaded = await backend2.load("persist-test")
        assert loaded is not None
        assert loaded.objective == "Test persistence"

    @pytest.mark.asyncio
    async def test_pattern_persistence(self, tmp_path):
        """Test pattern storage in filesystem"""
        backend = FileSystemBackend(str(tmp_path / "pattern_test"))

        # Save patterns
        patterns = {
            "pattern1": {"success": True, "tools": ["web_search"]},
            "pattern2": {"success": False, "error": "timeout"},
        }

        for key, data in patterns.items():
            await backend.save_pattern(f"research:{key}", data)

        # Load patterns
        loaded = await backend.load_patterns("research")
        assert len(loaded) == 2
        assert loaded["research:pattern1"]["success"] is True

    @pytest.mark.asyncio
    async def test_corrupted_file_handling(self, tmp_path):
        """Test handling of corrupted JSON files"""
        backend = FileSystemBackend(str(tmp_path / "corrupt_test"))

        # Create corrupted file
        executions_path = tmp_path / "corrupt_test" / "executions"
        executions_path.mkdir(parents=True, exist_ok=True)

        corrupt_file = executions_path / "corrupt.json"
        corrupt_file.write_text("{ invalid json }")

        # Should handle gracefully
        loaded = await backend.load("corrupt")
        assert loaded is None

        # List should skip corrupted files
        executions = await backend.list_executions()
        assert "corrupt" not in executions


class TestAdaptiveMemory:
    """Tests for adaptive learning functionality"""

    @pytest.mark.asyncio
    async def test_learn_from_execution(self):
        """Test learning from successful execution"""
        backend = InMemoryBackend()
        adaptive = AdaptiveMemory(backend)

        # Create execution with results
        memory = ExecutionMemory(
            execution_id="learn-test",
            objective="Research AI applications in healthcare",
            task_type=TaskType.RESEARCH,
            research_history=[
                ["Found medical AI uses"],
                ["Identified key applications"],
            ],
            subagent_results=[
                SubagentResult(
                    aspect_name="Medical Imaging",
                    findings="AI used for diagnosis",
                    success=True,
                    start_time=datetime.now(timezone.utc),
                ),
                SubagentResult(
                    aspect_name="Drug Discovery",
                    findings="AI accelerates research",
                    success=True,
                    start_time=datetime.now(timezone.utc),
                ),
            ],
        )

        # Learn from execution
        await adaptive.learn_from_execution(memory)

        # Check session patterns
        research_patterns = adaptive.session_patterns["successful_approaches"][
            "research"
        ]
        assert len(research_patterns) == 2  # One for each iteration

    @pytest.mark.asyncio
    async def test_suggest_approach_with_similarity(self):
        """Test approach suggestion based on similarity"""
        backend = InMemoryBackend()
        adaptive = AdaptiveMemory(backend)

        # Add some patterns
        adaptive.session_patterns["successful_approaches"]["research"] = [
            {
                "task_type": "research",
                "objective_snippet": "Research quantum computing applications",
                "successful_aspects": ["Quantum algorithms", "Hardware"],
                "synthesis": "Found key applications",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            {
                "task_type": "research",
                "objective_snippet": "Analyze machine learning frameworks",
                "successful_aspects": ["TensorFlow", "PyTorch"],
                "synthesis": "Compared frameworks",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        ]

        # Test similar objective
        suggestion = await adaptive.suggest_approach(
            "Research quantum computing algorithms", TaskType.RESEARCH
        )

        assert suggestion is not None
        assert "Quantum algorithms" in suggestion["suggested_aspects"]
        assert suggestion["confidence"] > 0

        # Test dissimilar objective
        suggestion = await adaptive.suggest_approach(
            "Fix the bug in the code", TaskType.RESEARCH
        )

        # Should not find good match
        assert suggestion is None or suggestion["confidence"] < 0.3

    def test_get_effective_tools(self):
        """Test getting effective tools for task type"""
        backend = InMemoryBackend()
        adaptive = AdaptiveMemory(backend)

        # Add tool effectiveness data
        adaptive.session_patterns["tool_effectiveness"]["research"] = {
            "web_search": 5,
            "filesystem": 2,
            "database": 1,
        }

        effective_tools = adaptive.get_effective_tools(TaskType.RESEARCH)

        # Should be sorted by effectiveness
        assert effective_tools[0] == "web_search"
        assert effective_tools[1] == "filesystem"
        assert len(effective_tools) == 3


class TestMemoryManager:
    """Tests for the main MemoryManager class"""

    @pytest.mark.asyncio
    async def test_memory_manager_with_learning(self):
        """Test memory manager with learning enabled"""
        manager = MemoryManager(enable_learning=True)

        # Create and save memory
        memory = ExecutionMemory(
            execution_id="mgr-test",
            objective="Test learning integration",
            task_type=TaskType.ACTION,
            subagent_results=[
                SubagentResult(
                    aspect_name="File Edit",
                    findings="Successfully edited",
                    success=True,
                    start_time=datetime.now(timezone.utc),
                )
            ],
        )

        await manager.save_memory(memory)

        # Should trigger learning
        suggestion = await manager.suggest_approach(
            "Edit another file", TaskType.ACTION
        )

        # May or may not have suggestions depending on similarity
        assert suggestion is None or isinstance(suggestion, dict)

    @pytest.mark.asyncio
    async def test_memory_manager_without_learning(self):
        """Test memory manager with learning disabled"""
        manager = MemoryManager(enable_learning=False)

        memory = ExecutionMemory(
            execution_id="no-learn",
            objective="Test without learning",
            task_type=TaskType.RESEARCH,
        )

        await manager.save_memory(memory)

        # Should not have learning capabilities
        suggestion = await manager.suggest_approach("Any objective", TaskType.RESEARCH)
        assert suggestion is None

        tools = manager.get_effective_tools(TaskType.RESEARCH)
        assert tools == []

    @pytest.mark.asyncio
    async def test_list_executions_through_manager(self):
        """Test listing executions through manager"""
        manager = MemoryManager()

        # Save multiple executions
        for i in range(3):
            memory = ExecutionMemory(
                execution_id=f"list-{i}",
                objective=f"Objective {i}",
                task_type=TaskType.RESEARCH,
                total_cost=i * 1.5,
            )
            await manager.save_memory(memory)

        # List executions
        executions = await manager.list_executions()

        assert len(executions) == 3
        assert executions["list-1"]["total_cost"] == 1.5
        assert all(
            exec_data["task_type"] == "research" for exec_data in executions.values()
        )
