"""
Comprehensive tests for TodoQueue with plan merging and queue operations.
"""

from mcp_agent.workflows.deep_orchestrator.queue import TodoQueue
from mcp_agent.workflows.deep_orchestrator.models import Plan, Step, Task


class TestTodoQueueBasics:
    """Basic TodoQueue functionality tests"""

    def test_init(self):
        """Test TodoQueue initialization"""
        queue = TodoQueue()

        assert queue.pending_steps == []
        assert queue.completed_steps == []
        assert queue.all_tasks == {}
        assert queue.completed_task_names == set()
        assert queue.failed_task_names == {}
        assert queue.seen_step_descriptions == set()
        assert queue.seen_task_hashes == set()
        assert queue.is_empty()

    def test_load_simple_plan(self):
        """Test loading a simple plan"""
        queue = TodoQueue()

        plan = Plan(
            steps=[
                Step(
                    description="Step 1",
                    tasks=[
                        Task(name="task1", description="Task 1"),
                        Task(name="task2", description="Task 2"),
                    ],
                ),
                Step(
                    description="Step 2",
                    tasks=[
                        Task(name="task3", description="Task 3"),
                    ],
                ),
            ],
            reasoning="Test plan",
            is_complete=False,
        )

        queue.load_plan(plan)

        assert len(queue.pending_steps) == 2
        assert len(queue.all_tasks) == 3
        assert "task1" in queue.all_tasks
        assert "task2" in queue.all_tasks
        assert "task3" in queue.all_tasks
        assert not queue.is_empty()

    def test_get_next_step(self):
        """Test getting the next step from queue"""
        queue = TodoQueue()

        step1 = Step(
            description="First step", tasks=[Task(name="task1", description="Task 1")]
        )
        step2 = Step(
            description="Second step", tasks=[Task(name="task2", description="Task 2")]
        )

        plan = Plan(steps=[step1, step2], reasoning="Test", is_complete=False)
        queue.load_plan(plan)

        next_step = queue.get_next_step()
        assert next_step is not None
        assert next_step.description == "First step"

        # Getting next step doesn't remove it
        next_step_again = queue.get_next_step()
        assert next_step_again is not None
        assert next_step_again.description == "First step"

    def test_complete_step(self):
        """Test completing a step"""
        queue = TodoQueue()

        task1 = Task(name="task1", description="Task 1")
        task2 = Task(name="task2", description="Task 2")
        step = Step(description="Test step", tasks=[task1, task2])

        plan = Plan(steps=[step], reasoning="Test", is_complete=False)
        queue.load_plan(plan)

        # Mark tasks as completed
        task1.status = "completed"
        task2.status = "completed"

        # Complete the step
        queue.complete_step(step)

        assert len(queue.pending_steps) == 0
        assert len(queue.completed_steps) == 1
        assert queue.completed_steps[0] == step
        assert step.completed is True
        assert "task1" in queue.completed_task_names
        assert "task2" in queue.completed_task_names
        assert queue.is_empty()

    def test_mark_task_failed(self):
        """Test marking tasks as failed"""
        queue = TodoQueue()

        queue.mark_task_failed("task1")
        assert queue.failed_task_names["task1"] == 1

        queue.mark_task_failed("task1")
        assert queue.failed_task_names["task1"] == 2

        queue.mark_task_failed("task2")
        assert queue.failed_task_names["task2"] == 1


