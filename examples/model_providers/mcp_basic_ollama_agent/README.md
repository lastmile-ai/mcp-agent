# MCP Ollama Agent example

This example shows a "finder" Agent using llama models to access the 'fetch' and 'filesystem' MCP servers.

You can ask it information about local files or URLs, and it will make the determination on what to use at what time to satisfy the request.

Make sure you have Ollama installed. Then pull the required models for the example:

```bash
ollama run llama3.2:3b

ollama run llama3.1:8b
```

Then simply run the example:
`uv run main.py`

<img width="2160" alt="Image" src="https://github.com/user-attachments/assets/14cbfdf4-306f-486b-9ec1-6576acf0aeb7" />
