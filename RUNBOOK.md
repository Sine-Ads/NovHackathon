# Runbook

Every command needed to go from a fresh clone to a running system, in order. Tested on Ubuntu 22.04, Python 3.10.12, Node 18+.

**The database ships populated.** Steps 1 and 2 rebuild it from scratch and are only needed if you want to re-ingest. To see the system, skip to step 3.

---

## 0. Prerequisites and configuration

```bash
python3 --version    # 3.10 or newer
node --version       # 18 or newer
```

### One `.env`, shared by all three components

Configuration lives in a **single `.env` at the repository root**. It is gitignored and never committed, so a fresh clone does not have one — create it.

`phase2/`, `llm_1/` and `data-ingestion-system/` each read `.env` from their own directory, so link all three back to the root file. This is why the `llm_1` classifier and the Phase 2 assistant share one `LLM_API_KEY`:

```bash
ln -sf ../.env phase2/.env
ln -sf ../.env llm_1/.env
ln -sf ../.env data-ingestion-system/.env
```

Verify all four paths are the same file:

```bash
ls -l .env phase2/.env llm_1/.env data-ingestion-system/.env
```

**`LLM_API_KEY` is the only value you must supply.** Everything else has a working default. Browsing, search, filtering and signal scoring all work without a key; AI summaries, both chatbots and the evaluation suite do not.

Both model stages — the `llm_1` classifier and the Phase 2 assistant — share one endpoint and one key. Any OpenAI-compatible provider works, because the client appends `/chat/completions` and sends the model name in the payload:

| Provider | `LLM_BASE_URL` | Where the key comes from |
|---|---|---|
| **Google Gemini** *(current default)* | `https://generativelanguage.googleapis.com/v1beta/openai` | <https://aistudio.google.com/apikey> |
| Groq | `https://api.groq.com/openai/v1` | <https://console.groq.com/keys> |
| OpenRouter | `https://openrouter.ai/api/v1` | <https://openrouter.ai/keys> |
| Ollama (local, no account) | `http://localhost:11434/v1` | any non-empty string |
| HuggingFace | *leave blank* | <https://huggingface.co/settings/tokens> |

Switching provider is two lines in `.env` and no code change.

### Variable reference

| Variable | Default | Used by |
|---|---|---|
| `LLM_API_KEY` | *(none — you supply this)* | `llm_1` + `phase2` |
| `LLM_BASE_URL` | Gemini OpenAI-compatible endpoint | `llm_1` + `phase2` |
| `LLM_MODEL` | `gemini-2.0-flash` | both, unless overridden below |
| `HF_MODEL` | blank → `LLM_MODEL` | `llm_1` override |
| `HF_PROVIDER` | `auto` | `llm_1`, HuggingFace path only |
| `HF_COUNCIL_MODELS` | `gemini-2.0-flash,gemini-2.0-flash-lite` | `llm_1` council mode |
| `PHASE2_LLM_MODEL` | blank → `LLM_MODEL` | `phase2` override |
| `PHASE2_EMBED_MODEL` | `BAAI/bge-small-en-v1.5` | `phase2` |
| `PHASE2_EMBED_DIM` | `384` | `phase2` |
| `PHASE2_SOURCE_DB` | blank → `../data-ingestion-system/haemophilia_data.db` | `phase2` |
| `PHASE2_SIDECAR_DB` | blank → `phase2/data/phase2.db` | `phase2` |
| `PHASE2_EMBED_CACHE` | blank → `phase2/data/models/` | `phase2` |
| `MIN_EVIDENCE` | `0.008` | confidence gate |
| `THIN_CONTENT_CHARS` | `50` | evidence ranking |
| `MAX_HISTORY_TURNS` | `6` | chat |
| `FRONTEND_ORIGIN` | `http://localhost:3000` | CORS |
| `DATABASE_URL` | `sqlite+aiosqlite:///./haemophilia_data.db` | Phase 1 — **relative to cwd** |
| `LOG_LEVEL` | `INFO` | Phase 1 |
| `INGESTORS_ENABLED` | all 8 | Phase 1 |
| `INGESTOR_*_INTERVAL_MINUTES` | 1440 or 10080 | Phase 1 scheduler |
| `API_RATE_LIMIT_DELAY_MS` | `333` | Phase 1 |
| `ERROR_RETRY_MAX_ATTEMPTS` | `3` | Phase 1 |
| `INGESTOR_MAX_ITEMS_PER_RUN` | `5000` | Phase 1 |
| `NCBI_API_KEY` / `OPENFDA_API_KEY` / `USPTO_API_KEY` | blank | Phase 1 — USPTO returns nothing without one |
| `SEC_EDGAR_USER_AGENT` | identifying string | Phase 1 — SEC requires this |

