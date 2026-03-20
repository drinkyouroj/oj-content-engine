"""
Unit tests for dedup utilities.

Tests URL normalization, SHA-256 hash computation, and Levenshtein
title similarity detection. All tests are pure functions with no
network or database access.
"""

from __future__ import annotations

from worker.discovery.dedup import compute_dedup_hash, is_title_duplicate, normalize_url


class TestNormalizeUrl:
    """Tests for normalize_url()."""

    def test_lowercases_scheme_and_host(self) -> None:
        result = normalize_url("HTTPS://Example.COM/path")
        assert result == "https://example.com/path"

    def test_strips_trailing_slash(self) -> None:
        result = normalize_url("https://example.com/path/")
        assert result == "https://example.com/path"

    def test_removes_utm_params(self) -> None:
        result = normalize_url(
            "https://example.com/page?utm_source=twitter&utm_medium=social&key=val"
        )
        assert "utm_source" not in result
        assert "utm_medium" not in result
        assert "key=val" in result

    def test_removes_fragment(self) -> None:
        result = normalize_url("https://example.com/page#section")
        assert "#" not in result

    def test_sorts_query_params(self) -> None:
        result = normalize_url("https://example.com/page?z=1&a=2")
        assert result == "https://example.com/page?a=2&z=1"

    def test_strips_whitespace(self) -> None:
        result = normalize_url("  https://example.com/path  ")
        assert result == "https://example.com/path"

    def test_preserves_path(self) -> None:
        result = normalize_url("https://example.com/a/b/c")
        assert result == "https://example.com/a/b/c"

    def test_empty_path(self) -> None:
        result = normalize_url("https://example.com")
        assert result == "https://example.com"


class TestComputeDedupHash:
    """Tests for compute_dedup_hash()."""

    def test_returns_hex_string(self) -> None:
        result = compute_dedup_hash("https://example.com/page")
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex digest length

    def test_same_input_same_hash(self) -> None:
        url = "https://example.com/test"
        assert compute_dedup_hash(url) == compute_dedup_hash(url)

    def test_different_input_different_hash(self) -> None:
        h1 = compute_dedup_hash("https://example.com/a")
        h2 = compute_dedup_hash("https://example.com/b")
        assert h1 != h2


class TestIsTitleDuplicate:
    """Tests for is_title_duplicate()."""

    def test_exact_match_is_duplicate(self) -> None:
        assert is_title_duplicate("Hello World", ["Hello World"]) is True

    def test_near_match_is_duplicate(self) -> None:
        assert is_title_duplicate("Hello World!", ["Hello World"]) is True

    def test_different_title_not_duplicate(self) -> None:
        assert is_title_duplicate("Completely different", ["Hello World"]) is False

    def test_empty_existing_not_duplicate(self) -> None:
        assert is_title_duplicate("Hello World", []) is False

    def test_case_insensitive(self) -> None:
        assert is_title_duplicate("HELLO WORLD", ["hello world"]) is True

    def test_custom_threshold(self) -> None:
        # These are somewhat similar but not 95% similar
        assert (
            is_title_duplicate("Hello World Today", ["Hello World", "Goodbye"], threshold=0.95)
            is False
        )

    def test_one_match_among_many(self) -> None:
        existing = ["Foo bar", "Completely unrelated", "Hello World"]
        assert is_title_duplicate("Hello World!", existing) is True
