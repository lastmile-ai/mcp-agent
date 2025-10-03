"""
Task registry for RCM quality control tasks.
Registers all tasks with the app instance.
"""

from mcp_agent.app import MCPApp


def register_rcm_tasks(app: MCPApp):
    """Register all RCM tasks with the given app instance"""

    # Import task modules to register them
    from . import llm_evaluators_impl
    from . import quality_control_impl

    # Register the tasks with the app
    llm_evaluators_impl.register_tasks(app)
    quality_control_impl.register_tasks(app)
