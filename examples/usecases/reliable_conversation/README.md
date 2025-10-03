# Reliable Conversation Manager (RCM)

Implementation of research findings from "LLMs Get Lost in Multi-Turn Conversation" (https://arxiv.org/abs/2505.06120) using mcp-agent framework.

## Implementation Status ✅

### Core Features (Fully Implemented)

- **Complete Data Models**: All research-based models with serialization (ConversationMessage, Requirement, QualityMetrics, ConversationState)
- **Quality Control Pipeline**: 7-dimension LLM-based quality evaluation with refinement loops
- **Requirement Tracking**: Cross-turn requirement extraction and status tracking
- **Context Consolidation**: Prevents lost-in-middle-turns phenomenon (every 3 turns)
- **Conversation Workflow**: Production-ready AsyncIO workflow with state persistence
- **REPL Interface**: Rich console interface with real-time metrics and commands
- **Robust Fallback System**: Heuristic fallbacks when LLM providers are unavailable
- **Real LLM Integration**: Works with OpenAI and Anthropic APIs via mcp-agent
- **Research Metrics**: Tracks answer bloat, premature attempts, quality scores, consolidation
- **Comprehensive Testing**: Automated test suite with readable output and validation

### Architecture

```
examples/reliable_conversation/
├── src/
│   ├── workflows/
│   │   └── conversation_workflow.py    # Main workflow (AsyncIO + Temporal ready)
│   ├── models/
│   │   └── conversation_models.py      # Research-based data models
│   ├── tasks/
│   │   ├── task_functions.py           # Quality control orchestration
│   │   ├── llm_evaluators.py          # LLM-based evaluation with fallbacks
│   │   └── quality_control.py         # Quality pipeline coordination
│   └── utils/
│       ├── logging.py                  # Enhanced logging with conversation context
│       ├── config.py                   # Configuration management
│       ├── test_runner.py              # Test framework with rich output
│       ├── progress_reporter.py        # Real-time progress display
│       └── readable_output.py          # Rich console formatting
├── main.py                             # Production REPL interface
├── test_basic.py                       # Automated test suite
├── mcp_agent.config.yaml              # mcp-agent configuration
└── requirements.txt                    # Dependencies
```

### Key Features

1. **Quality-Controlled Responses**: Every response undergoes 7-dimension evaluation and potential refinement
2. **Conversation State Management**: Complete state persistence with turn-by-turn tracking
3. **Research-Based Metrics**: Tracks answer bloat ratios, premature attempts, consolidation effectiveness
4. **Robust Fallback System**: Graceful degradation when LLM providers are unavailable
5. **Rich Console Interface**: Real-time progress, quality metrics, and conversation statistics
6. **Comprehensive Testing**: Automated 3-turn conversation tests with detailed validation
7. **MCP Integration**: Filesystem access and extensible tool framework
8. **Production Ready**: Error handling, logging, and operational monitoring

### Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run automated tests (recommended first)
python test_basic.py

# Launch interactive REPL
python main.py
```

### REPL Commands

- `/help` - Show comprehensive help with feature overview
- `/stats` - Show detailed conversation statistics and research metrics
- `/requirements` - Show tracked requirements with status and confidence
- `/config` - Display current configuration settings
- `/exit` - Exit the conversation with summary

### Configuration

Edit `mcp_agent.config.yaml` and `mcp_agent.secrets.yaml`:

**Configuration (`mcp_agent.config.yaml`):**
```yaml
rcm:
  quality_threshold: 0.8              # Minimum quality score for responses
  max_refinement_attempts: 3          # Max response refinement iterations  
  consolidation_interval: 3           # Context consolidation frequency (every N turns)
  evaluator_model_provider: "openai"  # LLM provider for quality evaluation
  verbose_metrics: false              # Show detailed quality metrics in REPL
```

**Secrets (`mcp_agent.secrets.yaml`):**
```yaml
# Add your API keys to enable real LLM calls
openai:
  api_key: "your-openai-api-key-here"

anthropic:
  api_key: "your-anthropic-api-key-here"
```

**Note**: The system includes comprehensive fallbacks that work without API keys for testing.

### Research Implementation

Implements all key findings from "LLMs Get Lost in Multi-Turn Conversation":

**1. Premature Answer Prevention (39% of failures)**
- Detects completion markers and pending requirements
- Prevents responses until sufficient information gathered
- Quality evaluation includes premature attempt scoring

**2. Answer Bloat Prevention (20-300% length increase)**
- Tracks response length ratios across turns
- Verbosity scoring in quality metrics
- Automatic response optimization

**3. Lost-in-Middle-Turns Prevention**
- Context consolidation every 3 turns
- Explicit middle-turn reference tracking
- Requirement extraction across all conversation turns

**4. Instruction Forgetting Prevention**
- Cross-turn requirement tracking with status management
- LLM-based requirement extraction and validation
- Complete conversation state persistence

### Quality Control Pipeline

**7-Dimension Evaluation System:**
1. **Clarity** (0-1): Response structure and comprehensibility
2. **Completeness** (0-1): Requirements coverage
3. **Assumptions** (0-1, lower better): Unsupported assumptions
4. **Verbosity** (0-1, lower better): Response bloat detection
5. **Premature Attempt** (boolean): Complete solution without info
6. **Middle Turn Reference** (0-1): References to middle conversation
7. **Requirement Tracking** (0-1): Cross-turn requirement awareness

**Refinement Loop**: Responses below quality threshold automatically refined up to 3 attempts

### Architecture Design

**Conversation-as-Workflow Pattern:**
```python
@app.workflow
class ConversationWorkflow(Workflow[Dict[str, Any]]):
    async def run(self, args: Dict[str, Any]) -> WorkflowResult[Dict[str, Any]]:
        # Supports both AsyncIO (single turn) and Temporal (long-running)
        return await self._process_turn_with_quality_control(args)
```

**Quality Control Integration:**
```python
# task_functions.py - All functions include heuristic fallbacks
async def process_turn_with_quality(params):
    requirements = await extract_requirements_with_llm(...)
    context = await consolidate_context_with_llm(...) 
    response = await generate_response_with_constraints(...)
    metrics = await evaluate_quality_with_llm(...)
    return refined_response_if_needed
```

### Testing

**Automated Test Suite:**
```bash
# Comprehensive 3-turn conversation test with validation
python test_basic.py
```

**Features Tested:**
- Multi-turn state persistence and requirement tracking
- Quality control pipeline with real LLM calls + fallbacks
- Context consolidation triggering (turn 3)
- Research metrics collection (bloat ratios, premature attempts)
- Rich console output with detailed analysis

**Manual Testing (REPL):**
```bash
python main.py
# Try a multi-turn coding request to see quality control in action
> I need help creating a Python function
> Actually, it should also handle edge cases  
> Can you add error handling too?
> /stats  # See research metrics
```

### Status

**✅ Fully Implemented & Tested:**
- Complete quality control pipeline based on research findings
- Robust fallback system for reliability
- Production-ready REPL with rich formatting
- Comprehensive test suite with detailed validation
- All core research metrics tracking

**🔄 Planned Enhancements:**
- Temporal workflow support for long-running conversations
- Specialized task handlers for code vs chat queries
- Advanced MCP tool integration patterns
