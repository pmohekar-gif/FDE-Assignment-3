FROM python:3.12-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /uvx /bin/
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/app/data/warrant.db \
    AI_PROVIDER=fixture

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "warrant.main:app", "--host", "0.0.0.0", "--port", "8000"]
