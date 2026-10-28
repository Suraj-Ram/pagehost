# Pagehost MCP server. Nginx is a separate compose service; it serves data/sites.
# Build with the same interpreter path in both stages so the venv stays valid.

FROM ghcr.io/astral-sh/uv:python3.12-trixie-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_DEV=1 UV_PYTHON_DOWNLOADS=0

WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project
COPY pyproject.toml uv.lock server.py fastmcp.json /app/
COPY pagehost /app/pagehost
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

FROM python:3.12-slim-trixie

RUN groupadd --system --gid 999 nonroot \
 && useradd --system --gid 999 --uid 999 --create-home nonroot \
 && mkdir -p /data/sites \
 && chown -R nonroot:nonroot /data

COPY --from=builder --chown=nonroot:nonroot /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER nonroot
WORKDIR /app
EXPOSE 8080

# fastmcp.json binds 127.0.0.1 for local `fastmcp run`. The compose port
# mapping reaches this process from the host, so listen on all interfaces.
# The factory reads PAGEHOST_* from the environment.
CMD ["fastmcp", "run", "server.py:server", "--transport", "http", "--host", "0.0.0.0", "--port", "8080", "--skip-env"]
