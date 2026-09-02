"""Tests for get_playlist_tracks."""

import httpx

from lexicon_mcp.tools.playlists import get_playlist_tracks


async def test_dedupes_trackids_and_fetches_full_tracks_in_order(make_client, load_fixture):
    playlist = load_fixture("playlist.json")  # trackIds [101,102,103,102,101]
    track_calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/playlist":
            return httpx.Response(200, json={"data": {"playlist": playlist}})
        if request.url.path == "/v1/track":
            tid = int(request.url.params["id"])
            track_calls.append(tid)
            return httpx.Response(200, json={"data": {"track": {"id": tid, "title": f"T{tid}"}}})
        raise AssertionError(f"unexpected path {request.url.path}")

    async with make_client(handler) as client:
        result = await get_playlist_tracks(client, 4)

    # Deduped to 3 unique ids, fetched once each, returned in playlist order.
    assert [t["id"] for t in result] == [101, 102, 103]
    assert sorted(track_calls) == [101, 102, 103]
    assert len(track_calls) == 3


async def test_skips_tracks_that_no_longer_exist(make_client):
    playlist = {"id": 4, "name": "P", "type": "2", "trackIds": [101, 102, 103]}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/playlist":
            return httpx.Response(200, json={"data": {"playlist": playlist}})
        tid = int(request.url.params["id"])
        if tid == 102:  # since-deleted track
            return httpx.Response(400, json={"message": "not found", "errorCode": 4})
        return httpx.Response(200, json={"data": {"track": {"id": tid}}})

    async with make_client(handler) as client:
        result = await get_playlist_tracks(client, 4)

    assert [t["id"] for t in result] == [101, 103]


async def test_empty_playlist_returns_empty_list(make_client):
    playlist = {"id": 9, "name": "Empty", "type": "2", "trackIds": []}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"playlist": playlist}})

    async with make_client(handler) as client:
        result = await get_playlist_tracks(client, 9)

    assert result == []


# --- v0.2: compact records by default, `fields` override, `full` opt-in ---

FULL_TRACK = {
    "id": 101,
    "title": "T",
    "artist": "A",
    "albumTitle": "Alb",
    "genre": "House",
    "comment": "8B - Energy 6",
    "bpm": 120,
    "key": "1D",
    "energy": 6,
    "year": 2020,
    "duration": 425,
    "rating": 0,
    "playCount": 3,
    "tags": [1],
    "location": "/Volumes/ExampleDrive/T.mp3",
    "locationUnique": "/volumes/exampledrive/t.mp3",
    "data": {"traktor": {"audioId": "AAAA"}},
    "cuepoints": [{"id": 1, "name": "AutoGrid"}],
    "tempomarkers": [{"id": 1, "bpm": 120}],
}


def _one_track_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/v1/playlist":
        playlist = {"id": 4, "name": "P", "type": "2", "trackIds": [101]}
        return httpx.Response(200, json={"data": {"playlist": playlist}})
    return httpx.Response(200, json={"data": {"track": dict(FULL_TRACK)}})


async def test_default_returns_compact_records_without_blobs(make_client):
    async with make_client(_one_track_handler) as client:
        [track] = await get_playlist_tracks(client, 4)

    # The fields a tagging or set-building conversation needs...
    for key in ("id", "title", "artist", "bpm", "key", "energy", "genre", "tags", "duration"):
        assert key in track, key
    # ...and none of the payload that was making pulls 3 KB per track.
    for key in ("data", "cuepoints", "tempomarkers", "location", "locationUnique"):
        assert key not in track, key


async def test_fields_returns_exactly_the_requested_fields(make_client):
    async with make_client(_one_track_handler) as client:
        [track] = await get_playlist_tracks(client, 4, fields=["id", "title", "cuepoints"])

    assert track == {"id": 101, "title": "T", "cuepoints": [{"id": 1, "name": "AutoGrid"}]}


async def test_full_returns_the_complete_record(make_client):
    async with make_client(_one_track_handler) as client:
        [track] = await get_playlist_tracks(client, 4, full=True)

    assert track == FULL_TRACK
