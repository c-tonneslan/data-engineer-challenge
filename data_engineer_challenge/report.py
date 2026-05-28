"""Build the 'AeroPoint groups used in London' CSV report.

The brief is careful about the difference between *filtering* groups
(a group qualifies if it has at least one capture inside London) and
*counting* per group (counts are across all locations, not just London).
That distinction lives in the SQL: ``london_groups`` is the qualifier set,
the per-group totals come from independent aggregations over the full
tables, then we LEFT JOIN them in.
"""

from __future__ import annotations

import csv
import logging
import sqlite3
from dataclasses import dataclass
from typing import Sequence

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class BoundingBox:
    north: float
    south: float
    west: float
    east: float

    def __post_init__(self) -> None:
        if self.north <= self.south:
            raise ValueError(
                f"bounding box north ({self.north}) must be greater than "
                f"south ({self.south})"
            )
        if self.east <= self.west:
            raise ValueError(
                f"bounding box east ({self.east}) must be greater than "
                f"west ({self.west})"
            )


# Bounding box from the brief.
LONDON = BoundingBox(north=51.6919, south=51.2868, west=-0.5104, east=0.3340)


REPORT_SQL = """
WITH london_groups AS (
    SELECT DISTINCT ap.aeropoint_group_id AS group_id
    FROM aeropoint ap
    JOIN aeropoint_capture c ON c.aeropoint_id = ap.id
    WHERE c.latitude  IS NOT NULL
      AND c.longitude IS NOT NULL
      AND c.latitude  BETWEEN :south AND :north
      AND c.longitude BETWEEN :west  AND :east
),
group_points AS (
    SELECT aeropoint_group_id AS group_id, COUNT(*) AS points
    FROM aeropoint
    GROUP BY aeropoint_group_id
),
group_captures AS (
    SELECT ap.aeropoint_group_id AS group_id, COUNT(*) AS captures
    FROM aeropoint_capture c
    JOIN aeropoint ap ON ap.id = c.aeropoint_id
    GROUP BY ap.aeropoint_group_id
)
SELECT g.name                       AS "Group Name",
       COALESCE(gp.points,   0)     AS "AeroPoints",
       COALESCE(gc.captures, 0)     AS "Captures"
FROM        aeropoint_group g
JOIN        london_groups   lg ON lg.group_id = g.id
LEFT JOIN   group_points    gp ON gp.group_id = g.id
LEFT JOIN   group_captures  gc ON gc.group_id = g.id
ORDER BY g.name;
"""

CSV_HEADER = ("Group Name", "AeroPoints", "Captures")


def query_rows(conn: sqlite3.Connection,
               box: BoundingBox = LONDON) -> list[tuple[str, int, int]]:
    rows = conn.execute(REPORT_SQL, {
        "north": box.north,
        "south": box.south,
        "west":  box.west,
        "east":  box.east,
    }).fetchall()
    return [(str(name), int(points), int(captures))
            for name, points, captures in rows]


def write_csv(path: str, rows: Sequence[tuple[str, int, int]]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(CSV_HEADER)
        w.writerows(rows)


def generate(conn: sqlite3.Connection, output_path: str,
             box: BoundingBox = LONDON) -> int:
    rows = query_rows(conn, box)
    write_csv(output_path, rows)
    log.info("wrote %d row(s) to %s", len(rows), output_path)
    return len(rows)
