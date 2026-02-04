"""
Multi-Agent Git-Based Coordination Workflow

This example demonstrates a real-world multi-agent coordination pattern used by
OpenClaw's 4-sibling agent system (Sammy, Coggy, Maude, Jane). The agents use
git branches as persistent workspaces and coordinate asynchronously through an
inbox-based messaging system.

Key Patterns Demonstrated:
- Git branches as agent workspaces
- Async communication via inbox files
- Skill sharing through git history
- Decentralized task delegation
- No central orchestrator - agents coordinate peer-to-peer

This pattern scales to any number of agents and provides:
- Complete audit trail (git history)
- Conflict resolution (git merge)
- Offline work support (git fetch/push)
- Explicit synchronization points
"""

import asyncio
import os
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Dict, List

from rich import print
from rich.panel import Panel
from rich.console import Console

console = Console()


class GitWorkspace:
    """
    Simulates a git-based agent workspace.
    Each agent has their own branch with:
    - inbox/ directory for receiving messages
    - memory/ directory for daily logs
    - skills/ directory for shared capabilities
    """

    def __init__(self, repo_path: Path, agent_name: str):
        self.repo_path = repo_path
        self.agent_name = agent_name
        self.branch = agent_name.lower()
        self.workspace_path = repo_path / agent_name.lower()

    async def setup(self):
        """Initialize git workspace for this agent"""
        # In a real system, this would be: git checkout -b {branch}
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        (self.workspace_path / "inbox").mkdir(exist_ok=True)
        (self.workspace_path / "memory").mkdir(exist_ok=True)
        (self.workspace_path / "skills").mkdir(exist_ok=True)

        # Create initial files
        with open(self.workspace_path / "SOUL.md", "w") as f:
            f.write(f"# {self.agent_name}\n\nI am {self.agent_name}, "
                    f"coordinating with my siblings via git.\n")

    async def send_message(self, to_agent: str, message: str):
        """
        Send a message to another agent.
        In the real system: Write to MY workspace's inbox/{recipient}/
        The recipient reads from THEIR workspace's inbox/{my_name}/
        """
        inbox_dir = self.workspace_path / "inbox" / to_agent.lower()
        inbox_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        message_file = inbox_dir / f"{timestamp}-message.md"

        with open(message_file, "w") as f:
            f.write(f"# Message from {self.agent_name} to {to_agent}\n\n")
            f.write(f"**Time:** {datetime.now().isoformat()}\n\n")
            f.write(message)

        console.print(
            f"📬 [cyan]{self.agent_name}[/cyan] → [yellow]{to_agent}[/yellow]: "
            f"Message sent"
        )

    async def check_messages(self, from_agent: str = None) -> List[Dict]:
        """
        Check for messages FROM other agents.
        In the real system: Check sibling workspaces' inbox/{my_name}/ directories
        This requires fetching their branches: git fetch origin {sibling}
        """
        messages = []

        if from_agent:
            # Check specific agent's workspace for messages to us
            other_workspace = self.repo_path / from_agent.lower()
            inbox_dir = other_workspace / "inbox" / self.agent_name.lower()

            if inbox_dir.exists():
                for msg_file in sorted(inbox_dir.glob("*.md")):
                    with open(msg_file) as f:
                        content = f.read()
                    messages.append({
                        "from": from_agent,
                        "file": msg_file.name,
                        "content": content
                    })
        else:
            # Check all sibling workspaces
            for sibling_dir in self.repo_path.iterdir():
                if not sibling_dir.is_dir() or sibling_dir.name == self.agent_name.lower():
                    continue

                inbox_dir = sibling_dir / "inbox" / self.agent_name.lower()
                if inbox_dir.exists():
                    for msg_file in sorted(inbox_dir.glob("*.md")):
                        with open(msg_file) as f:
                            content = f.read()
                        messages.append({
                            "from": sibling_dir.name,
                            "file": msg_file.name,
                            "content": content
                        })

        if messages:
            console.print(
                f"📨 [cyan]{self.agent_name}[/cyan]: "
                f"Found {len(messages)} message(s)"
            )

        return messages

    async def write_memory(self, entry: str):
        """Write to daily memory log"""
        today = datetime.now().strftime("%Y-%m-%d")
        memory_file = self.workspace_path / "memory" / f"{today}.md"

        with open(memory_file, "a") as f:
            timestamp = datetime.now().strftime("%H:%M:%S")
            f.write(f"\n## {timestamp}\n\n{entry}\n")

        console.print(
            f"📝 [cyan]{self.agent_name}[/cyan]: Memory updated"
        )

    async def share_skill(self, skill_name: str, skill_content: str):
        """Share a skill that other agents can discover"""
        skill_file = self.workspace_path / "skills" / f"{skill_name}.md"
        skill_file.parent.mkdir(exist_ok=True)

        with open(skill_file, "w") as f:
            f.write(f"# Skill: {skill_name}\n\n")
            f.write(f"**Author:** {self.agent_name}\n\n")
            f.write(skill_content)

        console.print(
            f"🛠️  [cyan]{self.agent_name}[/cyan]: Shared skill '{skill_name}'"
        )

    async def discover_skills(self) -> Dict[str, List[str]]:
        """Discover skills from all sibling workspaces"""
        all_skills = {}

        for sibling_dir in self.repo_path.iterdir():
            if not sibling_dir.is_dir():
                continue

            skills_dir = sibling_dir / "skills"
            if skills_dir.exists():
                skills = [f.stem for f in skills_dir.glob("*.md")]
                if skills:
                    all_skills[sibling_dir.name] = skills

        return all_skills


