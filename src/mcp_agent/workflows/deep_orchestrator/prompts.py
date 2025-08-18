"""
XML-structured prompts for the Deep Orchestrator workflow.

This module contains all the prompt templates used by the Deep Orchestrator
for planning, execution, knowledge extraction, and synthesis.
"""


# ============================================================================
# System Instructions
# ============================================================================

ORCHESTRATOR_SYSTEM_INSTRUCTION = """<system_prompt>
You are an Adaptive Orchestrator that excels at breaking down and solving complex objectives through intelligent planning and execution.

<core_capabilities>
  <capability name="full_planning">Create comprehensive, end-to-end execution plans upfront</capability>
  <capability name="dynamic_agents">Design and create specialized agents perfectly suited for each task</capability>
  <capability name="smart_coordination">Execute steps sequentially, tasks within steps in parallel for efficiency</capability>
  <capability name="knowledge_building">Extract and accumulate insights from each task for reuse</capability>
  <capability name="adaptive_replanning">Adjust strategy based on results, failures, and verification</capability>
</core_capabilities>

<process>
  <phase number="1">Deeply analyze the objective to understand requirements and constraints</phase>
  <phase number="2">Create a complete plan with clear sequential steps</phase>
  <phase number="3">Execute each step's tasks in parallel for efficiency</phase>
  <phase number="4">Extract reusable knowledge from each task result</phase>
  <phase number="5">Verify progress and replan if needed based on accumulated knowledge</phase>
  <phase number="6">Synthesize all work into a final deliverable that fully addresses the objective</phase>
</process>

<principles>
  <principle>Think deeply and plan thoroughly before acting</principle>
  <principle>Create clear task boundaries to enable parallel execution</principle>
  <principle>Use specialized agents for specialized work</principle>
  <principle>Build on accumulated knowledge - never repeat work</principle>
  <principle>Acknowledge limitations but always deliver value</principle>
  <principle>Monitor resources and adapt when constrained</principle>
</principles>
</system_prompt>"""


PLANNER_INSTRUCTION = """<planner_instruction>
You are an expert strategic planner who creates comprehensive execution plans.

<planning_process>
  <step>1. Deeply analyze the objective and any accumulated knowledge</step>
  <step>2. Identify major phases or milestones needed</step>
  <step>3. Break down into specific, actionable steps</step>
  <step>4. For each step, define parallel tasks with clear boundaries</step>
  <step>5. Order steps logically - later steps naturally depend on earlier ones</step>
  <step>6. Assign appropriate agents and tools to each task</step>
</planning_process>

<task_design_rules>
  <rule>Each task must have a single, clear deliverable</rule>
  <rule>Give each task a unique, descriptive name (e.g., "analyze_code", "check_grammar", "compile_report")</rule>
  <rule>Tasks should be specific enough to execute without ambiguity</rule>
  <rule>Parallel tasks within a step must not interfere with each other</rule>
  <rule>Leave agent field unset (not specified) to request dynamic agent creation</rule>
  <rule>CRITICAL: If you specify an agent name, it MUST be one of the available_agents - NEVER invent or hallucinate agent names</rule>
  <rule>CRITICAL: Only use MCP servers from the available_servers list - NEVER invent or hallucinate server names</rule>
  <rule>If no servers are needed for a task, use an empty list []</rule>
  <rule>Tasks run in parallel within a step, steps run sequentially</rule>
  <rule>Use requires_context_from to specify which previous task outputs this task needs</rule>
  <rule>requires_context_from can ONLY reference tasks from PREVIOUS steps, not the current step</rule>
  <rule>If a task needs output from another task in the same step, move it to a subsequent step</rule>
  <rule>Only set context_window_budget if task needs more than default (10000 tokens)</rule>
</task_design_rules>

<important_notes>
  <note>Do NOT recreate already completed steps - build on existing work</note>
  <note>If objective is already satisfied, set is_complete=true</note>
  <note>Consider resource constraints and prefer efficient approaches</note>
  <note>Think step by step about the best way to achieve the objective</note>
  <note>Tasks within a step run in parallel, steps run sequentially</note>
</important_notes>

<example_task_structure>
  Step 1: Analysis Phase
    - Task: name="check_grammar", description="Check grammar and spelling"
    - Task: name="analyze_style", description="Analyze writing style"
    - Task: name="assess_structure", description="Assess story structure"
  
  Step 2: Synthesis Phase  
    - Task: name="compile_report", description="Compile comprehensive grading report"
      requires_context_from=["check_grammar", "analyze_style", "assess_structure"]
      # Can reference tasks from Step 1, but NOT tasks from Step 2
</example_task_structure>
</planner_instruction>"""


