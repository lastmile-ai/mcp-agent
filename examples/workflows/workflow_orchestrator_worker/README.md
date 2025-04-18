# Orchestrator workflow example

This example shows an Orchestrator workflow which dynamically plans across a number of agents to accomplish a multi-step task.

It parallelizes the task executions where possible, and continues execution until the objective is attained.

This particular example is a student assignment grader, which requires:

- Finding the student's assignment in a short_story.md on disk (using MCP filesystem server)
- Using proofreader, fact checker and style enforcer agents to evaluate the quality of the report
- The style enforcer requires reading style guidelines from the APA website using the MCP fetch server.
- Writing the graded report to disk (using MCP filesystem server)

<img width="1650" alt="Image" src="https://github.com/user-attachments/assets/12263f81-f2f8-41e2-a758-13d764f782a1" />
