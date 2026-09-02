# Tag a playlist

**Goal:** apply custom tags to every track in one playlist. The LLM decides which tags fit; the tools do the plumbing.

This walkthrough was written from a real session against a ~40,000-track library. Tool calls are shown the way an MCP client sends them; responses are abridged and the library data is illustrative.

## 1. Learn the taxonomy

Tag tools take **tag ids**, not labels, so start by reading what exists.

```
list_custom_tag_categories()
```

```json
[
  {"id": 1, "label": "Genre", "color": "#11A03C",
   "tags": [{"id": 1, "label": "Afro House"}, {"id": 22, "label": "House"}, "..."]},
  {"id": 2, "label": "Mood",
   "tags": [{"id": 51, "label": "Warm"}, {"id": 49, "label": "Upbeat"}, "..."]},
  {"id": 3, "label": "Timing",
   "tags": [{"id": 52, "label": "Warmup"}, {"id": 55, "label": "Peak Hour"}, "..."]}
]
```

Keep this response around for the rest of the conversation. It is the label-to-id map for every write that follows. Membership is computed from each tag's `categoryId`, so it is correct even when Lexicon's own category listing is stale.

## 2. Find the playlist

```
list_playlists()
```

The response is the full tree: a `ROOT` node (id 2) containing folders (`type: "1"`) that contain playlists (`type: "2"`). Smartlists are `type: "3"`. There are no track counts in the tree; walk it by name to find the id you want.

```json
{"id": 74, "name": "Crates", "type": "1", "playlists": [
  {"id": 77, "name": "Afro pool", "type": "2", "parentId": 74}
]}
```

## 3. Pull the tracks

```
get_playlist_tracks(playlist_id=77)
```

Returns full track records in playlist order. Duplicate ids (which Lexicon can emit for folder playlists) are collapsed, and a track that no longer exists is skipped rather than failing the call.

The fields that matter for tagging decisions:

| Field | What it tells you |
|---|---|
| `title`, `artist`, `albumTitle` | Who and what |
| `genre` | Free text from the file's own metadata. Often messy (`"[Hip-Hop/Rap]"`, `"Amapiano, Dance"`) |
| `comment` | Often carries Mixed In Key output, e.g. `"8B - Energy 6"` |
| `bpm`, `key`, `energy`, `year` | The mechanical layer. `energy` may be 0 if never analysed |
| `tags` | Tag ids already applied. Empty list means untagged |

Full records are large (about 3 KB each, mostly cue points and source-specific blobs). Pull one playlist at a time.

## 4. Decide the tags

This is the LLM's job, not the server's. Read the tracks, reason about them, and produce a per-track list of tag ids. For example:

| Track | Reasoning | Tag ids |
|---|---|---|
| Track A | Afro house, 123 BPM, energy 8, comment says 8B | `[1, 55]` (Afro House, Peak Hour) |
| Track B | Mbira, 100 BPM, energy 2 | `[51, 52]` (Warm, Warmup) |

The server never suggests tags. It has no opinion about your taxonomy.

## 5. Write the tags

Per track, when each track gets its own set:

```
set_custom_tags(track_id=1849, tag_ids=[1, 55])
```

`set_custom_tags` has **replace** semantics: the list you pass becomes the track's complete tag set. To add a tag without disturbing existing ones, read the track first and pass the union. Pass `[]` to clear.

The response is the re-fetched track, so the confirmation is in the response rather than assumed:

```json
{"id": 1849, "title": "Track A", "tags": [1, 55], "...": "..."}
```

When many tracks get the *same* tag, use `bulk_apply_tags` instead. It has **merge** semantics and runs a count check before writing. See [bulk_tagging_recipe.md](./bulk_tagging_recipe.md).

## 6. Verify

```
get_track(track_id=1849)
```

Check `tags`. That is the whole loop.

## Things that will trip you up

- **Labels vs ids.** Every write takes ids. If you pass a label, the tool fails before touching anything.
- **Replace vs merge.** `set_custom_tags` replaces; `bulk_apply_tags` merges. Pick deliberately.
- **Untagged tracks cannot be searched for.** Lexicon's `tags=NONE` filter returns every track, so `search_tracks` refuses it. To find untagged tracks today, pull a playlist and filter on `tags == []` in the conversation.
