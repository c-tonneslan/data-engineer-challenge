"""CLI wrapper around data_engineer_challenge.report.

    python generate_report.py
    python generate_report.py --output london_groups.csv
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys

from data_engineer_challenge.db import missing_count
from data_engineer_challenge.report import generate


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default="challenge.db",
                   help="path to the SQLite database (default: challenge.db)")
    p.add_argument("--output", default="london_aeropoint_groups.csv",
                   help="output CSV path (default: london_aeropoint_groups.csv)")
    p.add_argument("--strict", action="store_true",
                   help="fail if any captures still lack lat/lng "
                        "(default: warn and continue)")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("generate_report")

    conn = sqlite3.connect(args.db)
    try:
        missing = missing_count(conn)
        if missing:
            msg = (f"{missing} capture(s) still missing lat/lng; "
                   "run enrich_data.py first to fill them in")
            if args.strict:
                log.error(msg)
                return 1
            log.warning(msg)
        generate(conn, args.output)
    except Exception as e:
        log.error("report generation failed: %s", e)
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