class TestPlanMerging:
    """Tests for plan merging functionality"""

    def test_merge_new_steps(self):
        """Test merging a plan with completely new steps"""
        queue = TodoQueue()

        # Load initial plan
        initial_plan = Plan(
            steps=[
                Step(
                    description="Initial step",
                    tasks=[Task(name="task1", description="Task 1")],
                )
            ],
            reasoning="Initial",
            is_complete=False,
        )
        queue.load_plan(initial_plan)

        # Merge new plan with different steps
        new_plan = Plan(
            steps=[
                Step(
                    description="New step 1",
                    tasks=[Task(name="task2", description="Task 2")],
                ),
                Step(
                    description="New step 2",
                    tasks=[Task(name="task3", description="Task 3")],
                ),
            ],
            reasoning="Additional work",
            is_complete=False,
        )

        added = queue.merge_plan(new_plan)

        assert added == 2
        assert len(queue.pending_steps) == 3
        assert len(queue.all_tasks) == 3

    def test_merge_duplicate_steps(self):
        """Test that duplicate steps are not added"""
        queue = TodoQueue()

        # Load initial plan
        initial_plan = Plan(
            steps=[
                Step(
                    description="Step 1",
                    tasks=[Task(name="task1", description="Task 1")],
                ),
                Step(
                    description="Step 2",
                    tasks=[Task(name="task2", description="Task 2")],
                ),
            ],
            reasoning="Initial",
            is_complete=False,
        )
        queue.load_plan(initial_plan)

        # Try to merge plan with duplicate steps
        duplicate_plan = Plan(
            steps=[
                Step(
                    description="Step 1",  # Duplicate
                    tasks=[Task(name="task3", description="Task 3")],
                ),
                Step(
                    description="Step 3",  # New
                    tasks=[Task(name="task4", description="Task 4")],
                ),
            ],
            reasoning="Duplicate attempt",
            is_complete=False,
        )

        added = queue.merge_plan(duplicate_plan)

        assert added == 1  # Only "Step 3" should be added
        assert len(queue.pending_steps) == 3
        assert queue.pending_steps[-1].description == "Step 3"

    def test_merge_with_completed_steps(self):
        """Test merging when some steps are already completed"""
        queue = TodoQueue()

        # Load and complete initial step
        step1 = Step(
            description="Completed step",
            tasks=[Task(name="task1", description="Task 1")],
        )
        initial_plan = Plan(steps=[step1], reasoning="Initial", is_complete=False)
        queue.load_plan(initial_plan)

        # Complete the step
        step1.tasks[0].status = "completed"
        queue.complete_step(step1)

        # Merge new plan
        new_plan = Plan(
            steps=[
                Step(
                    description="Completed step",  # Already done
                    tasks=[Task(name="task2", description="Task 2")],
                ),
                Step(
                    description="New step",
                    tasks=[Task(name="task3", description="Task 3")],
                ),
            ],
            reasoning="More work",
            is_complete=False,
        )

        added = queue.merge_plan(new_plan)

        assert added == 1  # Only "New step" should be added
        assert len(queue.pending_steps) == 1
        assert len(queue.completed_steps) == 1

    def test_merge_empty_plan(self):
        """Test merging an empty plan"""
        queue = TodoQueue()

        # Load initial plan
        initial_plan = Plan(
            steps=[
                Step(
                    description="Step 1",
                    tasks=[Task(name="task1", description="Task 1")],
                )
            ],
            reasoning="Initial",
            is_complete=False,
        )
        queue.load_plan(initial_plan)

        # Merge empty plan
        empty_plan = Plan(steps=[], reasoning="Empty", is_complete=False)
        added = queue.merge_plan(empty_plan)

        assert added == 0
        assert len(queue.pending_steps) == 1


class TestTaskDeduplication:
    """Tests for task deduplication within steps"""

    def test_deduplicate_tasks_in_step(self):
        """Test that duplicate tasks within a step are filtered"""
        queue = TodoQueue()

        # Create step with duplicate tasks (same hash)
        task1 = Task(name="task1", description="Do something", agent="agent1")
        task2 = Task(
            name="task2", description="Do something", agent="agent1"
        )  # Same description and agent
        task3 = Task(name="task3", description="Do something else", agent="agent1")

        step = Step(description="Step with duplicates", tasks=[task1, task2, task3])

        plan = Plan(steps=[step], reasoning="Test", is_complete=False)
        queue.load_plan(plan)

        # Only unique tasks should be added
        assert (
            len(queue.all_tasks) == 2
        )  # task1 and task3 (task2 is duplicate of task1)
        assert "task1" in queue.all_tasks
        assert "task3" in queue.all_tasks
        assert "task2" not in queue.all_tasks

    def test_deduplicate_tasks_across_steps(self):
        """Test that duplicate tasks across different steps are filtered"""
        queue = TodoQueue()

        # Create two steps with some overlapping tasks
        step1 = Step(
            description="Step 1",
            tasks=[
                Task(name="task1", description="Research", agent="researcher"),
                Task(name="task2", description="Analyze", agent="analyst"),
            ],
        )

        step2 = Step(
            description="Step 2",
            tasks=[
                Task(
                    name="task3", description="Research", agent="researcher"
                ),  # Duplicate of task1
                Task(name="task4", description="Report", agent="writer"),
            ],
        )

        plan = Plan(steps=[step1, step2], reasoning="Test", is_complete=False)
        queue.load_plan(plan)

        # task3 should be filtered out as duplicate
        assert len(queue.all_tasks) == 3  # task1, task2, task4
        assert "task1" in queue.all_tasks
        assert "task2" in queue.all_tasks
        assert "task4" in queue.all_tasks
        assert "task3" not in queue.all_tasks


