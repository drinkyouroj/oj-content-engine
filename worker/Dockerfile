# Stage 1: Builder — install Python dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools needed for C extensions (asyncpg, uvloop)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc python3-dev libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy all source so pip install can find all worker.* packages
COPY . .

RUN pip install --no-cache-dir .

# Stage 2: Runtime — slim image with only what's needed
FROM python:3.12-slim

WORKDIR /app

# libpq is needed at runtime by asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages (site-packages) from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages

# Copy application source
COPY . .

# Make entrypoint executable
RUN chmod +x entrypoint.sh

# Railway injects PORT; default to 8000 for local dev
ENV PORT=8000
EXPOSE ${PORT}

ENTRYPOINT ["./entrypoint.sh"]
