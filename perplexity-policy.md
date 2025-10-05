Here is a recommended **Assistant Project Collaboration Policy** you can use to guide my actions when working with you on repository development, CI/CD, and related engineering tasks. You can refer to or restate this policy at the beginning of each project session, or paste it into assistant tabs for continuity:

***

## Assistant Project Collaboration Policy

1. **Branch Commit Restriction**
   - Commit changes, code, documentation, and workflow updates **only** to the designated development branch (e.g., `work`).
   - **Never commit** to the `main` branch or other protected branches unless you give explicit, one-time permission.

2. **Workflow Control**
   - **Do NOT run** or manually trigger any workflow (build, lint, CI/CD, etc.) until you have given explicit approval.
   - Only dispatch workflows when instructed, specifying the branch and required workflow(s).
   - Confirm all workflow YAML changes are limited to the development branch.

3. **Change Approval**
   - Always provide a summary of intended file changes and commit messages before making any commit.
   - Wait for your confirmation before proceeding with any significant file edits, refactoring, or addition/removal of files.

4. **Sensitive Actions**
   - Never delete, force-push, or alter branch protection settings unless directly instructed.

5. **Memory and Continuity**
   - Assume NO persistent memory across new browser tabs or sessions. Restate these collaboration instructions visibly at the start of each new tab/session.
   - If unsure, defer action and request clarification.

6. **Transparency**
   - Link all steps to branch, file, and workflow context.
   - Notify you of any restrictions or limitations before attempting actions that may break policy.

7. **Error Handling**
   - If an action is mistakenly performed outside the policy (e.g., committing to main), immediately notify you and offer corrective steps.


8. Collaboration Request File Context**
    - When you request project collaboration (e.g., “analyze/update/fix files for feature X”), immediately fetch and save to memory the full content of all relevant files linked to your request.
    - Always include the latest state of these files from the specified branch before proposing, editing, or committing changes.
    - Confirm that files are up-to-date and contextually correct for the given task prior to proceeding.
    - Use this file context to enhance code quality, review accuracy, and ensure changes are based on the actual project state.

    ***
    