`DATABASE_URL` is relative to the working directory, so **run Phase 1 commands from inside `data-ingestion-system/`**. Running them from the repository root creates an empty database in the wrong place.

---

## 1. Phase 1 — ingestion (optional; the corpus is committed)

```bash
cd data-ingestion-system
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# uses the shared root .env via the symlink created in step 0
.venv/bin/python -m alembic upgrade head

.venv/bin/python run.py --once              # one pass over every ingestor
.venv/bin/python run.py --once --ingestor clinical_trials   # or just one
.venv/bin/python inspect_data.py            # what landed
```

Expect roughly 1,400 records. Four of the eight connectors return nothing — see [`LIMITATIONS.md`](LIMITATIONS.md) for which and why.

Verify:

```bash
.venv/bin/python -c "import sqlite3; c=sqlite3.connect('haemophilia_data.db'); \
print(c.execute('select source_name,count(*) from raw_items group by 1').fetchall())"
```

---

## 2. Phase 1b — classification (optional)

```bash
cd ../llm_1
../data-ingestion-system/.venv/bin/python main.py --limit 50   # smoke test first
../data-ingestion-system/.venv/bin/python main.py              # full run
```

The rules layer resolves 161 trials deterministically with no API calls. The remaining 1,238 records go to the LLM, one call each — run the smoke test first and check the rate.

Verify:

```bash
../data-ingestion-system/.venv/bin/python -c "import sqlite3; \
c=sqlite3.connect('../data-ingestion-system/haemophilia_data.db'); \
print(c.execute('select category,method,count(*) from classifications group by 1,2').fetchall())"
```

Expected after a rules-only run: `[('proven_false','rule',71), ('still_working_on','rule',90)]`.

---

## 3. Phase 2 — the demo

```bash
cd phase2
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/python scripts/check_env.py
```

`check_env.py` is the preflight. It proves the right database was found, the sidecar is writable and the embedding model resolves. **If it fails, stop here** — every later error will be a confusing downstream symptom of whatever it reports.

```bash
.venv/bin/python scripts/build_index.py     # ~8 min once; embeds 1,399 records
.venv/bin/python -m uvicorn api.main:app --port 8000
```

The first `build_index.py` run downloads the ONNX embedding model (~90 MB) into `data/models/`. Later runs are incremental; `--rebuild` forces a full re-index.

In a second terminal:

```bash
cd phase2/web
npm install
npm run dev                     # http://localhost:3000
```

Verify:

```bash
curl -s localhost:8000/api/health | python3 -m json.tool
curl -s 'localhost:8000/api/feed?limit=3' | head -c 400
```

Then open <http://localhost:3000> — the radar feed, a signal detail view, and the assistant.

---

## 4. Evaluation

```bash
cd phase2
.venv/bin/python scripts/run_eval.py
```

15 golden questions across 6 categories. Abstention recall is reported separately and gates the exit code: answering a question that should have been refused fails the suite regardless of the other results. See [`EVALUATION.md`](EVALUATION.md).

Requires `LLM_API_KEY` — the suite exercises generation, not just retrieval.

---

## 5. Tests

```bash
cd data-ingestion-system
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/ -v          # 13 tests, all HTTP mocked
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `check_env.py` reports the wrong database | Phase 1 config resolves paths against the process working directory | Run from `phase2/`, or set `PHASE2_SOURCE_DB` to an absolute path |
| Chat returns "insufficient evidence" for everything | Index not built | `.venv/bin/python scripts/build_index.py` |
| Summaries and chat fail; browsing works | `LLM_API_KEY` missing or empty | Set it in the root `.env` |
| `401` / `403` from the provider | Key is for a different provider than `LLM_BASE_URL` | The two must match — see the provider table in step 0 |
| `404 model not found` | `LLM_MODEL` is not a model that provider serves | e.g. Gemini needs `gemini-2.0-flash`, not a HuggingFace model id |
| `no such table: classifications` | Migration 002 not applied | `alembic upgrade head` in `data-ingestion-system/` |
| `llm_1` cannot import `app.database` | Running from the wrong directory | Run `main.py` from inside `llm_1/` |
| Any component ignores your `LLM_API_KEY` | A `.env` symlink is missing or was replaced by a real file | Re-run the `ln -sf` commands in step 0 |
| Verdict badges all blank | Classifier has not been run | Step 2 above |
