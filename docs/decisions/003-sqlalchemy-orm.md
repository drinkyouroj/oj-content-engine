# 003 — SQLAlchemy ORM Over Raw SQL
_Date: 2026-03-19 | Status: Accepted_

## Context

The Worker layer needs to interact with 7 Postgres tables. We need to
decide between raw SQL (via asyncpg directly), SQLAlchemy Core (table
definitions without ORM), or full SQLAlchemy ORM.

## Options Considered

1. **Raw asyncpg** — Write SQL strings directly, no abstraction layer.
   - Pros: Maximum performance, no ORM overhead, full SQL control
   - Cons: No Alembic autogenerate (must write migrations by hand).
     No relationship loading. Manual result-to-object mapping everywhere.

2. **SQLAlchemy Core** — Table definitions for Alembic, raw SQL for queries.
   - Pros: Alembic autogenerate works. Still close to SQL.
   - Cons: Awkward middle ground — defining tables twice (once for Alembic,
     once as query patterns). No relationship loading.

3. **SQLAlchemy ORM (async)** — Full ORM with mapped classes.
   - Pros: Alembic autogenerate. Pythonic queries. Relationship loading.
     Handles JSONB well. Type annotations via Mapped[].
   - Cons: ORM overhead (negligible at our scale). Learning curve for
     async patterns (mitigated by SQLAlchemy 2.x maturity).

## Decision

Option 3: Full async SQLAlchemy ORM. Alembic autogenerate is the killer
feature — writing 7 tables worth of migration SQL by hand is error-prone.
The ORM's relationship loading simplifies pipeline queries (e.g., loading
a topic with its scored signal and drafts). Performance overhead is
irrelevant at ~50 signals/day.

## Consequences

- **Easier:** Alembic autogenerate catches schema drift. Relationship
  loading simplifies multi-table queries in scoring and generation.
- **Harder:** Must understand SQLAlchemy async patterns (async sessions,
  lazy loading caveats). Team members need ORM familiarity.
- **Deferred:** If query performance becomes an issue (unlikely at scale),
  can drop to Core or raw SQL for hot paths without changing the models.
