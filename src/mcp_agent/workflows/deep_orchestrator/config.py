"""
Configuration for the Deep Orchestrator workflow.

This module provides configuration classes to simplify orchestrator initialization
and make configuration more manageable.
"""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM


class ExecutionConfig(BaseModel):
    """Configuration for workflow execution behavior."""

    max_iterations: int = 20
    """Maximum workflow iterations"""

    max_replans: int = 3
    """Maximum number of replanning attempts"""

    max_task_retries: int = 3
    """Maximum retries per failed task"""

    enable_parallel: bool = True
    """Enable parallel task execution within steps"""

    enable_filesystem: bool = True
    """Enable filesystem workspace for artifacts"""


class ContextConfig(BaseModel):
    """Configuration for context management."""

    task_context_budget: int = 50000
    """Maximum tokens for each task's context"""

    context_relevance_threshold: float = 0.7
    """Minimum relevance score to include context (0.0-1.0)"""

    context_compression_ratio: float = 0.8
    """Threshold to start compressing context (0.0-1.0)"""

    enable_full_context_propagation: bool = True
    """Whether to propagate full context to tasks"""

    context_window_limit: int = 100000
    """Model's context window limit"""


class BudgetConfig(BaseModel):
    """Configuration for resource budgets."""

    max_tokens: int = 100000
    """Maximum total tokens to use"""

    max_cost: float = 10.0
    """Maximum cost in dollars"""

    max_time_minutes: int = 30
    """Maximum execution time in minutes"""

    cost_per_1k_tokens: float = 0.001
    """Cost per 1000 tokens for budget calculation"""


class PolicyConfig(BaseModel):
    """Configuration for the policy engine."""

    max_consecutive_failures: int = 3
    """Maximum allowed consecutive task failures before emergency stop"""

    min_verification_confidence: float = 0.8
    """Minimum confidence for objective completion verification"""

    replan_on_empty_queue: bool = True
    """Whether to replan when task queue is empty"""

    budget_critical_threshold: float = 0.9
    """Budget usage threshold for critical state (0.0-1.0)"""


class CacheConfig(BaseModel):
    """Configuration for agent caching."""

    max_cache_size: int = 50
    """Maximum number of agents to cache"""

    enable_agent_cache: bool = True
    """Whether to cache dynamically created agents"""


class DeepOrchestratorConfig(BaseModel):
    """Complete configuration for Deep Orchestrator."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Core settings
    name: str = "DeepOrchestrator"
    """Name of the orchestrator"""

    available_agents: List[Agent | AugmentedLLM] = []
    """List of pre-defined agents"""

    available_servers: Optional[List[str]] = None
    """List of available MCP servers"""

    # Sub-configurations
    execution: ExecutionConfig = ExecutionConfig()
    context: ContextConfig = ContextConfig()
    budget: BudgetConfig = BudgetConfig()
    policy: PolicyConfig = PolicyConfig()
    cache: CacheConfig = CacheConfig()

    @classmethod
    def from_simple(
        cls,
        name: str = "DeepOrchestrator",
        max_iterations: int = 20,
        max_tokens: int = 100000,
        max_cost: float = 10.0,
        enable_parallel: bool = True,
    ) -> "DeepOrchestratorConfig":
        """
        Create configuration from simple parameters.

        Args:
            name: Orchestrator name
            max_iterations: Maximum workflow iterations
            max_tokens: Maximum token budget
            max_cost: Maximum cost budget
            enable_parallel: Enable parallel execution

        Returns:
            Configuration instance
        """
        return cls(
            name=name,
            execution=ExecutionConfig(
                max_iterations=max_iterations,
                enable_parallel=enable_parallel,
            ),
            budget=BudgetConfig(
                max_tokens=max_tokens,
                max_cost=max_cost,
            ),
        )

    def with_strict_budget(
        self,
        max_tokens: int = 50000,
        max_cost: float = 5.0,
        max_time_minutes: int = 15,
    ) -> "DeepOrchestratorConfig":
        """
        Apply strict budget limits.

        Args:
            max_tokens: Maximum tokens
            max_cost: Maximum cost in dollars
            max_time_minutes: Maximum time in minutes

        Returns:
            Updated configuration
        """
        self.budget.max_tokens = max_tokens
        self.budget.max_cost = max_cost
        self.budget.max_time_minutes = max_time_minutes
        return self

    def with_resilient_execution(
        self,
        max_task_retries: int = 5,
        max_consecutive_failures: int = 5,
        max_replans: int = 5,
    ) -> "DeepOrchestratorConfig":
        """
        Configure for resilient execution with more retries.

        Args:
            max_task_retries: Retries per task
            max_consecutive_failures: Consecutive failures before stop
            max_replans: Maximum replanning attempts

        Returns:
            Updated configuration
        """
        self.execution.max_task_retries = max_task_retries
        self.execution.max_replans = max_replans
        self.policy.max_consecutive_failures = max_consecutive_failures
        return self

    def with_minimal_context(
        self,
        task_context_budget: int = 10000,
        enable_full_context_propagation: bool = False,
    ) -> "DeepOrchestratorConfig":
        """
        Configure for minimal context usage.

        Args:
            task_context_budget: Maximum tokens per task
            enable_full_context_propagation: Whether to propagate full context

        Returns:
            Updated configuration
        """
        self.context.task_context_budget = task_context_budget
        self.context.enable_full_context_propagation = enable_full_context_propagation
        return self