SYNTHESIZER_INSTRUCTION = """<synthesizer_instruction>
You are responsible for creating the final deliverable that fully addresses the original objective.

<synthesis_process>
  <review>Review all completed work and extracted knowledge</review>
  <integrate>Combine findings into a cohesive response</integrate>
  <polish>Ensure clarity, completeness, and professionalism</polish>
  <deliver>Present the final result that fully satisfies the objective</deliver>
</synthesis_process>

<quality_standards>
  <standard>Address every aspect of the original objective</standard>
  <standard>Integrate all relevant findings and insights</standard>
  <standard>Acknowledge any limitations or gaps</standard>
  <standard>Provide clear, actionable information</standard>
  <standard>Maintain professional presentation</standard>
</quality_standards>

Your synthesis should be comprehensive yet concise, delivering maximum value to the user.
</synthesizer_instruction>"""


KNOWLEDGE_EXTRACTOR_INSTRUCTION = """You extract key insights and reusable knowledge from task outputs.

Focus on:
- Facts and findings
- Decisions made
- Resources discovered
- Patterns identified
- Limitations found

Be selective - only extract high-value, reusable knowledge."""


AGENT_DESIGNER_INSTRUCTION = """<agent_designer_instruction>
You are an expert at designing specialized AI agents perfectly suited for specific tasks.

<design_process>
  <analyze>Understand the task requirements, tools needed, and expected outcomes</analyze>
  <specialize>Create an agent with the exact expertise needed</specialize>
  <optimize>Design clear instructions and behaviors for effectiveness</optimize>
</design_process>

<design_principles>
  <principle>Agents should be focused on their specific task</principle>
  <principle>Instructions should be clear and actionable</principle>
  <principle>Include specific guidance on tool usage</principle>
  <principle>Consider edge cases and failure modes</principle>
</design_principles>
</agent_designer_instruction>"""


VERIFIER_INSTRUCTION = """<verifier_instruction>
You are a thorough verifier who checks if objectives have been completed successfully.

<verification_process>
  <check>Has the core objective been achieved?</check>
  <check>Are all requested deliverables present?</check>
  <check>Is the quality sufficient for the intended purpose?</check>
  <check>Are there any critical gaps or missing elements?</check>
</verification_process>

<assessment_criteria>
  <criterion>Completeness - all aspects addressed</criterion>
  <criterion>Correctness - accurate and valid results</criterion>
  <criterion>Quality - meets expected standards</criterion>
  <criterion>Usability - ready for intended use</criterion>
</assessment_criteria>

Be rigorous but fair. Consider partial success and acknowledge what has been achieved.
</verifier_instruction>"""


EMERGENCY_RESPONDER_INSTRUCTION = """<emergency_responder_instruction>
You must provide the best possible response despite technical difficulties.

<approach>
  <acknowledge>Briefly acknowledge the error</acknowledge>
  <salvage>Use any available partial results</salvage>
  <deliver>Provide maximum value possible</deliver>
  <suggest>Offer helpful next steps</suggest>
</approach>

Focus on being helpful rather than dwelling on the failure.
</emergency_responder_instruction>"""


# ============================================================================
# Planning Prompt Templates
# ============================================================================


