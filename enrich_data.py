"""CLI wrapper around data_engineer_challenge.enrich.

    # default: local pyproj conversion (recommended)
    python enrich_data.py

    # use the HTTP API the brief suggests (note: Cloudflare-protected today)
    python enrich_data.py --converter http
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys

from data_engineer_challenge.converters import (
    Converter, HTTPConverter, PyProjConverter,
)
from data_engineer_challenge.enrich import enrich


def build_converter(name: str) -> Converter:
    if name == "pyproj":
        return PyProjConverter()
    if name == "http":
        return HTTPConverter()
    raise ValueError(f"unknown converter: {name!r}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default="challenge.db",
                   help="path to the SQLite database (default: challenge.db)")
    p.add_argument("--converter", choices=["pyproj", "http"], default="pyproj",
                   help="how to convert BNG -> WGS84 (default: pyproj)")
    p.add_argument("--batch-commit", type=int, default=50,
                   help="commit every N coordinates (default: 50)")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("enrich_data")

    try:
        converter = build_converter(args.converter)
    except Exception as e:
        log.error("could not build converter: %s", e)
        return 2

    conn = sqlite3.connect(args.db)
    try:
        result = enrich(conn, converter, batch_commit=args.batch_commit)
    except Exception as e:
        log.error("enrichment aborted: %s", e)
        return 1
    finally:
        conn.close()

    if result.coords_failed > 0:
        log.warning("%d coordinate(s) could not be converted; re-run when "
                    "the converter is healthy", result.coords_failed)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
