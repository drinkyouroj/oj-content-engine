"""
Unit tests for ARQ discovery job wrappers.

Mocks pollers and database sessions to verify job wiring
without network or database access.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from worker.jobs.discovery_jobs import poll_hn, poll_reddit, poll_rss, poll_twitter


@pytest.fixture
def mock_session_and_engine():
    """Fixture providing a mock session and engine for job tests."""
    session = AsyncMock()
    engine = AsyncMock()
    return session, engine


class TestPollRSS:
    """Tests for poll_rss ARQ job."""

    @pytest.mark.asyncio
    @patch("worker.jobs.discovery_jobs._get_session")
    @patch("worker.discovery.rss_poller.RSSPoller")
    async def test_calls_poller_run(self, MockPoller, mock_get_session) -> None:
        session = AsyncMock()
        engine = AsyncMock()
        mock_get_session.return_value = (session, engine)

        poller_instance = AsyncMock()
        poller_instance.run.return_value = 5
        MockPoller.return_value = poller_instance

        result = await poll_rss({})

        assert result == 5
        poller_instance.run.assert_called_once_with(session)
        session.close.assert_called_once()
        engine.dispose.assert_called_once()


class TestPollReddit:
    """Tests for poll_reddit ARQ job."""

    @pytest.mark.asyncio
    @patch("worker.jobs.discovery_jobs._get_session")
    @patch("worker.discovery.reddit_poller.RedditPoller")
    async def test_calls_poller_run(self, MockPoller, mock_get_session) -> None:
        session = AsyncMock()
        engine = AsyncMock()
        mock_get_session.return_value = (session, engine)

        poller_instance = AsyncMock()
        poller_instance.run.return_value = 3
        MockPoller.return_value = poller_instance

        result = await poll_reddit({})

        assert result == 3
        poller_instance.run.assert_called_once_with(session)


class TestPollHN:
    """Tests for poll_hn ARQ job."""

    @pytest.mark.asyncio
    @patch("worker.jobs.discovery_jobs._get_session")
    @patch("worker.discovery.hn_poller.HNPoller")
    async def test_calls_poller_run(self, MockPoller, mock_get_session) -> None:
        session = AsyncMock()
        engine = AsyncMock()
        mock_get_session.return_value = (session, engine)

        poller_instance = AsyncMock()
        poller_instance.run.return_value = 10
        MockPoller.return_value = poller_instance

        result = await poll_hn({})

        assert result == 10
        poller_instance.run.assert_called_once_with(session)


class TestPollTwitter:
    """Tests for poll_twitter ARQ job."""

    @pytest.mark.asyncio
    @patch("worker.jobs.discovery_jobs._get_session")
    @patch("worker.discovery.twitter_poller.TwitterPoller")
    async def test_calls_poller_run(self, MockPoller, mock_get_session) -> None:
        session = AsyncMock()
        engine = AsyncMock()
        mock_get_session.return_value = (session, engine)

        poller_instance = AsyncMock()
        poller_instance.run.return_value = 0
        MockPoller.return_value = poller_instance

        result = await poll_twitter({})

        assert result == 0
        poller_instance.run.assert_called_once_with(session)