class TestQueueOperations:
    """Tests for queue operations and state management"""

    def test_clear_queue(self):
        """Test clearing the queue"""
        queue = TodoQueue()

        # Load a plan
        plan = Plan(
            steps=[
                Step(
                    description="Step 1",
                    tasks=[Task(name="task1", description="Task 1")],
                )
            ],
            reasoning="Test",
            is_complete=False,
        )
        queue.load_plan(plan)
        queue.mark_task_failed("task1")

        # Clear the queue
        queue.clear()

        assert queue.pending_steps == []
        assert queue.completed_steps == []
        assert queue.all_tasks == {}
        assert queue.completed_task_names == set()
        assert queue.failed_task_names == {}
        assert queue.seen_step_descriptions == set()
        assert queue.seen_task_hashes == set()
        assert queue.is_empty()

    def test_get_task_by_name(self):
        """Test retrieving tasks by name"""
        queue = TodoQueue()

        task = Task(name="test_task", description="Test task", agent="agent1")
        step = Step(description="Step", tasks=[task])
        plan = Plan(steps=[step], reasoning="Test", is_complete=False)

        queue.load_plan(plan)

        retrieved_task = queue.get_task_by_name("test_task")
        assert retrieved_task is not None
        assert retrieved_task.name == "test_task"
        assert retrieved_task.description == "Test task"

        non_existent = queue.get_task_by_name("non_existent")
        assert non_existent is None

    def test_has_ready_tasks(self):
        """Test checking if there are ready tasks"""
        queue = TodoQueue()

        assert not queue.has_ready_tasks()

        plan = Plan(
            steps=[
                Step(
                    description="Step 1",
                    tasks=[Task(name="task1", description="Task 1")],
                )
            ],
            reasoning="Test",
            is_complete=False,
        )
        queue.load_plan(plan)

        assert queue.has_ready_tasks()

        # Complete the step
        step = queue.get_next_step()
        step.tasks[0].status = "completed"
        queue.complete_step(step)

        assert not queue.has_ready_tasks()

    def test_progress_summary(self):
        """Test progress summary generation"""
        queue = TodoQueue()

        # Empty queue
        summary = queue.get_progress_summary()
        assert summary == "No steps planned yet."

        # Load plan with multiple steps
        plan = Plan(
            steps=[
                Step(
                    description="Step 1",
                    tasks=[
                        Task(name="task1", description="Task 1"),
                        Task(name="task2", description="Task 2"),
                    ],
                ),
                Step(
                    description="Step 2",
                    tasks=[Task(name="task3", description="Task 3")],
                ),
            ],
            reasoning="Test",
            is_complete=False,
        )
        queue.load_plan(plan)

        # Complete first step
        step1 = queue.get_next_step()
        step1.tasks[0].status = "completed"
        step1.tasks[1].status = "failed"
        queue.complete_step(step1)
        queue.mark_task_failed("task2")

        summary = queue.get_progress_summary()
        assert "1/2 steps" in summary
        assert "1/3 completed" in summary
        assert "1 failed" in summary
        assert "1 steps, 1 tasks" in summary


class TestEnqueueDequeue:
    """Tests for explicit enqueue/dequeue operations"""

    def test_enqueue_single_step(self):
        """Test enqueueing a single step"""
        queue = TodoQueue()

        step = Step(
            description="New step", tasks=[Task(name="task1", description="Task 1")]
        )

        queue.enqueue_step(step)

        assert len(queue.pending_steps) == 1
        assert queue.pending_steps[0] == step
        assert "task1" in queue.all_tasks

    def test_dequeue_step(self):
        """Test dequeueing a step"""
        queue = TodoQueue()

        step1 = Step(
            description="Step 1", tasks=[Task(name="task1", description="Task 1")]
        )
        step2 = Step(
            description="Step 2", tasks=[Task(name="task2", description="Task 2")]
        )

        queue.enqueue_step(step1)
        queue.enqueue_step(step2)

        # Dequeue first step
        dequeued = queue.dequeue_step()
        assert dequeued == step1
        assert len(queue.pending_steps) == 1
        assert queue.pending_steps[0] == step2

        # Dequeue second step
        dequeued = queue.dequeue_step()
        assert dequeued == step2
        assert len(queue.pending_steps) == 0

        # Dequeue from empty queue
        dequeued = queue.dequeue_step()
        assert dequeued is None

    def test_enqueue_with_deduplication(self):
        """Test that enqueue_step respects deduplication"""
        queue = TodoQueue()

        # First step
        step1 = Step(
            description="Research phase",
            tasks=[
                Task(name="task1", description="Research A"),
                Task(name="task2", description="Research B"),
            ],
        )
        queue.enqueue_step(step1)

        # Try to enqueue duplicate step
        step2 = Step(
            description="Research phase",  # Same description
            tasks=[Task(name="task3", description="Research C")],
        )
        queue.enqueue_step(step2)

        # Should not add duplicate step
        assert len(queue.pending_steps) == 1
        assert len(queue.all_tasks) == 2  # Only original tasks

    def test_enqueue_dequeue_workflow(self):
        """Test a complete enqueue/dequeue workflow"""
        queue = TodoQueue()

        # Enqueue multiple steps
        steps = [
            Step(
                description=f"Step {i}",
                tasks=[Task(name=f"task_{i}", description=f"Task {i}")],
            )
            for i in range(3)
        ]

        for step in steps:
            queue.enqueue_step(step)

        assert len(queue.pending_steps) == 3

        # Dequeue and process steps
        processed = []
        while not queue.is_empty():
            step = queue.dequeue_step()
            processed.append(step.description)

        assert processed == ["Step 0", "Step 1", "Step 2"]
        assert queue.is_empty()


