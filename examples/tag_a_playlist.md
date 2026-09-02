# Tag a playlist

**Goal:** apply custom tags to every track in one playlist. The LLM decides which tags fit; the tools do the plumbing.

This walkthrough was written from a real session against a ~40,000-track library. Tool calls are shown the way an MCP client sends them; responses are abridged and the library data is illustrative.

## 1. Learn the taxonomy

Tag tools accept labels or ids, but reading the taxonomy first tells you what exists and how it is spelled.

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

If the category you need does not exist yet, `create_tag_category(label="Undertow")` and `create_tag(category_id=..., label="deep")` add it. Lexicon keeps labels unique, so a duplicate comes back as its own error.

## 2. Find the playlist

```
list_playlists()
```

The response is a flat list, one row per node in Lexicon's order, with the folder path spelled out so you can scan by name:

```json
[
  {"id": 74, "name": "Crates", "path": "Crates", "kind": "folder", "parent_id": 2},
  {"id": 77, "name": "Afro pool", "path": "Crates / Afro pool", "kind": "playlist", "parent_id": 74}
]
```

There are no track counts. Pass `tree=True` if you want the raw nested tree instead.

## 3. Pull the tracks

```
get_playlist_tracks(playlist_id=77)
```

Returns compact track records in playlist order. Duplicate ids (which Lexicon can emit for folder playlists) are collapsed, and a track that no longer exists is skipped rather than failing the call. To see only the tracks still needing work, `list_untagged_tracks(playlist_id=77)` returns the same records filtered to those with no tags.

The fields that matter for tagging decisions:

| Field | What it tells you |
|---|---|
| `title`, `artist`, `albumTitle` | Who and what |
| `genre` | Free text from the file's own metadata. Often messy (`"[Hip-Hop/Rap]"`, `"Amapiano, Dance"`) |
| `comment` | Often carries Mixed In Key output, e.g. `"8B - Energy 6"` |
| `bpm`, `key`, `energy`, `year` | The mechanical layer. `energy` may be 0 if never analysed |
| `tags` | Tag ids already applied. Empty list means untagged |

Compact records are a few hundred bytes each. Pass `fields=[...]` to choose exactly which fields, or `full=True` for the complete records with cue points and source blobs (about 3 KB each).

## 4. Decide the tags

This is the LLM's job, not the server's. Read the tracks, reason about them, and produce a per-track list of tag ids. For example:

| Track | Reasoning | Tags |
|---|---|---|
| Track A | Afro house, 123 BPM, energy 8, comment says 8B | `["Genre/Afro House", "Timing/Peak Hour"]` |
| Track B | Mbira, 100 BPM, energy 2 | `["Mood/Warm", "Timing/Warmup"]` |

The server never suggests tags. It has no opinion about your taxonomy.

## 5. Write the tags

Per track, when each track gets its own set:

```
set_custom_tags(track_id=1849, tag_ids=["Genre/Afro House", "Timing/Peak Hour"])
```

Entries may be labels or ids. `"Category/Label"` is unambiguous; a bare `"Peak Hour"` also works because Lexicon keeps tag labels unique across the library. Labels are resolved against the live taxonomy before anything is written, and an unknown label is an error, not a silent skip.

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

- **Replace vs merge.** `set_custom_tags` replaces; `bulk_apply_tags` merges. Pick deliberately.
- **Case.** Labels match exactly first; `"warm"` still finds `"Warm"` when that is the only case-insensitive match, but an ambiguous match is an error that lists the candidates.
- **Untagged tracks cannot be searched for.** Lexicon's `tags=NONE` filter returns every track, so `search_tracks` refuses it. `list_untagged_tracks` does the scan instead.
