# Frontend Integration Notes

## Current data flow

1. Ingestors write source records to `raw_items`.
2. `main.py` reads active records from `raw_items`.
3. Records are validated and classified by the rules layer or Llama.
4. The latest result is upserted into `classifications`.

Running the classifier again updates the existing classification for a paper;
it does not create duplicates.

## Classification schema

The `classifications` table has one row per `raw_items.id`:

| Field | Meaning |
| --- | --- |
| `raw_item_id` | Foreign key to the source paper in `raw_items` |
| `category` | `proven_right`, `proven_false`, `proven_false_but_useful`, or `still_working_on`; null when failed |
| `justification` | LLM explanation; null for rule results |
| `method` | `rule` or `llm` |
| `status` | `classified` or `failed` |
| `reason` | Failure detail; null on success |
| `classified_at` | UTC timestamp of the latest attempt |

Join classifications to source data for display:

```sql
SELECT
    c.raw_item_id,
    c.category,
    c.justification,
    c.method,
    c.status,
    c.reason,
    c.classified_at,
    r.title,
    r.source_name,
    r.source_id,
    r.source_url,
    r.raw_content,
    r.date_published,
    r.metadata
FROM classifications AS c
JOIN raw_items AS r ON r.id = c.raw_item_id
WHERE r.is_active = 1
ORDER BY c.classified_at DESC;
```

## API recommendation

The repository currently has no frontend API. Add a backend endpoint that
returns the joined query above as JSON. Useful endpoints are:

- `GET /papers` for paginated classified papers
- `GET /papers/{raw_item_id}` for one paper and its classification
- `GET /categories/{category}` for filtered results

Recommended JSON shape:

```json
{
  "id": "raw-item-uuid",
  "title": "Paper title",
  "source": "arXiv",
  "source_id": "source identifier",
  "source_url": "https://example.org/paper",
  "abstract": "Stored raw content",
  "published_at": "2026-09-02T00:00:00Z",
  "category": "still_working_on",
  "justification": "The paper is an early-stage preprint.",
  "method": "llm",
  "status": "classified",
  "reason": null,
  "classified_at": "2026-09-02T00:00:00Z",
  "metadata": {}
}
```

Failed records should remain visible to operators with `status: "failed"` and
their `reason`, but should not be presented as a category.

## Running classification

From the repository root:

```bash
export HF_MODEL="meta-llama/Llama-3.1-8B-Instruct"
PYTHONPATH=. python main.py --limit 1
```

Use `--limit` while testing. Omitting it processes every active record and may
make a large number of LLM requests. The database schema is created by the
application's `init_db()` path; production deployments should run:

```bash
cd data-ingestion-system
alembic upgrade head
```