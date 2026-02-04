# Git-Based Multi-Agent Coordination

This example demonstrates a real-world multi-agent coordination pattern used in production by [OpenClaw](https://github.com/cyanheads/openclaw), where 4 sibling agents (Sammy, Coggy, Maude, and Jane) coordinate asynchronously using git branches as persistent workspaces.

## The Pattern

Unlike traditional multi-agent systems that rely on:
- Central orchestrators (single point of failure)
- In-memory message queues (no persistence)
- Synchronous RPC (tight coupling)

This pattern uses **git as the coordination substrate**:

```
workspace-sync.git/
├── sammy/              # Sammy's workspace branch
│   ├── inbox/
│   │   ├── coggy/      # Messages TO Coggy
│   │   ├── maude/      # Messages TO Maude
│   │   └── jane/       # Messages TO Jane
│   ├── memory/         # Daily logs
│   └── skills/         # Shared capabilities
├── coggy/              # Coggy's workspace branch
│   ├── inbox/
│   │   ├── sammy/
│   │   ├── maude/
│   │   └── jane/
│   ├── memory/
│   └── skills/
├── maude/              # Maude's workspace branch
│   └── ...
└── jane/               # Jane's workspace branch
    └── ...
```

### Key Principles

1. **Each agent owns exactly one branch** - no write conflicts
2. **Inbox protocol** - Agent A writes to `A/inbox/B/` to send to B; B reads from `A/inbox/B/`
3. **Async by default** - Agents check messages when convenient
4. **Git provides** - History, audit trail, conflict resolution, offline work
5. **No orchestrator** - Peer-to-peer coordination

## Why This Works

### Compared to Central Orchestrator Pattern

**Central Orchestrator:**
```python
# Orchestrator has to manage everything
orchestrator = Orchestrator(agents=[a, b, c])
result = await orchestrator.execute(plan)  # Single point of failure
```

**Git Coordination:**
```python
# Agents coordinate peer-to-peer
await agent_a.send_message("agent_b", task)
messages = await agent_b.check_messages()
# No central orchestrator needed
```

### Compared to Swarm/Handoff Pattern

**Swarm Pattern:**
- In-memory handoffs
- Lost if process crashes
- No audit trail
- Synchronous transitions

**Git Pattern:**
- Persistent messages
- Survives restarts
- Complete git history
- Async coordination

### Real-World Benefits

From production deployment with 4 agents over 2+ months:

1. **Survives restarts** - Messages persist across agent restarts
2. **Clear ownership** - Each agent has their own workspace
3. **Audit trail** - `git log` shows entire collaboration history
4. **Offline work** - Agents can work independently, sync later
5. **Conflict resolution** - Git handles merge conflicts
6. **Skill sharing** - Agents discover each other's capabilities via git
7. **No race conditions** - Only one writer per workspace

## Running the Example

### Prerequisites

1. Clone the mcp-agent repository:
```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/workflows/workflow_git_coordination
```

2. Install dependencies:
```bash
uv sync  # Install mcp-agent
uv pip install -r requirements.txt  # Install example-specific deps
```

3. Configure your LLM provider:
```bash
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
# Edit mcp_agent.secrets.yaml with your API key
```

### Run the Demo

```bash
uv run main.py
```

This will simulate a complete multi-agent coordination scenario:
- Sammy receives a research task
- Delegates subtasks to Maude (research), Coggy (analysis), Jane (code)
- Agents work independently
- Send progress updates via inbox
- Share skills with each other
- Sammy synthesizes final results

## Example Output

```
==========================================
Git-Based Multi-Agent Coordination Demo
Simulating OpenClaw's 4-sibling collaboration pattern
==========================================

Phase 1: Workspace Initialization

📝 Sammy: Memory updated
📝 Coggy: Memory updated
📝 Maude: Memory updated
📝 Jane: Memory updated

Phase 2: Task Arrival & Delegation

📬 Sammy → Maude: Message sent
📬 Sammy → Coggy: Message sent
📬 Sammy → Jane: Message sent

Phase 3: Agents Process Messages

📨 Maude: Found 1 message(s)
📨 Coggy: Found 1 message(s)
📨 Jane: Found 1 message(s)

Phase 4: Work & Skill Sharing

🛠️  Maude: Shared skill 'research-methodology'
🛠️  Coggy: Shared skill 'git-workflow-analysis'
🛠️  Jane: Shared skill 'code-generation'

Phase 5: Skill Discovery

Sammy discovered skills:
  • maude: research-methodology
  • coggy: git-workflow-analysis
  • jane: code-generation

Phase 6: Progress Updates

📬 Maude → Sammy: Message sent
📬 Coggy → Sammy: Message sent
📬 Jane → Sammy: Message sent

Phase 7: Results Synthesis

📨 Sammy: Found 3 message(s)

==========================================
Coordination Summary

  • Total Messages Exchanged: 7
  • Skills Shared: 3
  • Agents Coordinated: 4
  • Tasks Delegated: 3
  • Workspace Branches: 4

==========================================
✓ Coordination Complete

All agents coordinated asynchronously using git-based workspaces.
No central orchestrator required. Fully auditable via git history.
==========================================
```

## Architecture Deep Dive

### Message Flow

```
┌─────────┐                           ┌─────────┐
│ Agent A │                           │ Agent B │
└────┬────┘                           └────┬────┘
     │                                     │
     │ 1. Write to A/inbox/B/message.md   │
     │────────────────────────────────────>│
     │                                     │
     │ 2. git commit -m "Message to B"    │
     │                                     │
     │ 3. git push origin agent-a          │
     │                                     │
     │                                     │ 4. git fetch origin agent-a
     │                                     │
     │                                     │ 5. Read A/inbox/B/message.md
     │                                     │<────────────────────────────
     │                                     │
     │                                     │ 6. Process message
     │                                     │
     │                                     │ 7. Write to B/inbox/A/reply.md
     │<────────────────────────────────────│
     │                                     │
```

### Inbox Protocol

**Sending a message:**
```python
# Agent A sends to Agent B
inbox_dir = workspace_a / "inbox" / "agent-b"
inbox_dir.mkdir(parents=True, exist_ok=True)

message_file = inbox_dir / f"{timestamp}-message.md"
message_file.write_text(content)

# Commit and push
git commit -m "Message to Agent B"
git push origin agent-a
```

**Receiving messages:**
```python
# Agent B checks for messages FROM Agent A
other_workspace = workspace_a  # Fetch agent-a branch
inbox_dir = other_workspace / "inbox" / "agent-b"

for msg_file in inbox_dir.glob("*.md"):
    content = msg_file.read_text()
    # Process message
```

### Skill Sharing

Agents can share capabilities through their `skills/` directory:

```python
# Agent shares a skill
skill_file = workspace / "skills" / "research-methodology.md"
skill_file.write_text(skill_content)

# Other agents discover it
all_skills = {}
for sibling_workspace in workspaces:
    skills_dir = sibling_workspace / "skills"
    if skills_dir.exists():
        all_skills[sibling_workspace.name] = list(skills_dir.glob("*.md"))
```

## Production Deployment Notes

### Real-World Implementation (OpenClaw)

In production, this pattern is deployed as:

1. **Bare git repository** on a shared server
   ```bash
   git init --bare ~/.openclaw/git-repos/workspace-sync.git
   ```

2. **Each agent clones and works on their branch**
   ```bash
   git clone ~/.openclaw/git-repos/workspace-sync.git
   git checkout -b agent-name
   ```

3. **Periodic sync** (via heartbeat or cron)
   ```bash
   git fetch origin  # Get all sibling updates
   git push origin agent-name  # Share my updates
   ```

### Scaling Considerations

- **Works with N agents** - Just add another branch
- **Message retention** - Use git gc or prune old messages
- **Large files** - Use git-lfs for binary attachments
- **Network overhead** - Only fetch sibling branches when needed

### Integration with MCP

The pattern naturally integrates with MCP servers:

```python
agent = Agent(
    name="sammy",
    instruction="Use filesystem MCP to manage workspace and inbox",
    server_names=["filesystem"],
)

# Agent can use filesystem MCP tools to:
# - Read inbox messages
# - Write memory logs
# - Share skills
# - Commit changes
```

## Comparison with Other Patterns

| Pattern | Persistence | Audit Trail | Offline Work | Coordination |
|---------|------------|-------------|--------------|--------------|
| Central Orchestrator | ❌ | ❌ | ❌ | Synchronous |
| Swarm/Handoff | ❌ | ⚠️ | ❌ | Synchronous |
| Message Queue | ✅ | ⚠️ | ❌ | Async |
| **Git Coordination** | ✅ | ✅ | ✅ | **Async** |

## When to Use This Pattern

**Good fit:**
- Multiple agents with specialized skills
- Long-running workflows (hours/days)
- Need for audit trail
- Offline or unreliable network
- Distributed deployment

**Not ideal for:**
- Real-time coordination (use message queue)
- Single-session workflows (use orchestrator)
- Stateless request/response (use function calling)

## Contributing

This example demonstrates a novel coordination pattern tested in production. We welcome:

- Additional coordination patterns
- Performance benchmarks
- Integration examples with other MCP servers
- Multi-language implementations

See [CONTRIBUTING.md](../../../CONTRIBUTING.md) for guidelines.

## Related Examples

- [workflow_orchestrator_worker](../workflow_orchestrator_worker/) - Central orchestrator pattern
- [workflow_swarm](../workflow_swarm/) - Swarm/handoff pattern
- [workflow_parallel](../workflow_parallel/) - Parallel execution

## References

- [OpenClaw](https://github.com/cyanheads/openclaw) - Multi-agent coordination framework
- [MCP Specification](https://modelcontextprotocol.io/)
- [Git Internals](https://git-scm.com/book/en/v2/Git-Internals-Plumbing-and-Porcelain)

## License

This example is licensed under the same terms as mcp-agent (Apache 2.0).

---

**Questions?** Open an issue or ask in the [LastMile Discord](https://lmai.link/discord/mcp-agent).
