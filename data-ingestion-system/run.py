#!/usr/bin/env python3
"""run.py — Top-level launcher for Haemophilia Data Ingestion System."""
import asyncio
import sys

from app.main import main

if __name__ == "__main__":
    try:
        asyncio.run(main(sys.argv[1:]))
    except KeyboardInterrupt:
        print("\nShutdown requested. Goodbye.")
        sys.exit(0)
