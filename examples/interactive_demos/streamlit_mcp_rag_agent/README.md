# Streamlit MCP RAG Agent example

This Streamlit example shows a RAG Agent that is able to augment its responses using data from Qdrant vector database.

## Usage

Download latest Qdrant image from Dockerhub:

```bash
docker pull qdrant/qdrant
```

Then, run the Qdrant server locally with docker:

```bash
docker run -p 6333:6333 -v $(pwd)/qdrant_storage:/qdrant/storage qdrant/qdrant
```

Finally, run the example:

```bash
uv pip install -r requirements.txt
uv run streamlit run main.py
```

<img width="834" alt="Image" src="https://github.com/user-attachments/assets/14072029-1f37-4ac5-bccf-a76e726ba9b2" />
