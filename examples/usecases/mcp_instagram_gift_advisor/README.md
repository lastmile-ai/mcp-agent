# Instagram Gift Advisor

An MCP Agent that analyzes Instagram profiles to generate personalized gift recommendations with real Amazon product links.

## Overview

This agent uses Apify's Instagram scraper to analyze profiles and understand a person's interests, hobbies, and lifestyle patterns, then generates thoughtful gift recommendations with actual Amazon product links organized by interest categories.

## Features

- **Profile Analysis**: Analyzes Instagram bio, posts, hashtags, and visual themes using Apify
- **Interest Identification**: Identifies hobbies, lifestyle patterns, and preferences
- **Gift Recommendations**: Generates specific, personalized gift ideas
- **Real Amazon Links**: Provides actual working Amazon product URLs via Google Search
- **Category Organization**: Organizes gifts by interest categories (Travel, Pet Care, etc.)
- **Detailed Explanations**: Explains why each gift matches the person's interests

## Prerequisites

- Node.js (for MCP servers)
- Python 3.10+
- OpenAI API key
- Anthropic API key
- Apify API token

## Installation

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Set up secrets:

```bash
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
# Edit mcp_agent.secrets.yaml with your API keys
```

Required API keys:

- **OpenAI API Key**: Get from https://platform.openai.com/api-keys
- **Anthropic API Key**: Get from https://console.anthropic.com/
- **Apify API Token**: Get from https://apify.com → Settings → Integrations → API tokens (1,000 free runs/month)

## Usage

Run the agent with an Instagram username:

```bash
python main.py username_to_analyze
```

Example:

```bash
python main.py finnianthegoldie
```

The agent will:

1. Scrape the Instagram profile using Apify
2. Analyze the content for interests and patterns
3. Search for real Amazon products using Google Search
4. Generate personalized gift recommendations with working links

## Output Format

The agent provides:

### Profile Analysis

- Bio information and interests
- Visual themes from posts
- Hashtag analysis
- Lifestyle patterns
- Gift category suggestions (no specific products or prices)

### Gift Recommendations by Interest Category

Each recommendation includes:

- Product name from Amazon
- Real Amazon product URL
- Explanation of why it fits their interests

## Example Output

```
=== PROFILE ANALYSIS ===
### Profile Overview
- Username: finnianthegoldie
- Bio: "the globetrotting dog 🗺️⁀જ✈︎ 📍nyc"
- Followers: 106,875

### Key Interests Identified
- Travel and adventure
- Service dog advocacy
- Community engagement
- Urban lifestyle

### Gift Category Suggestions
- Travel accessories for pets
- Dog health and safety items
- Educational materials about service dogs

=== GIFT RECOMMENDATIONS ===

## Travel & Adventure
**Collapsible Dog Travel Bowl**
- Amazon URL: <link to amazon>
- Why it fits: Perfect for Finnian's globetrotting lifestyle and travel adventures

**Dog Car Safety Harness**
- Amazon URL: <link to amazon>
- Why it fits: Essential for safe travel with a service dog
```

## Configuration

The agent uses:

- **Apify Instagram Scraper**: For scraping Instagram profiles professionally
- **Google Search (g-search)**: For finding real Amazon product links
- **Fetch Server**: For web content retrieval
- **OpenAI GPT-4o-mini**: For content analysis and gift recommendation generation
- **Asyncio**: For asynchronous execution

## MCP Servers Used

1. **Apify**: `https://mcp.apify.com/sse` - Professional Instagram scraping
2. **G-Search**: `g-search-mcp` - Google search functionality
3. **Fetch**: `mcp-server-fetch` - Web content fetching

## Limitations

- Requires public Instagram profiles
- Some profiles may require login (handled by Apify OAuth)
- Gift recommendations depend on Amazon product availability
- Search results may vary over time

## Security Considerations

- Never commit your actual secrets file (`mcp_agent.secrets.yaml`)
- API keys are referenced via environment variables in config
- Apify handles bot detection and rate limiting professionally
- This tool is for legitimate gift-giving purposes only

## Troubleshooting

### Common Issues

1. **Apify Connection**: Ensure your API token is valid in secrets file
2. **Search Results**: G-search and fetch servers install automatically via npx

### Logging

Logs are saved to `logs/instagram_gift_advisor_[timestamp].jsonl` for debugging.

## License

This project follows the same license as the parent MCP Agent repository.
