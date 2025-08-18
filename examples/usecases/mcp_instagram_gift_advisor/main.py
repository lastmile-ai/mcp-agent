#!/usr/bin/env python3

import asyncio
import sys
import argparse
from textwrap import dedent
from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.llm.augmented_llm import RequestParams


class InstagramGiftAdvisor:
    def __init__(self):
        self.profile_data = {}
        self.gift_recommendations = []
        self.agent = None
        self.llm = None
        self.agent_app_cm = None

    async def __aenter__(self):
        """Initialize MCP App and create Instagram gift advisor agent"""
        self.app = MCPApp(name="instagram_gift_advisor")
        self.agent_app_cm = self.app.run()
        await self.agent_app_cm.__aenter__()

        self.agent = Agent(
            name="instagram_gift_advisor",
            instruction=dedent("""
                You are an Instagram Gift Advisor that analyzes Instagram profiles to recommend personalized gifts.
                
                IMPORTANT: You have access to these tools and MUST use them:
                - Apify Instagram scraper: Use to get real Instagram profile data
                - Fetch tool: Use to search the web for REAL Amazon product links - never make up URLs
                - Google Search (g-search): Use to search Google for Amazon products with real links
                
                Your capabilities include:
                - Analyzing Instagram profile content (posts, captions, hashtags, bio)
                - Identifying interests, hobbies, and lifestyle patterns
                - Generating gift recommendations based on inferred preferences
                - Finding REAL Amazon product links using search tools
                - Providing curated product recommendations with real Amazon links
                
                When analyzing a profile, look for:
                - Visual content themes (travel, fitness, food, fashion, art, etc.)
                - Hashtags that indicate interests
                - Bio information about hobbies or profession
                - Repeated patterns in posts that suggest preferences
                
                For gift recommendations:
                - MANDATORY: Use fetch tool or g-search tool to search for products before suggesting ANY product
                - FORBIDDEN: Writing "Please search on Amazon" or similar
                - FORBIDDEN: Making up or guessing Amazon URLs
                - REQUIRED: Only include products with real URLs from actual search results
                - Focus on finding relevant, high-quality products that match their interests
                - REQUIRED: Call fetch tool multiple times (8-10 searches minimum)
                - Show which search terms you used and the actual results
                
                Always format your response with clear sections:
                1. Profile Analysis Summary
                2. Identified Interests
                3. Curated Gift Recommendations (with real Amazon links)
            """),
            server_names=["apify", "fetch", "g-search"],
        )

        self.llm = await self.agent.attach_llm(OpenAIAugmentedLLM)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up resources"""
        if self.agent_app_cm:
            await self.agent_app_cm.__aexit__(exc_type, exc_val, exc_tb)
        if self.agent:
            await self.agent.close()

    async def scrape_instagram_profile(self, username):
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
            
            IMPORTANT: Do NOT include any Amazon links, prices, or specific product recommendations. 
            Only provide analysis and general gift categories/ideas.
            
            Format your response with clear sections:
            - Profile Overview
            - Key Interests Identified  
            - Lifestyle Analysis
            - Gift Category Suggestions (general ideas only, no links or prices)
        """)

        return await self.llm.generate_str(
            prompt, request_params=RequestParams(use_history=True)
        )

    async def generate_gift_recommendations(self, profile_analysis):
        """Generate personalized gift recommendations with real Amazon links"""
        prompt = dedent(f"""
            Based on this Instagram profile analysis, you MUST use the g-search tool to search for REAL Amazon products:

            {profile_analysis}
            
            STOP! Before you write ANYTHING, you must:
            1. Use g-search tool to find Amazon product URLs (at least 8-10 searches)
            2. Use fetch as a fallback if g-search fails
            3. Search for products that match the person's interests from the profile analysis
            4. Find a variety of products across different categories and interests
            5. Only include products with real Amazon URLs from search results

            You are FORBIDDEN from:
            - Writing "(Please search this directly on Amazon)"
            - Providing search terms without actual results
            - Making up Amazon URLs
            - Suggesting products without real links
            - Making up or guessing prices that aren't clearly shown in search results
            
            MANDATORY PROCESS FOR EACH GIFT:
            Step 1: Use g-search tool with "site:amazon.com [product related to their interests]" (use fetch as a fallback if g-search fails)
            Step 2: Extract the actual Amazon URL from the search results
            Step 3: Include the product with the real Amazon link
            
            Find 8-12 gift recommendations that match their interests and lifestyle.
            
            FORMAT REQUIREMENTS:
            ```
            **[Product Name from Amazon]**
            - Amazon URL: [Real Amazon URL from search results]
            - Why it fits: [How this matches their interests from the profile analysis]
            ```
            
            Organize the recommendations by categories based on their interests (e.g., Travel, Pet Care, etc.).
            
            DO NOT PROCEED until you have called g-search OR fetch multiple times and have real URLs!
        """)

        return await self.llm.generate_str(
            prompt, request_params=RequestParams(use_history=True)
        )


async def run_gift_advisor(username):
    print(f"Analyzing Instagram profile: @{username}...\n")

    try:
        async with InstagramGiftAdvisor() as advisor:
            print("Connected! Starting profile analysis...\n")

            # Scrape and analyze the Instagram profile
            profile_analysis = await advisor.scrape_instagram_profile(username)

            print("=== PROFILE ANALYSIS ===")
            print(f"{profile_analysis}\n")

            # Generate gift recommendations
            print("Generating personalized gift recommendations...\n")
            gift_recommendations = await advisor.generate_gift_recommendations(
                profile_analysis
            )

            print("=== GIFT RECOMMENDATIONS ===")
            print(f"{gift_recommendations}\n")

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
