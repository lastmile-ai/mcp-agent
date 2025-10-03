from mcp_agent.workflows.orchestrator.orchestrator_models import (
    Task,
    ServerTask,
    AgentTask,
    Step,
    Plan,
    TaskWithResult,
    StepResult,
    PlanResult,
    NextStep,
    format_task_result,
    format_step_result,
    format_plan_result,
)


class TestOrchestratorModels:
    """Tests for the orchestrator data models"""

    def test_task_creation(self):
        """Test that a Task can be created properly"""
        task = Task(description="Test task")
        assert task.description == "Test task"

    def test_server_task_creation(self):
        """Test that a ServerTask can be created properly"""
        server_task = ServerTask(
            description="Test server task", servers=["server1", "server2"]
        )
        assert server_task.description == "Test server task"
        assert server_task.servers == ["server1", "server2"]

    def test_agent_task_creation(self):
        """Test that an AgentTask can be created properly"""
        agent_task = AgentTask(description="Test agent task", agent="test_agent")
        assert agent_task.description == "Test agent task"
        assert agent_task.agent == "test_agent"

    def test_step_creation(self):
        """Test that a Step can be created properly"""
        tasks = [
            AgentTask(description="Task 1", agent="agent1"),
            AgentTask(description="Task 2", agent="agent2"),
        ]
        step = Step(description="Test step", tasks=tasks)
        assert step.description == "Test step"
        assert len(step.tasks) == 2
        assert step.tasks[0].description == "Task 1"
        assert step.tasks[1].agent == "agent2"

    def test_plan_creation(self):
        """Test that a Plan can be created properly"""
        step = Step(
            description="Test step",
            tasks=[AgentTask(description="Test task", agent="test_agent")],
        )
        plan = Plan(steps=[step], is_complete=False)

        assert len(plan.steps) == 1
        assert plan.steps[0].description == "Test step"
        assert not plan.is_complete

    def test_task_with_result_creation(self):
        """Test that a TaskWithResult can be created properly"""
        task_result = TaskWithResult(
            description="Test task", agent="test_agent", result="Task completed"
        )

        assert task_result.description == "Test task"
        assert task_result.agent == "test_agent"
        assert task_result.result == "Task completed"

    def test_step_result_creation(self):
        """Test that a StepResult can be created properly"""
        step = Step(
            description="Test step",
            tasks=[AgentTask(description="Test task", agent="test_agent")],
        )
        task_result = TaskWithResult(
            description="Test task", agent="test_agent", result="Task completed"
        )

        step_result = StepResult(
            step=step, task_results=[task_result], result="Step completed"
        )

        assert step_result.step.description == "Test step"
        assert len(step_result.task_results) == 1
        assert step_result.task_results[0].result == "Task completed"
        assert step_result.result == "Step completed"

    def test_step_result_add_task_result(self):
        """Test that a task result can be added to a StepResult"""
        step = Step(
            description="Test step",
            tasks=[AgentTask(description="Test task", agent="test_agent")],
        )
        step_result = StepResult(step=step)

        assert len(step_result.task_results) == 0

        task_result = TaskWithResult(
            description="Test task", agent="test_agent", result="Task completed"
        )
        step_result.add_task_result(task_result)

        assert len(step_result.task_results) == 1
        assert step_result.task_results[0].result == "Task completed"

    def test_plan_result_creation(self):
        """Test that a PlanResult can be created properly"""
        step = Step(
            description="Test step",
            tasks=[AgentTask(description="Test task", agent="test_agent")],
        )
        step_result = StepResult(
            step=step,
            task_results=[
                TaskWithResult(
                    description="Test task", agent="test_agent", result="Task completed"
                )
            ],
            result="Step completed",
        )

        plan_result = PlanResult(
            objective="Test objective",
            plan=Plan(steps=[step], is_complete=False),
            step_results=[step_result],
            is_complete=False,
        )

        assert plan_result.objective == "Test objective"
        assert len(plan_result.step_results) == 1
        assert not plan_result.is_complete
        assert plan_result.result is None

    def test_plan_result_add_step_result(self):
        """Test that a step result can be added to a PlanResult"""
        plan_result = PlanResult(objective="Test objective", step_results=[])

        assert len(plan_result.step_results) == 0

        step = Step(
            description="Test step",
            tasks=[AgentTask(description="Test task", agent="test_agent")],
        )
        step_result = StepResult(
            step=step,
            task_results=[
                TaskWithResult(
                    description="Test task", agent="test_agent", result="Task completed"
                )
            ],
            result="Step completed",
        )

        plan_result.add_step_result(step_result)

        assert len(plan_result.step_results) == 1
        assert plan_result.step_results[0].result == "Step completed"

    def test_next_step_creation(self):
        """Test that a NextStep can be created properly"""
        next_step = NextStep(
            description="Next step",
            tasks=[AgentTask(description="Test task", agent="test_agent")],
            is_complete=False,
        )

        assert next_step.description == "Next step"
        assert len(next_step.tasks) == 1
        assert not next_step.is_complete

    def test_format_task_result(self):
        """Test that a task result can be formatted correctly"""
        task_result = TaskWithResult(
            description="Test task", agent="test_agent", result="Task result"
        )

        formatted = format_task_result(task_result)

        assert "Test task" in formatted
        assert "Task result" in formatted

    def test_format_step_result(self):
        """Test that a step result can be formatted correctly"""
        step = Step(
            description="Test step",
            tasks=[AgentTask(description="Test task", agent="test_agent")],
        )
        step_result = StepResult(
            step=step,
            task_results=[
                TaskWithResult(
                    description="Test task", agent="test_agent", result="Task result"
                )
            ],
            result="Step result",
        )

        formatted = format_step_result(step_result)

        assert "Test step" in formatted
        assert "Test task" in formatted
        assert "Task result" in formatted

    def test_format_plan_result(self):
        """Test that a plan result can be formatted correctly"""
        step = Step(
            description="Test step",
            tasks=[AgentTask(description="Test task", agent="test_agent")],
        )
        step_result = StepResult(
            step=step,
            task_results=[
                TaskWithResult(
                    description="Test task", agent="test_agent", result="Task result"
                )
            ],
            result="Step result",
        )
        plan_result = PlanResult(
            objective="Test objective",
            plan=Plan(steps=[step], is_complete=False),
            step_results=[step_result],
            is_complete=False,
            result=None,
        )

        formatted = format_plan_result(plan_result)

        assert "Test objective" in formatted
        assert "Test step" in formatted
        assert "In Progress" in formatted

    def test_format_plan_result_complete(self):
        """Test that a completed plan result can be formatted correctly"""
        step = Step(
            description="Test step",
            tasks=[AgentTask(description="Test task", agent="test_agent")],
        )
        step_result = StepResult(
            step=step,
            task_results=[
                TaskWithResult(
                    description="Test task", agent="test_agent", result="Task result"
                )
            ],
            result="Step result",
        )
        plan_result = PlanResult(
            objective="Test objective",
            plan=Plan(steps=[step], is_complete=True),
            step_results=[step_result],
            is_complete=True,
            result="Plan completed",
        )

        formatted = format_plan_result(plan_result)

        assert "Test objective" in formatted
        assert "Test step" in formatted
        assert "Complete" in formatted
        assert "Plan completed" in formatted
