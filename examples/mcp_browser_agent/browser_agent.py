#!/usr/bin/env python3

import asyncio
import sys
import argparse
import re
from textwrap import dedent, wrap
from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.mcp.mcp_connection_manager import MCPConnectionManager
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.llm.augmented_llm import RequestParams
import colorama
from colorama import Fore, Style

# Initialize colorama
colorama.init()

# Constants for UI
USER_COLOR = Fore.CYAN
AGENT_COLOR = Fore.GREEN
SYSTEM_COLOR = Fore.YELLOW
ERROR_COLOR = Fore.RED
OPTION_COLOR = Fore.MAGENTA
TITLE_COLOR = Fore.BLUE + Style.BRIGHT
RESET = Style.RESET_ALL
BOLD = Style.BRIGHT

# Session state
current_url = ""
visited_urls = set()
interaction_count = 0

# Function to initialize MCP App and create browser agent
async def initialize_browser_agent(url):
    """Initialize MCP App and create browser agent with the given URL"""
    # Create MCP App instance
    app = MCPApp(name="browser_agent")
    agent_app = await app.run().__aenter__()
    context = agent_app.context
    
    # Create connection manager
    manager = MCPConnectionManager(context.server_registry)
    await manager.__aenter__()
    
    # Create browser agent with puppeteer
    browser_agent = Agent(
        name="browser_agent",
        instruction=dedent("""
            You are a browser assistant that helps users interact with websites.
            
            Your capabilities include:
            - Navigating to URLs
            - Extracting information from web pages
            - Clicking links and buttons
            - Filling out forms
            - Taking screenshots
            - Analyzing page content
            
            Always describe what you see on the page and be specific about 
            what actions you took in response to a query.
            
            After each interaction, suggest 3-4 possible next actions the user might want to take.
            Format these as a list prefixed with "POSSIBLE ACTIONS:" on a new line.
            
            Maintain browser state between interactions.
        """),
        server_names=["puppeteer"]
    )
    
    # Attach OpenAI LLM to agent
    llm = await browser_agent.attach_llm(OpenAIAugmentedLLM)
    
    # Navigate to initial URL
    initial_prompt = dedent(f"""
        Navigate to {url} and describe what you see on the page.
        
        After describing the page content, suggest 3-4 possible actions
        the user could take based on what's available on the page.
        
        Format your response with the page description first, then a clear list of
        suggested actions prefixed with "POSSIBLE ACTIONS:" on its own line.
    """)
    
    response = await llm.generate_str(initial_prompt, request_params=RequestParams(use_history=True))
    
    return {
        "browser_agent": browser_agent,
        "browser_llm": llm,
        "browser_app": agent_app,
        "browser_manager": manager,
        "initial_response": response
    }

# Function to send a query to the browser
async def interact_with_browser(llm, query):
    """Send a query to the browser agent"""
    prompt = dedent(f"""
        User query: {query}
        
        Perform this action in the browser and provide a detailed response.
        Describe what you did and what you found or saw on the page.
        
        After your description, suggest 3-4 new possible actions the user could take next
        based on the current state of the webpage.
        
        Format your reply with your description first, then a clear list of suggested actions
        prefixed with "POSSIBLE ACTIONS:" on its own line.
    """)
    
    return await llm.generate_str(prompt, request_params=RequestParams(use_history=True))

# Function to close the browser session
async def close_browser_session(browser_agent, browser_manager, browser_app):
    """Close the browser session and clean up resources"""
    if browser_agent:
        await browser_agent.close()
    
    if browser_manager:
        await browser_manager.__aexit__(None, None, None)
    
    if browser_app:
        await browser_app.__aexit__(None, None, None)


# Print application banner
def print_banner():
    banner = [
        "╔═══════════════════════════════════════════════════════════════╗",
        "║                                                               ║",
        "║                     BROWSER CONSOLE AGENT                     ║",
        "║                                                               ║",
        "╚═══════════════════════════════════════════════════════════════╝"
    ]
    
    for line in banner:
        print(f"{TITLE_COLOR}{line}{RESET}")

# Print welcome message
def print_welcome():
    print_banner()
    print(f"\n{BOLD}Welcome to Browser Console Agent{RESET}")
    print("Interact with websites using natural language in your terminal.\n")
    print(f"{SYSTEM_COLOR}You can type a {BOLD}number{RESET}{SYSTEM_COLOR} to select from suggested actions or type your own queries.{RESET}")
    print(f"{SYSTEM_COLOR}Type {BOLD}'exit'{RESET}{SYSTEM_COLOR} or {BOLD}'quit'{RESET}{SYSTEM_COLOR} to end the session.{RESET}\n")