def get_planning_context(
    objective: str,
    progress_summary: str = "",
    completed_steps: list = None,
    knowledge_items: list = None,
    available_servers: list = None,
    available_agents: dict = None,
) -> str:
    """Build planning context with XML structure."""
    context_parts = ["<planning_context>"]
    context_parts.append(f"  <objective>{objective}</objective>")

    # Add progress if replanning
    if progress_summary:
        context_parts.append("  <progress>")
        context_parts.append(f"    <summary>{progress_summary}</summary>")
        if completed_steps:
            context_parts.append("    <completed_steps>")
            for step in completed_steps[:5]:  # Last 5 steps
                context_parts.append(f"      <step>{step}</step>")
            context_parts.append("    </completed_steps>")
        context_parts.append("  </progress>")

    # Add accumulated knowledge
    if knowledge_items:
        context_parts.append("  <accumulated_knowledge>")
        for item in knowledge_items[:10]:  # Top 10 items
            context_parts.append(
                f'    <knowledge confidence="{item.get("confidence", 0.8):.2f}" '
                f'category="{item.get("category", "general")}">'
            )
            context_parts.append(f"      <key>{item.get('key', 'Unknown')}</key>")
            value_str = str(item.get("value", ""))[:200]
            context_parts.append(f"      <value>{value_str}</value>")
            context_parts.append("    </knowledge>")
        context_parts.append("  </accumulated_knowledge>")

    # Add available resources
    context_parts.append("  <resources>")
    if available_servers:
        context_parts.append(
            f"    <mcp_servers>{', '.join(available_servers)}</mcp_servers>"
        )
        context_parts.append(
            "    <important>You MUST only use these exact server names. Do NOT invent or guess server names.</important>"
        )
    else:
        context_parts.append("    <mcp_servers>None available</mcp_servers>")
        context_parts.append(
            "    <important>No MCP servers are available. All tasks must have empty server lists.</important>"
        )
    if available_agents:
        context_parts.append(
            f"    <agents>{', '.join(available_agents.keys())}</agents>"
        )
        context_parts.append(
            "    <important>You MUST only use these exact agent names if specifying an agent. Do NOT invent or guess agent names. Leave agent field unset for dynamic creation.</important>"
        )
    else:
        context_parts.append(
            "    <agents>None available - all tasks must have agent field unset</agents>"
        )
        context_parts.append(
            "    <important>No predefined agents are available. All tasks must leave the agent field unset for dynamic agent creation.</important>"
        )
    context_parts.append("  </resources>")

    context_parts.append("</planning_context>")
    return "\n".join(context_parts)


def get_full_plan_prompt(context: str) -> str:
    """Get prompt for creating a full execution plan."""
    return f"""<plan_request>
{context}

Create a comprehensive plan to achieve the objective.
</plan_request>"""


# ============================================================================
# Task Execution Prompt Templates
# ============================================================================


def get_task_context(
    objective: str,
    task_description: str,
    relevant_knowledge: list = None,
    available_artifacts: list = None,
    scratchpad_path: str = None,
    required_servers: list = None,
) -> str:
    """Build task execution context."""
    parts = [
        "<task_context>",
        f"  <objective>{objective}</objective>",
        f"  <task>{task_description}</task>",
    ]

    # Add relevant knowledge
    if relevant_knowledge:
        parts.append("  <relevant_knowledge>")
        for item in relevant_knowledge[:5]:
            confidence = item.get("confidence", 0.8)
            key = item.get("key", "Unknown")
            value = str(item.get("value", ""))[:150]
            parts.append(f'    <knowledge confidence="{confidence:.2f}">')
            parts.append(f"      <insight>{key}: {value}</insight>")
            parts.append("    </knowledge>")
        parts.append("  </relevant_knowledge>")

    # Add available artifacts
    if available_artifacts:
        parts.append("  <available_artifacts>")
        for name in available_artifacts[:5]:  # Last 5
            parts.append(f"    <artifact>{name}</artifact>")
        parts.append("  </available_artifacts>")
        parts.append(
            "  <note>You can reference these artifacts if they contain relevant information</note>"
        )

    # Add scratchpad info
    if scratchpad_path:
        parts.append(f"  <scratchpad_path>{scratchpad_path}</scratchpad_path>")
        parts.append(
            "  <note>You can use the scratchpad directory for temporary files if needed</note>"
        )

    # Tool usage reminder
    if required_servers:
        parts.append("  <required_tools>")
        for server in required_servers:
            parts.append(f"    <tool>{server}</tool>")
        parts.append("  </required_tools>")
        parts.append(
            "  <important>You MUST use these tools actively to complete your task</important>"
        )

    parts.append("</task_context>")

    return "\n".join(parts)


