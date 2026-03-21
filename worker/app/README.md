# App Module

## Purpose

Core application code for the Worker layer: FastAPI app, configuration,
database connection management, and ORM model definitions.

## Structure

- `main.py` — FastAPI app with /health endpoint and lifespan management
- `config.py` — pydantic-settings configuration from environment variables
- `database.py` — Async SQLAlchemy engine and session factory
- `models/` — One ORM model per file, shared base class with UUID PK + timestamps

## How it fits in the pipeline

Provides the foundational infrastructure that all pipeline stages build on.
Models define the shared Postgres schema. Config validates required env vars.
Database module manages connection pooling.
