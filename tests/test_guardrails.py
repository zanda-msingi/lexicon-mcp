"""Tests for the safety guardrails.

These invariants, if broken, can mass-mutate or misrepresent a real DJ library.
Each one is tested explicitly (per the working agreement). The quirks they defend
against are documented in docs/upstream-api-issues.md.
"""

import pytest

from lexicon_mcp.guardrails import (
    DEFAULT_BULK_WRITE_CEILING,
    BulkWriteSafetyError,
    UnsafeFilterError,
    assert_bulk_within_ceiling,
    assert_safe_search_filter,
    dedupe_track_ids,
)

# --- dedupe_track_ids: /v1/playlist can return duplicate trackIds for folders ---


def test_dedupe_preserves_first_seen_order_and_removes_duplicates():
    assert dedupe_track_ids([10, 8, 10, 5, 8, 8]) == [10, 8, 5]


def test_dedupe_empty_list_returns_empty():
    assert dedupe_track_ids([]) == []


# --- assert_safe_search_filter: bad filters SILENTLY return the whole library ---


def test_filter_on_drop_list_field_raises():
    # 'id' is in the silent-return-all drop list per upstream api-issues.md.
    with pytest.raises(UnsafeFilterError):
        assert_safe_search_filter({"id": 5})


def test_filter_tags_none_raises():
    # tags=NONE returns ALL tracks instead of untagged ones — a bulk-write trap.
    with pytest.raises(UnsafeFilterError):
        assert_safe_search_filter({"tags": "NONE"})


def test_filter_date_field_with_comparison_operator_raises():
    # date comparisons with > / < are silently dropped by the API.
    with pytest.raises(UnsafeFilterError):
        assert_safe_search_filter({"dateAdded": ">=2024-01-01"})


def test_safe_filter_passes():
    # A normal artist/bpm filter is fine and must not raise.
    assert_safe_search_filter({"artist": "Daft Punk", "bpm": ">=120"})


def test_empty_filter_raises_because_search_requires_a_filter():
    # /v1/search/tracks requires a filter; an empty one would match everything.
    with pytest.raises(UnsafeFilterError):
        assert_safe_search_filter({})


# --- assert_bulk_within_ceiling: never silently mass-mutate the library ---


def test_bulk_over_ceiling_raises():
    with pytest.raises(BulkWriteSafetyError):
        assert_bulk_within_ceiling(list(range(DEFAULT_BULK_WRITE_CEILING + 1)))


def test_bulk_within_ceiling_passes():
    # Should not raise.
    assert_bulk_within_ceiling([1, 2, 3])


def test_bulk_empty_raises():
    with pytest.raises(BulkWriteSafetyError):
        assert_bulk_within_ceiling([])


def test_bulk_explicit_confirm_count_must_match_actual():
    # If the caller asserts "I expect to write N", a mismatch must abort —
    # this is the count-before-bulk-write guard.
    with pytest.raises(BulkWriteSafetyError):
        assert_bulk_within_ceiling([1, 2, 3], expected_count=5)
