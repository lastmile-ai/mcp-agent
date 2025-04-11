# Supabase Migration Agent with MCP

This tool automates the process of generating TypeScript types from Supabase database migrations and pushing them to GitHub. Powered by an MCP Agent, it connects to your Supabase project, analyzes a migration file, generates updated types, and commits them to a specified branch on GitHub — all with one command.

---

## What It Does

- Parses your local SQL migration file
- Uses Supabase CLI to connect and generate updated types
- Commits the changes to a specified GitHub branch
- Runs via a Python-based MCP agent (with OpenAI-powered context support)
- Cleans up and reports its actions

---

## Dependencies

| Tool        | Use Case                        |
|-------------|---------------------------------|
| [Python 3.10+](https://www.python.org/downloads/) | Running the MCP agent |
| [uv](https://github.com/astral-sh/uv)         | Fast Python dependency manager |
| [Supabase CLI](https://supabase.com/docs/guides/cli) | Schema sync + TypeScript codegen |
| `mcp-agent`                                   | The framework powering your automation |
| `openai`, `pyyaml`, `aiofiles`                | Runtime dependencies for LLM + YAML handling |

---

## Required Tokens

### Supabase Personal Access Token

1. Go to [Supabase Account Tokens](https://supabase.com/dashboard/account/tokens)
2. Click **Generate new token**
3. Copy the token (starts with `sbp_...`)

### GitHub Personal Access Token

1. Go to [GitHub Tokens](https://github.com/settings/tokens)
2. Click **Generate new token (classic)**
3. Give it the `repo` scope
4. Copy the token (starts with `ghp_...`)