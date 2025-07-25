#!/usr/bin/env python3

import asyncio
import sys
import argparse
from textwrap import dedent
from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.mcp.mcp_connection_manager import MCPConnectionManager
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.llm.augmented_llm import RequestParams


class InstagramGiftAdvisor:
    def __init__(self):
        self.profile_data = {}
        self.gift_recommendations = []

    async def initialize_agent(self):
        """Initialize MCP App and create Instagram gift advisor agent"""
        self.app = MCPApp(name="instagram_gift_advisor")
        self.agent_app_cm = self.app.run()
        self.agent_app = await self.agent_app_cm.__aenter__()
        context = self.agent_app.context

        self.manager = MCPConnectionManager(context.server_registry)
        await self.manager.__aenter__()

        gift_agent = Agent(
            name="instagram_gift_advisor",
            instruction=dedent("""
                You are an Instagram Gift Advisor that analyzes Instagram profiles to recommend personalized gifts.
                
                IMPORTANT: You have access to these tools and MUST use them:
                - Apify Instagram scraper: Use to get real Instagram profile data
                - Brave Search: Use to find REAL Amazon product links - never make up URLs
                
                Your capabilities include:
                - Analyzing Instagram profile content (posts, captions, hashtags, bio)
                - Identifying interests, hobbies, and lifestyle patterns
                - Generating gift recommendations based on inferred preferences
                - Finding REAL Amazon product links using search tools
                - Organizing recommendations by price ranges ($10-25, $25-50, $50-100, $100+)
                
                When analyzing a profile, look for:
                - Visual content themes (travel, fitness, food, fashion, art, etc.)
                - Hashtags that indicate interests
                - Bio information about hobbies or profession
                - Repeated patterns in posts that suggest preferences
                
                For gift recommendations:
                - MANDATORY: Use brave_search tool before suggesting ANY product
                - FORBIDDEN: Writing "Please search on Amazon" or similar
                - FORBIDDEN: Making up or guessing Amazon URLs
                - REQUIRED: Only include products with real URLs from actual search results
                - REQUIRED: Include actual prices from search results
                - REQUIRED: Call brave_search multiple times (8-10 searches minimum)
                - Show which search terms you used and the actual results
                
                Always format your response with clear sections:
                1. Profile Analysis Summary
                2. Identified Interests
                3. Gift Recommendations by Price Range (with real search results)
            """),
            server_names=["apify", "brave-search"],
        )

        llm = await gift_agent.attach_llm(OpenAIAugmentedLLM)

        return {"agent": gift_agent, "llm": llm}

    async def scrape_instagram_profile(self, llm, username):
        """Scrape Instagram profile and analyze content using Apify"""
        
        prompt = dedent(f"""
            Use the Apify Instagram scraper to analyze the Instagram profile: {username}
            
            Please scrape and analyze:
            1. Profile information - bio, follower count, following count, posts count
            2. Recent posts - captions, hashtags, image descriptions
            3. Overall profile themes and patterns
            
            Based on this data, identify the person's:
            - Interests and hobbies
            - Lifestyle patterns
            - Age demographic (if apparent from content)
            - Activities they enjoy
            - Aesthetic preferences
            
            Provide a comprehensive analysis that will be used for personalized gift recommendations.
            Focus on extracting actionable insights about what this person might enjoy receiving as gifts.
            
            Format your response with clear sections:
            - Profile Overview
            - Key Interests Identified  
            - Lifestyle Analysis
            - Gift Recommendation Insights
        """)

        return await llm.generate_str(
            prompt, request_params=RequestParams(use_history=True)
        )

    async def generate_gift_recommendations(self, llm, profile_analysis):
        """Generate personalized gift recommendations with real Amazon links"""
        prompt = dedent(f"""
            Based on this Instagram profile analysis, you MUST use the brave_search tool to find REAL Amazon products:
            
            {profile_analysis}
            
            STOP! Before you write ANYTHING, you must:
            1. Call the brave_search tool at least 8-10 times to find actual Amazon products
            2. Use search queries like: "site:amazon.com dog crate under $100"
            3. Only proceed after you have REAL search results with REAL URLs
            
            You are FORBIDDEN from:
            - Writing "(Please search this directly on Amazon)"
            - Providing search terms without actual results
            - Making up Amazon URLs
            - Suggesting products without real links
            
            MANDATORY PROCESS FOR EACH GIFT:
            Step 1: Call brave_search with "site:amazon.com [product] [price range]"
            Step 2: Extract the actual Amazon URL from the search results
            Step 3: Only then write the gift recommendation with the real URL
            
            Find 2-3 gifts per price range:
            
            **$10-25 Range:**
            - Search: "site:amazon.com [item] under $25"
            - Extract real Amazon URLs from results
            
            **$25-50 Range:**
            - Search: "site:amazon.com [item] $25 $50"
            - Extract real Amazon URLs from results
            
            **$50-100 Range:**
            - Search: "site:amazon.com [item] $50 $100"
            - Extract real Amazon URLs from results
            
            **$100+ Range:**
            - Search: "site:amazon.com [item] over $100"
            - Extract real Amazon URLs from results
            
            FORMAT REQUIREMENTS:
            ```
            **[Exact Product Name from Amazon]**
            - Amazon URL: [Copy exact URL from search results]
            - Price: [Actual price from search results]
            - Why it fits: [Based on their interests]
            ```
            
            If brave_search returns no results for a product type, write:
            "No Amazon products found for [item type] in this price range."
            
            DO NOT PROCEED until you have called brave_search multiple times and have real URLs!
        """)

        return await llm.generate_str(
            prompt, request_params=RequestParams(use_history=True)
        )

    async def close_session(self, components):
        """Clean up resources"""
        if components["agent"]:
            await components["agent"].close()
        if hasattr(self, "manager"):
            await self.manager.__aexit__(None, None, None)
        if hasattr(self, "agent_app_cm"):
            await self.agent_app_cm.__aexit__(None, None, None)


async def run_gift_advisor(username):
    print(f"Analyzing Instagram profile: @{username}...\n")

    advisor = InstagramGiftAdvisor()

    try:
        # Initialize the agent
        components = await advisor.initialize_agent()

        print("Connected! Starting profile analysis...\n")

        # Scrape and analyze the Instagram profile
        profile_analysis = await advisor.scrape_instagram_profile(
            components["llm"], username
        )

        print("=== PROFILE ANALYSIS ===")
        print(f"{profile_analysis}\n")

        # Generate gift recommendations
        print("Generating personalized gift recommendations...\n")
        gift_recommendations = await advisor.generate_gift_recommendations(
            components["llm"], profile_analysis
        )

        print("=== GIFT RECOMMENDATIONS ===")
        print(f"{gift_recommendations}\n")

        # Clean up
        await advisor.close_session(components)

        print("Analysis complete! Gift recommendations generated.")

    except Exception as e:
        print(f"Error: {str(e)}")
        return False

    return True


def parse_args():
    parser = argparse.ArgumentParser(
        description="Instagram Gift Advisor - Generate personalized gift recommendations from Instagram profiles"
    )
    parser.add_argument("username", help="Instagram username to analyze (without @)")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        asyncio.run(run_gift_advisor(args.username))
    except KeyboardInterrupt:
        print("\n\nSession terminated by user.")
        sys.exit(0)
