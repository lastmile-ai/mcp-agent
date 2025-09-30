# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.11-slim

FROM python:${PYTHON_VERSION} AS builder
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md LICENSE /app/
COPY src /app/src
RUN python -m pip install --no-cache-dir --upgrade pip==23.3.2 build==1.2.2 && python -m build --wheel --outdir /dist /app

FROM python:${PYTHON_VERSION} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app
RUN useradd -m appuser && chown -R appuser:appuser /app
COPY --from=builder /dist/*.whl /tmp/pkg.whl
RUN python -m pip install --no-cache-dir --no-index --find-links=/tmp /tmp/pkg.whl && rm -rf /tmp/*
USER appuser
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s CMD python - <<'PY' | grep -q 200 || exit 1
import os, urllib.request
u=f"http://127.0.0.1:{os.getenv('PORT','8080')}/health"
try:
  with urllib.request.urlopen(u, timeout=2) as r:
    print(r.status)
except Exception:
  print(0)
PY

CMD ["python", "-m", "mcp_agent.health.server"]
