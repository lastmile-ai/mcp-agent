# OAUTH scenarios

## preconfigured

In this case, a token is hard-coded into the configuration. 
This is useful for testing or when the token is static.

## workflow_pre_auth

In this case, the client can call a `workflows_pre_auth` tool before calling a workflow to seed the tokens.
This is useful when the client can do the auth step, but the workflow cannot (e.g. because it runs async).
There is a slight hack employed here: since we don't have oauth for the mcp app, we do not have a user.
Since we need a user to store the token against, we create a synthetic user and use that.

## dynamic_auth

In this case, no tokens are provided, and the calls comes back to the client to do the auth step.
Currently implemented as an elicitation request (to align with the future elicit URL scheme).
I have not achieved full end-to-end flow here.