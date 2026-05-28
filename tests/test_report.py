"""Report query tests: London box filter + per-group totals."""

from __future__ import annotations

import csv
import os
import tempfile

import pytest

from data_engineer_challenge.converters import LatLng
from data_engineer_challenge.enrich import enrich
from data_engineer_challenge.report import LONDON, BoundingBox, generate, query_rows


class FakeConverter:
    """Maps the seeded fixtures into deterministic lat/lng that we know fall
    in or out of the London box per the fixture's design.
    """

    # Tower Bridge / central London
    LONDON_1 = (51.505, -0.075)
    LONDON_2 = (51.510, -0.072)
    LONDON_3 = (51.499, -0.080)
    # Edinburgh / outside
    EDINBURGH = (55.95, -3.20)
    # Midlands / outside
    MIDLANDS = (52.5, -1.5)
    # Scottish borders / outside
    BORDERS = (55.3, -2.8)

    _MAP = {
        (533630, 180220): LONDON_1,
        (533700, 180300): LONDON_2,
        (530000, 180000): LONDON_3,
        (325000, 673500): EDINBURGH,
        (400000, 400000): MIDLANDS,
        (350000, 600000): BORDERS,
    }

    def convert(self, easting, northing):
        lat, lng = self._MAP[(easting, northing)]
        return LatLng(latitude=lat, longitude=lng)


def test_report_includes_only_groups_with_at_least_one_london_capture(seeded_conn):
    enrich(seeded_conn, FakeConverter())
    rows = query_rows(seeded_conn)
    names = {r[0] for r in rows}
    # London Bridge (all London) -> in
    # Edinburgh (all outside) -> out
    # Mixed (one London, rest outside) -> in
    # Empty (no captures at all) -> out
    assert names == {"London Bridge", "Mixed"}


def test_report_counts_are_unrestricted_by_box(seeded_conn):
    enrich(seeded_conn, FakeConverter())
    rows = {r[0]: (r[1], r[2]) for r in query_rows(seeded_conn)}
    # London Bridge: 2 points, 3 captures (all in London but the brief says
    # counts are not box-restricted, so this is the same answer either way).
    assert rows["London Bridge"] == (2, 3)
    # Mixed: 2 points total, 4 captures total (only one of which is in London,
    # but the count is across all captures).
    assert rows["Mixed"] == (2, 4)


def test_report_excludes_groups_with_no_captures(seeded_conn):
    enrich(seeded_conn, FakeConverter())
    rows = query_rows(seeded_conn)
    assert "Empty" not in {r[0] for r in rows}


def test_report_skips_captures_with_null_latlng(seeded_conn):
    # Skip enrichment entirely -> every capture's lat/lng is NULL.
    from data_engineer_challenge.db import ensure_latlng_columns
    ensure_latlng_columns(seeded_conn)
    rows = query_rows(seeded_conn)
    assert rows == []


def test_generate_writes_csv_with_header(seeded_conn, tmp_path):
    enrich(seeded_conn, FakeConverter())
    out = tmp_path / "out.csv"
    n = generate(seeded_conn, str(out))
    assert n == 2
    with open(out, newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)
    assert rows[0] == ["Group Name", "AeroPoints", "Captures"]
    assert len(rows) == 3  # header + 2 data rows


def test_bounding_box_rejects_inverted_bounds():
    with pytest.raises(ValueError):
        BoundingBox(north=51.0, south=52.0, west=-1.0, east=1.0)
    with pytest.raises(ValueError):
        BoundingBox(north=52.0, south=51.0, west=1.0, east=-1.0)


def test_london_box_matches_brief():
    assert LONDON.north == 51.6919
    assert LONDON.south == 51.2868
    assert LONDON.west == -0.5104
    assert LONDON.east == 0.3340
