# syntax=docker/dockerfile:1

FROM python:3.13-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src/ src/

RUN uv sync --frozen --no-dev --extra app --no-editable

FROM python:3.13-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 10001 tenon \
    && useradd --uid 10001 --gid 10001 --create-home --home-dir /home/tenon tenon \
    && mkdir -p /data \
    && chown tenon:tenon /data

WORKDIR /app
COPY --from=build --chown=tenon:tenon /app /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PATH=/app/.venv/bin:$PATH

USER tenon

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=5)"

ENTRYPOINT ["tenon"]
CMD ["provider", "serve", "--bundles", "/data/bundles", "--db", "/data/tenon.db", "--host", "0.0.0.0", "--port", "8080"]
