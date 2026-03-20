"""
Tests for the ARQ worker configuration and example ping job.
"""

from __future__ import annotations

import pytest

from worker.jobs.worker import WorkerSettings, ping


@pytest.mark.asyncio
async def test_ping_job():
    """Ping job returns the expected pong message."""
    result = await ping({})
    assert result == "pong"


def test_worker_settings_has_functions():
    """WorkerSettings registers at least the ping function."""
    func_names = [f.__name__ if callable(f) else f for f in WorkerSettings.functions]
    assert "ping" in func_names
