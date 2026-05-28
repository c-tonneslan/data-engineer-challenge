"""Schema management + pending-coords dedup tests."""

from __future__ import annotations

from data_engineer_challenge.db import (
    ensure_latlng_columns, missing_count, pending_coords, update_coord,
)


def _column_names(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def test_ensure_latlng_columns_adds_them(empty_conn):
    assert "latitude" not in _column_names(empty_conn, "aeropoint_capture")
    changed = ensure_latlng_columns(empty_conn)
    assert changed is True
    cols = _column_names(empty_conn, "aeropoint_capture")
    assert "latitude" in cols
    assert "longitude" in cols


def test_ensure_latlng_columns_is_idempotent(empty_conn):
    ensure_latlng_columns(empty_conn)
    changed = ensure_latlng_columns(empty_conn)
    assert changed is False


def test_pending_coords_dedups_repeated_pairs(seeded_conn):
    ensure_latlng_columns(seeded_conn)
    pending = pending_coords(seeded_conn)
    # 9 captures but only 6 distinct (easting, northing) pairs in the fixture
    assert len(pending) == 6
    assert (533630, 180220) in pending
    assert (325000, 673500) in pending


def test_pending_coords_skips_already_filled(seeded_conn):
    ensure_latlng_columns(seeded_conn)
    update_coord(seeded_conn, 533630, 180220, 51.505, -0.075)
    seeded_conn.commit()
    pending = pending_coords(seeded_conn)
    assert (533630, 180220) not in pending
    # Both rows that had that coord should be filled in.
    assert missing_count(seeded_conn) == 7
