"""Enrich aeropoint_capture rows with latitude/longitude.

The flow is:

  1. Add latitude/longitude columns to aeropoint_capture (if not already there).
  2. Find every distinct (easting, northing) that doesn't have lat/lng yet.
  3. For each one, ask the converter, then UPDATE every row sharing that
     coordinate (one API call, many row updates).
  4. Commit in batches so a mid-run failure leaves real progress on disk.

Re-running the script picks up where the last run left off because step 2
only returns rows where latitude or longitude is still NULL.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass

from .converters import Converter, HTTPConverter
from .db import ensure_latlng_columns, pending_coords, update_coord

log = logging.getLogger(__name__)


@dataclass
class EnrichResult:
    coords_processed: int
    captures_updated: int
    coords_failed: int


def enrich(conn: sqlite3.Connection, converter: Converter,
           batch_commit: int = 50) -> EnrichResult:
    ensure_latlng_columns(conn)
    pending = pending_coords(conn)
    if not pending:
        log.info("nothing to enrich, every capture already has lat/lng")
        return EnrichResult(0, 0, 0)

    log.info("converting %d unique coordinate pairs", len(pending))
    processed = 0
    updated_rows = 0
    failed = 0

    for easting, northing in pending:
        try:
            ll = converter.convert(easting, northing)
        except Exception as e:
            log.error("conversion failed for easting=%s northing=%s: %s",
                      easting, northing, e)
            failed += 1
            continue
        rowcount = update_coord(conn, easting, northing,
                                ll.latitude, ll.longitude)
        processed += 1
        updated_rows += rowcount
        if processed % batch_commit == 0:
            conn.commit()
            log.info("committed %d/%d coordinate pairs", processed, len(pending))
        # Polite spacing for HTTP-backed converters.
        if isinstance(converter, HTTPConverter):
            converter.throttle()

    conn.commit()
    log.info("done: %d coordinates -> %d rows updated (%d failed)",
             processed, updated_rows, failed)
    return EnrichResult(processed, updated_rows, failed)
