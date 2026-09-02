# Generate a set

**Goal:** assemble a tracklist along an energy arc from your own library, then save the candidate pool as a Lexicon smartlist.

There is no `generate_set` tool in v0.1. The LLM composes `search_tracks` calls, reasons about the results, and orders the set. This is deliberate: the server does plumbing, the LLM does taste.

## Before you search: know your library's notation

Lexicon stores keys in **Open Key** notation: `1D` is a major key, `6M` is minor. Its key filter understands Camelot equivalents, so `"key": "1M"` also matches tracks stored as `8A`. Mixed In Key, if you use it, writes Camelot plus energy into the `comment` field (`"8B - Energy 6"`).

Two other facts shape every query:

- Tracks that were never analysed carry `bpm: 0` and `energy: 0`. A `"bpm": "<=124"` filter sweeps them in. Use a range with a real lower bound instead.
- `energy` is only populated where analysis (Lexicon or Mixed In Key) ran. In the library this was written against, that was a third of tracks.

## Filter syntax that works

| Want | Filter |
|---|---|
| Text contains (case-insensitive) | `{"artist": "chiweshe"}` |
| At least / at most | `{"bpm": ">=120"}`, `{"energy": "<=4"}` |
| Inclusive range | `{"bpm": "118-124"}`, `{"energy": "5-7"}`, `{"year": "1990-1999"}` |
| Several conditions (AND) | `{"bpm": "118-124", "key": "6M", "energy": ">=6"}` |

Two comparisons in one string (`">=118 <=124"`) match nothing, silently. Use the range form.

## 1. Build the pools

One search per segment of the arc. Ask for only the fields you need and sort so the interesting end comes first.

Warm-up, low energy, around 100 to 112 BPM:

```
search_tracks(
  filter={"bpm": "100-112", "energy": "2-4"},
  fields=["id", "title", "artist", "bpm", "key", "energy", "genre"],
  sort=[{"field": "energy", "dir": "asc"}],
  limit=30
)
```

Build, mid energy, harmonically near the warm-up's landing key:

```
search_tracks(
  filter={"bpm": "112-120", "energy": "5-6", "key": "6M"},
  fields=["id", "title", "artist", "bpm", "key", "energy", "genre"],
  sort=[{"field": "bpm", "dir": "asc"}],
  limit=30
)
```

Peak:

```
search_tracks(
  filter={"bpm": "120-126", "energy": ">=7"},
  fields=["id", "title", "artist", "bpm", "key", "energy", "genre"],
  sort=[{"field": "energy", "dir": "desc"}],
  limit=30
)
```

Each response looks like:

```json
{"total": 282, "returned": 30, "tracks": [
  {"id": 803, "title": "...", "artist": "...", "bpm": 120, "key": "6M", "energy": 7, "genre": ""},
  "..."
]}
```

`total` is the true match count; `returned` is what came back after `limit`. If `total` is over 1000, Lexicon itself capped the result set and you should narrow the filter.

## 2. Order the set

The LLM's job. With three pools in hand, pick tracks, sequence them for key compatibility and energy flow, and check durations add up. Nothing in the server does this.

## 3. Save the pool as a smartlist

Optional, but useful: a smartlist is live, so it keeps picking up new tracks that match.

```
create_smartlist(
  name="Warm-up pool 100-112",
  rules=[
    {"field": "bpm", "operator": "NumberBetween", "values": [100, 112]},
    {"field": "energy", "operator": "NumberBetween", "values": [2, 4]}
  ],
  match_all=True
)
```

`match_all=True` means every rule must hold (AND); `False` is any rule (OR). The tool plumbs the rules through unchanged and returns the created smartlist with its resolved `trackIds`.

The operator vocabulary is Lexicon's, not this server's. From Lexicon's API spec (as captured by the upstream `lexicon-python` project):

| Field type | Operators |
|---|---|
| Number | `NumberEquals`, `NumberNotEquals`, `NumberGreaterThan`, `NumberGreaterThanEquals`, `NumberLessThan`, `NumberLessThanEquals`, `NumberBetween` (values `[low, high]`) |
| String | `StringEquals`, `StringNotEquals`, `StringContains`, `StringNotContains`, `StringStartsWith`, `StringNotStartsWith`, `StringEndsWith`, `StringNotEndsWith`, `StringRegExpMatch`, `StringNotRegExpMatch` |
| Date | `DateEquals`, `DateNotEquals`, `DateBefore`, `DateAfter`, `DateBetween`, `DateRecent`, `DateNotRecent` (values like `[1, "months"]`) |
| Key | `KeySimilar` (harmonic neighbours of a key) |

Each rule may also carry `"or": false`; Lexicon's own example includes it. Only `NumberEquals`, `NumberGreaterThan`, and `DateRecent` have been seen live in this project's stock smartlists; the rest come from the spec.

Creation is one-way in v0.1. There is no delete tool, so remove experiments in Lexicon itself.

## What is missing, honestly

- No `find_similar_tracks` yet. Approximate it with a key-and-BPM-window search around a seed track.
- No duration-aware assembly. The LLM adds up `duration` (seconds) by hand.
- Energy coverage depends on your analysis history. If most tracks read `energy: 0`, run analysis in Lexicon first.
