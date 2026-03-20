# Jobs Module

## Purpose

ARQ background job definitions and worker configuration. Each pipeline
stage registers its jobs here. Implements PRD Section 8 (ARQ as async
task queue).

## Structure

- `worker.py` — ARQ WorkerSettings class, job registry, Redis connection
- Future: one file per pipeline stage (discovery_jobs.py, scoring_jobs.py, etc.)

## How it fits in the pipeline

ARQ jobs are the execution units of the pipeline. Discovery pollers,
scoring passes, content generation, and Notion staging all run as
independent ARQ jobs with retry and scheduling support.

## Running locally

```bash
# Run the ARQ worker
arq worker.jobs.worker.WorkerSettings
```
