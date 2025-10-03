"""
LLM-based evaluation tasks implementing paper methodologies.
Each task uses mcp-agent patterns for consistency.
"""

import json
import uuid
from typing import Dict, Any, List
from mcp_agent.agents.agent import Agent

# Import our utilities
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.config import get_llm_class
from utils.logging import get_rcm_logger

# We'll register tasks with the app instance passed from main.py
app = None

# Quality evaluation prompt from paper Appendix
QUALITY_EVALUATOR_PROMPT = """You are an expert evaluator assessing conversation quality based on research findings.

Evaluate responses across these research-backed dimensions:

1. CLARITY (0-1, higher better): Is the response clear, well-structured, and easy to understand?
2. COMPLETENESS (0-1, higher better): Does it appropriately address pending user requirements?
3. ASSUMPTIONS (0-1, LOWER better): Does it make unsupported assumptions about unstated details?
4. VERBOSITY (0-1, LOWER better): Is it unnecessarily long or repetitive? (Research shows 20-300% bloat)
5. PREMATURE_ATTEMPT (boolean): Is this attempting a complete answer without sufficient information?
6. MIDDLE_TURN_REFERENCE (0-1, higher better): Does it reference information from middle conversation turns?
7. REQUIREMENT_TRACKING (0-1, higher better): Does it track and reference user requirements across turns?

Research context: Multi-turn conversations show 39% performance degradation due to instruction forgetting,
answer bloat, premature attempts, and lost-in-middle-turns phenomena.

Return your evaluation as valid JSON with this exact format:
{
    "clarity": 0.0-1.0,
    "completeness": 0.0-1.0,
    "assumptions": 0.0-1.0,
    "verbosity": 0.0-1.0,
    "premature_attempt": true/false,
    "middle_turn_reference": 0.0-1.0,
    "requirement_tracking": 0.0-1.0,
    "issues": ["specific issue 1", "specific issue 2"],
    "strengths": ["strength 1", "strength 2"],
    "improvement_suggestions": ["suggestion 1", "suggestion 2"]
}"""

REQUIREMENT_EXTRACTOR_PROMPT = """You extract and track user requirements across conversation turns to prevent instruction forgetting.

Your task:
1. Identify explicit and implicit user requirements from the conversation
2. Track requirements that span multiple turns
3. Update status of existing requirements based on conversation progress
4. Distinguish between different types of requirements (functional, constraints, preferences)

Focus on preventing the "instruction forgetting" phenomenon identified in research.

Return requirements as valid JSON array with this exact format:
[
    {
        "id": "existing_id_or_new_uuid",
        "description": "clear requirement description",
        "source_turn": turn_number,
        "status": "pending|addressed|confirmed",
        "confidence": 0.0-1.0
    }
]

Rules:
1. Update existing requirements if mentioned in latest turns
2. Add new requirements from user messages
3. Mark requirements as "addressed" if assistant has handled them
4. Mark as "confirmed" if user explicitly confirms satisfaction
5. Include both explicit and reasonable implicit requirements
6. Maintain requirement IDs for tracking across turns"""

CONTEXT_CONSOLIDATOR_PROMPT = """You consolidate conversation context to prevent "lost-in-middle-turns" issues.

Your task:
1. Preserve all critical information from the conversation
2. Focus on maintaining middle turn information that could be lost
3. Keep requirements and their status clearly visible
4. Maintain chronological order of important events
5. Compress redundant information while preserving meaning

Return a consolidated context that:
- Preserves all user requirements
- Maintains key decisions and confirmations
- Includes relevant technical details
- Stays under token limits while being comprehensive"""


