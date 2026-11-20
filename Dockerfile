# Portale Saporesta - istruttoria istanze A02
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.16 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONUNBUFFERED=1 \
    SAPORESTA_DATI=/data/pratiche \
    SAPORESTA_CONFIG=/data/config/impostazioni.json \
    SAPORESTA_MODELLI=/data/modelli

WORKDIR /app

# dipendenze (strato in cache finché pyproject/uv.lock non cambiano)
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY README.md ./
RUN uv sync --frozen --no-dev \
    && useradd --create-home --uid 1000 saporesta \
    && mkdir -p /data && chown saporesta /data

USER saporesta
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD ["/app/.venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/accesso', timeout=4)"]

CMD ["/app/.venv/bin/saporesta", "web", "--host", "0.0.0.0", "--porta", "8000"]
