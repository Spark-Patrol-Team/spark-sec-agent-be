FROM ghcr.io/astral-sh/uv:0.12.4 AS uv

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY --from=uv /uv /uvx /usr/local/bin/
COPY pyproject.toml uv.lock ./
COPY README.md ./

RUN uv sync --locked --no-dev --no-install-project --no-cache

COPY src ./src
RUN uv sync --locked --no-dev --no-editable --no-cache

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)" || exit 1

CMD ["uvicorn", "sec_agent.main:app", "--host", "0.0.0.0", "--port", "8080"]
