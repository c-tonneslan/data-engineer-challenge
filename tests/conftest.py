"""Shared test fixtures: build a tiny challenge.db from scratch in memory."""

from __future__ import annotations

import sqlite3
from typing import Iterable

import pytest

SCHEMA = """
CREATE TABLE aeropoint_group (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE aeropoint (
    id                  INTEGER PRIMARY KEY,
    aeropoint_group_id  INTEGER,
    FOREIGN KEY (aeropoint_group_id) REFERENCES aeropoint_group(id)
);
CREATE TABLE aeropoint_capture (
    id            INTEGER PRIMARY KEY,
    aeropoint_id  INTEGER,
    easting       INTEGER,
    northing      INTEGER,
    FOREIGN KEY (aeropoint_id) REFERENCES aeropoint(id)
);
"""


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    return conn


def _seed(conn: sqlite3.Connection,
          groups: Iterable[tuple[int, str]],
          points: Iterable[tuple[int, int]],
          captures: Iterable[tuple[int, int, int, int]]) -> None:
    conn.executemany("INSERT INTO aeropoint_group (id, name) VALUES (?, ?)", groups)
    conn.executemany("INSERT INTO aeropoint (id, aeropoint_group_id) VALUES (?, ?)", points)
    conn.executemany(
        "INSERT INTO aeropoint_capture (id, aeropoint_id, easting, northing) "
        "VALUES (?, ?, ?, ?)", captures,
    )
    conn.commit()


@pytest.fixture
def empty_conn():
    conn = _make_conn()
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def seeded_conn():
    """A small fixture covering London + non-London + repeated coords.

    Group 1 (London Bridge area): 2 points, 3 captures, all inside London.
    Group 2 (Edinburgh): 1 point, 2 captures, both outside London.
    Group 3 (mixed): 2 points, 4 captures, one inside London, three outside.
    Group 4 (no captures): present in the table but never captured.
    """
    conn = _make_conn()
    _seed(
        conn,
        groups=[
            (1, "London Bridge"),
            (2, "Edinburgh"),
            (3, "Mixed"),
            (4, "Empty"),
        ],
        points=[
            (1, 1), (2, 1),       # group 1: 2 points
            (3, 2),               # group 2: 1 point
            (4, 3), (5, 3),       # group 3: 2 points
        ],
        captures=[
            # Tower Bridge area, BNG ~533630, 180220 -> ~51.505, -0.075
            (1, 1, 533630, 180220),
            (2, 1, 533630, 180220),  # duplicate coord (dedup target)
            (3, 2, 533700, 180300),  # also in London, different point
            # Edinburgh-ish: ~325000, 673500 -> ~55.95, -3.20 (outside London)
            (4, 3, 325000, 673500),
            (5, 3, 325000, 673500),  # duplicate
            # Group 3: one London capture, three non-London
            (6, 4, 530000, 180000),  # London
            (7, 5, 400000, 400000),  # somewhere in the Midlands
            (8, 5, 400000, 400000),  # duplicate
            (9, 5, 350000, 600000),  # Scottish borders
        ],
    )
    try:
        yield conn
    finally:
        conn.close()
