"""
Task functions for RCM quality control.
Implements paper methodologies with robust fallbacks.
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
from models.conversation_models import ConversationState
from utils.progress_reporter import (
    report_step,
    report_thinking,
    report_quality_check,
    report_requirement_extraction,
    report_context_consolidation,
    show_llm_interaction,
)

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
]"""

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


async def evaluate_quality_with_llm(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    LLM-based quality evaluation implementing paper's quality dimensions.
    With robust fallbacks for when LLM providers are not available.
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
        # Try LLM-based evaluation
        evaluator_agent = Agent(
            name="quality_evaluator",
            instruction=QUALITY_EVALUATOR_PROMPT,
            server_names=[],
        )

        async with evaluator_agent:
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

            # Show the LLM interaction for transparency
            show_llm_interaction(
                "Quality Evaluator", evaluation_prompt, result, truncate_at=800
            )

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
        logger.warning(
            f"LLM quality evaluation failed, using heuristic fallback: {str(e)}"
        )

        # Robust heuristic fallback based on paper findings
        response_length = len(response)
        word_count = len(response.split())

        # Heuristic scoring based on response characteristics
        clarity = 0.8 if response_length > 50 and "." in response else 0.5
        completeness = min(
            1.0, word_count / 100
        )  # Longer responses tend to be more complete
        assumptions = (
            0.3
            if any(
                word in response.lower() for word in ["assume", "probably", "might be"]
            )
            else 0.2
        )
        verbosity = min(
            1.0, max(0.1, (response_length - 200) / 1000)
        )  # Penalty for very long responses
        premature_attempt = has_complete_solution_markers and len(pending_reqs) > 1
        middle_turn_reference = 0.3 if turn_number > 3 else 0.5  # Default assumption
        requirement_tracking = 0.4 if len(pending_reqs) > 0 else 0.6

        fallback_metrics = {
            "clarity": clarity,
            "completeness": completeness,
            "assumptions": assumptions,
            "verbosity": verbosity,
            "premature_attempt": premature_attempt,
            "middle_turn_reference": middle_turn_reference,
            "requirement_tracking": requirement_tracking,
            "issues": [f"Heuristic evaluation due to LLM unavailability: {str(e)}"],
            "strengths": ["Response generated successfully"],
            "improvement_suggestions": [
                "Consider using LLM evaluation for better quality assessment"
            ],
        }

        return {
            "metrics": fallback_metrics,
            "issues": fallback_metrics["issues"],
            "evaluator_raw_response": f"Heuristic evaluation: {str(e)}",
        }


async def extract_requirements_with_llm(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    LLM-based requirement extraction to prevent instruction forgetting.
    With robust fallbacks for when LLM providers are not available.
    """
    logger = get_rcm_logger("requirement_extractor")

    messages = params["messages"]
    existing_requirements = params.get("existing_requirements", [])
    config = params.get("config", {})

    try:
        # Try LLM-based extraction
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

            # Show the LLM interaction for transparency
            show_llm_interaction(
                "Requirement Extractor", extraction_prompt, result, truncate_at=800
            )

            try:
                requirements_data = json.loads(result)
            except json.JSONDecodeError:
                # Try to extract JSON array from the response
                import re

                json_match = re.search(r"\[.*\]", result, re.DOTALL)
                if json_match:
                    requirements_data = json.loads(json_match.group())
                else:
                    logger.warning(
                        "Could not parse requirements JSON, using heuristic fallback"
                    )
                    raise ValueError("JSON parsing failed")

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
        logger.warning(
            f"LLM requirement extraction failed, using heuristic fallback: {str(e)}"
        )

        # Heuristic fallback - extract basic requirements from user messages
        heuristic_requirements = []

        for msg in messages:
            if msg.get("role") == "user":
                content = msg.get("content", "").lower()
                turn_number = msg.get("turn_number", 0)

                # Simple keyword-based requirement detection
                requirement_indicators = [
                    "help me with",
                    "i need",
                    "can you",
                    "please",
                    "show me",
                    "explain",
                    "how to",
                    "what is",
                    "implement",
                    "create",
                ]

                if any(indicator in content for indicator in requirement_indicators):
                    req_id = str(uuid.uuid4())[:8]
                    description = f"User request from turn {turn_number}: {msg.get('content', '')[:100]}..."

                    heuristic_requirements.append(
                        {
                            "id": req_id,
                            "description": description,
                            "source_turn": turn_number,
                            "status": "pending",
                            "confidence": 0.6,  # Lower confidence for heuristic extraction
                        }
                    )

        # Include existing requirements if new extraction failed
        all_requirements = existing_requirements + heuristic_requirements

        logger.info(
            "Heuristic requirements extracted",
            data={
                "heuristic_requirements": len(heuristic_requirements),
                "total_requirements": len(all_requirements),
            },
        )

        return all_requirements


async def consolidate_context_with_llm(params: Dict[str, Any]) -> str:
    """
    LLM-based context consolidation to prevent lost-in-middle-turns.
    With robust fallbacks for when LLM providers are not available.
    """
    logger = get_rcm_logger("context_consolidator")

    messages = params["messages"]
    requirements = params.get("requirements", [])
    previous_context = params.get("previous_context", "")
    config = params.get("config", {})

    try:
        # Try LLM-based consolidation
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

            # Show the LLM interaction for transparency
            show_llm_interaction(
                "Context Consolidator", consolidation_prompt, result, truncate_at=800
            )

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
        logger.warning(
            f"LLM context consolidation failed, using heuristic fallback: {str(e)}"
        )

        # Heuristic fallback - simple context summarization
        recent_messages = (
            messages[-10:] if len(messages) > 10 else messages
        )  # Keep last 10 messages

        # Build fallback context
        context_parts = []

        # Add requirements summary
        if requirements:
            context_parts.append("REQUIREMENTS:")
            for req in requirements:
                status = req.get("status", "pending")
                desc = req.get("description", "")[:100]  # Truncate long descriptions
                context_parts.append(f"- {desc} (Status: {status})")
            context_parts.append("")

        # Add recent conversation
        context_parts.append("RECENT CONVERSATION:")
        for msg in recent_messages:
            if msg.get("role") != "system":
                role = msg.get("role", "unknown").title()
                content = msg.get("content", "")[:200]  # Truncate long messages
                context_parts.append(f"{role}: {content}")

        fallback_context = "\n".join(context_parts)

        logger.info(
            "Heuristic context consolidation completed",
            data={
                "messages_included": len(recent_messages),
                "requirements_included": len(requirements),
                "fallback_length": len(fallback_context),
            },
        )

        return fallback_context


async def generate_response_with_constraints(params: Dict[str, Any]) -> str:
    """
    Generate response with quality constraints and context awareness.
    With robust fallbacks for when LLM providers are not available.
    """
    logger = get_rcm_logger("response_generator")

    messages = params["messages"]
    consolidated_context = params.get("consolidated_context", "")
    requirements = params.get("requirements", [])
    attempt = params.get("attempt", 0)
    previous_issues = params.get("previous_issues", [])
    config = params.get("config", {})

    try:
        # Try LLM-based generation
        generator_agent = Agent(
            name="constrained_generator",
            instruction=f"""You are a helpful assistant that generates high-quality responses with awareness of conversation context and requirements.

QUALITY GUIDELINES:
1. Be clear and well-structured
2. Address pending requirements appropriately
3. Avoid making unsupported assumptions
4. Be concise without being incomplete
5. Reference information from previous turns when relevant
6. Track and acknowledge user requirements across turns

AVOID:
- Premature complete solutions when requirements are still pending
- Excessive verbosity and answer bloat
- Ignoring information from middle conversation turns
- Making assumptions about unstated details

This is attempt {attempt + 1}. {"Previous issues to address: " + str(previous_issues) if previous_issues else "First attempt - focus on quality."}""",
            server_names=config.get("mcp_servers", []),
        )

        async with generator_agent:
            llm_class = get_llm_class(config.get("evaluator_model_provider", "openai"))
            llm = await generator_agent.attach_llm(llm_class)

            # Build context-aware prompt
            conversation_text = "\n".join(
                [
                    f"{msg['role'].title()}: {msg['content']}"
                    for msg in messages[-5:]
                    if msg["role"] != "system"  # Last 5 messages
                ]
            )

            pending_reqs = [r for r in requirements if r.get("status") == "pending"]
            requirements_text = (
                "\n".join([f"- {req['description']}" for req in pending_reqs])
                if pending_reqs
                else "No pending requirements"
            )

            generation_prompt = f"""Based on the conversation context and requirements, provide a helpful response.

RECENT CONVERSATION:
{conversation_text}

CONSOLIDATED CONTEXT:
{consolidated_context}

PENDING REQUIREMENTS:
{requirements_text}

Respond naturally while being mindful of quality guidelines. {"Address these previous issues: " + str(previous_issues) if previous_issues else ""}"""

            response = await llm.generate_str(generation_prompt)

            # Show the LLM interaction for transparency
            show_llm_interaction(
                "Response Generator", generation_prompt, response, truncate_at=800
            )

            logger.info(
                "Response generated",
                data={
                    "attempt": attempt + 1,
                    "response_length": len(response),
                    "pending_requirements": len(pending_reqs),
                },
            )

            return response

    except Exception as e:
        logger.warning(
            f"LLM response generation failed, using template fallback: {str(e)}"
        )

        # Template-based fallback response
        last_user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_message = msg.get("content", "")
                break

        pending_reqs = [r for r in requirements if r.get("status") == "pending"]

        # Generate a reasonable fallback response
        if pending_reqs:
            fallback_response = f"Thank you for your message about '{last_user_message[:50]}...'. I understand you have {len(pending_reqs)} pending requirement(s). I'm working on addressing: {', '.join([req.get('description', '')[:50] for req in pending_reqs[:2]])}. Let me provide what I can based on our conversation so far."
        else:
            fallback_response = f"Thank you for your message: '{last_user_message[:100]}...'. I'm here to help and will do my best to provide a useful response based on our conversation context."

        if previous_issues:
            fallback_response += (
                f" (Attempt {attempt + 1} - addressing previous feedback)"
            )

        logger.info(
            "Template fallback response generated",
            data={
                "attempt": attempt + 1,
                "response_length": len(fallback_response),
                "pending_requirements": len(pending_reqs),
            },
        )

        return fallback_response


async def process_turn_with_quality(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main turn processing implementing paper's quality refinement methodology.
    With robust fallbacks at every step.
    """
    logger = get_rcm_logger("quality_control")

    state_dict = params["state"]
    config = params["config"]

    # Recreate state object
    state = ConversationState.from_dict(state_dict)

    logger.info(
        "Starting quality-controlled turn processing",
        data={"conversation_id": state.conversation_id, "turn": state.current_turn},
    )

    report_thinking("Starting quality-controlled turn processing")

    try:
        # Step 1: Extract requirements (with fallback)
        report_step("Extracting requirements from conversation")
        requirements = await extract_requirements_with_llm(
            {
                "messages": [m.to_dict() for m in state.messages],
                "existing_requirements": [r.to_dict() for r in state.requirements],
                "config": config,
            }
        )
        report_requirement_extraction(len(requirements))

        # Step 2: Consolidate context if needed (with fallback)
        consolidated_context = state.consolidated_context
        context_consolidated = False

        if _should_consolidate_context(state, config):
            report_step("Context consolidation needed", f"turn {state.current_turn}")
            logger.info(
                "Consolidating context",
                data={"turn": state.current_turn, "trigger": "consolidation_interval"},
            )

            old_length = len(state.consolidated_context)
            consolidated_context = await consolidate_context_with_llm(
                {
                    "messages": [m.to_dict() for m in state.messages],
                    "requirements": requirements,
                    "previous_context": state.consolidated_context,
                    "config": config,
                }
            )
            context_consolidated = True
            report_context_consolidation(old_length, len(consolidated_context))
        else:
            report_step("Context consolidation skipped", "not needed this turn")

        # Step 3: Generate response with quality refinement loop (with fallbacks)
        best_response = ""
        best_metrics = None
        max_attempts = config.get("max_refinement_attempts", 3)

        report_step("Starting response generation", f"max {max_attempts} attempts")

        for attempt in range(max_attempts):
            report_step(f"Generating response attempt {attempt + 1}/{max_attempts}")
            logger.info(
                "Generating response attempt",
                data={"attempt": attempt + 1, "max_attempts": max_attempts},
            )

            # Generate response (with fallback)
            response = await generate_response_with_constraints(
                {
                    "messages": [m.to_dict() for m in state.messages],
                    "consolidated_context": consolidated_context,
                    "requirements": requirements,
                    "attempt": attempt,
                    "previous_issues": []
                    if attempt == 0
                    else best_metrics.get("issues", []),
                    "config": config,
                }
            )

            # Evaluate quality (with fallback)
            report_step("Evaluating response quality")
            evaluation = await evaluate_quality_with_llm(
                {
                    "response": response,
                    "consolidated_context": consolidated_context,
                    "requirements": requirements,
                    "turn_number": state.current_turn,
                    "conversation_history": [m.to_dict() for m in state.messages],
                    "config": config,
                }
            )

            metrics = evaluation["metrics"]
            overall_score = _calculate_overall_score(metrics)

            # Track best response
            if best_metrics is None or overall_score > best_metrics.get(
                "overall_score", 0
            ):
                best_response = response
                best_metrics = {
                    "metrics": metrics,
                    "issues": evaluation.get("issues", []),
                    "overall_score": overall_score,
                }

            # Report quality evaluation
            report_quality_check(overall_score, len(evaluation.get("issues", [])))

            # Check quality threshold
            quality_threshold = config.get("quality_threshold", 0.8)
            if overall_score >= quality_threshold:
                report_step(
                    "Quality threshold met",
                    f"score {overall_score:.0%} >= {quality_threshold:.0%}",
                )
                logger.info(
                    "Quality threshold met",
                    data={
                        "attempt": attempt + 1,
                        "score": overall_score,
                        "threshold": quality_threshold,
                    },
                )
                break
            else:
                report_step(
                    "Quality below threshold",
                    f"score {overall_score:.0%} < {quality_threshold:.0%}, continuing",
                )
                logger.info(
                    "Quality below threshold, continuing refinement",
                    data={
                        "attempt": attempt + 1,
                        "score": overall_score,
                        "threshold": quality_threshold,
                        "issues": evaluation.get("issues", []),
                    },
                )

        logger.info(
            "Quality-controlled turn processing completed",
            data={
                "final_score": best_metrics["overall_score"],
                "refinement_attempts": attempt + 1,
                "context_consolidated": context_consolidated,
            },
        )

        return {
            "response": best_response,
            "requirements": requirements,
            "consolidated_context": consolidated_context,
            "context_consolidated": context_consolidated,
            "metrics": best_metrics["metrics"],
            "refinement_attempts": attempt + 1,
        }

    except Exception as e:
        logger.error(
            f"Quality-controlled processing failed completely, using basic fallback: {str(e)}"
        )

        # Ultimate fallback - return basic response structure
        last_user_message = ""
        for msg in reversed(state.messages):
            if msg.to_dict().get("role") == "user":
                last_user_message = msg.to_dict().get("content", "")
                break

        fallback_response = f"Thank you for your message. I encountered some technical difficulties but will do my best to help you with: '{last_user_message[:100]}...'"

        fallback_metrics = {
            "clarity": 0.5,
            "completeness": 0.4,
            "assumptions": 0.6,
            "verbosity": 0.3,
            "premature_attempt": False,
            "middle_turn_reference": 0.3,
            "requirement_tracking": 0.3,
            "issues": [f"Complete system fallback due to: {str(e)}"],
            "strengths": ["System remained operational"],
            "improvement_suggestions": ["Check system configuration and connectivity"],
        }

        return {
            "response": fallback_response,
            "requirements": [
                req.to_dict() for req in state.requirements
            ],  # Preserve existing
            "consolidated_context": state.consolidated_context,  # Preserve existing
            "context_consolidated": False,
            "metrics": fallback_metrics,
            "refinement_attempts": 1,
        }


def _should_consolidate_context(
    state: ConversationState, config: Dict[str, Any]
) -> bool:
    """Determine if context consolidation is needed based on paper findings"""
    consolidation_interval = config.get("consolidation_interval", 3)

    return (
        state.current_turn % consolidation_interval == 0  # Every N turns
        or len(state.consolidated_context) > 2000  # Long context threshold
        or state.current_turn == 1  # Always consolidate first turn
    )


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


# No registration needed - these are regular async functions called directly by workflows
