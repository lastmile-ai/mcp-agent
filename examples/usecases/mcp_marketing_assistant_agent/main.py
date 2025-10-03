#!/usr/bin/env python3
"""
Marketing Content Agent
==========================================================
Agentic system using EvaluatorOptimizerLLM with comprehensive context.
"""

import asyncio
import sys
import yaml
import os
from datetime import datetime
from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.evaluator_optimizer.evaluator_optimizer import (
    EvaluatorOptimizerLLM,
    QualityRating,
)

# Configuration constants
CONFIG_FILE = "company_config.yaml"
OUTPUT_DIR = "posts"
CONTENT_SAMPLES_DIR = "content_samples"
COMPANY_DOCS_DIR = "company_docs"

# Initialize the main application
app = MCPApp(name="marketing_content_agent")


def detect_platform(request: str) -> str:
    """
    Detect the intended platform from the user's request.
    Defaults to 'linkedin' if no platform is found.
    """
    request_lower = request.lower()
    platforms = ["twitter", "linkedin", "instagram", "facebook", "email", "reddit"]
    for platform in platforms:
        if platform in request_lower:
            return platform
    return "linkedin"  # Default platform


def load_company_config() -> dict:
    """
    Load the company configuration from CONFIG_FILE.
    Returns a default config if the file is not found.
    """
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print(f"⚠️ {CONFIG_FILE} not found. Using default config...")
        return {
            "company": {"name": "Your Company"},
            "platforms": {"linkedin": {"max_word_count": 150}},
        }


