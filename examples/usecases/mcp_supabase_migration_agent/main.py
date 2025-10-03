import asyncio
import time
import argparse
from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.mcp.mcp_connection_manager import MCPConnectionManager
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from rich import print

app = MCPApp(name="supabase_migration_codegen")


async def supabase_migration_codegen(
    github_owner: str,
    github_repo: str,
    branch_name: str,
    project_path: str,
    migration_file: str,
):
    """
    Automated workflow to generate and commit types for a Supabase database migration.

    Args:
        github_owner: GitHub repository owner
        github_repo: GitHub repository name
        branch_name: Branch name for the new code changes
        project_path: Path to the project within the repository
        migration_file: Path to the migration SQL file
    """
    async with app.run() as agent_app:
        context = agent_app.context

        async with MCPConnectionManager(context.server_registry):
            supabase_migration_agent = Agent(
                name="supabase_migration_agent",
                instruction=f"""You are an agent that automates Supabase database migration code generation and GitHub commits.
                
                Your tasks are:
                1. Use the Supabase server to generate TypeScript types from a migration
                2. Update the existing project code to incorporate these new types
                3. Ensure the project builds and passes tests
                4. Create a commit and push to GitHub repository {github_owner}/{github_repo} on branch {branch_name}
                
                You will work with a project located at {project_path} and process the migration file {migration_file}.
                
                Be careful not to overwrite or incorrectly merge existing type definitions. Ensure backward compatibility
                and follow the project's code style for consistency.""",
                server_names=["supabase", "github"],
            )

            try:
                llm = await supabase_migration_agent.attach_llm(OpenAIAugmentedLLM)

                prompt = f"""Complete the following workflow for automating Supabase migration code generation and GitHub commits:

                1. Clone the GitHub repository {github_owner}/{github_repo} and navigate to the project at {project_path}.
                   Use the GitHub server to get this information.

                2. Analyze the migration SQL file located at {migration_file}.
                   Review the schema changes to understand what new types need to be generated.

                3. Use the Supabase server to:
                   - Generate TypeScript types from the database schema after the migration
                   - Extract only the newly created or modified types

                4. Integrate these new types with the existing codebase:
                   - Find the appropriate files where types should be added or updated
                   - Insert or modify the type definitions while preserving existing code
                   - Resolve any type conflicts or dependencies
                   - Follow the project's code style conventions

                5. Validate the changes:
                   - Ensure the project builds without errors
                   - Run any existing TypeScript type checks or tests
                   - Fix any issues that arise from the integration

                6. Create a new branch named {branch_name} if it doesn't exist yet,
                   or use the existing branch with that name.

                7. Commit the changes with a descriptive message explaining:
                   - What schema changes were made
                   - What types were added or modified
                   - Any special considerations for developers

                8. Push the commit to the remote repository.

                9. Provide a summary of actions taken and any recommendations for manual review or testing.
                """

                # Execute the workflow
                print(
                    f"Starting Supabase migration codegen workflow for {github_owner}/{github_repo}..."
                )
                print(f"Processing migration file: {migration_file}")
                print(f"Target branch: {branch_name}")

                result = await llm.generate_str(prompt)

                print("Workflow completed!")
                print("Summary of changes:")
                print(result)

            finally:
                # Clean up the agent
                await supabase_migration_agent.close()


def parse_args():
    parser = argparse.ArgumentParser(description="Supabase Migration Codegen Tool")
    parser.add_argument("--owner", required=True, help="GitHub repository owner")
    parser.add_argument("--repo", required=True, help="GitHub repository name")
    parser.add_argument("--branch", required=True, help="Branch name for the changes")
    parser.add_argument(
        "--project-path",
        required=True,
        help="Path to the project within the repository",
    )
    parser.add_argument(
        "--migration-file", required=True, help="Path to the migration SQL file"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    start = time.time()
    try:
        asyncio.run(
            supabase_migration_codegen(
                args.owner,
                args.repo,
                args.branch,
                args.project_path,
                args.migration_file,
            )
        )
    except KeyboardInterrupt:
        print("\nReceived keyboard interrupt, shutting down gracefully...")
    except Exception as e:
        print(f"Error during execution: {e}")
        raise

    finally:
        end = time.time()
        t = end - start
        print(f"Total run time: {t:.2f}s")
