# Instagram Gift Advisor

An MCP Agent that analyzes Instagram profiles to generate personalized gift recommendations with Amazon product links, organized by price ranges.

## Overview

This agent scrapes Instagram profiles to understand a person's interests, hobbies, and lifestyle patterns, then generates thoughtful gift recommendations categorized by price points ($10-25, $25-50, $50-100, $100+).

## Features

- **Profile Analysis**: Analyzes Instagram bio, posts, hashtags, and visual themes
- **Interest Identification**: Identifies hobbies, lifestyle patterns, and preferences
- **Gift Recommendations**: Generates specific, personalized gift ideas
- **Amazon Integration**: Provides specific Amazon search terms for each recommendation
- **Price Categorization**: Organizes gifts by budget ranges
- **Detailed Explanations**: Explains why each gift matches the person's interests

## Prerequisites

- Node.js (for Puppeteer MCP server)
- Python 3.8+
- OpenAI API key

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Install Puppeteer MCP server:
```bash
npx -y @modelcontextprotocol/server-puppeteer
```

3. Set up secrets:
```bash
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
# Edit mcp_agent.secrets.yaml with your OpenAI API key
```

## Usage

Run the agent with an Instagram username:

```bash
python main.py username_to_analyze
```

Example:
```bash
python main.py johndoe
```

The agent will:
1. Navigate to the Instagram profile
2. Analyze the content for interests and patterns
3. Generate personalized gift recommendations
4. Organize recommendations by price ranges
5. Provide Amazon search terms for each gift

## Output Format

The agent provides:

### Profile Analysis
- Bio information and interests
- Visual themes from posts
- Hashtag analysis
- Lifestyle patterns

### Gift Recommendations by Price Range

**$10-25 Range**: Budget-friendly options
**$25-50 Range**: Mid-range gifts  
**$50-100 Range**: Higher-end options
**$100+ Range**: Premium/luxury items

Each recommendation includes:
- Gift name and description
- Amazon search term
- Explanation of why it fits their interests
- Estimated price range

## Example Output

```
=== PROFILE ANALYSIS ===
Bio Analysis: Travel enthusiast and coffee lover based in Seattle
Visual Themes: Mountain hiking, specialty coffee, vintage cameras
Key Interests: Photography, outdoor adventures, artisan coffee

=== GIFT RECOMMENDATIONS ===

$10-25 Range:
- Coffee Bean Sampler Pack
- Amazon Search: "specialty coffee bean sampler gift set"
- Why It Fits: Matches their love for artisan coffee culture
- Estimated Price: $15-20

$25-50 Range:
- Portable Coffee Grinder
- Amazon Search: "manual coffee grinder travel camping"  
- Why It Fits: Perfect for their hiking and coffee interests
- Estimated Price: $30-40
```

## Configuration

The agent uses:
- **Puppeteer MCP Server**: For web scraping Instagram profiles
- **OpenAI GPT-4**: For content analysis and gift recommendation generation
- **Asyncio**: For asynchronous execution

## Limitations

- Requires public Instagram profiles
- Dependent on Instagram's current layout and accessibility
- Gift recommendations are suggestions, not guaranteed product availability
- Amazon search terms may need refinement for specific products

## Security Considerations

- Never commit your actual secrets file (`mcp_agent.secrets.yaml`)
- Use environment variables in production
- Respect Instagram's terms of service and rate limits
- This tool is for legitimate gift-giving purposes only

## License

This project follows the same license as the parent MCP Agent repository.