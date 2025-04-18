#!/usr/bin/env python3
"""
Generalized MCP Agent Framework with Evaluation Support

This is a generalized framework for running and evaluating various 
intellagent scenarios (education, airline, retail, etc.) with MCP Agent.
"""

import asyncio
import os
import sys
import time
import argparse
from typing import Optional, Dict, Any, List

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

# Define available scenarios
SCENARIOS = {
    "education": {
        "wiki_path": "/home/ubuntu/mahtab/projects/intellagent/examples/education/input/wiki.md",
        "agent_name": "education_tutor",
        "sample_questions": [
            "I'm stuck on this equation: 2x + 5 = 15. Can you help?",
            "Why does the moon change shape?",
            "I need to write a story about dinosaurs.",
            "How do plants make their own food?",
            "What's the difference between a simile and a metaphor?"
        ]
    },
    "airline": {
        "wiki_path": "/home/ubuntu/mahtab/projects/intellagent/examples/airline/input/wiki.md",
        "agent_name": "airline_assistant",
        "sample_questions": [
            "I need to change my flight from New York to Los Angeles tomorrow.",
            "What's your baggage policy for international flights?",
            "My flight was delayed by 3 hours. Am I eligible for compensation?",
            "I have a layover in Chicago. How much time do I need to make my connection?",
            "Can I bring my pet on the flight?"
        ]
    },
}

app = MCPApp(name="mcp_scenario_agent")

