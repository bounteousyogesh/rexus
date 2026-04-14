FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# Install into /app/backend so the source tree matches 'backend.api.*' imports
WORKDIR /app/backend

COPY backend/requirements.txt .

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app"

# WORKDIR is /app — source is copied to /app/backend/
# so Python can resolve 'backend.api.*' imports via PYTHONPATH=/app
WORKDIR /app/backend

COPY --from=builder /opt/venv /opt/venv
# Build context is the repo root — copy backend source and repo-level data
COPY backend/ .
COPY data/ /app/data/

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8000"]