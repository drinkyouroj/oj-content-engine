"""
Shared pytest fixtures for the worker test suite.

Sets dummy env vars so that modules requiring config (like WorkerSettings)
can be imported during tests without a real .env file.
pytest-asyncio with asyncio_mode = "auto" in pyproject.toml handles
async test discovery automatically.
"""

from __future__ import annotations

import os

# Set dummy env vars before any test imports trigger get_settings().
# These are only used if real env vars / .env file are not present.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("ARQ_REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("UPSTASH_REDIS_REST_URL", "https://localhost")
os.environ.setdefault("UPSTASH_REDIS_REST_TOKEN", "test-token")
