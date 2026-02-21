"""
scripts/ingest_ngos.py
----------------------
Ingest NGO profile data into the Supabase `ngos` table.

Usage:
    python scripts/ingest_ngos.py --input data/ngos.json

Input JSON format (list of objects):
    [
      {
        "name": "Mamatha Foundation",
        "district": "Warangal",
        "state": "Telangana",
        "focus_areas": ["maternal health", "nutrition"],
        "level": "district",
        "contact_name": "Sunita Rao",
        "contact_email": "sunita@mamatha.org",
        "contact_phone": "+91-9876543210",
        "description": "Mamatha Foundation operates maternal health camps ..."
      },
      ...
    ]

The `description` field is used to generate the embedding.
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openai import OpenAI
from modules.config import get_settings
from modules.ngo_repository import NgoRepository
from supabase_client import supabase_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS  = 1536
BATCH_DELAY_SEC = 0.3   # gentle rate-limit buffer between OpenAI calls


def embed_text(client: OpenAI, text: str) -> list[float]:
    """Call OpenAI embeddings API and return a float vector."""
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
        dimensions=EMBEDDING_DIMS,
    )
    return response.data[0].embedding


def ingest(input_path: Path) -> None:
    settings   = get_settings()
    openai_cli = OpenAI(api_key=settings.openai_api_key)
    repo       = NgoRepository(supabase_client)

    logger.info("Loading NGOs from %s", input_path)
    with open(input_path, encoding="utf-8") as f:
        ngos: list[dict] = json.load(f)

    logger.info("Found %d NGO(s) to ingest.", len(ngos))

    success = 0
    failed  = 0

    for i, ngo in enumerate(ngos, start=1):
        name = ngo.get("name", f"NGO #{i}")
        desc = ngo.get("description", "").strip()

        if not desc:
            logger.warning("[%d/%d] Skipping '%s' — empty description.", i, len(ngos), name)
            failed += 1
            continue

        logger.info("[%d/%d] Embedding '%s' ...", i, len(ngos), name)
        try:
            vector = embed_text(openai_cli, desc)
        except Exception as exc:
            logger.error("  Embedding failed for '%s': %s", name, exc)
            failed += 1
            continue

        record = {
            **ngo,
            "embedding": vector,
        }

        try:
            repo.upsert_ngo(record)
            logger.info("  ✅ Upserted '%s' (district: %s)", name, ngo.get("district"))
            success += 1
        except Exception as exc:
            logger.error("  ❌ Upsert failed for '%s': %s", name, exc)
            failed += 1

        time.sleep(BATCH_DELAY_SEC)

    logger.info("─" * 50)
    logger.info("Ingestion complete — success: %d, failed: %d", success, failed)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest NGOs into Supabase.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/ngos.json"),
        help="Path to the NGO JSON file (default: data/ngos.json)",
    )
    args = parser.parse_args()

    if not args.input.exists():
        logger.error("Input file not found: %s", args.input)
        sys.exit(1)

    ingest(args.input)


if __name__ == "__main__":
    main()
