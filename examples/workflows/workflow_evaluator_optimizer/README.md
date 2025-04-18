# Evaluator-Optimizer Workflow example

To illustrate an evaluator-optimizer workflow, we will build a job cover letter refinement system,
which generates a draft based on job description, company information, and candidate details.

Then the evaluator reviews the letter, provides a quality rating, and offers actionable feedback.
The cycle continues until the letter meets a predefined quality standard.

To make things interesting, we specify the company information as a URL, expecting the agent to fetch
it using the MCP 'fetch' server, and then using that information to generate the cover letter.
