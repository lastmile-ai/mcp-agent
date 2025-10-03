# Streamlit MCP RAG Agent example

This Streamlit example shows a RAG Agent that is able to augment its responses using data from Qdrant vector database.

<img width="834" alt="Image" src="https://github.com/user-attachments/assets/14072029-1f37-4ac5-bccf-a76e726ba9b2" />

---

```plaintext
┌───────────┐      ┌─────────┐      ┌──────────────┐
│ Streamlit │─────▶│  Agent  │─────▶│  Qdrant      │
│ App       │      │         │      │  MCP Server  │
└───────────┘      └─────────┘      └──────────────┘
```

## `1` App set up

First, clone the repo and navigate to the streamlit mcp rag agent example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/usecase/streamlit_mcp_rag_agent
```

Install `uv` (if you don’t have it):

```bash
pip install uv
```

Sync `mcp-agent` project dependencies:

```bash
uv sync
```

Install requirements specific to this example:

```bash
uv pip install -r requirements.txt
```

## `1.1` Install Qdrant

Download latest Qdrant image from Dockerhub:

```bash
docker pull qdrant/qdrant
```

Then, run the Qdrant server locally with docker:

```bash
docker run -p 6333:6333 -v $(pwd)/qdrant_storage:/qdrant/storage qdrant/qdrant
```

## `2` Set up secrets and environment variables

Copy and configure your secrets and env variables:

```bash
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
```

Then open `mcp_agent.secrets.yaml` and add your api key for your preferred LLM.

## `3` Run locally

Run your MCP Agent app:

```bash
uv run streamlit run main.py
```
