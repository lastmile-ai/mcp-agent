# MCP Agent Example: Supabase → GitHub Automation

This example shows how to use a custom MCP Agent to:
- Analyze a Supabase SQL migration file 
- Auto-generate updated TypeScript types
- Commit and push the changes to a GitHub branch

Perfect for projects where your database schema evolves and you want your app types to always stay in sync — *without doing it manually*.

---

## What This Example Does

- Loads config and secrets from `mcp_agent.config.yaml` and `.env`
- Uses Supabase CLI to:
  - Pull current DB schema
  - Generate latest TypeScript types
- Automatically commits and pushes the updated types to a GitHub branch
- Fully automated and reusable with any MCP-supported stack

---

## Folder Structure

```
examples/mcp_supabase-github/
├── supabase_migration_agent.py       # The main agent code
├── mcp_agent.config.yaml             # MCP agent + server setup
├── .env.example                      # Sample env file (no secrets)
```

---

## Environment Variables (from `.env`)

Rename `.env.example` → `.env` and fill in:

```
OPENAI_API_KEY=sk-xxx
GITHUB_PERSONAL_ACCESS_TOKEN=ghp-xxx
SUPABASE_ACCESS_TOKEN=sbp-xxx
SUPABASE_PROJECT_ID=your-project-id
```

> All secrets are loaded using `os.getenv()` so nothing sensitive is hardcoded.

---

## Prerequisites

- Python 3.10+
- Supabase CLI installed (`brew install supabase/tap/supabase`)

---

## Install Dependencies

From the `mcp-agent` repo root:

```bash
cd examples/mcp_supabase-github
python3 -m venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt  # or manually install: openai, pyyaml, aiofiles, mcp-agent
```

---

##  Run the Agent

```bash
uv run python supabase_migration_agent.py \
  --owner YOUR_GITHUB_USERNAME \
  --repo YOUR_REPO_NAME \
  --branch feature/update-types \
  --project-path /absolute/path/to/your/project \
  --migration-file /absolute/path/to/migration/file.sql
```

### Example:

```bash
uv run python supabase_migration_agent.py \
  --owner Haniehz1 \
  --repo supabase-codegen-test \
  --branch feature/update-types \
  --project-path ~/supabase-codegen-test \
  --migration-file ~/supabase-codegen-test/supabase/migrations/20250409_add_users.sql
```

---

## Optional Flags

- `--dry-run`: Don’t commit or push, just simulate
- `--skip-tests`: Skip any build/lint/test commands

---

## Why This Matters

- **Supabase** provides an amazing SQL-first experience
- **Database migrations** are how you version-control your schema
- **TypeScript codegen** keeps your app synced with DB structure
- **GitHub automation** ensures traceability and clean workflows
- **MCP** lets you do all of this across systems without glue code

---

## Customize Me!

You can easily adapt this agent to work with:

- Other DBs (MySQL, MongoDB, Firebase, etc.)
- Other version control platforms (GitLab, Bitbucket)
- Add PR creation, Slack notifications, CI triggers, and more

---
Built by [@Haniehz1](https://github.com/Haniehz1) using @LastMileai-MCP repo [MCP](https://github.com/lastmile-ai/mcp-agent), Supabase, GitHub, and OpenAI ✨