# ============================================================================
# Knowledge Extraction Prompt Templates
# ============================================================================


def get_extraction_prompt(objective: str, task_output: str) -> str:
    """Get prompt for knowledge extraction."""
    # Truncate output if too long
    if len(task_output) > 2000:
        task_output = task_output[:2000]

    return f"""<extraction_request>
<objective>{objective}</objective>
<task_output>
{task_output}
</task_output>

Extract 1-5 key pieces of knowledge from this output.
</extraction_request>"""


# ============================================================================
# Agent Design Prompt Templates
# ============================================================================


def get_agent_design_prompt(
    task_description: str, required_servers: list, objective_context: str
) -> str:
    """Get prompt for designing a dynamic agent."""
    servers_str = ", ".join(required_servers) if required_servers else "none specified"
    objective_preview = (
        objective_context[:200] + "..."
        if len(objective_context) > 200
        else objective_context
    )

    return f"""<design_request>
<task>
  <description>{task_description}</description>
  <required_servers>{servers_str}</required_servers>
  <objective_context>{objective_preview}</objective_context>
</task>

Design an agent perfectly suited for this task.
</design_request>"""


def build_agent_instruction(design: dict) -> str:
    """Build comprehensive agent instruction from design."""
    instruction_parts = [
        "<agent_instruction>",
        design.get("instruction", ""),
        "",
        f"<role>{design.get('role', 'Task executor')}</role>",
        "",
        "<key_behaviors>",
    ]

    for behavior in design.get("key_behaviors", []):
        instruction_parts.append(f"  <behavior>{behavior}</behavior>")
    instruction_parts.append("</key_behaviors>")

    if design.get("tool_usage_tips"):
        instruction_parts.append("")
        instruction_parts.append("<tool_usage>")
        for tip in design["tool_usage_tips"]:
            instruction_parts.append(f"  <tip>{tip}</tip>")
        instruction_parts.append("</tool_usage>")

    instruction_parts.extend(
        [
            "",
            "<remember>",
            "  <point>Complete your specific task thoroughly</point>",
            "  <point>Use available tools actively - don't just describe what should be done</point>",
            "  <point>Build on previous work when relevant</point>",
            "  <point>Be precise and detailed in your execution</point>",
            "</remember>",
            "</agent_instruction>",
        ]
    )

    return "\n".join(instruction_parts)


# ============================================================================
# Verification Prompt Templates
# ============================================================================


def get_verification_context(
    objective: str,
    progress_summary: str,
    knowledge_summary: str = "",
    artifacts: dict = None,
) -> str:
    """Build verification context."""
    context_parts = [
        "<verification_context>",
        f"  <original_objective>{objective}</original_objective>",
        f"  <execution_summary>{progress_summary}</execution_summary>",
    ]

    # Add knowledge summary
    if knowledge_summary:
        context_parts.append("  <accumulated_knowledge>")
        context_parts.append(knowledge_summary)
        context_parts.append("  </accumulated_knowledge>")

    # Add created artifacts
    if artifacts:
        context_parts.append("  <created_artifacts>")
        for name, content in list(artifacts.items())[-5:]:
            context_parts.append(f'    <artifact name="{name}">')
            preview = content[:200] + "..." if len(content) > 200 else content
            context_parts.append(f"      {preview}")
            context_parts.append("    </artifact>")
        context_parts.append("  </created_artifacts>")

    context_parts.append("</verification_context>")
    return "\n".join(context_parts)


def get_verification_prompt(context: str) -> str:
    """Get prompt for verification."""
    return f"""{context}

<request>Verify if the objective has been completed.</request>"""


# ============================================================================
# Synthesis Prompt Templates
# ============================================================================


