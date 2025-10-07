import os
import textwrap
from dataclasses import dataclass
from typing import Dict, List

from mcp_agent.services.github_mcp_client import GithubMCPClient


@dataclass
class Plan:
    owner: str
    repo: str
    default_branch: str
    language: str
    branch: str
    files: Dict[str, str]
    notes: List[str]
    pr_title: str
    pr_body: str
    skipped: bool = False


def _load_template(rel_path: str) -> str:
    # project root relative path
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    p = os.path.join(base, "templates", "repo", rel_path)
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def _detect_language(cli: GithubMCPClient, owner: str, repo: str, ref: str) -> str:
    node = cli.stat(owner, repo, ref, "package.json")
    py = cli.stat(owner, repo, ref, "pyproject.toml") or cli.stat(owner, repo, ref, "requirements.txt")
    if node and not py:
        return "node"
    if py and not node:
        return "python"
    if node and py:
        return "node"
    return "node"


def _ci_exists(cli: GithubMCPClient, owner: str, repo: str, ref: str) -> bool:
    return cli.stat(owner, repo, ref, ".github/workflows/ci.yml") or cli.stat(owner, repo, ref, ".github/workflows/ci.yaml")


def build_plan(cli: GithubMCPClient, owner: str, repo: str, default_branch: str, language_hint: str) -> Plan:
    ref = default_branch
    if _ci_exists(cli, owner, repo, ref):
        return Plan(owner, repo, default_branch, language_hint, "vibe/bootstrap", {}, ["existing CI detected"], "noop", "noop", skipped=True)
    lang = language_hint if language_hint in ("node","python") else _detect_language(cli, owner, repo, ref)
    ci_tpl = "ci/node.yml" if lang == "node" else "ci/python.yml"
    body = textwrap.dedent(f"""
    Bootstrap minimal green-first CI and CODEOWNERS.

    Why
    - Baseline CI keeps changes green.
    - Add-only: existing workflows are not changed.

    What
    - Adds `.github/workflows/ci.yml` for **{lang}**.
    - Adds `CODEOWNERS` if missing.

    Notes
    - Required checks should include this job name.
    """ ).strip()
    files = {
        ".github/workflows/ci.yml": _load_template(ci_tpl).replace("$default-branch", default_branch or "main"),
        ".github/CODEOWNERS": _load_template("CODEOWNERS"),
    }
    return Plan(owner, repo, default_branch, lang, "vibe/bootstrap", files, [], "Bootstrap CI + CODEOWNERS (green-first)", body)


def run(owner: str, repo: str, trace_id: str, language: str = "auto", dry_run: bool = False) -> Dict:
    cli = GithubMCPClient()
    default_branch = cli.get_default_branch(owner, repo)
    plan = build_plan(cli, owner, repo, default_branch, language if language != "auto" else "auto")
    if dry_run:
        return {"skipped": plan.skipped, "plan": plan.__dict__}
    if plan.skipped:
        return {"skipped": True, "reason": "existing_ci"}
    cli.create_branch(owner, repo, base=default_branch, name=plan.branch)
    for path, content in plan.files.items():
        # belt-and-suspenders add-only
        if cli.stat(owner, repo, plan.branch, path):
            continue
        cli.put_add_only(owner, repo, branch=plan.branch, path=path, content=content.encode("utf-8"))
    pr_id = cli.open_pr(owner, repo, base=default_branch, head=plan.branch, title=plan.pr_title, body=plan.pr_body)
    try:
        cli.run_ci_on_pr(owner, repo, pr_id)
    except Exception:
        pass
    return {"skipped": False, "pr_id": pr_id, "branch": plan.branch, "default_branch": default_branch, "language": plan.language}
