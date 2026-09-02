"""MCP server entrypoint for lexicon-mcp.

A stdio MCP server that exposes the eight MVP tools as thin wrappers over the
Lexicon client. The tools are the plumbing; the LLM composes them.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import LexiconClient
from .config import Config, load_config
from .tools import library, playlists, smartlists, tags, tracks


def build_server(config: Config | None = None) -> FastMCP:
    """Build the FastMCP server with all MVP tools registered.

    A fresh LexiconClient is opened per call — stdio MCP traffic is low-volume,
    and a multi-call tool (e.g. get_playlist_tracks) reuses the one client for
    the duration of its call.
    """
    cfg = config or load_config()
    mcp = FastMCP("lexicon-mcp")

    def client() -> LexiconClient:
        return LexiconClient(cfg.base_url)

    @mcp.tool()
    async def list_playlists(tree: bool = False) -> list[dict[str, Any]]:
        """Return every playlist, folder and smartlist as a flat list of
        {id, name, path, kind, parent_id} rows in Lexicon's order, where path
        joins folder names with " / ". Pass tree=True for the raw nested tree.
        No track counts either way; use get_playlist_tracks for contents.
        """
        async with client() as lex:
            return await playlists.list_playlists(lex, tree=tree)

    @mcp.tool()
    async def get_playlist_tracks(
        playlist_id: int,
        fields: list[str] | None = None,
        full: bool = False,
    ) -> list[dict[str, Any]]:
        """Return a playlist's tracks in playlist order. By default each record
        carries a compact field set (id, title, artist, albumTitle, genre,
        comment, bpm, key, energy, year, duration, rating, playCount, tags).
        Pass `fields` to choose exactly which fields, or `full=True` for the
        complete records including cue points and tempo markers (~3 KB each).
        """
        async with client() as lex:
            return await playlists.get_playlist_tracks(lex, playlist_id, fields=fields, full=full)

    @mcp.tool()
    async def search_tracks(
        filter: dict[str, Any],
        fields: list[str] | None = None,
        sort: list[Any] | None = None,
        source: str | None = None,
        limit: int | None = 100,
    ) -> dict[str, Any]:
        """Search the library. `filter` maps field -> value/comparison, e.g.
        {"artist": "Daft Punk", "bpm": ">=120"}. Returns {total, returned,
        tracks}; results are capped by `limit` while `total` is the real count.
        Unsafe filters that would match the whole library are rejected.
        """
        async with client() as lex:
            return await tracks.search_tracks(
                lex, filter, fields=fields, sort=sort, source=source, limit=limit
            )

    @mcp.tool()
    async def library_info() -> dict[str, Any]:
        """Summarise the whole library in one call: track totals and how many
        carry bpm / key / energy / any tag; key notation in use (open_key,
        camelot, mixed); playlist counts by kind; every tag category and tag
        with the number of tracks carrying it. Scans all tracks (fast).
        """
        async with client() as lex:
            return await library.library_info(lex)

    @mcp.tool()
    async def get_track(track_id: int) -> dict[str, Any]:
        """Return the full record for one track (metadata, tags, cues)."""
        async with client() as lex:
            return await tracks.get_track(lex, track_id)

    @mcp.tool()
    async def list_custom_tag_categories() -> list[dict[str, Any]]:
        """Return the custom-tag taxonomy: each category with its tags."""
        async with client() as lex:
            return await tags.list_custom_tag_categories(lex)

    @mcp.tool()
    async def create_tag_category(label: str, color: str | None = None) -> dict[str, Any]:
        """Create a custom-tag category (e.g. "Undertow") and return it with its
        new id. Labels must be unique; Lexicon rejects duplicates.
        """
        async with client() as lex:
            return await tags.create_tag_category(lex, label, color=color)

    @mcp.tool()
    async def create_tag(category_id: int, label: str) -> dict[str, Any]:
        """Create a custom tag inside a category and return it with its new id.
        Tag labels are unique across the whole library (case-sensitive).
        """
        async with client() as lex:
            return await tags.create_tag(lex, category_id, label)

    @mcp.tool()
    async def set_custom_tags(track_id: int, tag_ids: list[int | str]) -> dict[str, Any]:
        """Set a track's custom tags to EXACTLY tag_ids (replace). Entries may
        be tag ids or labels ("Genre/Afro House" or just "Afro House"). Pass []
        to clear. To add without disturbing others, read the track and set the
        union, or use bulk_apply_tags for many tracks.
        """
        async with client() as lex:
            return await tags.set_custom_tags(lex, track_id, tag_ids)

    @mcp.tool()
    async def bulk_apply_tags(
        track_ids: list[int],
        tag_ids: list[int | str],
        expected_count: int | None = None,
        ceiling: int = 500,
    ) -> dict[str, Any]:
        """Add tag_ids (ids or labels like "Genre/Afro House") to each of
        track_ids (merge, never wipe). Refuses an empty set, a set over
        `ceiling`, or a mismatch with `expected_count`, before any write.
        Returns a summary of updated/unchanged/failed.
        """
        async with client() as lex:
            return await tags.bulk_apply_tags(
                lex,
                track_ids,
                tag_ids,
                expected_count=expected_count,
                ceiling=ceiling,
            )

    @mcp.tool()
    async def create_smartlist(
        name: str,
        rules: list[dict[str, Any]],
        match_all: bool = True,
        parent_id: int | None = None,
    ) -> dict[str, Any]:
        """Create a smartlist from rules, e.g.
        [{"field": "bpm", "operator": "NumberGreaterThan", "values": [120]}].
        match_all=True requires every rule (AND), False is ANY (OR).
        """
        async with client() as lex:
            return await smartlists.create_smartlist(
                lex, name, rules, match_all=match_all, parent_id=parent_id
            )

    return mcp


def main() -> None:
    """Console-script entrypoint (``lexicon-mcp``); runs over stdio."""
    build_server().run()


if __name__ == "__main__":
    main()
