# Streamlit MCP Agent example

This Streamlit example shows a "finder" Agent which has access to the 'fetch' and 'filesystem' MCP servers.

You can ask it information about local files or URLs, and it will make the determination on what to use at what time to satisfy the request.

To run this example:

With uv:

```bash
uv pip install -r requirements.txt
uv run streamlit run main.py
```

<img src="https://github.com/user-attachments/assets/7ad27d23-9ed6-4e0e-ba7f-2d3b0afef847" height="512">
