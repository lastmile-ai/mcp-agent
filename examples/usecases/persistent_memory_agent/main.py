"""Persistent, *typed* cross-session memory using Dakera MCP.

Most "memory" demos treat `store` as "save everything the agent said" — a
transcript dump that gets noisy and useless within a few runs. This example
instead models memory as a **project-continuity layer** with an explicit
contract, following the three-tier model discussed in issue #12:

    working context  -> in-process mcp-agent state (ephemeral, not stored)
    session trace    -> what happened this run   (Dakera session, auditable)
    project memory   -> durable, *promoted* facts (Dakera long-term, typed)

The teaching point: only **promoted** records enter project memory, and each
one carries a type and scope so it can be retrieved deliberately later:

    MEMORY CONTRACT (encoded as Dakera tags on each stored record)
      type:<decision|convention|failed_path|bug_fix|open_question>
      project:<scope>          e.g. project:multi-agent-frameworks
      status:<accepted|candidate|superseded>

This unlocks the two capabilities from #12 that a plain store/recall loop
misses, and which this example demonstrates end to end:

  * scope-filtered retrieval — `dakera_batch_recall` filtered by the scope and
    status tags, so a new session pulls back *only* accepted project facts
    instead of a semantic soup of everything ever stored.
  * entity / knowledge-graph memory — `dakera_extract_entities` +
    `dakera_knowledge_graph` turn stored prose into a queryable entity graph.

Prereq (self-hosted server + MinIO via docker-compose; the server needs the
object store the compose provisions, so use dakera-deploy, not a bare docker run):
    git clone https://github.com/dakera-ai/dakera-deploy
    cd dakera-deploy && docker compose up -d   # REST API on http://localhost:3000
    npx @dakera-ai/dakera-mcp --help  # confirms the MCP server starts

Usage:
    # First run: research and promote typed facts to project memory
    DAKERA_API_URL=http://localhost:3000 DAKERA_API_KEY=dk-... python main.py

    # Second run: a fresh agent recalls prior *accepted* facts by scope
    DAKERA_API_URL=http://localhost:3000 DAKERA_API_KEY=dk-... python main.py
"""

import asyncio

from mcp_agent.agents.agent import Agent
from mcp_agent.app import MCPApp
from mcp_agent.workflows.llm.augmented_llm_anthropic import AnthropicAugmentedLLM

app = MCPApp(name="persistent_memory_agent")

# Scope for this demo. Everything promoted to project memory is tagged with it,
# so retrieval can be filtered to exactly this project (see recall_phase).
PROJECT_SCOPE = "project:multi-agent-frameworks"

# The promotion contract, injected into every agent so storage stays disciplined
# rather than becoming a transcript dump.
MEMORY_CONTRACT = f"""\
You have persistent project memory via Dakera. Treat it as a continuity layer,
NOT a transcript. Follow this contract exactly:

1. At the start, call dakera_session_start, then dakera_batch_recall with
   tags ["{PROJECT_SCOPE}", "status:accepted"] to load what is already known.
   Do not re-research anything already recorded.
2. Only PROMOTE durable facts to memory with dakera_store. A fact is promotable
   if it is a decision, a convention, a failed path worth avoiding, a bug fix,
   or an open question — never a greeting, a restatement, or chit-chat.
3. Every dakera_store call MUST include tags:
     - "{PROJECT_SCOPE}"
     - one of "type:decision" | "type:convention" | "type:failed_path"
              | "type:bug_fix" | "type:open_question"
     - "status:accepted" for facts you are confident in (else "status:candidate")
   Use importance 0.8-0.9 for accepted facts so they survive decay.
4. Keep each record self-contained and one idea per record.
5. Call dakera_session_end with a short summary when finished.
"""


