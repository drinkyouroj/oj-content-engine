"""
Deduplication utilities for the trend discovery layer.

Provides URL normalization, SHA-256 hashing, and Levenshtein-based title
similarity checking. Used by BasePoller._dedup_and_persist() to prevent
inserting duplicate signals into the database.

Implements PRD Section 2 (Dedup via SHA-256 hash of normalized URL).
"""

from __future__ import annotations

import hashlib
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from rapidfuzz import fuzz


def normalize_url(url: str) -> str:
    """Normalize a URL for consistent deduplication hashing.

    Transformations applied:
    - Lowercase scheme and host
    - Strip trailing slash from path
    - Remove fragment (#...)
    - Remove common tracking query params (utm_*)
    - Re-sort remaining query params alphabetically

    Args:
        url: Raw URL string from the source.

    Returns:
        Normalized URL string suitable for hashing.
    """
    parsed = urlparse(url.strip())

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    # Remove fragment
    fragment = ""

    # Filter out tracking params
    query_params = parse_qs(parsed.query, keep_blank_values=True)
    filtered_params = {
        k: v for k, v in query_params.items() if not k.lower().startswith("utm_")
    }
    # Sort params for consistency
    sorted_query = urlencode(dict(sorted(filtered_params.items())), doseq=True)

    return urlunparse((scheme, netloc, path, parsed.params, sorted_query, fragment))


def compute_dedup_hash(normalized_url: str) -> str:
    """Compute a SHA-256 hash of a normalized URL for dedup lookup.

    Args:
        normalized_url: URL that has already been passed through normalize_url().

    Returns:
        Hex-encoded SHA-256 digest string.
    """
    return hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()


def is_title_duplicate(
    title: str, existing_titles: list[str], threshold: float = 0.85
) -> bool:
    """Check whether a title is a near-duplicate of any existing title.

    Uses rapidfuzz Levenshtein ratio for fuzzy string matching.
    A ratio above the threshold means the titles are considered duplicates.

    Args:
        title: Candidate title to check.
        existing_titles: List of titles already in the database for this source.
        threshold: Similarity ratio (0.0-1.0) above which titles are duplicates.
            Defaults to 0.85.

    Returns:
        True if the title is a near-duplicate of any existing title.
    """
    if not existing_titles:
        return False

    for existing in existing_titles:
        ratio = fuzz.ratio(title.lower(), existing.lower()) / 100.0
        if ratio >= threshold:
            return True

    return False
