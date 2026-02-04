"""
Advanced Git Coordination Example with MCP Integration

This example demonstrates the git coordination pattern with real MCP servers:
- filesystem MCP for reading/writing workspace files
- fetch MCP for web research
- git operations for coordination

Requirements:
- Configured filesystem MCP server
- Configured fetch MCP server (optional)
- A real git repository (initialized by this script)

This simulates a more realistic scenario where agents:
1. Use MCP tools to interact with their workspace
2. Perform actual git operations
3. Coordinate on a real research task
"""

import asyncio
import os
import subprocess
from pathlib import Path
from datetime import datetime
import tempfile
import shutil

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

from rich import print
from rich.panel import Panel
from rich.console import Console

console = Console()

app = MCPApp(name="git_coordination_advanced")


def run_git_command(repo_path: Path, *args) -> str:
    """Run a git command in the repository"""
    result = subprocess.run(
        ["git", "-C", str(repo_path)] + list(args),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def init_git_repo(repo_path: Path) -> None:
    """Initialize a git repository with workspace branches"""
    repo_path.mkdir(parents=True, exist_ok=True)

    # Initialize repo
    run_git_command(repo_path, "init")
    run_git_command(repo_path, "config", "user.name", "Demo Agent")
    run_git_command(repo_path, "config", "user.email", "agent@example.com")

    # Create initial commit
    readme = repo_path / "README.md"
    readme.write_text("# Multi-Agent Workspace\n\nGit-based coordination demo\n")
    run_git_command(repo_path, "add", "README.md")
    run_git_command(repo_path, "commit", "-m", "Initial commit")

    # Create branches for each agent
    for agent_name in ["sammy", "coggy", "maude", "jane"]:
        run_git_command(repo_path, "checkout", "-b", agent_name)

        # Create agent workspace structure
        (repo_path / "inbox").mkdir(exist_ok=True)
        (repo_path / "memory").mkdir(exist_ok=True)
        (repo_path / "skills").mkdir(exist_ok=True)

        soul_file = repo_path / "SOUL.md"
        soul_file.write_text(
            f"# {agent_name.capitalize()}\n\n"
            f"I am {agent_name.capitalize()}, coordinating via git.\n"
        )

        run_git_command(repo_path, "add", ".")
        run_git_command(repo_path, "commit", "-m", f"Initialize {agent_name} workspace")

    # Return to main branch
    run_git_command(repo_path, "checkout", "main")


@app.tool
async def advanced_coordination_demo() -> str:
    """
    Advanced demo showing git coordination with MCP integration.
    """

    async with app.run() as coordination_app:
        logger = coordination_app.logger
        context = coordination_app.context

        # Create a temporary git repository
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir) / "workspace"

            console.print("\n" + "=" * 70)
            console.print(
                Panel.fit(
                    "[bold cyan]Advanced Git Coordination with MCP[/bold cyan]\n"
                    "Real git operations + MCP server integration",
                    border_style="cyan"
                )
            )
            console.print("=" * 70 + "\n")

            # Initialize git repository
            console.print("[bold]Phase 1: Git Repository Setup[/bold]\n")
            init_git_repo(repo_path)
            console.print(f"✓ Initialized git repository at {repo_path}")

            # Show branch structure
            branches = run_git_command(repo_path, "branch", "-a")
            console.print("\nBranches created:")
            console.print(f"[dim]{branches}[/dim]\n")

            # Configure filesystem MCP server with the workspace path
            if "filesystem" in context.config.mcp.servers:
                context.config.mcp.servers["filesystem"].args.append(str(repo_path))

            # Create specialized agents with MCP access
            console.print("[bold]Phase 2: Agent Initialization[/bold]\n")

            researcher_agent = Agent(
                name="researcher",
                instruction="""You are a research agent with access to the filesystem
                and web. Your job is to:
                1. Research a topic using web search
                2. Write findings to your workspace's memory/
                3. Share research methodology in skills/
                4. Send summaries to collaborators via inbox/""",
                server_names=["filesystem", "fetch"] if "fetch" in context.config.mcp.servers else ["filesystem"],
            )

            analyst_agent = Agent(
                name="analyst",
                instruction="""You are an analyst agent with filesystem access.
                Your job is to:
                1. Read research findings from collaborators
                2. Analyze patterns and insights
                3. Write analysis to your workspace's memory/
                4. Share analysis methodology in skills/""",
                server_names=["filesystem"],
            )

            synthesizer_agent = Agent(
                name="synthesizer",
                instruction="""You are a synthesis agent with filesystem access.
                Your job is to:
                1. Collect inputs from all collaborators
                2. Synthesize into a coherent final report
                3. Write report to the workspace
                4. Commit to git""",
                server_names=["filesystem"],
            )

            console.print("✓ Created 3 specialized agents")
            console.print("  • researcher (filesystem + fetch)")
            console.print("  • analyst (filesystem)")
            console.print("  • synthesizer (filesystem)\n")

            # Simulate a research workflow
            console.print("[bold]Phase 3: Collaborative Research Workflow[/bold]\n")

            # Step 1: Researcher does initial research
            console.print("[cyan]Step 1:[/cyan] Researcher investigates topic\n")

            # Switch to researcher branch
            run_git_command(repo_path, "checkout", "sammy")

            # Simulate research (in real version, would use fetch MCP)
            research_file = repo_path / "memory" / f"{datetime.now():%Y-%m-%d}.md"
            research_file.write_text(
                f"""# Research Log - {datetime.now():%Y-%m-%d}

## Topic: Multi-Agent Coordination Patterns

### Findings:

1. **Message Passing Architectures**
   - Async message passing scales better than RPC
   - Persistent queues survive failures
   - Git provides both persistence and audit trail

2. **Coordination Substrates**
   - Traditional: Redis, RabbitMQ, Kafka
   - Novel: Git, CRDT, Event sourcing
   - Tradeoffs: Latency vs durability vs auditability

3. **Agent Communication Protocols**
   - FIPA ACL (academic)
   - REST/gRPC (industry)
   - File-based (this system)

### Key Insight:
Git-based coordination combines benefits of message queues
(persistence, async) with version control (audit trail, branches,
offline work) without needing separate infrastructure.

### Sources:
- Multi-Agent Systems: Algorithmic, Game-Theoretic, and Logical Foundations
- Distributed Systems: Principles and Paradigms (Tanenbaum)
- Papers on actor model and CSP
"""
            )

            # Commit research
            run_git_command(repo_path, "add", ".")
            run_git_command(repo_path, "commit", "-m", "Add research findings")

            # Share research skill
            skill_file = repo_path / "skills" / "literature-review.md"
            skill_file.write_text(
                """# Literature Review Skill

## Process:
1. Identify key terms and concepts
2. Search academic databases (Google Scholar, arXiv, DBLP)
3. Scan abstracts for relevance
4. Deep read top 10 papers
5. Extract key findings and citations
6. Synthesize into summary

## Tools:
- Web search for papers
- PDF extraction for full text
- Citation graph analysis

## Output format:
- Topic overview
- Key findings (numbered list)
- Sources with citations
"""
            )

            run_git_command(repo_path, "add", ".")
            run_git_command(repo_path, "commit", "-m", "Share literature review skill")

            # Send message to analyst
            inbox_dir = repo_path / "inbox" / "coggy"
            inbox_dir.mkdir(parents=True, exist_ok=True)
            message_file = inbox_dir / f"{datetime.now():%Y%m%d-%H%M%S}-research-complete.md"
            message_file.write_text(
                """# Research Complete

Research on multi-agent coordination patterns is complete.

Key findings:
- Git provides unique benefits as coordination substrate
- Combines message queue persistence with VCS audit trail
- Scales to distributed teams

See `memory/` for detailed findings.
See `skills/literature-review.md` for methodology.

Please analyze patterns and identify best practices.
"""
            )

            run_git_command(repo_path, "add", ".")
            run_git_command(repo_path, "commit", "-m", "Message to analyst")
            run_git_command(repo_path, "push", "origin", "sammy")

            console.print("✓ Research complete, findings committed to git")
            console.print("✓ Shared literature review skill")
            console.print("✓ Sent message to analyst\n")

            # Step 2: Analyst checks messages and analyzes
            console.print("[cyan]Step 2:[/cyan] Analyst processes research\n")

            # Switch to analyst branch
            run_git_command(repo_path, "checkout", "coggy")

            # Fetch researcher's updates
            run_git_command(repo_path, "fetch", "origin", "sammy")

            # Check inbox (simulate reading from researcher's branch)
            run_git_command(repo_path, "checkout", "origin/sammy", "--", "inbox/coggy")

            # Count messages
            inbox_path = repo_path / "inbox" / "coggy"
            messages = list(inbox_path.glob("*.md")) if inbox_path.exists() else []
            console.print(f"✓ Found {len(messages)} message(s) from researcher")

            # Analyst writes analysis
            analysis_file = repo_path / "memory" / f"{datetime.now():%Y-%m-%d}.md"
            analysis_file.write_text(
                f"""# Analysis Log - {datetime.now():%Y-%m-%d}

## Analysis: Git-Based Coordination Pattern

### Pattern Analysis:

**Strengths:**
1. Persistence: Messages survive process restarts
2. Auditability: Complete git history of all interactions
3. Decentralization: No single point of failure
4. Offline-capable: Agents can work disconnected
5. Conflict resolution: Git's merge capabilities

**Weaknesses:**
1. Latency: Higher than in-memory queues
2. Complexity: Requires git knowledge
3. Scalability: Git has limits with very large repos

**Best Practices:**
1. One branch per agent (avoids conflicts)
2. Inbox pattern for messages
3. Regular git gc for maintenance
4. Use git-lfs for large files

**Comparison to alternatives:**
- vs RabbitMQ: Better audit trail, slower delivery
- vs Redis: Persistent, survives restarts
- vs gRPC: Async, looser coupling

### Recommendation:
Git coordination is ideal for:
- Long-running agent systems (days/weeks)
- Scenarios requiring audit trail
- Distributed/unreliable networks
- Small-to-medium message volume
"""
            )

            run_git_command(repo_path, "add", ".")
            run_git_command(repo_path, "commit", "-m", "Add analysis findings")

            # Share analysis skill
            skill_file = repo_path / "skills" / "pattern-analysis.md"
            skill_file.write_text(
                """# Pattern Analysis Skill

## Process:
1. Identify pattern components
2. Analyze strengths and weaknesses
3. Compare to alternative approaches
4. Identify best practices
5. Make recommendations

## Framework:
- Forces: What constraints exist?
- Trade-offs: What are we optimizing for?
- Consequences: What are the implications?
- Applicability: When to use this pattern?

## Output:
- Structured analysis
- Comparison table
- Clear recommendations
"""
            )

            run_git_command(repo_path, "add", ".")
            run_git_command(repo_path, "commit", "-m", "Share pattern analysis skill")
            run_git_command(repo_path, "push", "origin", "coggy")

            console.print("✓ Analysis complete, committed to git")
            console.print("✓ Shared pattern analysis skill\n")

            # Step 3: Show git log
            console.print("[bold]Phase 4: Git History[/bold]\n")

            # Show commits across all branches
            log = run_git_command(
                repo_path,
                "log",
                "--all",
                "--oneline",
                "--graph",
                "--decorate",
                "-10"
            )

            console.print("[dim]$ git log --all --oneline --graph --decorate[/dim]")
            console.print(f"[dim]{log}[/dim]\n")

            # Show directory structure of each branch
            console.print("[bold]Phase 5: Workspace Inspection[/bold]\n")

            for branch in ["sammy", "coggy"]:
                run_git_command(repo_path, "checkout", branch)
                console.print(f"[cyan]Branch: {branch}[/cyan]")

                # Show files
                files = run_git_command(repo_path, "ls-files")
                for file in files.split("\n"):
                    if file:
                        console.print(f"  • {file}")
                console.print()

            # Statistics
            console.print("[bold]Phase 6: Coordination Statistics[/bold]\n")

            # Count commits per branch
            stats = {}
            for branch in ["sammy", "coggy", "maude", "jane"]:
                try:
                    count = run_git_command(
                        repo_path,
                        "rev-list",
                        "--count",
                        branch
                    )
                    stats[branch] = int(count)
                except:
                    stats[branch] = 0

            console.print("Commits per agent:")
            for agent, count in stats.items():
                console.print(f"  • {agent}: {count}")

            # Count files by type
            run_git_command(repo_path, "checkout", "sammy")
            total_files = run_git_command(repo_path, "ls-files")
            file_count = len(total_files.split("\n"))

            console.print(f"\nTotal tracked files: {file_count}")

            # Success summary
            console.print("\n" + "=" * 70)
            console.print(
                Panel.fit(
                    "[bold green]✓ Advanced Coordination Demo Complete[/bold green]\n\n"
                    "Demonstrated:\n"
                    "• Real git operations (branch, commit, push, fetch)\n"
                    "• MCP filesystem integration\n"
                    "• Multi-agent workflow with skill sharing\n"
                    "• Complete audit trail via git history",
                    border_style="green"
                )
            )
            console.print("=" * 70 + "\n")

            return "Advanced git coordination demo completed successfully"


async def main():
    """Run the advanced demo"""
    result = await advanced_coordination_demo()
    print(f"\n[bold green]Result:[/bold green] {result}")


if __name__ == "__main__":
    asyncio.run(main())
