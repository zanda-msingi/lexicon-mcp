"""Safety guardrails for operations that could damage or misrepresent a library.

The Lexicon Local API has quirks where a *bad* request silently succeeds against
the WHOLE library instead of erroring (see docs/upstream-api-issues.md). Chained
into a bulk write, that can mass-mutate ~40k tracks by accident. These pure,
independently-tested functions are the defenses.
"""

from __future__ import annotations

# Filter fields that the API SILENTLY DROPS — a filter on any of these returns the
# entire library instead of a filtered set (docs/upstream-api-issues.md).
SILENT_RETURN_ALL_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "type",
        "locationUnique",
        "incoming",
        "archived",
        "archivedSince",
        "beatshiftCase",
        "fingerprint",
        "streamingService",
        "streamingId",
        "cuepoints",
        "tempomarkers",
    }
)

# Date fields whose `>`/`<` comparisons are silently dropped by the API.
DATE_FIELDS: frozenset[str] = frozenset({"lastPlayed", "dateAdded", "dateModified"})

# A bulk write touching more tracks than this aborts unless the caller raises the
# ceiling explicitly. A backstop against accidental whole-library mutation.
DEFAULT_BULK_WRITE_CEILING: int = 500


class UnsafeFilterError(ValueError):
    """A search filter would silently match the entire library."""


class BulkWriteSafetyError(ValueError):
    """A bulk write is empty, exceeds the safety ceiling, or fails its count check."""


def dedupe_track_ids(track_ids: list[int]) -> list[int]:
    """Drop duplicate track ids while preserving first-seen order.

    `GET /v1/playlist` can return duplicate `trackIds` for folder playlists.
    """
    seen: set[int] = set()
    out: list[int] = []
    for tid in track_ids:
        if tid not in seen:
            seen.add(tid)
            out.append(tid)
    return out


def assert_safe_search_filter(filter: dict) -> None:
    """Raise UnsafeFilterError if the filter would silently match everything.

    Empty filters, known silently-dropped fields, the `tags=NONE` trap, and
    `>`/`<` comparisons on date fields are all rejected before they ever reach
    the API.
    """
    if not filter:
        raise UnsafeFilterError(
            "Empty search filter would match the entire library. "
            "Provide at least one concrete filter (e.g. {'artist': 'Daft Punk'})."
        )

    bad_fields = sorted(set(filter) & SILENT_RETURN_ALL_FIELDS)
    if bad_fields:
        raise UnsafeFilterError(
            f"Filtering on {bad_fields} is silently dropped by the Lexicon API and "
            "returns the ENTIRE library. Use a different field, or fetch by id."
        )

    tags_value = filter.get("tags")
    if isinstance(tags_value, str) and tags_value.strip().upper() == "NONE":
        raise UnsafeFilterError(
            "tags=NONE returns ALL tracks (not untagged ones) on the Lexicon API. "
            "The 'find untagged tracks' filter is not supported server-side."
        )

    for field in DATE_FIELDS:
        value = filter.get(field)
        if isinstance(value, str) and value.strip()[:1] in {">", "<"}:
            raise UnsafeFilterError(
                f"Comparison filters (>/<) on date field '{field}' are silently "
                "dropped by the Lexicon API and return the entire library."
            )


def assert_bulk_within_ceiling(
    track_ids: list[int],
    ceiling: int = DEFAULT_BULK_WRITE_CEILING,
    expected_count: int | None = None,
) -> None:
    """Raise BulkWriteSafetyError unless a bulk write is sized safely.

    Guards against: empty target sets, sets larger than the ceiling (likely a
    silent return-all leaking into a write), and a mismatch with the caller's
    explicitly expected count (the count-before-bulk-write check).
    """
    count = len(track_ids)
    if count == 0:
        raise BulkWriteSafetyError("Refusing a bulk write with an empty track set.")
    if count > ceiling:
        raise BulkWriteSafetyError(
            f"Bulk write targets {count} tracks, over the safety ceiling of {ceiling}. "
            "This often means a search silently returned the whole library. "
            "Narrow the set or raise the ceiling explicitly if this is intended."
        )
    if expected_count is not None and count != expected_count:
        raise BulkWriteSafetyError(
            f"Bulk write count mismatch: caller expected {expected_count} tracks but "
            f"the target set has {count}. Aborting rather than writing the wrong set."
        )
