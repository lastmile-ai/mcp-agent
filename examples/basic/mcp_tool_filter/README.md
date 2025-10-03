# MCP Tool Filter Example

This example demonstrates a **non-invasive** approach to filtering MCP tools without modifying any core mcp-agent code.

## Overview

The MCP Tool Filter provides:
- ✅ **Zero code modification** - Works with existing mcp-agent installation
- ✅ **Dynamic filtering** - Change filters at runtime
- ✅ **Model agnostic** - Works with any LLM provider
- ✅ **Minimal overhead** - Simple wrapper pattern
- ✅ **Flexible rules** - Whitelist, blacklist, or custom logic

## Quick Start

1. **Install dependencies**:
   ```bash
   cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
   # Edit mcp_agent.secrets.yaml with your API keys
   ```

2. **Run the example**:
   ```bash
   python main.py
   ```

3. **Try the quickstart**:
   ```bash
   python quickstart.py
   ```

## How It Works

The tool filter wraps the LLM's `generate` method to intercept tool listings:

```python
# 1. Create your agent and LLM as usual
agent = Agent(name="my_agent", server_names=["filesystem"])
llm = await agent.attach_llm(OpenAIAugmentedLLM)

# 2. Create a filter
filter = ToolFilter(allowed=["filesystem_read_file", "filesystem_list_directory"])

# 3. Apply the filter
apply_tool_filter(llm, filter)

# 4. Use normally - the LLM only sees filtered tools
result = await llm.generate_str("List the files")
```

## Filter Types

### 1. Allowed List (Whitelist)
Only allow specific tools:
```python
filter = ToolFilter(allowed=["filesystem_read_file", "filesystem_list_directory"])
```

### 2. Excluded List (Blacklist)
Block-specific tools:
```python
filter = ToolFilter(excluded=["filesystem_delete_file", "filesystem_write_file"])
```

### 3. Server-Specific Filters
Different rules for different servers:
```python
filter = ToolFilter(
    server_filters={
        "filesystem": {"allowed": ["read_file", "list_directory"]},
        "github": {"excluded": ["delete_repository"]}
    }
)
```

### 4. Custom Filter Function
Complete control over filtering logic:
```python
def my_filter(tool):
    return "read" in tool.name.lower()

filter = ToolFilter(custom_filter=my_filter)
```

## Tool Naming Convention

MCP tools are namespaced using the format `server_tool` with underscore as separator:

- Full name: `filesystem_read_file`
- Server: `filesystem`
- Tool: `read_file`

The filter intelligently handles both formats:
- Simple names: `read_file` matches any server's read_file tool
- Full names: `filesystem_read_file` matches exactly

## Examples in This Directory

- `main.py` - Interactive demo with 4 filtering scenarios
- `quickstart.py` - Minimal example to get started

## Benefits

1. **Reduced Token Usage**: Fewer tools in prompts = lower costs
2. **Improved Safety**: Prevent accidental dangerous operations
3. **Better Focus**: Agents only see relevant tools for their task
4. **Easy Testing**: Quickly test with different tool sets
5. **No Lock-in**: Remove filtering anytime without code changes

## Implementation Details

The filter works by:
1. Wrapping the LLM's `generate` method
2. Temporarily modifying the agent's `list_tools` method
3. Filtering the tool list before it's sent to the LLM
4. Restoring original behavior after each call

This approach:
- Doesn't modify any source files
- Works with all LLM providers
- Has minimal performance impact
- Can be applied/removed dynamically