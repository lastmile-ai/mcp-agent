# MCP Supabase Migration Agent with GitHub Integration

This example demonstrates an automated migration workflow that keeps your TypeScript types perfectly synchronized with your Supabase database schema changes. When you create a database migration, the agent automatically generates the corresponding TypeScript types and commits them to your repository.

## How It Works

When you run a database migration, the agent:

1. **Analyzes your SQL migration** to understand schema changes
2. **Connects to Supabase** to generate accurate TypeScript types
3. **Updates your codebase** with the new type definitions
4. **Creates a GitHub pull request** with all changes ready for review

This eliminates the manual work of keeping database schemas and TypeScript types in sync, reducing bugs and development time.

```plaintext

┌────────────┐      ┌────────────┐
│ Migration  │──┬──▶│ Supabase   │
│ Agent      │  │   │ MCP Server │
└────────────┘  │   └────────────┘
                │   ┌────────────┐
                └──▶│ Github     │
                    │ MCP Server │
                    └────────────┘

```

## `1` App Setup

First, clone the repository and navigate to the project:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/usecases/mcp_supabase_migration_agent
```

Install the required dependencies:

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install Node.js dependencies
npm install
```

Install the MCP servers:

```bash
# GitHub MCP Server (Docker)
docker pull ghcr.io/github/github-mcp-server

# Supabase MCP Server
npm install -g @supabase/mcp-server-supabase
```

## `2` Set up secrets and environment variables

Copy and configure your secrets:

```bash
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
```

Then open `mcp_agent.secrets.yaml` and add your API keys:

```yaml
mcp:
  servers:
    github:
      env:
        GITHUB_PERSONAL_ACCESS_TOKEN: ADD_YOUR_GITHUB_PERSONAL_ACCESS_TOKEN
    supabase:
      env:
        SUPABASE_ACCESS_TOKEN: ADD_YOUR_SUPABASE_ACCESS_TOKEN
        SUPABASE_PROJECT_ID: ADD_YOUR_SUPABASE_PROJECT_ID
openai:
  api_key: "YOUR_OPENAI_API_KEY"
```

### GitHub Personal Access Token

1. Go to [https://github.com/settings/tokens](https://github.com/settings/tokens)
2. Click **"Generate new token"** → **"Generate new token (classic)"**
3. Give it a name (e.g., "MCP Migration Agent")
4. Set expiration (recommended: 90 days)
5. Select these scopes:
   - `repo` (Full control of private repositories)
   - `workflow` (Update GitHub Action workflows)
6. Click **"Generate token"**
7. Copy the token immediately and paste it in your `mcp_agent.secrets.yaml`

#### Supabase Access Token and Project Reference

1. Go to [https://supabase.com/dashboard](https://supabase.com/dashboard)
2. Sign in to your Supabase account
3. **For Access Token:**
   - Click on your profile icon (top right)
   - Go to **"Access Tokens"**
   - Click **"Generate new token"**
   - Give it a name (e.g., "MCP Migration Agent")
   - Copy the token and paste it as `access_token` in your config
4. **For Project Reference:**
   - Go to your project dashboard
   - Click on **"Settings"** → **"General"**
   - Find **"Reference ID"** in the General settings
   - Copy this ID and paste it as `SUPABASE_PROJECT_ID` in your secrets.yaml file

> ⚠️ **Security Note**: Never commit your `mcp_agent.secrets.yaml` file to version control. Make sure it's in your `.gitignore`.

## `3` Project Structure

```
personal-proj/
├── src/
│   ├── index.ts              # Main application entry point
│   └── types/
│       └── database.ts       # Supabase type definitions (auto-generated)
├── migrations/
│   └── 001_add_profiles_and_posts.sql  # Database migration files
├── main.py                   # Migration agent script
├── supabase_migration_agent.py         # Alternative agent script
├── mcp_agent.config.yaml     # MCP agent configuration
├── existing-types.ts         # Additional type definitions
├── main-app.ts              # Main application logic
├── package.json             # Node.js dependencies
├── tsconfig.json            # TypeScript configuration
└── README.md                # This file
```

## `4` Run locally

Run your MCP Migration Agent with a migration file:

```bash
uv run main.py \
  --owner your-github-username \
  --repo your-repository-name \
  --branch feature/update-types \
  --project-path ./path/to/project \
  --migration-file ./path/to/migration.sql
```

## Agent Workflow Details

The Migration Agent coordinates all operations through MCP server interactions:

1. **SQL Analysis**: Parses migration files to identify schema changes, new tables, relationships, index management, and Row Level Security (RLS) policy definitions
2. **Supabase Integration**: Uses Supabase MCP server to generate accurate TypeScript types from database schema
3. **Code Integration**: Intelligently merges generated types with existing codebase while preserving custom code
4. **GitHub Operations**: Uses GitHub MCP server to create branches, commit changes, and push updates
5. **Validation**: Ensures TypeScript compilation and tests pass before finalizing changes

## Command Line Options

| Option             | Required | Description                         |
| ------------------ | -------- | ----------------------------------- |
| `--owner`          | Yes      | GitHub repository owner             |
| `--repo`           | Yes      | GitHub repository name              |
| `--branch`         | Yes      | Feature branch name for changes     |
| `--project-path`   | Yes      | Path to TypeScript source directory |
| `--migration-file` | Yes      | Path to SQL migration file          |

## Example Migration Workflow

1. **Create a new migration file:**

   ```sql
   -- migrations/002_add_comments.sql
   CREATE TABLE comments (
     id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
     post_id UUID REFERENCES posts(id) ON DELETE CASCADE,
     author_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
     content TEXT NOT NULL,
     created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
   );
   ```

2. **Run the migration agent:**

   ```bash
   python main.py \
     --owner Haniehz1 \
     --repo personal-proj \
     --branch feature/add-comments \
     --project-path ./src \
     --migration-file ./migrations/002_add_comments.sql
   ```

3. **Agent automatically:**

   - Analyzes the new `comments` table structure
   - Generates TypeScript types for Comment operations
   - Updates `src/types/database.ts` with new interface
   - Creates feature branch `feature/add-comments`
   - Commits with message: "Add comments table types and schema updates"
   - Pushes to GitHub for review

4. **Review and merge** the generated pull request
