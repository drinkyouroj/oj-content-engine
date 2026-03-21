# Stage 1: Builder — install Python dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools needed for C extensions (asyncpg, uvloop)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc python3-dev libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy everything into /build (could be worker/ contents or full repo)
COPY . /build/src

# pip install: handle both build contexts
#   - Local docker build from worker/: pyproject.toml at /build/src/pyproject.toml
#   - Railway (full repo): pyproject.toml at /build/src/worker/pyproject.toml
RUN if [ -f /build/src/pyproject.toml ]; then \
      pip install --no-cache-dir /build/src; \
    elif [ -f /build/src/worker/pyproject.toml ]; then \
      pip install --no-cache-dir /build/src/worker; \
    else \
      echo "ERROR: pyproject.toml not found" && exit 1; \
    fi

# Stage 2: Runtime — slim image with only what's needed
FROM python:3.12-slim

WORKDIR /app

# libpq is needed at runtime by asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages and CLI scripts (uvicorn, arq, etc.) from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy worker source to /app/worker/ so imports like worker.app.main work.
# Handle both contexts: local (source IS worker/) and Railway (source has worker/ subdir)
COPY . /tmp/src
RUN if [ -d /tmp/src/worker ]; then \
      cp -r /tmp/src/worker /app/worker; \
    else \
      mkdir -p /app/worker && cp -r /tmp/src/* /app/worker/; \
    fi && rm -rf /tmp/src

# Make entrypoint executable
RUN chmod +x /app/worker/entrypoint.sh

# Railway injects PORT; default to 8000 for local dev
ENV PORT=8000
EXPOSE ${PORT}

ENTRYPOINT ["/app/worker/entrypoint.sh"]
