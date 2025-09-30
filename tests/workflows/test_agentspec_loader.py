from textwrap import dedent

import pytest

from mcp_agent.workflows.factory import (
    AgentSpec,
    load_agent_specs_from_text,
    load_agent_specs_from_file,
    load_agent_specs_from_dir,
)


def sample_fn():
    return "ok"


def test_yaml_agents_list_parses_agentspecs(tmp_path):
    yaml_text = dedent(
        """
        agents:
          - name: finder
            instruction: You can read files
            server_names: [filesystem]
          - name: fetcher
            servers: [fetch]
            instruction: You can fetch URLs
        """
    )
    specs = load_agent_specs_from_text(yaml_text, fmt="yaml")
    assert len(specs) == 2
    assert isinstance(specs[0], AgentSpec)
    assert specs[0].name == "finder"
    assert specs[0].instruction == "You can read files"
    assert specs[0].server_names == ["filesystem"]
    assert specs[1].name == "fetcher"
    assert specs[1].server_names == ["fetch"]


def test_json_single_agent_object(tmp_path):
    json_text = dedent(
        """
        {"agent": {"name": "coder", "instruction": "Modify code", "servers": ["filesystem"]}}
        """
    )
    specs = load_agent_specs_from_text(json_text, fmt="json")
    assert len(specs) == 1
    spec = specs[0]
    assert spec.name == "coder"
    assert spec.instruction == "Modify code"
    assert spec.server_names == ["filesystem"]


def test_markdown_front_matter_and_body_merges_instruction():
    md_text = dedent(
        """
        ---
        name: code-reviewer
        description: Expert code reviewer, use proactively
        tools: filesystem, fetch
        ---

        You are a senior code reviewer ensuring high standards.

        Provide feedback organized by priority.
        """
    )
    specs = load_agent_specs_from_text(md_text, fmt="md")
    assert len(specs) == 1
    spec = specs[0]
    assert spec.name == "code-reviewer"
    # instruction should combine description + body when explicit instruction absent
    assert "Expert code reviewer" in (spec.instruction or "")
    assert "senior code reviewer" in (spec.instruction or "")
    # tools map to server_names if servers/server_names absent
    assert spec.server_names == ["filesystem", "fetch"]


def test_markdown_code_blocks_yaml_and_json():
    md_text = dedent(
        """
        Here are some agents:

        ```yaml
        agents:
          - name: a
            servers: [filesystem]
        ```

        And some JSON:

        ```json
        {"agent": {"name": "b", "servers": ["fetch"]}}
        ```
        """
    )
    specs = load_agent_specs_from_text(md_text, fmt="md")
    # At least one should be parsed from either block
    assert any(s.name == "a" for s in specs) or any(s.name == "b" for s in specs)


def test_functions_resolution_with_dotted_ref(tmp_path, monkeypatch):
    yaml_text = dedent(
        """
        agents:
          - name: tools-agent
            servers: [filesystem]
            functions:
              - "tests.workflows.test_agentspec_loader:sample_fn"
        """
    )
    specs = load_agent_specs_from_text(yaml_text, fmt="yaml")
    assert len(specs) == 1
    spec = specs[0]
    assert len(spec.functions) == 1
    assert spec.functions[0]() == "ok"


def test_load_agents_from_dir(tmp_path):
    # create multiple files in a temp directory
    (tmp_path / "agents.yaml").write_text(
        dedent(
            """
            agents:
              - name: one
                servers: [filesystem]
              - name: two
                servers: [fetch]
            """
        ),
        encoding="utf-8",
    )
    (tmp_path / "agent.json").write_text(
        '{"agent": {"name": "json-agent", "servers": ["fetch"]}}',
        encoding="utf-8",
    )
    specs = load_agent_specs_from_dir(str(tmp_path))
    names = {s.name for s in specs}
    assert {"one", "two", "json-agent"}.issubset(names)


