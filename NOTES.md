# Design notes

A walk through the decisions I'd defend in the "talk us through your thinking" part of the interview.

## Where the lat/lng data lives

I extended `aeropoint_capture` with nullable `latitude` and `longitude` columns. The other options I weighed:

- **Separate cache table** keyed on `(easting, northing)`. Cleaner separation, and you only convert each coord once even across runs. But every reporting query then needs a join, and the table never gets pruned. Worth doing in a real warehouse, overkill for one report.
- **A view** that does the conversion at query time. Can't, because the conversion is not expressible in SQLite SQL.
- **External lookup file** (parquet, etc.). Same as the cache table, but with extra I/O concerns. Not a fit for a one-shot script.

Adding columns to the same row keeps the writes idempotent (re-running `enrich_data.py` is safe), makes the report a single query, and the schema migration is a two-line `ALTER TABLE` guarded by `PRAGMA table_info`.

## Dedup before converting

There are 389 captures in the fixture and they all share `(easting, northing)` pairs across multiple captures. The script does a `SELECT DISTINCT easting, northing` first, calls the converter once per unique pair, then `UPDATE`s every row sharing that coord. In the bundled DB that cuts the work in roughly half. For a real Propeller dataset where one AeroPoint sits still and uploads its location every few minutes, the savings would be far bigger.

## Why pyproj is the default and not the API

The brief points to https://www.getthedata.com/bng2latlong as the conversion endpoint. Today that host serves Cloudflare's "Just a moment..." JS challenge to every non-browser client, so a plain `requests.get` returns HTML and `.json()` blows up. It's possible the API still works from inside Propeller's network (allowlisted by CF), but it's a flaky thing to put a scheduled job behind.

`pyproj` is the right tool anyway:

- Deterministic, no rate limit, no third-party uptime dependency.
- Uses the published EPSG:27700 → EPSG:4326 transformation. Same accuracy as the API for our purposes (a bounding-box test).
- Plays nicely if Propeller ever needs to handle other projected coordinate systems (the README hints they do), because pyproj already supports the full EPSG catalogue.

The HTTP client is still in `data_engineer_challenge/converters.py` and `enrich_data.py --converter http` wires it up. If the API ever ships an unprotected endpoint, swapping is a one-flag change. The two converters share a `Converter` Protocol so the rest of the pipeline can't tell them apart.

## SQL shape for the report

```sql
WITH london_groups AS (...)        -- filter set
, group_points    AS (...)         -- per-group totals, no box restriction
, group_captures  AS (...)
SELECT g.name, COALESCE(gp.points, 0), COALESCE(gc.captures, 0)
FROM aeropoint_group g
JOIN london_groups   lg ON lg.group_id = g.id   -- inner join filters
LEFT JOIN group_points    gp ON gp.group_id = g.id
LEFT JOIN group_captures  gc ON gc.group_id = g.id
```

The brief is explicit that the "used at least once in London" condition only filters which groups appear, and that the AeroPoint and capture counts are across all locations. Doing the count and the filter in the same scan would double-restrict. Three CTEs is the clearest way to keep them honest.

## Things I'd add for actual production

This is a one-shot script, so I stopped here. In a real pipeline you'd want:

- A coordinate cache table so re-enrichments don't even hit pyproj.
- Retry/backoff metrics surfaced to whatever scheduler runs it (the HTTP path has it locally; the pyproj path doesn't fail).
- A structured log handler (JSON for ingest into the warehouse audit table).
- Schema migrations in a real migration tool (alembic, sqitch) rather than the inline `PRAGMA table_info` check.

## Schema nit

The brief mentions tables called `aeropoint_groups` and `aeropoints`, but in the actual `challenge.db` they're singular (`aeropoint_group`, `aeropoint`). I went with the real schema. Worth a heads-up to whoever owns the brief.

## Bounding box gotcha

The brief gives the box as NW (51.6919, -0.5104) and SE (51.2868, 0.3340). Latitude decreases going south, so the "north" value is the larger of the two. I baked the validation into `BoundingBox.__post_init__` so a swap would fail loudly rather than silently returning zero rows.