def get_synthesis_context(
    objective: str,
    execution_summary: dict,
    completed_steps: list,
    knowledge_by_category: dict,
    artifacts: dict,
) -> str:
    """Build comprehensive synthesis context."""
    context_parts = [
        "<synthesis_context>",
        f"  <original_objective>{objective}</original_objective>",
        "",
        "  <execution_summary>",
        f"    <iterations>{execution_summary.get('iterations', 0)}</iterations>",
        f"    <steps_completed>{execution_summary.get('steps_completed', 0)}</steps_completed>",
        f"    <tasks_completed>{execution_summary.get('tasks_completed', 0)}</tasks_completed>",
        f"    <tokens_used>{execution_summary.get('tokens_used', 0)}</tokens_used>",
        f"    <cost>${execution_summary.get('cost', 0):.2f}</cost>",
        "  </execution_summary>",
        "",
        "  <completed_work>",
    ]

    # Summarize completed steps and their results
    for step in completed_steps:
        context_parts.append(f'    <step name="{step.get("description", "Unknown")}">')

        for task_result in step.get("task_results", []):
            if task_result.get("success"):
                task_desc = task_result.get("description", "Unknown task")
                output_summary = task_result.get("output", "")[:300]
                if len(task_result.get("output", "")) > 300:
                    output_summary += "..."

                context_parts.append("      <task_result>")
                context_parts.append(f"        <task>{task_desc}</task>")
                context_parts.append(f"        <output>{output_summary}</output>")
                context_parts.append("      </task_result>")

        context_parts.append("    </step>")

    context_parts.append("  </completed_work>")

    # Add accumulated knowledge
    if knowledge_by_category:
        context_parts.append("")
        context_parts.append("  <accumulated_knowledge>")

        for category, items in knowledge_by_category.items():
            context_parts.append(f'    <category name="{category}">')
            for item in items[:5]:  # Limit per category
                context_parts.append(
                    f'      <knowledge confidence="{item.confidence:.2f}">'
                )
                context_parts.append(f"        <key>{item.key}</key>")
                value_str = (
                    str(item.value)[:200] + "..."
                    if len(str(item.value)) > 200
                    else str(item.value)
                )
                context_parts.append(f"        <value>{value_str}</value>")
                context_parts.append("      </knowledge>")
            context_parts.append("    </category>")

        context_parts.append("  </accumulated_knowledge>")

    # Add artifacts
    if artifacts:
        context_parts.append("")
        context_parts.append("  <artifacts_created>")
        for name, content in list(artifacts.items())[-10:]:  # Last 10 artifacts
            content_preview = content[:500] + "..." if len(content) > 500 else content
            context_parts.append(f'    <artifact name="{name}">')
            context_parts.append(f"      {content_preview}")
            context_parts.append("    </artifact>")
        context_parts.append("  </artifacts_created>")

    context_parts.append("</synthesis_context>")
    return "\n".join(context_parts)


def get_synthesis_prompt(context: str) -> str:
    """Get prompt for final synthesis."""
    return f"""{context}

<synthesis_request>
Create the final deliverable that fully addresses the original objective.
Synthesize all work completed, knowledge gained, and artifacts created into a comprehensive response.
</synthesis_request>"""


# ============================================================================
# Emergency Completion Prompt Templates
# ============================================================================


def get_emergency_context(
    objective: str,
    error: str,
    progress_summary: str,
    partial_knowledge: list = None,
    artifacts_created: list = None,
) -> str:
    """Build emergency completion context."""
    context_parts = [
        "<emergency_context>",
        f"  <objective>{objective}</objective>",
        f"  <error>{error}</error>",
        f"  <progress>{progress_summary}</progress>",
    ]

    # Add any partial results
    if partial_knowledge:
        context_parts.append("  <partial_knowledge>")
        for item in partial_knowledge[:10]:
            key = item.get("key", "Unknown")
            value = str(item.get("value", ""))[:100]
            context_parts.append(f"    - {key}: {value}")
        context_parts.append("  </partial_knowledge>")

    if artifacts_created:
        artifacts_str = ", ".join(artifacts_created[:5])
        context_parts.append(
            f"  <artifacts_created>{artifacts_str}</artifacts_created>"
        )

    context_parts.append("</emergency_context>")
    return "\n".join(context_parts)


def get_emergency_prompt(context: str) -> str:
    """Get prompt for emergency completion."""
    return f"""{context}

Provide the most helpful response possible given the circumstances."""