@pytest.mark.asyncio
async def test_app_loads_inline_and_disk_subagents(tmp_path):
    # Arrange inline subagent
    from mcp_agent.config import Settings, SubagentSettings
    from mcp_agent.app import MCPApp

    inline = AgentSpec(
        name="inline-helper", instruction="Be helpful", server_names=["filesystem"]
    )

    # Arrange Claude-style project/user agents
    proj_dir = tmp_path / "proj_agents"
    user_dir = tmp_path / "user_agents"
    proj_dir.mkdir()
    user_dir.mkdir()

    (proj_dir / "code-reviewer.md").write_text(
        dedent(
            """
            ---
            name: code-reviewer
            description: Expert code review specialist. Use proactively.
            tools: filesystem, fetch
            ---

            You are a senior code reviewer ensuring high standards.
            """
        ),
        encoding="utf-8",
    )
    (user_dir / "debugger.md").write_text(
        dedent(
            """
            ---
            name: debugger
            description: Debugging specialist for errors and failures
            ---

            You are an expert debugger specializing in root cause analysis.
            """
        ),
        encoding="utf-8",
    )

    settings = Settings(
        agents=SubagentSettings(
            enabled=True,
            definitions=[inline],
            search_paths=[str(proj_dir), str(user_dir)],
            pattern="**/*.*",
        )
    )

    # Act
    app = MCPApp(settings=settings)
    async with app.run():
        loaded = getattr(app.context, "loaded_subagents", [])

    # Assert
    names = {s.name for s in loaded}
    assert {"inline-helper", "code-reviewer", "debugger"}.issubset(names)
    # Claude-style tools map to server_names (ignore tool semantics otherwise)
    cr = next(s for s in loaded if s.name == "code-reviewer")
    assert cr.server_names == ["filesystem", "fetch"]
    assert "senior code reviewer" in (cr.instruction or "")


def test_load_agent_specs_from_file_markdown(tmp_path):
    md_path = tmp_path / "agent.md"
    md_path.write_text(
        dedent(
            """
            ---
            name: data-scientist
            description: Data analysis expert
            tools: Bash, Read, Write
            ---

            You are a data scientist specializing in SQL and BigQuery analysis.
            """
        ),
        encoding="utf-8",
    )
    specs = load_agent_specs_from_file(str(md_path))
    assert len(specs) == 1
    spec = specs[0]
    assert spec.name == "data-scientist"
    assert spec.server_names == ["Bash", "Read", "Write"]
    assert "data scientist" in (spec.instruction or "")


def test_markdown_name_conflict_precedence_logged_and_overwritten(tmp_path):
    # Project (higher precedence) should overwrite user (lower precedence)
    # when loaded via the app with search_paths order [project, user].
    from mcp_agent.config import Settings, SubagentSettings
    from mcp_agent.app import MCPApp

    project_dir = tmp_path / "proj"
    user_dir = tmp_path / "user"
    project_dir.mkdir()
    user_dir.mkdir()

    (user_dir / "agent.md").write_text(
        dedent(
            """
            ---
            name: same-name
            description: user level agent
            ---

            Body for user agent
            """
        ),
        encoding="utf-8",
    )
    (project_dir / "agent.md").write_text(
        dedent(
            """
            ---
            name: same-name
            description: project level agent
            ---

            Body for project agent
            """
        ),
        encoding="utf-8",
    )

    settings = Settings(
        agents=SubagentSettings(
            enabled=True,
            search_paths=[str(project_dir), str(user_dir)],
        )
    )

    app = MCPApp(settings=settings)

    async def run_and_get():
        async with app.run():
            return getattr(app.context, "loaded_subagents", [])

    import asyncio

    loaded = asyncio.get_event_loop().run_until_complete(run_and_get())
    specs = [s for s in loaded if s.name == "same-name"]
    assert len(specs) == 1
    # The surviving spec should have the project description merged into instruction
    assert "project level agent" in (specs[0].instruction or "")


@pytest.mark.asyncio
async def test_app_loads_subagents_from_config_file_path(tmp_path):
    # Arrange a Claude-style agent on disk and a config YAML that points to it
    proj_dir = tmp_path / ".claude" / "agents"
    proj_dir.mkdir(parents=True)
    (proj_dir / "code-reviewer.md").write_text(
        dedent(
            """
            ---
            name: code-reviewer
            description: Expert code review specialist. Use proactively.
            tools: filesystem, fetch
            ---

            You are a senior code reviewer ensuring high standards.
            """
        ),
        encoding="utf-8",
    )

    config_path = tmp_path / "mcp_agent.config.yaml"
    config_path.write_text(
        dedent(
            f"""
            agents:
              enabled: true
              search_paths:
                - "{proj_dir}"
              pattern: "**/*.*"
              definitions:
                - name: inline-a
                  instruction: Hello
                  servers: [filesystem]
            """
        ),
        encoding="utf-8",
    )

    from mcp_agent.app import MCPApp

    app = MCPApp(settings=str(config_path))
    async with app.run():
        loaded = getattr(app.context, "loaded_subagents", [])

    names = {s.name for s in loaded}
    assert {"inline-a", "code-reviewer"}.issubset(names)