async def run_scenario_agent(scenario_name: str, non_interactive: bool = False):
    """Run the agent for a specific scenario."""
    # Validate scenario
    if scenario_name not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario_name}. Available scenarios: {', '.join(SCENARIOS.keys())}")
    
    scenario = SCENARIOS[scenario_name]
    
    # Load the scenario instructions
    with open(scenario["wiki_path"], "r") as f:
        instructions = f.read()
    
    async with app.run() as agent_app:
        logger = agent_app.logger
        context = agent_app.context

        logger.info("Current config:", data=context.config.model_dump())

        # Create an agent based on the selected scenario
        scenario_agent = Agent(
            name=scenario["agent_name"],
            instruction=instructions,
            server_names=[]  # No server needed for basic conversation
        )

        async with scenario_agent:
            # Use either OpenAI or Anthropic model based on config
            if context.config.anthropic and context.config.anthropic.api_key:
                llm = await scenario_agent.attach_llm(AnthropicAugmentedLLM)
                logger.info(f"Using Anthropic model for {scenario_name} agent")
            else:
                llm = await scenario_agent.attach_llm(OpenAIAugmentedLLM)
                logger.info(f"Using OpenAI model for {scenario_name} agent")

            print(f"\n=== {scenario_name.title()} Assistant ===")
            
            # Run through sample questions in non-interactive mode
            if non_interactive:
                print(f"This is a non-interactive demo. The agent will respond to sample questions for the {scenario_name} scenario.\n")
                
                for question in scenario["sample_questions"]:
                    print(f"User: {question}")
                    
                    start_time = time.time()
                    print("Assistant: ", end="", flush=True)
                    
                    # Check if API key is missing and use mock response if needed
                    try:
                        result = await llm.generate_str(
                            message=question,
                            request_params=RequestParams(
                                modelPreferences=ModelPreferences(
                                    intelligencePriority=0.8,
                                    speedPriority=0.2,
                                ),
                            ),
                        )
                    except Exception as e:
                        # Use a mock response for demonstration
                        print(f"Error generating response: {e}")
                        print("Using simulated response for demonstration...")
                        
                        # Simulated responses based on question types
                        if "change my flight" in question.lower():
                            result = "I'd be happy to help you change your flight from New York to Los Angeles tomorrow. To assist you better, I'll need your booking reference number and some details about your preferred new flight time. There is a change fee of $50 for basic economy tickets and no fee for premium tickets. Would you like me to check available flights for tomorrow?"
                        elif "baggage policy" in question.lower():
                            result = "For international flights, our baggage policy allows one checked bag up to 23kg (50 pounds) for free. Additional bags cost $75 each. Carry-on allowance includes one personal item and one carry-on bag not exceeding dimensions of 56cm x 36cm x 23cm (22\" x 14\" x 9\"). Overweight bags between 23-32kg incur a fee of $100."
                        elif "delayed" in question.lower() and "compensation" in question.lower():
                            result = "I'm sorry to hear about your flight delay. For delays of 3 hours or more, you may be eligible for compensation according to our policy. For domestic flights, we offer meal vouchers and, if the delay extends overnight, hotel accommodations. For specific financial compensation, you'll need to file a claim through our customer service portal with your flight details and boarding pass. Would you like me to explain how to submit this claim?"
                        elif "layover" in question.lower() or "connection" in question.lower():
                            result = "For domestic connections at Chicago O'Hare airport, we recommend at least 60 minutes between flights. This allows sufficient time to deplane, navigate to your next gate (which could be in a different terminal), and board your connecting flight. If you have checked baggage, it will be automatically transferred to your next flight."
                        elif "pet" in question.lower():
                            result = "Yes, you can bring your pet on the flight, but there are some restrictions. Small dogs and cats that fit in a carrier under the seat can travel in the cabin for a fee of $125. Larger pets must travel in the temperature-controlled cargo hold for $200. Service animals are allowed in the cabin at no extra charge with proper documentation. What type and size of pet will be traveling with you?"
                        else:
                            result = "I'd be happy to help you with your question about our airline services. Could you provide a bit more information so I can assist you better?"
                    
                    print(f"{result}")
                    logger.debug(f"Response time: {time.time() - start_time:.2f}s")
                    print("\n" + "-"*50 + "\n")
            else:
                # Interactive loop for normal usage
                print("(Type 'exit' to quit)\n")
                
                while True:
                    try:
                        user_input = input("User: ")
                        if user_input.lower() == "exit":
                            break
                        
                        start_time = time.time()
                        print("Assistant: ", end="", flush=True)
                        
                        # Check if API key is missing and use mock response if needed
                        try:
                            result = await llm.generate_str(
                                message=user_input,
                                request_params=RequestParams(
                                    modelPreferences=ModelPreferences(
                                        intelligencePriority=0.8,
                                        speedPriority=0.2,
                                    ),
                                ),
                            )
                        except Exception as e:
                            # Use a mock response for demonstration
                            print(f"Error generating response: {e}")
                            print("Using simulated response for demonstration...")
                            
                            # Simulated responses based on input types
                            if "change my flight" in user_input.lower():
                                result = "I'd be happy to help you change your flight. To assist you better, I'll need your booking reference number and some details about your preferred new flight time. There is a change fee of $50 for basic economy tickets and no fee for premium tickets. Would you like me to check available flights for you?"
                            elif "baggage" in user_input.lower() or "luggage" in user_input.lower():
                                result = "Our baggage policy allows one checked bag up to 23kg (50 pounds) for free. Additional bags cost $75 each. Carry-on allowance includes one personal item and one carry-on bag not exceeding dimensions of 56cm x 36cm x 23cm (22\" x 14\" x 9\"). Overweight bags between 23-32kg incur a fee of $100."
                            elif "delayed" in user_input.lower() or "cancel" in user_input.lower():
                                result = "I'm sorry to hear about your flight issue. For delays of 3 hours or more, you may be eligible for compensation according to our policy. For cancellations, we offer either a full refund or rebooking on the next available flight. Would you like me to explain the specific options for your situation?"
                            elif "pet" in user_input.lower() or "animal" in user_input.lower():
                                result = "Yes, you can bring your pet on the flight, but there are some restrictions. Small dogs and cats that fit in a carrier under the seat can travel in the cabin for a fee of $125. Larger pets must travel in the temperature-controlled cargo hold for $200. Service animals are allowed in the cabin at no extra charge with proper documentation."
                            else:
                                result = "I'd be happy to help you with your question about our airline services. Could you provide a bit more information so I can assist you better?"
                        
                        print(f"{result}")
                        logger.debug(f"Response time: {time.time() - start_time:.2f}s")
                    
                    except (EOFError, KeyboardInterrupt):
                        print("\nExiting...")
                        break

if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Run an MCP Agent for a specific scenario")
    parser.add_argument(
        "--scenario", 
        type=str, 
        default="education",
        choices=SCENARIOS.keys(),
        help=f"Scenario to run. Available options: {', '.join(SCENARIOS.keys())}"
    )
    parser.add_argument(
        "--non-interactive", 
        action="store_true",
        help="Run in non-interactive mode with sample questions"
    )
    
    args = parser.parse_args()
    
    # Detect if we're running with uv run and set non-interactive mode
    is_non_interactive = args.non_interactive
    if not is_non_interactive and not sys.stdin.isatty():
        print("Detected non-interactive environment. Switching to non-interactive mode.")
        is_non_interactive = True
    
    # Run the selected scenario
    start = time.time()
    asyncio.run(run_scenario_agent(args.scenario, is_non_interactive))
    end = time.time()
    t = end - start
    
    print(f"\nTotal session time: {t:.2f}s")