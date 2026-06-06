"""Pydantic models built from the REAL Lexicon API shapes (see discovery/).

Design choices:
- ``extra="allow"``: Lexicon returns undocumented fields (cloudFileState, shortcut,
  activeLoop, source-specific blobs) that keep changing. We preserve everything
  rather than silently dropping data — faithful and library-shape-agnostic.
- Only the stable, broadly-useful fields are typed explicitly; the rest ride along.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class _Lossless(BaseModel):
    """Base that keeps unknown fields instead of dropping them."""

    model_config = ConfigDict(extra="allow")


class Tag(_Lossless):
    id: int
    categoryId: int | None = None
    label: str
    shortcut: str | None = None


class TagCategory(_Lossless):
    id: int
    label: str
    color: str | None = None
    tags: list[int] = []


class Cuepoint(_Lossless):
    id: int
    name: str | None = None
    startTime: float | None = None
    endTime: float | None = None


class Track(_Lossless):
    id: int
    title: str | None = None
    artist: str | None = None
    albumTitle: str | None = None
    location: str | None = None
    key: str | None = None
    genre: str | None = None
    bpm: float | None = None
    rating: int | None = None
    energy: int | None = None
    duration: float | None = None
    comment: str | None = None
    tags: list[int] = []
    cuepoints: list[Cuepoint] = []


class Playlist(_Lossless):
    id: int
    name: str
    type: str | None = None
    parentId: int | None = None
    position: int | None = None
    # Present on /v1/playlists (tree) — children playlists/folders.
    playlists: list[Playlist] | None = None
    # Present on /v1/playlist?id= — the ordered membership.
    trackIds: list[int] | None = None
    data: Any | None = None
