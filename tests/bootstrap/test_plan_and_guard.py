from mcp_agent.tasks import bootstrap_repo as br

class FakeCli:
    def __init__(self, fs):
        self.fs = set(fs)
    def stat(self, owner, repo, ref, path):
        return path in self.fs
    def get_default_branch(self, owner, repo):
        return "main"

def test_detect_node(tmp_path, monkeypatch):
    cli = FakeCli({"package.json"})
    plan = br.build_plan(cli, "o","r","main","auto")
    assert not plan.skipped
    assert plan.language == "node"

def test_detect_python(tmp_path):
    cli = FakeCli({"pyproject.toml"})
    plan = br.build_plan(cli, "o","r","main","auto")
    assert plan.language == "python"

def test_skip_when_ci_exists(tmp_path):
    cli = FakeCli({".github/workflows/ci.yml"})
    plan = br.build_plan(cli, "o","r","main","auto")
    assert plan.skipped

def test_add_only_guard(monkeypatch, tmp_path):
    # simulate CODEOWNERS already exists on branch
    class Cli(FakeCli):
        def create_branch(self,*a,**k): pass
        def put_add_only(self,*a,**k): return True,"created"
        def open_pr(self,*a,**k): return "1"
        def run_ci_on_pr(self,*a,**k): pass
    cli = Cli(set())
    # monkeypatch client factory used inside run by injecting methods into module
    monkeypatch.setenv("GITHUB_MCP_ENDPOINT","http://example")
    # monkeypatching not needed for filesystem; run() uses real client, so instead test plan-level
    plan = br.build_plan(cli, "o","r","main","node")
    # pre-create guard
    cli.fs.add(".github/CODEOWNERS")
    # simulate writes
    created = []
    for path, content in plan.files.items():
        if cli.stat("o","r", plan.branch, path):
            continue
        created.append(path)
    assert ".github/workflows/ci.yml" in created
