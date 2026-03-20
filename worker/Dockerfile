# Stage 1: Builder — install Python dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

# Copy source first so pip install can find the package
COPY pyproject.toml .
COPY app/ app/
COPY jobs/ jobs/

RUN pip install --no-cache-dir .

# Stage 2: Runtime — slim image with only what's needed
FROM python:3.12-slim

WORKDIR /app

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
