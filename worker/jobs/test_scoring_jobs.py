"""
Tests for the scoring ARQ job.

Mocks the database, config, and scoring pipeline to verify the job
discovers unscored signals and processes them correctly.
All tests run without network, API keys, or a real database.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from worker.jobs.scoring_jobs import run_scoring_pipeline


def _make_signal(signal_id: uuid.UUID | None = None) -> SimpleNamespace:
    """Create a fake Signal row."""
    return SimpleNamespace(id=signal_id or uuid.uuid4())


@pytest.mark.asyncio
async def test_scores_unscored_signals():
    """Job finds unscored signals and scores each one."""
    sig1 = _make_signal()
    sig2 = _make_signal()

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [sig1, sig2]
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock(return_value=mock_session)

    mock_engine = AsyncMock()
    mock_engine.dispose = AsyncMock()

    mock_settings = SimpleNamespace(
        database_url="postgresql://test:test@localhost/test",
        anthropic_api_key="sk-test",
    )

    with (
        patch("worker.jobs.scoring_jobs.get_settings", return_value=mock_settings),
        patch("worker.jobs.scoring_jobs.make_engine", return_value=mock_engine),
        patch("worker.jobs.scoring_jobs.make_session_factory", return_value=mock_factory),
        patch(
            "worker.jobs.scoring_jobs.score_signal",
            new_callable=AsyncMock,
        ) as mock_score,
    ):
        count = await run_scoring_pipeline({})

    assert count == 2
    assert mock_score.call_count == 2


@pytest.mark.asyncio
async def test_handles_individual_signal_failure():
    """Job logs error and continues if one signal fails."""
    sig1 = _make_signal()
    sig2 = _make_signal()

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [sig1, sig2]
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock(return_value=mock_session)

    mock_engine = AsyncMock()
    mock_engine.dispose = AsyncMock()

    mock_settings = SimpleNamespace(
        database_url="postgresql://test:test@localhost/test",
        anthropic_api_key="sk-test",
    )

    with (
        patch("worker.jobs.scoring_jobs.get_settings", return_value=mock_settings),
        patch("worker.jobs.scoring_jobs.make_engine", return_value=mock_engine),
        patch("worker.jobs.scoring_jobs.make_session_factory", return_value=mock_factory),
        patch(
            "worker.jobs.scoring_jobs.score_signal",
            new_callable=AsyncMock,
            side_effect=[Exception("Score failed"), MagicMock()],
        ),
    ):
        count = await run_scoring_pipeline({})

    # Only second signal should count as scored
    assert count == 1


@pytest.mark.asyncio
async def test_no_unscored_signals():
    """Job returns 0 when no unscored signals exist."""
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock(return_value=mock_session)

    mock_engine = AsyncMock()
    mock_engine.dispose = AsyncMock()

    mock_settings = SimpleNamespace(
        database_url="postgresql://test:test@localhost/test",
        anthropic_api_key="sk-test",
    )

    with (
        patch("worker.jobs.scoring_jobs.get_settings", return_value=mock_settings),
        patch("worker.jobs.scoring_jobs.make_engine", return_value=mock_engine),
        patch("worker.jobs.scoring_jobs.make_session_factory", return_value=mock_factory),
    ):
        count = await run_scoring_pipeline({})

    assert count == 0
