"""Tests for the Pydantic models.

Fixtures under tests/fixtures/ are SANITIZED copies of real API shapes (fake
names/paths, real structure). The real captures live in discovery/ which is
gitignored — we never publish library data.
"""

import json
from pathlib import Path

from lexicon_mcp.models import Tag, TagCategory, Track

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str):
    return json.loads((FIXTURES / name).read_text())


def test_track_parses_real_shape():
    track = Track.model_validate(_load("track.json"))
    assert track.id == 1
    assert track.title == "Example Track"
    assert track.artist == "Example Artist"
    assert track.bpm == 136
    assert track.key == "7M"
    assert track.tags == []  # no custom tags applied library-wide yet


def test_track_preserves_unknown_fields_losslessly():
    raw = _load("track.json")
    track = Track.model_validate(raw)
    dumped = track.model_dump()
    assert "data" in dumped  # the nested source-specific blob survives
    assert dumped["data"]["source"]["exampleField"] == "preserved-losslessly"
    # cloudFileState is undocumented but must not be dropped.
    assert "cloudFileState" in dumped


def test_tag_category_and_tags_parse_real_shape():
    raw = _load("tags.json")
    categories = [TagCategory.model_validate(c) for c in raw["categories"]]
    tags = [Tag.model_validate(t) for t in raw["tags"]]
    labels = {c.label for c in categories}
    assert {"Genre", "Mood", "Timing", "Mix"} <= labels
    # Tag carries the undocumented `shortcut` field without choking.
    assert any(t.shortcut is None for t in tags)