async def research_phase() -> None:
    """Phase 1 — research a topic and *promote* typed facts to project memory.

    The agent first loads prior accepted facts (so a re-run does not duplicate
    work), researches the gap, then stores only promotable records under the
    memory contract. Nothing about the raw conversation is dumped to storage.
    """
    async with app.run():
        agent = Agent(
            name="researcher",
            instruction=MEMORY_CONTRACT
            + """
Task: research the current state of multi-agent AI frameworks. Identify the top
frameworks by adoption and their key architectural differences. Promote each
distinct architectural decision or convention as its own typed memory record.
""",
            server_names=["dakera", "fetch"],
        )
        async with agent:
            llm = await agent.attach_llm(AnthropicAugmentedLLM)
            result = await llm.generate_str(
                "Research multi-agent AI frameworks and promote your findings as "
                "typed project-memory records per the contract. Report what you stored."
            )
            print(f"[Phase 1 — Research & promote]\n{result[:600]}...\n")


async def recall_phase() -> None:
    """Phase 2 — a fresh agent recalls prior facts via *scope-filtered* retrieval.

    This simulates a process/container restart: no in-process state survives.
    The agent uses ``dakera_batch_recall`` filtered by the project scope and
    ``status:accepted`` so it pulls back only durable, promoted facts for this
    project — not a semantic soup of everything ever stored.
    """
    async with app.run():
        agent = Agent(
            name="analyst",
            instruction=f"""You are an analyst with persistent project memory.

Start by calling dakera_batch_recall with tags
["{PROJECT_SCOPE}", "status:accepted"] to load the accepted facts for this
project. Base your analysis only on those recalled facts and say which record
IDs you relied on. If a fact is missing, flag it as an open question rather
than inventing it.""",
            server_names=["dakera"],
        )
        async with agent:
            llm = await agent.attach_llm(AnthropicAugmentedLLM)
            result = await llm.generate_str(
                "Using only the accepted project-memory facts for "
                f'"{PROJECT_SCOPE}", recommend a multi-agent framework for a '
                "production enterprise deployment and justify it from the recalled records."
            )
            print(f"[Phase 2 — Scope-filtered recall & analysis]\n{result}\n")


async def knowledge_graph_phase() -> None:
    """Phase 3 — build and query entity/knowledge-graph memory.

    Beyond flat store/recall, Dakera can turn stored prose into a queryable
    entity graph. The agent extracts entities from the accepted facts with
    ``dakera_extract_entities`` and then traverses relationships with
    ``dakera_knowledge_graph`` — the graph/entity memory tier from issue #12.
    """
    async with app.run():
        agent = Agent(
            name="graph_explorer",
            instruction=f"""You explore the knowledge graph built from project memory.

1. Call dakera_batch_recall with tags ["{PROJECT_SCOPE}", "status:accepted"].
2. For each recalled fact, call dakera_extract_entities to pull out frameworks,
   organizations, and architectural concepts as graph entities.
3. Call dakera_knowledge_graph to inspect how those entities relate.
Report the entities discovered and any relationships between frameworks.""",
            server_names=["dakera"],
        )
        async with agent:
            llm = await agent.attach_llm(AnthropicAugmentedLLM)
            result = await llm.generate_str(
                "Extract entities from the accepted project facts and describe the "
                "relationships in the knowledge graph between the frameworks you find."
            )
            print(f"[Phase 3 — Entity / knowledge-graph memory]\n{result}\n")


async def main() -> None:
    """Run the three phases in sequence to demonstrate the full memory lifecycle.

    Phase 1 promotes typed facts; Phase 2 restarts fresh and recalls them by
    scope; Phase 3 explores the entity graph built from those facts. Re-running
    the whole script shows continuity: Phase 1 recalls what a prior run stored
    before adding anything new.
    """
    print("=== Phase 1: Research — promote typed facts to Dakera ===\n")
    await research_phase()

    print("\n--- Simulating a new agent session (process-restart equivalent) ---\n")
    print("=== Phase 2: Scope-filtered recall from Dakera ===\n")
    await recall_phase()

    print("\n=== Phase 3: Entity / knowledge-graph memory ===\n")
    await knowledge_graph_phase()


if __name__ == "__main__":
    asyncio.run(main())
