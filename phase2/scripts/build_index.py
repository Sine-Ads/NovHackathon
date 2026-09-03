#!/usr/bin/env python3
"""Build the Phase 2 search index from the Phase 1 corpus.

Reads ``raw_items`` read-only, writes chunks, FTS5 rows, embeddings and the
landscape statistics into the sidecar database. The Phase 1 file is never
touched.

Idempotent: a content hash per item means a re-run after a fresh ingest
re-embeds only what actually changed. Running it twice in a row embeds nothing
the second time.

Usage:
    python scripts/build_index.py              # incremental
    python scripts/build_index.py --rebuild    # drop and rebuild everything
    python scripts/build_index.py --skip-embeddings
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api import chunker, config, landscape, source_db, store  # noqa: E402

EMBED_BATCH = 64


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Phase 2 index")
    parser.add_argument("--rebuild", action="store_true", help="drop the index first")
    parser.add_argument("--skip-embeddings", action="store_true")
    args = parser.parse_args()

    started = time.time()
    src = source_db.connect()
    side = store.connect()

    try:
        source_db.assert_schema(src)
        if args.rebuild:
            print("Dropping existing index...")
            store.drop_all(side)

        known = store.existing_hashes(side)
        seen: set[str] = set()
        inserted = updated = unchanged = 0

        print(f"Reading {config.source_db_path()}")
        for item in source_db.iter_items(src):
            seen.add(item.item_id)
            digest = chunker.content_hash(item)
            previous = known.get(item.item_id)

            if previous == digest:
                unchanged += 1
                continue

            store.upsert_item(
                side,
                item_id=item.item_id,
                source_name=item.source_name,
                source_id=item.source_id,
                source_url=item.source_url,
                title=item.title,
                date_published=item.date_published,
                date_ingested=item.date_ingested,
                metadata_json=json.dumps(item.metadata),
                n_chars=len(item.raw_content or ""),
                is_thin=int(
                    len(item.raw_content or "") < config.THIN_CONTENT_CHARS
                    or item.source_name == "SEC EDGAR"
                ),
                date_class=item.date_class,
                content_hash=digest,
            )
            store.replace_chunks(side, item.item_id, item.title, chunker.chunk_item(item))
            # A changed body invalidates any cached summary of it.
            side.execute("DELETE FROM summary_cache WHERE item_id = ?", (item.item_id,))
            side.execute("DELETE FROM embedding WHERE item_id = ?", (item.item_id,))

            if previous is None:
                inserted += 1
            else:
                updated += 1

        removed = store.delete_items(side, set(known) - seen)
        side.commit()

        print(
            f"Items: {inserted} inserted, {updated} updated, "
            f"{unchanged} unchanged, {removed} removed"
        )

        embedded = 0
        if not args.skip_embeddings:
            from api import embed

            pending = store.chunks_missing_embeddings(side, config.EMBED_MODEL)
            if pending:
                print(f"Embedding {len(pending)} chunks with {config.EMBED_MODEL}...")
                for start in range(0, len(pending), EMBED_BATCH):
                    batch = pending[start : start + EMBED_BATCH]
                    vectors = embed.embed_passages([r["text"] for r in batch])
                    store.store_embeddings(
                        side,
                        [
                            (
                                row["chunk_id"],
                                row["item_id"],
                                config.EMBED_MODEL,
                                vectors.shape[1],
                                vectors[i].tobytes(),
                            )
                            for i, row in enumerate(batch)
                        ],
                    )
                    side.commit()
                    embedded += len(batch)
                    print(f"  {embedded}/{len(pending)}", end="\r", flush=True)
                print()
            else:
                print("Embeddings: nothing to do")

        print("Computing landscape statistics...")
        store.put_landscape(side, landscape.compute(src))

        stats = store.index_stats(side)
        print("\nIndex:")
        for key, value in stats.items():
            print(f"  {key:<18} {value}")
        print(f"\nDone in {time.time() - started:.1f}s")

        if stats["items"] and stats["embeddings"] < stats["chunks"]:
            print(
                f"WARNING: {stats['chunks'] - stats['embeddings']} chunks have no "
                "embedding — semantic search will be partial."
            )
        return 0
    finally:
        src.close()
        side.close()


if __name__ == "__main__":
    raise SystemExit(main())