class TestComplexScenarios:
    """Tests for complex queue scenarios"""

    def test_interleaved_operations(self):
        """Test interleaved load, merge, complete operations"""
        queue = TodoQueue()

        # Load initial plan
        plan1 = Plan(
            steps=[
                Step(
                    description="Step 1",
                    tasks=[Task(name="task1", description="Task 1")],
                ),
                Step(
                    description="Step 2",
                    tasks=[Task(name="task2", description="Task 2")],
                ),
            ],
            reasoning="Initial",
            is_complete=False,
        )
        queue.load_plan(plan1)

        # Complete first step
        step1 = queue.get_next_step()
        step1.tasks[0].status = "completed"
        queue.complete_step(step1)

        # Merge additional plan
        plan2 = Plan(
            steps=[
                Step(
                    description="Step 3",
                    tasks=[Task(name="task3", description="Task 3")],
                ),
                Step(
                    description="Step 2",  # Duplicate, should be ignored
                    tasks=[Task(name="task4", description="Task 4")],
                ),
            ],
            reasoning="Additional",
            is_complete=False,
        )
        added = queue.merge_plan(plan2)

        assert added == 1  # Only Step 3 added
        assert len(queue.pending_steps) == 2  # Step 2 and Step 3
        assert len(queue.completed_steps) == 1  # Step 1

        # Complete remaining steps
        while not queue.is_empty():
            step = queue.get_next_step()
            for task in step.tasks:
                task.status = "completed"
            queue.complete_step(step)

        assert len(queue.completed_steps) == 3
        assert len(queue.completed_task_names) == 3

    def test_replanning_scenario(self):
        """Test a replanning scenario with partial completion"""
        queue = TodoQueue()

        # Initial plan
        initial_plan = Plan(
            steps=[
                Step(
                    description="Research",
                    tasks=[
                        Task(name="research1", description="Research topic A"),
                        Task(name="research2", description="Research topic B"),
                    ],
                ),
                Step(
                    description="Analysis",
                    tasks=[Task(name="analyze", description="Analyze findings")],
                ),
            ],
            reasoning="Initial plan",
            is_complete=False,
        )
        queue.load_plan(initial_plan)

        # Complete research partially (one task failed)
        research_step = queue.get_next_step()
        research_step.tasks[0].status = "completed"
        research_step.tasks[1].status = "failed"
        queue.complete_step(research_step)
        queue.mark_task_failed("research2")

        # Replan with additional research and modified analysis
        replan = Plan(
            steps=[
                Step(
                    description="Additional Research",
                    tasks=[
                        Task(name="research3", description="Research topic C"),
                        Task(name="research2_retry", description="Retry topic B"),
                    ],
                ),
                Step(
                    description="Analysis",  # Duplicate step name, should be filtered
                    tasks=[
                        Task(name="analyze_extended", description="Extended analysis")
                    ],
                ),
                Step(
                    description="Synthesis",
                    tasks=[Task(name="synthesize", description="Synthesize results")],
                ),
            ],
            reasoning="Replanning after partial failure",
            is_complete=False,
        )

        added = queue.merge_plan(replan)

        # Should add "Additional Research" and "Synthesis" (Analysis is duplicate)
        assert added == 2
        assert len(queue.pending_steps) == 3  # Original Analysis + 2 new steps

        # Verify state
        assert "research1" in queue.completed_task_names
        assert "research2" in queue.failed_task_names
        assert queue.failed_task_names["research2"] == 1