async def main():
    """
    Main function: Orchestrates the agent workflow for content creation,
    evaluation, user feedback, and learning.
    """
    print("🎯 Marketing Content Agent")
    print("🤖 EvaluatorOptimizerLLM + Comprehensive Context")

    # Get user request from command line or prompt
    if len(sys.argv) > 1:
        request = " ".join(sys.argv[1:])
    else:
        request = input("\nWhat content would you like me to create? ").strip()

    if not request:
        print("❌ No request provided")
        return False

    # Load configuration and determine platform
    platform = detect_platform(request)
    config = load_company_config()
    company_name = config["company"]["name"]

    # Ensure required directories exist
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(CONTENT_SAMPLES_DIR, exist_ok=True)
    os.makedirs(COMPANY_DOCS_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"{platform}_content_{timestamp}.md"
    output_path = os.path.join(OUTPUT_DIR, output_file)

    async with app.run() as content_app:
        logger = content_app.logger

        logger.info(f"Creating {platform} content for {company_name}")

        # --- Define Agents ---

        # Content Creator Agent: generates two content variations
        content_creator = Agent(
            name="content_creator",
            instruction=f"""You are an expert marketing content creator for {company_name}, with 15+ years of experience in digital marketing and brand storytelling.

ROLE: Senior Content Strategist who deeply understands {company_name}'s voice and consistently creates high-performing content.

TASK: Create 2 distinct, compelling content variations for: "{request}"
PLATFORM: {platform}

THOUGHT PROCESS (follow this exactly):

1. RESEARCH & CONTEXT (2-3 min)
   - Search memory for user preferences: search_nodes "user_preference {platform}"
   - Review content samples: List & read 2-3 files from content_samples/
   - Study brand guidelines: Read files in company_docs/
   - Analyze company_config.yaml for voice, requirements, and quality standards
   - For URLs in request: Use fetch tool to gather context

2. CONTENT STRATEGY (1-2 min)
   - Target Audience: Who exactly am I writing for?
   - Key Message: What's the ONE thing they need to know?
   - Value Prop: Why should they care?
   - Emotional Hook: What will make them stop scrolling?
   - Call to Action: What should they do next?

3. WRITE TWO DISTINCT APPROACHES (5-7 min)
   VERSION A - DIRECT & DATA-DRIVEN
   - Lead with specific numbers/results
   - Focus on practical value
   - Use clear, authoritative voice
   - Include concrete examples
   
   VERSION B - NARRATIVE & EMOTIONAL
   - Start with a hook/story
   - Build emotional connection
   - Use vivid language
   - Make it personally relevant

4. QUALITY CHECK (2-3 min)
   ✓ Matches brand voice perfectly
   ✓ Follows {platform} best practices
   ✓ No banned phrases or corporate speak
   ✓ Specific details (no vague claims)
   ✓ Natural, human tone
   ✓ Clear call to action
   ✓ Proper length for platform

OUTPUT FORMAT:

VERSION A: [Brief strategy explanation]
[Content that reads exactly like a skilled human wrote it]

VERSION B: [Brief strategy explanation]
[Content that reads exactly like a skilled human wrote it]

CRITICAL RULES:
- Write like a human expert, not an AI, natural and conversational tone
- Be specific - use real examples, numbers, and details
- Never use banned phrases or corporate jargon
- Make each version genuinely different in approach
- Stay within platform word limits
- Sound natural and conversational""",
            server_names=["memory", "fetch", "filesystem", "markitdown"],
        )

        # Quality Evaluator Agent: rates and reviews content
        quality_evaluator = Agent(
            name="quality_evaluator",
            instruction=f"""You are a highly selective Chief Marketing Officer for {company_name} with 20+ years of experience building world-class brands.

ROLE: Your job is to ensure ONLY the highest quality content represents our brand. You have a reputation for maintaining exceptional standards and catching even subtle issues that could weaken our brand voice.

EVALUATION PROCESS (follow exactly):

1. PREPARATION (2-3 min)
   - Study company_config.yaml quality standards
   - Review content samples for benchmark quality
   - Analyze brand guidelines for voice requirements
   - Note platform-specific rules for {platform}

2. DEEP ANALYSIS (4-5 min for each version)
   
   BRAND VOICE (Must match ALL)
   - Perfectly matches our personality
   - Uses approved tone keywords
   - Avoids ALL banned phrases
   - Sounds authentically human
   - Consistent voice throughout

   CONTENT QUALITY (Must have ALL)
   - Clear, specific value proposition
   - Real examples/numbers/details
   - Zero filler or fluff words
   - Natural flow and structure
   - Proper length for platform
   - Compelling call to action

   ENGAGEMENT POTENTIAL (Must have 3+)
   - Stops the scroll
   - Drives meaningful interaction
   - Provides actual value
   - Creates emotional connection
   - Inspires action

   RED FLAGS (ANY of these = automatic POOR rating)
   - Generic marketing speak
   - Vague or unsubstantiated claims
   - Corporate or AI-like tone
   - Missing specific details
   - Banned phrases used
   - Wrong platform format

3. RATING SYSTEM

   EXCELLENT (Must meet ALL criteria)
   - Exceeds every quality standard
   - Perfect brand voice match
   - Highly engaging approach
   - Zero improvements needed
   - Ready to publish as-is

   GOOD (Minor issues)
   - Meets most standards
   - Mostly on-brand voice
   - Generally engaging
   - Needs small tweaks
   
   FAIR (Notable issues)
   - Missing some standards
   - Inconsistent brand voice
   - Limited engagement
   - Needs significant revision

   POOR (Major issues)
   - Fails multiple standards
   - Off-brand voice
   - Not engaging
   - Complete rewrite needed

OUTPUT FORMAT:

VERSION [A/B] EVALUATION:
Rating: [EXCELLENT/GOOD/FAIR/POOR]

Strengths:
• [Specific strength with example]
• [Specific strength with example]
• [Specific strength with example]

Areas for Improvement:
• [Specific issue + how to fix]
• [Specific issue + how to fix]

Brand Alignment: [Detailed assessment]

CRITICAL RULES:
- Be extremely selective
- Rate EXCELLENT only if truly perfect
- Provide specific examples for every point
- Focus on substance over style
- Consider target audience impact
- Flag ANY banned phrases or corporate speak""",
            server_names=["filesystem", "markitdown"],
        )

        # EvaluatorOptimizerLLM: Combines content creation and evaluation
        content_quality_system = EvaluatorOptimizerLLM(
            optimizer=content_creator,
            evaluator=quality_evaluator,
            llm_factory=OpenAIAugmentedLLM,
            min_rating=QualityRating.EXCELLENT,
        )

        # Memory Manager Agent: stores user feedback and choices
        memory_manager = Agent(
            name="memory_manager",
            instruction=f"""You are a simple learning system for {company_name} marketing content.

When given feedback or user choices, store them as simple entities.

For feedback: Create one entity with the feedback details.
For user choices: Create one entity with what they chose.

Use create_entities tool with simple structure:
- name: unique identifier with timestamp
- entityType: "user_preference" 
- observations: array with the learning data

Keep it simple - one entity per learning.""",
            server_names=["memory"],
        )

        # Attach LLM to memory manager agent
        memory_manager_llm = OpenAIAugmentedLLM(agent=memory_manager)

        # Main content creation and feedback loop
        logger.info("Starting content creation workflow")

        try:
            feedback_context = ""  # Holds the latest user feedback for context

            while True:
                # Build the content creation task, including any user feedback
                task = f"""Create 2 excellent content variations for: "{request}"

Platform: {platform}
Company: {company_name}

{feedback_context}

Use all available context sources (memory, filesystem, config, URLs) to create the best possible content.
Ensure both versions meet EXCELLENT quality standards but offer different approaches.

Present the final result as:

VERSION A: [approach description]
[content]

VERSION B: [approach description]  
[content]

Both versions should be complete, ready-to-post content."""

                # Generate content using the optimizer/evaluator system
                result = await content_quality_system.generate_str(
                    message=task, request_params=RequestParams(model="gpt-4o")
                )

                # Display content options to the user
                print(f"\n{'=' * 60}")
                if feedback_context:
                    print("🎯 IMPROVED CONTENT OPTIONS (Based on your feedback):")
                else:
                    print("🎯 EXCELLENT CONTENT OPTIONS:")
                print(f"{'=' * 60}")
                print(result)
                print(f"{'=' * 60}")

                # Prompt user for their choice or feedback
                while True:
                    choice = (
                        input("\nWhich version do you prefer? (A/B/feedback/quit): ")
                        .strip()
                        .upper()
                    )
                    if choice in ["A", "B", "FEEDBACK", "QUIT"]:
                        break
                    print("Please enter A, B, feedback, or quit")

                if choice == "QUIT":
                    logger.info("User cancelled")
                    return False

                # Handle user feedback and regenerate content if needed
                if choice == "FEEDBACK":
                    feedback = input(
                        "\nWhat feedback do you have? What would you like me to improve? "
                    ).strip()
                    if not feedback:
                        print("No feedback provided, continuing...")
                        continue

                    # Store feedback in memory for future learning
                    feedback_task = f"""Store this user feedback as a simple learning:

Feedback: "{feedback}"
Platform: {platform}
Request: "{request}"

Create one simple entity to remember this feedback."""

                    await memory_manager_llm.generate_str(
                        message=feedback_task,
                        request_params=RequestParams(model="gpt-4o-mini"),
                    )

                    # Update feedback context for the next content generation
                    feedback_context = f"""CRITICAL USER FEEDBACK TO ADDRESS: "{feedback}"

The user was not satisfied with the previous attempt. You must completely change your approach to fix their specific complaints.

Previous content failed because: {feedback}

Create entirely new content that directly addresses and fixes these issues."""

                    print(
                        "🧠 Feedback stored! Creating completely new content based on your input..."
                    )
                    continue  # Regenerate content with new feedback

                # If user chose A or B, exit loop to save and learn
                break

            # Store the user's choice in memory for future learning
            learning_task = f"""Store this user choice as a simple learning:

User chose: VERSION {choice}
Platform: {platform} 
Request: "{request}"

Create one simple entity to remember this choice."""

            await memory_manager_llm.generate_str(
                message=learning_task, request_params=RequestParams(model="gpt-4o-mini")
            )

            # Save the selected content to file
            content_to_save = f"""---
platform: {platform}
version: {choice}
company: {company_name}
created: {datetime.now().isoformat()}
request: "{request}"
---

{result}
"""

            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content_to_save)

            print(f"\n✅ Great choice! Content saved to: {output_path}")
            print(" Learned from your preference for future content")

            logger.info(f"Content successfully created and saved to {output_path}")
            return True

        except Exception as e:
            logger.error(f"Error during content creation: {str(e)}")
            print(f"❌ Error: {e}")
            return False


if __name__ == "__main__":
    # Run the main async function and exit with appropriate status code
    success = asyncio.run(main())
    exit(0 if success else 1)