# Format agent response for display and extract possible actions
def format_agent_response(response):
    # Split into description and possible actions
    parts = re.split(r'(?i)possible actions:', response, 1)
    
    description = parts[0].strip()
    
    # Format description with line wrapping
    formatted_description = ""
    for paragraph in description.split('\n'):
        if paragraph.strip():
            wrapped = wrap(paragraph, width=80)
            formatted_description += '\n'.join(wrapped) + '\n\n'
    
    # Format actions if present and extract them
    actions_text = ""
    action_items_list = []
    
    if len(parts) > 1:
        action_text = parts[1].strip()
        actions_text = f"\n{OPTION_COLOR}POSSIBLE ACTIONS:{RESET}\n"
        
        # Extract actions with bullet points, numbers, or dashes
        action_items = re.findall(r'(?:^|\n)[•\-\d*)\s]+(.+?)(?=$|\n[•\-\d*)])', action_text, re.MULTILINE)
        
        if not action_items:
            # If no structured actions found, just use the whole text
            actions_text += action_text
        else:
            # Store actions for later lookup
            action_items_list = [action.strip() for action in action_items]
            
            # Number the actions
            for i, action in enumerate(action_items_list, 1):
                actions_text += f"{OPTION_COLOR}{i}.{RESET} {action}\n"
    
    return formatted_description, actions_text, action_items_list

# Update session information based on response
def update_session_info(response):
    global current_url, visited_urls
    
    # Check for URLs in the response
    urls = re.findall(r'https?://[^\s<>"]+|www\.[^\s<>"]+', response)
    if urls:
        new_url = urls[0]
        if new_url != current_url:
            current_url = new_url
            visited_urls.add(current_url)
    
    return ""

# Main function that runs the agent
async def run_browser_session(url):
    global current_url, interaction_count, visited_urls
    current_url = url
    visited_urls.add(url)
    
    # Print welcome message
    print_welcome()
    
    # Show connecting message
    print(f"{SYSTEM_COLOR}Connecting to {url}...{RESET}")
    
    try:
        # Initialize the browser agent
        components = await initialize_browser_agent(url)
        
        browser_agent = components["browser_agent"]
        browser_llm = components["browser_llm"]
        browser_app = components["browser_app"]
        browser_manager = components["browser_manager"]
        initial_response = components["initial_response"]
        
        # Show connection success
        print(f"{SYSTEM_COLOR}Connected! Browser session started.{RESET}\n")
        
        # Display initial response
        description, actions_text, action_items = format_agent_response(initial_response)
        print(f"{AGENT_COLOR}{description}{RESET}")
        print(actions_text)
        
        # Main interaction loop
        while True:
            # Display command prompt with styling
            print(f"{USER_COLOR}You: {RESET}", end="")
            user_input = input()
            
            # Check for commands
            if user_input.lower() in ['exit', 'quit']:
                print(f"\n{SYSTEM_COLOR}Closing browser session...{RESET}")
                await close_browser_session(browser_agent, browser_manager, browser_app)
                
                # Show session summary
                print(f"\n{TITLE_COLOR}=== SESSION SUMMARY ==={RESET}")
                print(f"{BOLD}Total Interactions:{RESET} {interaction_count}")
                print(f"{BOLD}URLs Visited:{RESET} {len(visited_urls)}")
                
                print(f"\n{SYSTEM_COLOR}Browser session closed. Goodbye!{RESET}")
                break
            
            # Empty input
            elif not user_input.strip():
                continue
            
            # Check if input is a number that corresponds to an action
            if user_input.isdigit() and action_items:
                action_num = int(user_input)
                if 1 <= action_num <= len(action_items):
                    # Convert the number to the corresponding action
                    user_input = action_items[action_num - 1]
                    print(f"{SYSTEM_COLOR}Selected: {user_input}{RESET}")
            
            # Process the user action
            try:
                print(f"{SYSTEM_COLOR}Processing...{RESET}")
                interaction_count += 1
                
                # Send the query to the browser
                response = await interact_with_browser(browser_llm, user_input)
                
                # Update session information
                update_session_info(response)
                
                # Format and display the response
                description, actions_text, action_items = format_agent_response(response)
                print(f"\n{AGENT_COLOR}{description}{RESET}")
                
                # Show possible actions
                print(actions_text)
                
            except Exception as e:
                print(f"\n{ERROR_COLOR}Error: {str(e)}{RESET}\n")
    
    except Exception as e:
        print(f"\n{ERROR_COLOR}Error starting browser session: {str(e)}{RESET}")
        return False
    
    return True

# Parse command-line arguments
def parse_args():
    parser = argparse.ArgumentParser(description="Browser Console Agent - Interact with websites using natural language")
    parser.add_argument("url", nargs="?", default="https://en.wikipedia.org/wiki/Large_language_model", 
                        help="URL to browse (default: https://en.wikipedia.org/wiki/Large_language_model)")
    return parser.parse_args()

# Entry point
if __name__ == "__main__":
    args = parse_args()
    try:
        asyncio.run(run_browser_session(args.url))
    except KeyboardInterrupt:
        print(f"\n\n{SYSTEM_COLOR}Session terminated by user. Goodbye!{RESET}")
        sys.exit(0)