@app.workflow_task(name="evaluate_quality_with_llm")
async def evaluate_quality_with_llm(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    LLM-based quality evaluation implementing paper's quality dimensions.
    From paper Section 5.4.2.
    """
    logger = get_rcm_logger("quality_evaluator")

    response = params["response"]
    consolidated_context = params.get("consolidated_context", "")
    requirements = params.get("requirements", [])
    turn_number = params["turn_number"]
    conversation_history = params.get("conversation_history", [])
    config = params.get("config", {})

    # Detect premature attempts based on pending requirements
    pending_reqs = [r for r in requirements if r.get("status") == "pending"]
    has_complete_solution_markers = _detect_complete_solution_attempt(response)

    try:
        # Create evaluator agent with specialized prompt
        evaluator_agent = Agent(
            name="quality_evaluator",
            instruction=QUALITY_EVALUATOR_PROMPT,
            server_names=[],  # No MCP servers needed for evaluation
        )

        async with evaluator_agent:
            # Get LLM based on config
            llm_class = get_llm_class(config.get("evaluator_model_provider", "openai"))
            llm = await evaluator_agent.attach_llm(llm_class)

            evaluation_prompt = f"""Evaluate this conversation response for quality issues identified in research.

RESPONSE TO EVALUATE:
{response}

CONVERSATION CONTEXT:
{consolidated_context}

PENDING REQUIREMENTS:
{json.dumps([r.get("description", "") for r in pending_reqs], indent=2)}

CONVERSATION HISTORY LENGTH: {len(conversation_history)} messages
TURN NUMBER: {turn_number}

ADDITIONAL CONTEXT:
- Has complete solution markers: {has_complete_solution_markers}
- Pending requirements count: {len(pending_reqs)}

Evaluate each dimension carefully and return JSON with exact format specified in your instructions."""

            result = await llm.generate_str(evaluation_prompt)

            # Parse JSON response with validation
            try:
                data = json.loads(result)
            except json.JSONDecodeError:
                # Try to extract JSON from the response
                import re

                json_match = re.search(r"\{.*\}", result, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                else:
                    raise ValueError("Could not parse JSON from LLM response")

            # Apply paper-based heuristics
            if has_complete_solution_markers and len(pending_reqs) > 2:
                data["premature_attempt"] = True
                if "issues" not in data:
                    data["issues"] = []
                data["issues"].append(
                    "Complete solution attempt with multiple pending requirements"
                )

            # Apply verbosity penalty for answer bloat
            response_length = len(response)
            if turn_number > 1 and response_length > 500:
                verbosity_penalty = min(0.3, (response_length - 500) / 1000)
                data["verbosity"] = min(
                    1.0, data.get("verbosity", 0.5) + verbosity_penalty
                )
                if "issues" not in data:
                    data["issues"] = []
                data["issues"].append(
                    f"Response length ({response_length} chars) shows potential answer bloat"
                )

            logger.info(
                "Quality evaluation completed",
                data={
                    "turn": turn_number,
                    "overall_score": _calculate_overall_score(data),
                    "premature_attempt": data.get("premature_attempt", False),
                },
            )

            return {
                "metrics": data,
                "issues": data.get("issues", []),
                "evaluator_raw_response": result,
            }

    except Exception as e:
        logger.error(f"Quality evaluation failed: {str(e)}")
        # Fallback scores if evaluation fails
        return {
            "metrics": {
                "clarity": 0.5,
                "completeness": 0.5,
                "assumptions": 0.7,
                "verbosity": 0.6,
                "premature_attempt": has_complete_solution_markers
                and len(pending_reqs) > 1,
                "middle_turn_reference": 0.3,
                "requirement_tracking": 0.4,
            },
            "issues": [f"Quality evaluation error: {str(e)}"],
            "evaluator_raw_response": str(e),
        }


@app.workflow_task(name="extract_requirements_with_llm")
async def extract_requirements_with_llm(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    LLM-based requirement extraction to prevent instruction forgetting.
    From paper Section 5.4.3.
    """
    logger = get_rcm_logger("requirement_extractor")

    messages = params["messages"]
    existing_requirements = params.get("existing_requirements", [])
    config = params.get("config", {})

    try:
        # Create requirement extraction agent
        extractor_agent = Agent(
            name="requirement_extractor",
            instruction=REQUIREMENT_EXTRACTOR_PROMPT,
            server_names=[],
        )

        async with extractor_agent:
            llm_class = get_llm_class(config.get("evaluator_model_provider", "openai"))
            llm = await extractor_agent.attach_llm(llm_class)

            # Build conversation context
            conversation_text = "\n".join(
                [
                    f"Turn {msg.get('turn_number', 0)} ({msg.get('role', 'unknown')}): {msg.get('content', '')}"
                    for msg in messages
                    if msg.get("role") != "system"
                ]
            )

            existing_req_text = "\n".join(
                [
                    f"- {req.get('id', 'unknown')}: {req.get('description', '')} (Status: {req.get('status', 'unknown')})"
                    for req in existing_requirements
                ]
            )

            extraction_prompt = f"""Analyze this conversation to extract and update user requirements.

CONVERSATION:
{conversation_text}

EXISTING REQUIREMENTS:
{existing_req_text}

Extract requirements and return JSON array with the exact format specified in your instructions."""

            result = await llm.generate_str(extraction_prompt)

            try:
                requirements_data = json.loads(result)
            except json.JSONDecodeError:
                # Try to extract JSON array from the response
                import re

                json_match = re.search(r"\[.*\]", result, re.DOTALL)
                if json_match:
                    requirements_data = json.loads(json_match.group())
                else:
                    logger.warning("Could not parse requirements JSON, using existing")
                    return existing_requirements

            # Validate and add IDs if missing
            for req in requirements_data:
                if "id" not in req or not req["id"]:
                    req["id"] = str(uuid.uuid4())[:8]
                if "confidence" not in req:
                    req["confidence"] = 0.8
                if "status" not in req:
                    req["status"] = "pending"

            logger.info(
                "Requirements extracted",
                data={
                    "new_requirements": len(requirements_data),
                    "existing_requirements": len(existing_requirements),
                },
            )

            return requirements_data

    except Exception as e:
        logger.error(f"Requirement extraction failed: {str(e)}")
        # Preserve existing requirements on failure
        return existing_requirements


@app.workflow_task(name="consolidate_context_with_llm")
async def consolidate_context_with_llm(params: Dict[str, Any]) -> str:
    """
    LLM-based context consolidation to prevent lost-in-middle-turns.
    From paper Section 5.4.4.
    """
    logger = get_rcm_logger("context_consolidator")

    messages = params["messages"]
    requirements = params.get("requirements", [])
    previous_context = params.get("previous_context", "")
    config = params.get("config", {})

    try:
        # Create context consolidation agent
        consolidator_agent = Agent(
            name="context_consolidator",
            instruction=CONTEXT_CONSOLIDATOR_PROMPT,
            server_names=[],
        )

        async with consolidator_agent:
            llm_class = get_llm_class(config.get("evaluator_model_provider", "openai"))
            llm = await consolidator_agent.attach_llm(llm_class)

            # Build full conversation text
            conversation_text = "\n".join(
                [
                    f"Turn {msg.get('turn_number', 0)} ({msg.get('role', 'unknown')}): {msg.get('content', '')}"
                    for msg in messages
                    if msg.get("role") != "system"
                ]
            )

            # Build requirements text
            requirements_text = "\n".join(
                [
                    f"- {req.get('id', 'unknown')}: {req.get('description', '')} (Status: {req.get('status', 'pending')})"
                    for req in requirements
                ]
            )

            consolidation_prompt = f"""Consolidate this conversation context to prevent information loss.

FULL CONVERSATION:
{conversation_text}

CURRENT REQUIREMENTS:
{requirements_text}

PREVIOUS CONSOLIDATED CONTEXT:
{previous_context}

Create a consolidated context following your instructions. Focus on preserving middle turn information and all requirements."""

            result = await llm.generate_str(consolidation_prompt)

            logger.info(
                "Context consolidated",
                data={
                    "original_length": len(conversation_text),
                    "consolidated_length": len(result),
                    "compression_ratio": len(result) / len(conversation_text)
                    if conversation_text
                    else 0,
                },
            )

            return result

    except Exception as e:
        logger.error(f"Context consolidation failed: {str(e)}")
        # Fallback to simple concatenation
        fallback_context = "\n".join(
            [
                f"Turn {msg.get('turn_number', 0)}: {msg.get('content', '')}"
                for msg in messages[-5:]
                if msg.get("role") != "system"  # Last 5 messages
            ]
        )
        return fallback_context


def _detect_complete_solution_attempt(response: str) -> bool:
    """Detect if response contains markers of complete solution attempts"""
    solution_markers = [
        "here's the complete",
        "here is the full",
        "final solution",
        "complete implementation",
        "this should handle everything",
        "final answer",
        "complete response",
        "here's everything you need",
    ]

    response_lower = response.lower()
    return any(marker in response_lower for marker in solution_markers)


def _calculate_overall_score(metrics: Dict[str, Any]) -> float:
    """Calculate overall quality score from paper's formula"""
    clarity = metrics.get("clarity", 0.5)
    completeness = metrics.get("completeness", 0.5)
    assumptions = metrics.get("assumptions", 0.5)
    verbosity = metrics.get("verbosity", 0.5)
    middle_turn_reference = metrics.get("middle_turn_reference", 0.5)
    requirement_tracking = metrics.get("requirement_tracking", 0.5)
    premature_attempt = metrics.get("premature_attempt", False)

    base = (
        clarity
        + completeness
        + middle_turn_reference
        + requirement_tracking
        + (1 - assumptions)
        + (1 - verbosity)
    ) / 6

    if premature_attempt:
        base *= 0.5  # Heavy penalty from paper

    return base
