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

# Write healthcheck script via RUN heredoc (allowed)
RUN <<'PY' bash -lc 'cat > /usr/local/bin/healthcheck.py && chmod +x /usr/local/bin/healthcheck.py'
import os, urllib.request, sys
u = f"http://127.0.0.1:{os.getenv('PORT','8080')}/health"
try:
    s = urllib.request.urlopen(u, timeout=2).status
    sys.exit(0 if s == 200 else 1)
except Exception:
    sys.exit(1)
PY

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s CMD ["python","/usr/local/bin/healthcheck.py"]

CMD ["python", "-m", "mcp_agent.health.server"]
