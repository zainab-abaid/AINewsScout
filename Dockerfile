# Build the React UI, then run FastAPI (API + static UI) for Railway.
# Railway detects this file automatically when named `Dockerfile`.

FROM node:22-bookworm-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    DATA_DIR=/app/data \
    UV_LINK_MODE=copy

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY backend ./backend
COPY skills ./skills
COPY --from=frontend /frontend/dist ./frontend/dist

# SQLite lives on a Railway volume mounted at /app/data (see docs/RAILWAY.md).
RUN mkdir -p /app/data

EXPOSE 8000

# Railway injects $PORT. overlapSeconds=0 in railway.toml keeps a single SQLite writer.
CMD ["sh", "-c", "uv run uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
