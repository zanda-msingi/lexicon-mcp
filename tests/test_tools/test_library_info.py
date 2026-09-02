"""Tests for library_info."""

import json

import httpx

from lexicon_mcp.tools.library import library_info

TRACKS = [
    {"id": 1, "bpm": 120, "key": "1D", "energy": 6, "tags": [1, 2]},
    {"id": 2, "bpm": 0, "key": "", "energy": 0, "tags": []},
    {"id": 3, "bpm": 100, "key": "6M", "energy": 0, "tags": [2]},
]
TAGS = {
    "categories": [{"id": 10, "label": "Genre", "color": "#000", "tags": [1, 2]}],
    "tags": [
        {"id": 1, "categoryId": 10, "label": "House"},
        {"id": 2, "categoryId": 10, "label": "Soul"},
        {"id": 3, "categoryId": 10, "label": "Unused"},
    ],
}


def _handler(tracks, tags, tree, seen=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/tracks":
            body = json.loads(request.content)
            if seen is not None:
                seen.append(body)
            off, lim = body.get("offset", 0), body.get("limit", 1000)
            page = tracks[off : off + lim]
            return httpx.Response(
                200,
                json={"data": {"total": len(tracks), "limit": lim, "offset": off, "tracks": page}},
            )
        if request.url.path == "/v1/tags":
            return httpx.Response(200, json={"data": tags})
        if request.url.path == "/v1/playlists":
            return httpx.Response(200, json={"data": tree})
        raise AssertionError(f"unexpected path {request.url.path}")

    return handler


async def test_counts_coverage_tags_and_playlists(make_client, load_fixture):
    tree = load_fixture("playlists.json")  # 1 folder, 3 playlists, 1 smartlist

    async with make_client(_handler(TRACKS, TAGS, tree)) as client:
        info = await library_info(client)

    assert info["tracks"] == {
        "total": 3,
        "with_bpm": 2,
        "with_key": 2,
        "with_energy": 1,
        "tagged": 2,
    }
    assert info["key_notation"] == {"open_key": 2, "camelot": 0, "other": 0}
    assert info["playlists"] == {"folders": 1, "playlists": 3, "smartlists": 1}
    assert info["tag_categories"] == [
        {"id": 10, "label": "Genre", "tag_count": 3, "tracks_tagged": 2}
    ]
    assert info["tags"] == [
        {"id": 1, "label": "House", "category": "Genre", "track_count": 1},
        {"id": 2, "label": "Soul", "category": "Genre", "track_count": 2},
        {"id": 3, "label": "Unused", "category": "Genre", "track_count": 0},
    ]


async def test_scans_every_page_with_minimal_fields(make_client, load_fixture):
    seen: list[dict] = []
    tree = load_fixture("playlists.json")

    def handler(request: httpx.Request) -> httpx.Response:
        # Force 2-row pages so a 3-track library needs two requests.
        if request.url.path == "/v1/tracks":
            body = json.loads(request.content)
            seen.append(body)
            off = body["offset"]
            page = TRACKS[off : off + 2]
            return httpx.Response(200, json={"data": {"total": 3, "tracks": page}})
        return _handler(TRACKS, TAGS, tree)(request)

    async with make_client(handler) as client:
        info = await library_info(client)

    assert info["tracks"]["total"] == 3
    assert [b["offset"] for b in seen] == [0, 2]
    assert all(b["limit"] == 1000 for b in seen)
    assert all(b["fields"] == ["id", "bpm", "key", "energy", "tags"] for b in seen)


async def test_key_notation_counts_each_style(make_client, load_fixture):
    tree = load_fixture("playlists.json")
    mixed = [{"id": 1, "key": "8A", "tags": []}, {"id": 2, "key": "1D", "tags": []}]
    none = [{"id": 1, "key": "", "tags": []}]

    async with make_client(_handler(mixed, TAGS, tree)) as client:
        assert (await library_info(client))["key_notation"] == {
            "open_key": 1,
            "camelot": 1,
            "other": 0,
        }
    async with make_client(_handler(none, TAGS, tree)) as client:
        assert (await library_info(client))["key_notation"] == {
            "open_key": 0,
            "camelot": 0,
            "other": 0,
        }
