from typing import TypeVar, TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM

    # Define a TypeVar for AugmentedLLM and its subclasses that's only used at type checking time
    LLM = TypeVar("LLM", bound="AugmentedLLM")
else:
    # Define a TypeVar without the bound for runtime
    LLM = TypeVar("LLM")
