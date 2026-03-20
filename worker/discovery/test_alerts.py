"""
Unit tests for dead source detection alerts.

Mocks AsyncSession to test alert creation, update, and resolution
without database access.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from worker.discovery.alerts import ALERT_TYPE, FAILURE_THRESHOLD, update_alert


def _make_mock_session(existing_alert=None):
    """Create a mock AsyncSession that returns the given alert.

    Args:
        existing_alert: An existing SystemAlert mock to return from the query,
            or None if no active alert exists.

    Returns:
        Mock AsyncSession.
    """
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = existing_alert
    session.execute.return_value = result_mock
    return session


def _make_alert(
    source: str = "rss",
    consecutive_failures: int = 0,
    resolved_at: datetime | None = None,
) -> MagicMock:
    """Create a mock SystemAlert."""
    alert = MagicMock()
    alert.source = source
    alert.alert_type = ALERT_TYPE
    alert.consecutive_failures = consecutive_failures
    alert.last_failure_at = None
    alert.resolved_at = resolved_at
    return alert


class TestUpdateAlert:
    """Tests for update_alert()."""

    @pytest.mark.asyncio
    async def test_success_with_no_existing_alert(self) -> None:
        """result_count > 0 and no existing alert — no-op."""
        session = _make_mock_session(existing_alert=None)
        await update_alert(session, "rss", result_count=5)

        # Should not create any alert or commit
        session.add.assert_not_called()
        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_success_resolves_existing_alert(self) -> None:
        """result_count > 0 with an active alert — resolve it."""
        alert = _make_alert(consecutive_failures=3)
        session = _make_mock_session(existing_alert=alert)

        await update_alert(session, "rss", result_count=5)

        assert alert.resolved_at is not None
        assert alert.consecutive_failures == 0
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_failure_creates_new_alert(self) -> None:
        """result_count == 0 with no existing alert — create one."""
        session = _make_mock_session(existing_alert=None)

        await update_alert(session, "rss", result_count=0)

        session.add.assert_called_once()
        added_alert = session.add.call_args[0][0]
        assert added_alert.source == "rss"
        assert added_alert.consecutive_failures == 1
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_failure_increments_existing_alert(self) -> None:
        """result_count == 0 with existing alert — increment failures."""
        alert = _make_alert(consecutive_failures=2)
        session = _make_mock_session(existing_alert=alert)

        await update_alert(session, "rss", result_count=0)

        assert alert.consecutive_failures == 3
        assert alert.last_failure_at is not None
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_failure_threshold_constant(self) -> None:
        """Verify the failure threshold is set to 3."""
        assert FAILURE_THRESHOLD == 3
