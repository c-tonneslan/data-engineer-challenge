"""SQLite helpers: schema migration + pending coordinate query."""

from __future__ import annotations

import sqlite3
from typing import Iterable


def ensure_latlng_columns(conn: sqlite3.Connection) -> bool:
    """Add latitude/longitude columns to aeropoint_capture if missing.

    Returns True if the schema was modified, False if it was already current.
    Safe to call repeatedly; this is what makes the enrich script idempotent.
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(aeropoint_capture)")}
    altered = False
    if "latitude" not in cols:
        conn.execute("ALTER TABLE aeropoint_capture ADD COLUMN latitude REAL")
        altered = True
    if "longitude" not in cols:
        conn.execute("ALTER TABLE aeropoint_capture ADD COLUMN longitude REAL")
        altered = True
    if altered:
        conn.commit()
    return altered


def pending_coords(conn: sqlite3.Connection) -> list[tuple[int, int]]:
    """Distinct (easting, northing) pairs that still need a lat/lng.

    Dedups at the SQL layer so we hit the converter once per unique pair, even
    if many captures share coordinates.
    """
    rows = conn.execute(
        "SELECT DISTINCT easting, northing FROM aeropoint_capture "
        "WHERE latitude IS NULL OR longitude IS NULL"
    ).fetchall()
    return [(int(e), int(n)) for e, n in rows]


def update_coord(conn: sqlite3.Connection, easting: int, northing: int,
                 latitude: float, longitude: float) -> int:
    """Write a converted lat/lng to every capture row sharing this coordinate."""
    cur = conn.execute(
        "UPDATE aeropoint_capture SET latitude=?, longitude=? "
        "WHERE easting=? AND northing=?",
        (latitude, longitude, easting, northing),
    )
    return cur.rowcount


def missing_count(conn: sqlite3.Connection) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM aeropoint_capture "
        "WHERE latitude IS NULL OR longitude IS NULL"
    ).fetchone()[0]
