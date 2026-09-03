#!/usr/bin/env python3
"""M0 sanity check — run this before anything else, and again if the feed looks empty.

Proves three things:
  1. The Phase 1 database resolves to the same absolute path regardless of the
     working directory this script is launched from.
  2. That database has the expected schema and a plausible row count.
  3. Writes to it are refused by SQLite, not merely avoided by convention.

Usage:  python scripts/check_env.py
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api import config, source_db  # noqa: E402


def main() -> int:
    print("=" * 68)
    print("Phase 2 environment check")
    print("=" * 68)
    print(f"cwd                 : {Path.cwd()}")
    print(f"phase2 dir          : {config.PHASE2_DIR}")

    try:
        src = config.source_db_path()
    except RuntimeError as exc:
        print(f"\nFAIL: {exc}")
        return 1

    print(f"source database     : {src}")
    print(f"source size         : {src.stat().st_size:,} bytes")
    print(f"sidecar database    : {config.sidecar_db_path()}")
    print(f"LLM model           : {config.LLM_MODEL}")
    print(f"embedding model     : {config.EMBED_MODEL}")
    print(f"HF_TOKEN present    : {'yes' if config.HF_TOKEN else 'NO (chat/summary will fail)'}")

    conn = source_db.connect()
    try:
        source_db.assert_schema(conn)
        total = source_db.count_rows(conn)
        print(f"\nraw_items rows      : {total:,}")
        print("\nper source:")
        rows = conn.execute(
            """SELECT source_name, count(*) n,
                      sum(CASE WHEN raw_content IS NULL OR length(raw_content) < ?
                               THEN 1 ELSE 0 END) thin,
                      sum(CASE WHEN date_published IS NULL THEN 1 ELSE 0 END) undated
               FROM raw_items GROUP BY 1 ORDER BY n DESC""",
            (config.THIN_CONTENT_CHARS,),
        ).fetchall()
        for row in rows:
            print(
                f"  {row['source_name']:<22} {row['n']:>5} rows"
                f"   thin={row['thin']:<4} undated={row['undated']}"
            )

        # The write must be refused by SQLite itself.
        try:
            conn.execute("CREATE TABLE _phase2_write_probe (x)")
        except sqlite3.OperationalError as exc:
            print(f"\nread-only enforced  : yes ({exc})")
        else:
            print("\nFAIL: the source database accepted a write. Aborting.")
            return 1
    finally:
        conn.close()

    if total == 0:
        print("\nFAIL: source database has no rows — almost certainly the wrong file.")
        return 1

    print("\nOK — Phase 2 can read Phase 1 safely.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
