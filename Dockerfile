# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.11-slim

FROM python:${PYTHON_VERSION} AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Copy only project files needed for install and runtime
COPY pyproject.toml README.md LICENSE /app/
COPY src /app/src

# Install project (src layout)
RUN pip install --upgrade pip && pip install --no-cache-dir /app

# Non-root runtime
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser
ENV PORT=8080
EXPOSE 8080

# Healthcheck probes the health server
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s CMD python - <<'PY' | grep -q 200 || exit 1
import os, urllib.request
u=f"http://127.0.0.1:{os.getenv('PORT','8080')}/health"
try:
  with urllib.request.urlopen(u, timeout=2) as r:
    print(r.status)
except Exception:
  print(0)
PY

# Start health endpoint; main agent processes are launched by workflows/tools as needed
CMD ["python", "-m", "mcp_agent.health.server"]
