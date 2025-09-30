# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.11-slim

FROM python:${PYTHON_VERSION} AS builder
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md LICENSE /app/
COPY src /app/src
RUN python -m pip install --no-cache-dir --upgrade pip==23.3.2 build==1.2.2 && python -m build --wheel --outdir /dist /app
RUN python -m pip download --no-cache-dir --dest /wheelhouse /dist/*.whl

FROM python:${PYTHON_VERSION} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app
RUN useradd -m appuser && chown -R appuser:appuser /app
COPY --from=builder /dist/*.whl /tmp/
COPY --from=builder /wheelhouse /wheelhouse
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheelhouse /tmp/*.whl && rm -rf /tmp/* /wheelhouse
USER appuser
EXPOSE 8080

# Write healthcheck script using a nested heredoc inside RUN (valid)
RUN <<'SH'
cat >/usr/local/bin/healthcheck.py <<'PY'
import os, urllib.request, sys
u = f"http://127.0.0.1:{os.getenv('PORT','8080')}/health"
try:
    s = urllib.request.urlopen(u, timeout=2).status
    sys.exit(0 if s == 200 else 1)
except Exception:
    sys.exit(1)
PY
chmod +x /usr/local/bin/healthcheck.py
SH

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s CMD ["python","/usr/local/bin/healthcheck.py"]


CMD ["python", "-m", "mcp_agent.health.server"]