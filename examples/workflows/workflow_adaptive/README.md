# Adaptive Workflow Examples

This directory contains examples for both versions of the Adaptive Workflow implementation.

## Overview

The Adaptive Workflow implements a multi-agent system based on the Claude Deep Research architecture, where a Lead Researcher coordinates multiple specialized subagents to complete complex tasks.

## Files

- `main.py` - Examples using AdaptiveWorkflow (V1)
- `main_v2.py` - Examples using AdaptiveWorkflowV2

## AdaptiveWorkflow vs AdaptiveWorkflowV2

### AdaptiveWorkflow (V1)
The original implementation with comprehensive features:

**Pros:**
- Mature and battle-tested
- Complex task categorization system
- Detailed metrics tracking (tokens, costs, etc.)
- Citation tracking for research tasks
- Strategy selection (BFS, DFS, Balanced)

**Cons:**
- More complex memory model
- Tightly coupled to specific message formats
- Heavier weight with more overhead
- Strategy selection can be over-engineered for simple tasks

**Best for:**
- Complex research tasks requiring citations
- When you need detailed metrics and cost tracking
- Projects requiring specific search strategies
- Long-running workflows with complex memory needs

### AdaptiveWorkflowV2

A cleaner, more focused implementation following Deep Research architecture:

**Pros:**
- Cleaner separation of concerns
- Support for predefined agents (reuse existing specialists)
- Provider-agnostic message handling
- Simplified memory model without rigid categorization
- More intuitive phase progression
- Lighter weight and faster

**Cons:**
- Less detailed metrics tracking
- No citation tracking
- No strategy selection (always balanced)
- Newer, less battle-tested

**Best for:**
- When you have existing specialized agents to reuse
- Projects requiring provider-agnostic message handling
- Simpler workflows that don't need citations
- When you want cleaner, more maintainable code
- Rapid prototyping and experimentation

## Running the Examples

1. Ensure you have the MCP Agent configuration set up:
   ```bash
   cp config/mcp_agent.config.yaml.example config/mcp_agent.config.yaml
   # Edit the config file with your API keys and settings
   ```

2. Run V1 examples:
   ```bash
   python main.py
   ```

3. Run V2 examples:
   ```bash
   python main_v2.py
   ```

## Key Differences in Examples

### V1 Example Features
- Shows task type detection (RESEARCH, ACTION, HYBRID)
- Demonstrates citation tracking
- Complex memory persistence
- Detailed token and cost metrics
- Strategy-based execution

### V2 Example Features
- Predefined agent creation and reuse
- Native message format handling
- Simplified memory with learning
- Clean phase progression visibility
- Multi-agent coordination
- Structured output examples

## Choosing Which Version

**Choose V1 if you need:**
- Citation tracking for research
- Detailed cost/token metrics
- Complex task categorization
- Specific search strategies

**Choose V2 if you want:**
- Cleaner, simpler implementation
- Reusable specialized agents
- Provider-agnostic messages
- Faster execution
- Better maintainability

## Architecture Patterns

Both versions implement the Deep Research pattern but with different approaches:

### V1 Pattern
```
User Query → Task Analysis → Strategy Selection → Dynamic Subagents → 
Citations → Synthesis → Result
```

### V2 Pattern
```
User Query → Analyze → Plan → Execute (with predefined/dynamic agents) → 
Synthesize → Decide → Result
```

## Tips for Usage

1. **For V1**: Configure memory persistence carefully as it can grow large
2. **For V2**: Create specialized agents upfront for better performance
3. **Both**: Set appropriate time and cost budgets for your use case
4. **Both**: Use parallel execution for independent subtasks
5. **V2**: Leverage the simplified memory for learning patterns

## Future Considerations

- V2 is the recommended path forward for new projects
- V1 will continue to be maintained for backward compatibility
- Features like citation tracking may be added to V2 as optional modules
- The predefined agent pattern in V2 enables better composition