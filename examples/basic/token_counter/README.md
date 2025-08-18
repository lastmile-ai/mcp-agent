# Token Counter Example

This example demonstrates the MCP Agent's token counting capabilities with custom monitoring and real-time tracking.

## Features

### 1. **Live Token Tracking**
- Uses `TokenProgressDisplay` to show real-time token usage
- Updates continuously as LLM calls are made
- Shows total tokens and cumulative cost

### 2. **Custom Watch Callbacks**
- Implements a `TokenMonitor` class that tracks:
  - All LLM calls with timestamps and model information
  - High token usage alerts (>1000 tokens per call)
  - Token breakdown (input/output/total) for each call

### 3. **Comprehensive Summaries**
- **Token Usage Summary**: Total tokens, costs, and breakdowns by model and agent
- **Token Usage Tree**: Hierarchical view of token consumption across the entire execution
- **LLM Call Timeline**: Detailed log of each LLM interaction

## Architecture

```plaintext
┌────────────────┐      ┌──────────────┐
│ TokenMonitor   │◀────▶│ TokenCounter │
│ (Custom Watch) │      │              │
└────────────────┘      └──────────────┘
        │                       │
        ▼                       ▼
┌────────────────┐      ┌──────────────┐
│ Finder Agent   │      │ TokenProgress│
│ (OpenAI)       │      │ Display      │
└────────────────┘      └──────────────┘
        │
        ▼
┌────────────────┐
│ Analyzer Agent │
│ (Anthropic)    │
└────────────────┘
```

## Setup

First, clone the repo and navigate to the token_counter example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/basic/token_counter
```

Install `uv` (if you don't have it):

```bash
pip install uv
```

Sync `mcp-agent` project dependencies:

```bash
uv sync
```

Install requirements specific to this example:

```bash
uv pip install -r requirements.txt
```

## Configuration

In `main.py`, set your API keys in the configuration or use environment variables:
- OpenAI API key for the finder agent
- Anthropic API key for the analyzer agent

## Running the Example

```bash
uv run main.py
```

## Sample Output

```
✨ Token Counter Example with Live Monitoring
Watch the token usage update in real-time!

Token Usage [bold]TOTAL                         2,895    $0.0049

📁 Task 1: File system query (OpenAI)
Found: Here are the Python files in the current directory:...

🔍 Task 2: Analysis (Anthropic)
Components: A token counting system for LLMs typically consists of several key components...

📝 Task 3: Follow-up question
Summary: • **Tokenizer**: Breaks text into tokens using model-specific rules...

📊 LLM Call Summary:
  14:23:45 - gpt-4-turbo-preview: 1,234 tokens
  14:23:47 - claude-3-opus-20240229: 876 tokens
  14:23:49 - claude-3-opus-20240229: 432 tokens

============================================================
TOKEN USAGE SUMMARY
============================================================

Total Usage:
  Total tokens: 2,542
  Input tokens: 1,832
  Output tokens: 710
  Total cost: $0.0234

Breakdown by Model:

  gpt-4-turbo-preview:
    Tokens: 1,234 (input: 876, output: 358)
    Cost: $0.0123

  claude-3-opus-20240229:
    Tokens: 1,308 (input: 956, output: 352)
    Cost: $0.0111

============================================================
TOKEN USAGE TREE
============================================================

└─ token_counter_example [app]
    ├─ Total: 2,542 tokens ($0.0234)
    ├─ Input: 1,832
    └─ Output: 710
    
    ├─ finder [agent]
    │   ├─ Total: 1,234 tokens ($0.0123)
    │   ├─ Input: 876
    │   └─ Output: 358
    │   
    │   └─ llm_1234 [llm]
    │       ├─ Total: 1,234 tokens ($0.0123)
    │       ├─ Input: 876
    │       └─ Output: 358
    │          Model: gpt-4-turbo-preview (openai)
    
    └─ analyzer [agent]
        ├─ Total: 1,308 tokens ($0.0111)
        ├─ Input: 956
        └─ Output: 352
```

## Key Concepts

### TokenProgressDisplay
- Provides a clean, real-time display of token usage
- Alternative to RichProgressDisplay when you want focused token tracking
- Automatically updates as tokens are consumed

### Custom Watchers
The example demonstrates how to implement custom token monitoring:

```python
# Create a custom monitor
monitor = TokenMonitor()

# Register a watch callback
watch_id = token_counter.watch(
    callback=monitor.on_token_update,
    threshold=1  # Track all updates
)
```

Features:
- Register callbacks to monitor specific token events
- Can filter by node type (e.g., "llm", "agent", "app")
- Support for thresholds and throttling to control callback frequency

### Token Tree Visualization
- Hierarchical view showing token distribution across components
- Includes cost calculations at each level
- Shows model information when available

## Customization

You can extend the `TokenMonitor` class to track additional metrics:
- Token usage by time of day
- Average tokens per request type
- Model performance comparisons
- Cost optimization insights
- Alerts for specific patterns or anomalies

The watch functionality is highly flexible and can be adapted to your specific monitoring needs.