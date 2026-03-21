"""
Base poller interface and RawSignal data structure.

Implements PRD Section 2 (Trend Discovery Layer). All concrete pollers
inherit from BasePoller, implement `fetch()`, and rely on the shared
`run()` method for dedup, persistence, and alert updates.

Inputs: External source data (RSS feeds, Reddit JSON, HN API, Twitter API).
Outputs: New Signal rows written to the signals table.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar

from sqlalchemy.ext.asyncio import AsyncSession

from worker.app.models.signal import Signal, SignalSource
from worker.discovery.alerts import update_alert
from worker.discovery.dedup import compute_dedup_hash, is_title_duplicate, normalize_url

logger = logging.getLogger(__name__)


@dataclass
class RawSignal:
    """Intermediate representation of a discovered trend before persistence.

    Attributes:
        url: Original URL of the trend.
        title: Signal title / headline.
        body_preview: First 500 characters of content, if available.
        discovered_at: Timestamp when the poller found or published the item.
        source_metrics: Engagement data from the source (upvotes, comments, velocity).
    """

    url: str
    title: str
    body_preview: str | None
    discovered_at: datetime
    source_metrics: dict = field(default_factory=dict)


class BasePoller(ABC):
    """Abstract base class for all trend discovery pollers.

    Subclasses must set the `source` class variable and implement `fetch()`.
    The `run()` method handles deduplication, persistence, and alert updates.
    """

    source: ClassVar[SignalSource]

    @abstractmethod
    async def fetch(self) -> list[RawSignal]:
        """Fetch raw signals from the external source.

        Returns:
            List of RawSignal instances discovered from the source.

        Raises:
            Exception: Subclass-specific errors from the external API.
        """
        ...

    async def run(self, session: AsyncSession) -> int:
        """Fetch, dedup, persist to signals table, and update alerts.

        This is the main entry point called by ARQ jobs. It orchestrates
        the full poller lifecycle: fetch from external source, deduplicate
        against existing signals, persist new ones, and update the dead
        source detection alert system.

        Args:
            session: Async SQLAlchemy session for database operations.

        Returns:
            Count of new signals inserted.
        """
        raw = await self.fetch()
        new_signals = await self._dedup_and_persist(session, raw)
        await update_alert(session, self.source.value, len(new_signals))
        return len(new_signals)

    async def _dedup_and_persist(
        self, session: AsyncSession, raw_signals: list[RawSignal]
    ) -> list[Signal]:
        """Deduplicate raw signals against existing DB entries and persist new ones.

        Deduplication is two-phase:
        1. URL hash check — SHA-256 of the normalized URL must be unique.
        2. Title similarity — Levenshtein ratio > 0.85 against recent titles
           from the same source flags a duplicate.

        Args:
            session: Async SQLAlchemy session.
            raw_signals: List of RawSignal instances from fetch().

        Returns:
            List of newly created Signal ORM instances that were persisted.
        """
        from sqlalchemy import select

        if not raw_signals:
            return []

        # Load existing hashes and titles for this source
        stmt = select(Signal.dedup_hash, Signal.title).where(
            Signal.source == self.source
        )
        result = await session.execute(stmt)
        rows = result.all()
        existing_hashes = {row.dedup_hash for row in rows}
        existing_titles = [row.title for row in rows]

        new_signals: list[Signal] = []
        for raw in raw_signals:
            normalized = normalize_url(raw.url)
            dedup_hash = compute_dedup_hash(normalized)

            if dedup_hash in existing_hashes:
                logger.debug("Skipping duplicate URL hash: %s", raw.url)
                continue

            if is_title_duplicate(raw.title, existing_titles):
                logger.debug("Skipping duplicate title: %s", raw.title)
                continue

            signal = Signal(
                source=self.source,
                url=raw.url,
                title=raw.title,
                body_preview=raw.body_preview[:500] if raw.body_preview else None,
                discovered_at=raw.discovered_at,
                source_metrics=raw.source_metrics,
                dedup_hash=dedup_hash,
            )
            session.add(signal)
            new_signals.append(signal)
            # Track for intra-batch dedup
            existing_hashes.add(dedup_hash)
            existing_titles.append(raw.title)

        if new_signals:
            await session.commit()
            logger.info(
                "Persisted %d new signals from %s", len(new_signals), self.source.value
            )

        return new_signals
