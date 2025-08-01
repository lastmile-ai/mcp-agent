# Adaptive Workflow V2

An adaptive multi-agent workflow implementation that properly follows the Claude Deep Research architecture.

## Design Philosophy

The Adaptive Workflow V2 implements the true Deep Research pattern:

1. **Lead Researcher Control**: A lead researcher maintains control throughout the investigation
2. **Iterative Refinement**: Plan → Execute → Synthesize → Decide → Repeat
3. **Dynamic Aspect Research**: Subagents created on-demand for specific research aspects
4. **Synthesis-Driven Progress**: Each iteration synthesizes findings to inform next steps
5. **Natural Completion**: Research concludes when the objective is sufficiently addressed

## Key Components

### Lead Researcher
The lead researcher agent that:
- Analyzes the initial objective
- Plans what aspects to investigate
- Synthesizes findings from subagents
- Decides whether to continue or conclude
- Generates the final report

### Research Aspects
Instead of complex task management, we use simple research aspects:
- Each aspect has a clear name and objective
- Aspects can specify required MCP servers
- Subagents are created dynamically per aspect

### Iterative Loop
The core workflow follows this pattern:
1. Plan: Identify aspects to research
2. Execute: Create subagents to investigate
3. Synthesize: Combine findings coherently
4. Decide: Continue or conclude based on progress

## Implementation Details

### Clean Architecture
The V2 implementation removes over-engineering:
- No TaskComplexity enums
- No complex strategy objects  
- No pre-determined resource buckets
- Simple, clear data models

### Dynamic Adaptation
Resource allocation happens naturally:
```python
# Aspects determined by what's needed
asepcts = await self._plan_research(span)

# Parallel execution when beneficial
if self.enable_parallel and len(aspects) > 1:
    results = await asyncio.gather(*tasks)
```

### Synthesis and Decision Making
The lead researcher:
- Synthesizes findings after each research round
- Evaluates progress toward the objective
- Decides whether more research is needed
- Identifies new aspects based on gaps

### Non-Cascading Iterations
Each subagent has limited iterations (typically 5):
- Prevents exponential growth
- Keeps subagents focused
- Allows many aspects to be explored
- Main loop controlled by lead researcher

## Usage Examples

### Simple Research
```python
workflow = AdaptiveWorkflowV2(
    llm_factory=factory, 
    available_servers=["filesystem", "github"]
)
result = await workflow.generate_str(
    "What are the main features of our authentication system?"
)
```

### Complex Investigation
```python
# The workflow will iteratively explore different aspects
result = await workflow.generate_str("""
    Analyze our codebase architecture and identify 
    areas that could benefit from refactoring
""")
```

### Action-Oriented Task
```python
# Will research then take action
result = await workflow.generate_str("""
    Find all deprecated API endpoints in our codebase 
    and update them to use the new API versions
""")
```

## How It Works

1. **Initial Analysis**: The lead researcher analyzes your objective to understand what type of task it is

2. **Iterative Research Loop**:
   - Plans which aspects need investigation
   - Creates specialized subagents for each aspect  
   - Executes research (in parallel when beneficial)
   - Synthesizes all findings
   - Decides if more research is needed

3. **Natural Conclusion**: The workflow concludes when the lead researcher determines the objective has been sufficiently addressed

4. **Final Report**: A comprehensive report is generated synthesizing all research findings

## Advantages Over Traditional Approaches

1. **No Pre-Planning**: Research adapts based on discoveries
2. **Focused Subagents**: Each subagent has a specific, clear objective
3. **Synthesis-Driven**: Progress is evaluated based on synthesized understanding
4. **Natural Flow**: Mimics how human researchers actually work
5. **Clean Implementation**: Simple, understandable code without over-engineering