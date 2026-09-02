# Bulk tagging recipe

**Goal:** apply the same tag or tags to every track that matches a search, without ever writing to the wrong set.

The Lexicon API has quirks where a bad filter silently returns the *entire* library instead of erroring. Chained into a bulk write, that would tag 40,000 tracks by accident. `bulk_apply_tags` exists to make that impossible. This recipe shows the safe pattern and what each refusal looks like.

## The pattern: search, count, write

**1. Search with only the fields you need.**

```
search_tracks(
  filter={"genre": "amapiano"},
  fields=["id", "title", "artist"],
  limit=None
)
```

```json
{"total": 100, "returned": 100, "tracks": [{"id": 449, "...": "..."}, "..."]}
```

**2. Read `total` and decide.**

- If `total` is what you expected, collect the ids.
- If `total` is in the thousands for a filter you thought was narrow, the filter probably did not apply. Stop and check it.
- If `total` is over 1000, Lexicon capped the result set; `returned` will be 1000 at most. Narrow the filter and run it in slices.

**3. Write, asserting the count.**

```
bulk_apply_tags(
  track_ids=[449, 489, 832, "..."],
  tag_ids=["Genre/Afro House"],
  expected_count=100
)
```

`tag_ids` takes labels or ids; labels are resolved against the live taxonomy once, before any write.

`expected_count` is the count-before-bulk-write check: if the deduplicated id list is not exactly that long, nothing is written.

```json
{"requested": 100, "updated": 97, "unchanged": 3, "failed": 0,
 "results": [{"track_id": 449, "status": "updated", "tags": [1]}, "..."]}
```

`bulk_apply_tags` has **merge** semantics. For each track it reads the current tags and writes back the union, so nothing already applied is lost. Tracks that already carry every requested tag are reported `unchanged` and not written.

## The refusals, verbatim

Each of these fires before any write.

**Empty filter, or a field the API silently ignores.**

```
search_tracks(filter={})
```

> Empty search filter would match the entire library. Provide at least one concrete filter (e.g. {'artist': 'Daft Punk'}).

Fields on the silently-ignored list (`id`, `type`, `locationUnique`, `archived`, `fingerprint`, and others) get a similar refusal naming the field.

**The untagged-tracks trap.**

```
search_tracks(filter={"tags": "NONE"})
```

> tags=NONE returns ALL tracks (not untagged ones) on the Lexicon API. The 'find untagged tracks' filter is not supported server-side.

**Count mismatch.**

```
bulk_apply_tags(track_ids=[841, 803, 890], tag_ids=[1], expected_count=2)
```

> Bulk write count mismatch: caller expected 2 tracks but the target set has 3. Aborting rather than writing the wrong set.

**Over the ceiling.**

```
bulk_apply_tags(track_ids=[...1533 ids...], tag_ids=[1])
```

> Bulk write targets 1533 tracks, over the safety ceiling of 500. This often means a search silently returned the whole library. Narrow the set or raise the ceiling explicitly if this is intended.

The ceiling defaults to 500. Raise it with `ceiling=` only when you have looked at `total` and mean it.

## Slicing a large job

For a tag that legitimately applies to thousands of tracks, slice by a second field so each slice is under the ceiling and under Lexicon's 1000-record cap:

```
search_tracks(filter={"genre": "house", "bpm": "120-124"}, fields=["id"], limit=None)
search_tracks(filter={"genre": "house", "bpm": "125-128"}, fields=["id"], limit=None)
...
```

Then one `bulk_apply_tags` per slice, each with its own `expected_count`. Merge semantics make re-running a slice harmless: tracks already tagged come back `unchanged`.

## Failure inside a batch

A track that errors on its own (deleted between search and write, for instance) is reported as `failed` in `results` and the batch continues. A connection error aborts the whole batch. Either way, the summary tells you exactly which tracks were written.

## What this recipe cannot do yet

- **Remove a tag in bulk.** `bulk_apply_tags` only adds. To remove, use `set_custom_tags` per track with the reduced list.

To find what still needs tagging, `list_untagged_tracks(playlist_id=...)` for one crate, or `list_untagged_tracks(limit=100, offset=0)` to page through the whole library's untagged subset with a true total.
