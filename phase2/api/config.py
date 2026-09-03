"""Phase 2 configuration.

Every path is resolved from ``__file__``, never from the process working
directory. Phase 1's ``app/config.py`` defaults ``database_url`` to
``./haemophilia_data.db`` and loads ``.env`` relative to the cwd, so a process
started from the wrong directory silently reads (or creates) an empty database.
Phase 2 must never inherit that behaviour: resolving from ``__file__`` makes the
correct path independent of where uvicorn happens to be launched.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PHASE2_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PHASE2_DIR.parent

load_dotenv(PHASE2_DIR / ".env")

DEFAULT_SOURCE_DB = REPO_ROOT / "data-ingestion-system" / "haemophilia_data.db"
DEFAULT_SIDECAR_DB = PHASE2_DIR / "data" / "phase2.db"

# fastembed defaults to /tmp, which most systems clear on reboot — that would
# silently re-download the model on the first query after a restart. Keep it
# inside phase2 so the cache survives.
# `or` rather than a getenv default: a variable present but empty in .env
# yields "", which Path() would resolve to the current directory.
EMBED_CACHE_DIR = Path(
    os.getenv("PHASE2_EMBED_CACHE") or PHASE2_DIR / "data" / "models"
).expanduser()

LLM_MODEL = os.getenv("PHASE2_LLM_MODEL", "Qwen/Qwen2.5-72B-Instruct")
EMBED_MODEL = os.getenv("PHASE2_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
EMBED_DIM = int(os.getenv("PHASE2_EMBED_DIM", "384"))
HF_TOKEN = os.getenv("HF_TOKEN") or None

FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")

# Below this evidence score the chat layer declines instead of calling the LLM.
MIN_EVIDENCE = float(os.getenv("MIN_EVIDENCE", "0.008"))
# Items shorter than this are treated as stubs: summarised from a template
# rather than by the LLM, and down-weighted during evidence ranking.
THIN_CONTENT_CHARS = int(os.getenv("THIN_CONTENT_CHARS", "50"))
# Conversation turns replayed for continuity. History carries no factual
# authority (see chat.py), so this stays small.
MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", "6"))


def source_db_path() -> Path:
    """Absolute path to the Phase 1 database, with the empty-file trap guarded.

    A zero-byte ``haemophilia_data.db`` sits at the repository root. Any
    cwd-relative resolution finds it, opens it happily, and yields an empty
    feed with no error anywhere, so the size check is not paranoia.
    """
    raw = os.getenv("PHASE2_SOURCE_DB") or DEFAULT_SOURCE_DB
    path = Path(raw).expanduser().resolve()
    if not path.is_file():
        raise RuntimeError(
            f"Phase 1 database not found at {path}. "
            "Set PHASE2_SOURCE_DB or check the repository layout."
        )
    if path.stat().st_size == 0:
        raise RuntimeError(
            f"Phase 1 database at {path} is 0 bytes. This is probably the stray "
            "placeholder at the repository root rather than the real database in "
            "data-ingestion-system/."
        )
    return path


def sidecar_db_path() -> Path:
    """Absolute path to Phase 2's own database. Created if absent."""
    raw = os.getenv("PHASE2_SIDECAR_DB") or DEFAULT_SIDECAR_DB
    path = Path(raw).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def read_only_uri() -> str:
    """SQLite URI that opens the Phase 1 database read-only.

    ``mode=ro`` is enforced by SQLite itself, so the "never write to Phase 1"
    constraint survives any bug in Phase 2 rather than depending on discipline.
    """
    return f"file:{source_db_path().as_posix()}?mode=ro"
