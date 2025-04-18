import asyncio
import os
import time
import sys

from mcp_agent.app import MCPApp
from mcp_agent.config import (
    Settings,
    LoggerSettings,
    MCPSettings,
    MCPServerSettings,
    OpenAISettings,
    AnthropicSettings,
)
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.llm_selector import ModelPreferences
from mcp_agent.workflows.llm.augmented_llm_anthropic import AnthropicAugmentedLLM
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

# Load the educational instructions from intellagent
EDUCATION_WIKI_PATH = "/home/ubuntu/mahtab/projects/intellagent/examples/education/input/wiki.md"

with open(EDUCATION_WIKI_PATH, "r") as f:
    EDUCATION_INSTRUCTIONS = f.read()

app = MCPApp(name="mcp_education_agent")

# Sample questions to demonstrate the agent's capabilities
SAMPLE_QUESTIONS = [
    "I'm stuck on this equation: 2x + 5 = 15. Can you help?",
    "Why does the moon change shape?",
    "I need to write a story about dinosaurs.",
    "How do plants make their own food?",
    "What's the difference between a simile and a metaphor?"
]

async def run_education_agent():
    async with app.run() as agent_app:
        logger = agent_app.logger
        context = agent_app.context

        logger.info("Current config:", data=context.config.model_dump())

        # Create an education agent based on the intellagent scenario
        education_agent = Agent(
            name="education_tutor",
            instruction=EDUCATION_INSTRUCTIONS,
            server_names=[]  # No server needed for basic conversation
        )

        async with education_agent:
            # Use either OpenAI or Anthropic model based on config
            if context.config.anthropic and context.config.anthropic.api_key:
                llm = await education_agent.attach_llm(AnthropicAugmentedLLM)
                logger.info("Using Anthropic model for education agent")
            else:
                llm = await education_agent.attach_llm(OpenAIAugmentedLLM)
                logger.info("Using OpenAI model for education agent")

            print("\n=== Education Tutor Assistant ===")
            print("This is a non-interactive demo. The agent will respond to sample questions.\n")
            
            # Run through sample questions when using uv run
            if len(sys.argv) > 1 and sys.argv[1] == "--non-interactive":
                for question in SAMPLE_QUESTIONS:
                    print(f"Student: {question}")
                    
                    start_time = time.time()
                    print("Tutor: ", end="", flush=True)
                    
                    result = await llm.generate_str(
                        message=question,
                        request_params=RequestParams(
                            modelPreferences=ModelPreferences(
                                intelligencePriority=0.8,
                                speedPriority=0.2,
                            ),
                        ),
                    )
                    
                    print(f"{result}")
                    logger.debug(f"Response time: {time.time() - start_time:.2f}s")
                    print("\n" + "-"*50 + "\n")
            else:
                # Interactive loop for normal usage
                print("(Type 'exit' to quit)\n")
                
                while True:
                    try:
                        user_input = input("Student: ")
                        if user_input.lower() == "exit":
                            break
                        
                        start_time = time.time()
                        print("Tutor: ", end="", flush=True)
                        
                        result = await llm.generate_str(
                            message=user_input,
                            request_params=RequestParams(
                                modelPreferences=ModelPreferences(
                                    intelligencePriority=0.8,
                                    speedPriority=0.2,
                                ),
                            ),
                        )
                        
                        print(f"{result}")
                        logger.debug(f"Response time: {time.time() - start_time:.2f}s")
                    
                    except (EOFError, KeyboardInterrupt):
                        print("\nExiting...")
                        break

if __name__ == "__main__":
    start = time.time()
    
    # Always use non-interactive mode when run with uv run
    # Even with normal Python, check if stdin is not a TTY
    is_non_interactive = not sys.stdin.isatty()
    if is_non_interactive:
        print("Detected non-interactive environment. Using sample questions mode.")
        if "--non-interactive" not in sys.argv:
            sys.argv.append("--non-interactive")
    
    asyncio.run(run_education_agent())
    end = time.time()
    t = end - start
    
    print(f"\nTotal session time: {t:.2f}s")