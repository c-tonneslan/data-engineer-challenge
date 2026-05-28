"""End-to-end enrich tests using a fake converter so we don't hit the network."""

from __future__ import annotations

from data_engineer_challenge.converters import LatLng
from data_engineer_challenge.db import missing_count
from data_engineer_challenge.enrich import enrich


class FakeConverter:
    """Deterministic converter for tests.

    Tags each coordinate with a unique lat/lng so we can verify each one
    landed in the right rows.
    """

    def __init__(self, fail_on=None):
        self.calls = []
        self._fail_on = set(fail_on or [])

    def convert(self, easting, northing):
        self.calls.append((easting, northing))
        if (easting, northing) in self._fail_on:
            raise RuntimeError(f"forced failure for {easting},{northing}")
        # Map easting/northing into a deterministic small lat/lng we can spot.
        return LatLng(latitude=easting / 1_000_000, longitude=northing / 1_000_000)


def test_enrich_fills_every_capture(seeded_conn):
    fc = FakeConverter()
    result = enrich(seeded_conn, fc)
    assert result.coords_processed == 6
    assert result.coords_failed == 0
    assert result.captures_updated == 9
    assert missing_count(seeded_conn) == 0


def test_enrich_calls_converter_once_per_unique_coord(seeded_conn):
    fc = FakeConverter()
    enrich(seeded_conn, fc)
    # 9 captures, 6 unique pairs -> 6 API calls
    assert len(fc.calls) == 6
    assert len(set(fc.calls)) == 6


def test_enrich_is_idempotent(seeded_conn):
    fc1 = FakeConverter()
    enrich(seeded_conn, fc1)
    fc2 = FakeConverter()
    result2 = enrich(seeded_conn, fc2)
    # Second run finds nothing to do.
    assert result2.coords_processed == 0
    assert len(fc2.calls) == 0


def test_enrich_continues_past_failed_coords(seeded_conn):
    fc = FakeConverter(fail_on=[(325000, 673500)])
    result = enrich(seeded_conn, fc)
    # 6 unique pairs, one fails, 5 succeed
    assert result.coords_processed == 5
    assert result.coords_failed == 1
    # The two captures sharing (325000, 673500) remain null
    assert missing_count(seeded_conn) == 2
