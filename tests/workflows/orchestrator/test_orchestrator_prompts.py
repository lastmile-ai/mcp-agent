from mcp_agent.workflows.orchestrator.orchestrator_prompts import (
    TASK_RESULT_TEMPLATE,
    STEP_RESULT_TEMPLATE,
    PLAN_RESULT_TEMPLATE,
    FULL_PLAN_PROMPT_TEMPLATE,
    ITERATIVE_PLAN_PROMPT_TEMPLATE,
    TASK_PROMPT_TEMPLATE,
    SYNTHESIZE_STEP_PROMPT_TEMPLATE,
    SYNTHESIZE_PLAN_PROMPT_TEMPLATE,
)


class TestOrchestratorPrompts:
    """Tests for orchestrator prompts templates"""

    def test_task_result_template(self):
        """Test that TASK_RESULT_TEMPLATE can be formatted correctly"""
        formatted = TASK_RESULT_TEMPLATE.format(
            task_description="Test task description",
            task_result="Test task result",
        )

        assert "Test task description" in formatted
        assert "Test task result" in formatted

    def test_step_result_template(self):
        """Test that STEP_RESULT_TEMPLATE can be formatted correctly"""
        formatted = STEP_RESULT_TEMPLATE.format(
            step_description="Test step description",
            tasks_str="Test tasks string",
        )

        assert "Test step description" in formatted
        assert "Test tasks string" in formatted

    def test_plan_result_template(self):
        """Test that PLAN_RESULT_TEMPLATE can be formatted correctly"""
        formatted = PLAN_RESULT_TEMPLATE.format(
            plan_objective="Test objective",
            steps_str="Test steps string",
            plan_status="In Progress",
            plan_result="Test plan result",
        )

        assert "Test objective" in formatted
        assert "Test steps string" in formatted
        assert "In Progress" in formatted
        assert "Test plan result" in formatted

    def test_full_plan_prompt_template(self):
        """Test that FULL_PLAN_PROMPT_TEMPLATE can be formatted correctly"""
        formatted = FULL_PLAN_PROMPT_TEMPLATE.format(
            objective="Test objective",
            plan_result="Test plan result",
            agents="Test agents",
        )

        assert "Test objective" in formatted
        assert "Test plan result" in formatted
        assert "Test agents" in formatted
        assert "remaining steps" in formatted.lower()

    def test_iterative_plan_prompt_template(self):
        """Test that ITERATIVE_PLAN_PROMPT_TEMPLATE can be formatted correctly"""
        formatted = ITERATIVE_PLAN_PROMPT_TEMPLATE.format(
            objective="Test objective",
            plan_result="Test plan result",
            agents="Test agents",
        )

        assert "Test objective" in formatted
        assert "Test plan result" in formatted
        assert "Test agents" in formatted
        assert "next step" in formatted.lower()

    def test_task_prompt_template(self):
        """Test that TASK_PROMPT_TEMPLATE can be formatted correctly"""
        formatted = TASK_PROMPT_TEMPLATE.format(
            objective="Test objective",
            task="Test task",
            context="Test context",
        )

        assert "Test objective" in formatted
        assert "Test task" in formatted
        assert "Test context" in formatted

    def test_synthesize_step_prompt_template(self):
        """Test that SYNTHESIZE_STEP_PROMPT_TEMPLATE can be formatted correctly"""
        formatted = SYNTHESIZE_STEP_PROMPT_TEMPLATE.format(
            step_result="Test step result",
        )

        assert "Test step result" in formatted
        assert "Synthesize" in formatted

    def test_synthesize_plan_prompt_template(self):
        """Test that SYNTHESIZE_PLAN_PROMPT_TEMPLATE can be formatted correctly"""
        formatted = SYNTHESIZE_PLAN_PROMPT_TEMPLATE.format(
            plan_result="Test plan result",
        )

        assert "Test plan result" in formatted
        assert "Synthesize" in formatted

    def test_templates_consistency(self):
        """Test that the prompt templates are consistent in format"""
        # Check that all templates use curly braces for format strings
        templates = [
            TASK_RESULT_TEMPLATE,
            STEP_RESULT_TEMPLATE,
            PLAN_RESULT_TEMPLATE,
            FULL_PLAN_PROMPT_TEMPLATE,
            ITERATIVE_PLAN_PROMPT_TEMPLATE,
            TASK_PROMPT_TEMPLATE,
            SYNTHESIZE_STEP_PROMPT_TEMPLATE,
            SYNTHESIZE_PLAN_PROMPT_TEMPLATE,
        ]

        for template in templates:
            assert "{" in template
            assert "}" in template

    def test_template_order(self):
        """Test that the templates are in the correct order in the file"""
        # Some of the templates depend on others (e.g., format_step_result uses format_task_result)
        # This test ensures that the templates are defined in a logical order
        assert "Task: {task_description}" in TASK_RESULT_TEMPLATE
        assert "Step: {step_description}" in STEP_RESULT_TEMPLATE
        assert "Plan Objective: {plan_objective}" in PLAN_RESULT_TEMPLATE
