#!/usr/bin/env bash
set -euo pipefail

echo "Starting OJ Content Engine Worker..."
echo "  FastAPI on port ${PORT:-8000}"
echo "  ARQ worker connecting to Redis"

# Run both processes; exit if either dies
uvicorn worker.app.main:app --host 0.0.0.0 --port "${PORT:-8000}" &
python -m arq worker.jobs.worker.WorkerSettings &
wait -n
