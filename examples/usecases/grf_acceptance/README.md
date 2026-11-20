# GRF acceptance gate for an mcp-agent workflow

This optional example keeps mcp-agent's normal workflow API and makes its
successful return conditional on a fresh GRF acceptance run. A failed check
raises before `WorkflowResult` is returned, so the workflow is recorded as an
error and the same GRF task remains active for repair. GRF is not a dependency
of mcp-agent and no cloud enrollment is used.

## Setup

1. Install the public GRF 0.6.1 release using its published release instructions.
   From this example directory, initialize a new project-local subdirectory and
   set a concrete task:

   ```bash
   python /path/to/grf_starter.py init .grf-project --intent "Produce and verify a workflow deliverable"
   (cd .grf-project && python grf.py session sign-in --task "Produce and verify a workflow deliverable")
   ```

   GRF initialization refuses to overwrite an existing directory. The new
   `.grf-project/` subdirectory keeps the framework checkout and example source
   intact; keep its `.grf/` state local and untracked as directed by the
   generated instructions.

2. Replace `project.grf`'s generated acceptance placeholder with checks for your
   actual deliverable. For a simple smoke check, the command can be
   `python checks/acceptance.py`; the script should assert the required behavior,
   not merely exit successfully. Ensure each declared check has a unique ID and
   uses an argv array.
3. Start the example with the repository's usual Python environment and a
   configured mcp-agent provider, e.g. `uv run --directory . main.py`. The sample
   workflow writes `deliverable.txt`, then calls `complete_grf_task`; GRF itself
   reruns acceptance and requires that file as hashed evidence.
4. If acceptance fails, inspect the check output and fix the code that produces
   `deliverable.txt`, or correct the check if it is wrong; editing only the generated
   file is overwritten by the next workflow run. Run the recovery commands from the
   GRF project directory, then rerun the workflow from this example directory:

   ```bash
   (cd .grf-project && python grf.py check)
   (cd .grf-project && python grf.py session resume)
   uv run --directory . main.py
   ```

   Do not sign in over an active task.

The adapter invokes the project-local `grf.py` with an argument list and the
project as its working directory. It surfaces GRF's exact command and error
output; it does not alter GRF state files or silently turn failures into success.
GRF acceptance is cooperative evidence, not a sandbox or proof that checks are
well-designed.

The sample's task setup is separate from mcp-agent workflow execution: start the
GRF task before running the workflow. In a long-running application, preserve
that task identity across retries rather than signing in on each invocation.