async def demonstrate_coordination() -> str:
    """
    Demonstrates multi-agent coordination using git-based workspaces.

    This simulates a real scenario where agents:
    1. Receive a complex task
    2. Delegate subtasks to specialized siblings
    3. Coordinate async via inbox messages
    4. Share skills and discoveries
    5. Synthesize results
    """

    # Create a temporary git repository to simulate our workspace
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "workspace-sync"
        repo_path.mkdir()

        console.print("\n" + "=" * 60)
        console.print(
            Panel.fit(
                "[bold cyan]Git-Based Multi-Agent Coordination Demo[/bold cyan]\n"
                "Simulating OpenClaw's 4-sibling collaboration pattern",
                border_style="cyan"
            )
        )
        console.print("=" * 60 + "\n")

        # Initialize our 4 agents with git workspaces
        agents = {
            "Sammy": GitWorkspace(repo_path, "Sammy"),
            "Coggy": GitWorkspace(repo_path, "Coggy"),
            "Maude": GitWorkspace(repo_path, "Maude"),
            "Jane": GitWorkspace(repo_path, "Jane"),
        }

        console.print("[bold]Phase 1: Workspace Initialization[/bold]\n")
        for agent in agents.values():
            await agent.setup()

        # Simulate a research task arriving to Sammy
        console.print("\n[bold]Phase 2: Task Arrival & Delegation[/bold]\n")

        await agents["Sammy"].write_memory(
            "Received research task: Analyze impact of async agent "
            "coordination patterns in production systems"
        )

        # Sammy delegates subtasks via inbox messages
        await agents["Sammy"].send_message(
            "Maude",
            "**Task:** Literature Review\n\n"
            "Please research academic papers on multi-agent coordination "
            "patterns. Focus on async communication methods.\n\n"
            "**Deadline:** EOD\n"
            "**Priority:** High"
        )

        await agents["Sammy"].send_message(
            "Coggy",
            "**Task:** Technical Analysis\n\n"
            "Analyze our git-based coordination system. Document the "
            "architecture, benefits, and potential improvements.\n\n"
            "**Deadline:** EOD\n"
            "**Priority:** High"
        )

        await agents["Sammy"].send_message(
            "Jane",
            "**Task:** Implementation Examples\n\n"
            "Create code examples showing how to implement the inbox "
            "pattern in different languages (Python, TypeScript).\n\n"
            "**Deadline:** EOD\n"
            "**Priority:** Medium"
        )

        # Simulate agents checking their messages
        console.print("\n[bold]Phase 3: Agents Process Messages[/bold]\n")

        maude_messages = await agents["Maude"].check_messages()
        coggy_messages = await agents["Coggy"].check_messages()
        jane_messages = await agents["Jane"].check_messages()

        # Agents work and share skills
        console.print("\n[bold]Phase 4: Work & Skill Sharing[/bold]\n")

        await agents["Maude"].share_skill(
            "research-methodology",
            """
## Research Methodology Skill

**Purpose:** Systematic approach to researching complex topics

**Steps:**
1. Identify key search terms
2. Query academic databases (Google Scholar, arXiv)
3. Filter by relevance and citation count
4. Extract key findings
5. Synthesize into coherent summary

**Tools needed:**
- Web search MCP server
- PDF reader MCP server
- Note-taking system
"""
        )

        await agents["Coggy"].share_skill(
            "git-workflow-analysis",
            """
## Git Workflow Analysis Skill

**Purpose:** Analyze git-based collaboration patterns

**Key metrics:**
- Commit frequency per agent
- Message exchange patterns
- Skill sharing frequency
- Merge conflict rate

**Analysis tools:**
- git log analysis
- Branch comparison
- File change tracking
"""
        )

        await agents["Jane"].share_skill(
            "code-generation",
            """
## Code Generation Skill

**Purpose:** Generate clean, tested code examples

**Approach:**
1. Understand requirements
2. Choose appropriate patterns
3. Generate implementation
4. Add comprehensive tests
5. Document usage

**Languages:**
- Python (primary)
- TypeScript
- Rust
"""
        )

        # Agents discover each other's skills
        console.print("\n[bold]Phase 5: Skill Discovery[/bold]\n")

        for agent_name, agent in agents.items():
            skills = await agent.discover_skills()
            if skills:
                console.print(f"[cyan]{agent_name}[/cyan] discovered skills:")
                for sibling, skill_list in skills.items():
                    console.print(f"  • {sibling}: {', '.join(skill_list)}")

        # Agents send progress updates back to Sammy
        console.print("\n[bold]Phase 6: Progress Updates[/bold]\n")

        await agents["Maude"].send_message(
            "Sammy",
            "**Status Update:** Literature Review\n\n"
            "Found 12 relevant papers on multi-agent coordination. "
            "Key finding: Async message-passing scales better than "
            "synchronous RPC for loosely-coupled agents.\n\n"
            "Drafting summary document."
        )

        await agents["Coggy"].send_message(
            "Sammy",
            "**Status Update:** Technical Analysis\n\n"
            "Completed architecture analysis. Main benefits:\n"
            "- Explicit sync points (git commits)\n"
            "- Complete audit trail\n"
            "- Works offline\n"
            "- No single point of failure\n\n"
            "Writing technical report."
        )

        await agents["Jane"].send_message(
            "Sammy",
            "**Status Update:** Code Examples\n\n"
            "Created Python implementation with pathlib and asyncio. "
            "TypeScript version uses Node.js fs/promises.\n\n"
            "Both include tests and documentation. Ready for review."
        )

        # Sammy checks final results
        console.print("\n[bold]Phase 7: Results Synthesis[/bold]\n")

        final_messages = await agents["Sammy"].check_messages()

        await agents["Sammy"].write_memory(
            f"Received {len(final_messages)} progress updates. "
            "All subtasks completed successfully. Synthesizing final report."
        )

        # Demonstrate the coordination statistics
        console.print("\n" + "=" * 60)
        console.print("[bold cyan]Coordination Summary[/bold cyan]\n")

        stats = {
            "Total Messages Exchanged": 7,
            "Skills Shared": 3,
            "Agents Coordinated": 4,
            "Tasks Delegated": 3,
            "Workspace Branches": 4,
        }

        for key, value in stats.items():
            console.print(f"  • {key}: [yellow]{value}[/yellow]")

        console.print("\n" + "=" * 60)
        console.print(
            Panel.fit(
                "[bold green]✓ Coordination Complete[/bold green]\n\n"
                "All agents coordinated asynchronously using git-based workspaces.\n"
                "No central orchestrator required. Fully auditable via git history.",
                border_style="green"
            )
        )
        console.print("=" * 60 + "\n")

        # Show example of what git history would look like
        console.print("[bold]Example Git History:[/bold]\n")
        git_log = """[dim]$ git log --all --oneline --graph
* abc123 (sammy) Synthesize final research report
| * def456 (jane) Add TypeScript implementation
| * ghi789 (jane) Add Python implementation examples
|/
| * jkl012 (coggy) Complete technical analysis
| * mno345 (coggy) Document git workflow patterns
|/
| * pqr678 (maude) Summarize research findings
| * stu901 (maude) Complete literature review
|/
* vwx234 (main) Initialize workspace branches[/dim]"""
        console.print(git_log)

        return "Multi-agent git coordination demo completed successfully"


async def main():
    """Run the coordination demo"""
    result = await demonstrate_coordination()
    print(f"\n[bold green]Result:[/bold green] {result}")


if __name__ == "__main__":
    asyncio.run(main())
