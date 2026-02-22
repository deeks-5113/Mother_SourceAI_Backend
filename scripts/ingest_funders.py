"""
scripts/ingest_funders.py
--------------------------
Ingests data/funders.json into the Supabase `funders` table.

Generates 1536-dim embeddings for each funder's description
using OpenAI text-embedding-3-small, then inserts into Supabase.

Usage:
    python scripts/ingest_funders.py
    python scripts/ingest_funders.py --input data/funders.json
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so `modules.*` imports work.
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.config import get_settings

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS = 1536
TABLE_NAME = "funders"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_json(path: Path) -> list[dict[str, Any]]:
    """Load and return the funders JSON array."""
    logger.info("Loading funders from %s ...", path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Expected a JSON array at top level.")
    logger.info("Loaded %d funder(s).", len(data))
    return data


def get_embedding(client: Any, text: str) -> list[float]:
    """
    Generate an embedding for `text` using OpenAI text-embedding-3-small.

    Returns an empty list on failure (the caller skips the record).
    """
    try:
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=[text.replace("\n", " ")],
            dimensions=EMBEDDING_DIMS,
        )
        return response.data[0].embedding
    except Exception as exc:
        logger.error("Embedding failed for text[:60]=%r: %s", text[:60], exc)
        return []


def build_payload(record: dict[str, Any], embedding: list[float]) -> dict[str, Any]:
    """Map a raw JSON record to the funders table schema."""
    return {
        "name":          record["name"],
        "city":          record.get("city", "Global"),
        "state":         record.get("state", "Global"),
        "focus_areas":   record.get("focus_areas", []),
        "level":         record.get("level"),
        "contact_name":  record.get("contact_name"),
        "contact_email": record.get("contact_email"),
        "description":   record["description"],
        "embedding":     embedding,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def ingest(input_path: Path) -> None:
    """Run the full ingestion pipeline."""
    settings = get_settings()

    # ── Clients ───────────────────────────────────────────────────────
    from openai import OpenAI
    from supabase import create_client

    openai_client = OpenAI(api_key=settings.openai_api_key)
    supabase = create_client(settings.supabase_url, settings.supabase_key)

    # ── Load data ─────────────────────────────────────────────────────
    records = load_json(input_path)
    if not records:
        logger.warning("No records to ingest.")
        return

    success = 0
    failed = 0
    total = len(records)

    for i, record in enumerate(records, start=1):
        name = record.get("name", "Unknown")
        city = record.get("city", "N/A")
        logger.info("[%d/%d] Embedding '%s' (city: %s) ...", i, total, name, city)

        # ── Step 1: Embed description ─────────────────────────────────
        description = record.get("description", "")
        if not description:
            logger.warning("  ⚠️  Skipping '%s' — empty description.", name)
            failed += 1
            continue

        embedding = get_embedding(openai_client, description)
        if not embedding:
            logger.error("  ❌ Embedding failed for '%s'. Skipping.", name)
            failed += 1
            continue

        # ── Step 2: Insert into Supabase ──────────────────────────────
        payload = build_payload(record, embedding)
        try:
            supabase.table(TABLE_NAME).insert(payload).execute()
            logger.info("  ✅ Inserted '%s' — city: %s", name, city)
            success += 1
        except Exception as exc:
            logger.error("  ❌ DB insert failed for '%s': %s", name, exc)
            failed += 1

        # Small delay to respect API rate limits
        time.sleep(0.2)

    # ── Summary ───────────────────────────────────────────────────────
    logger.info(
        "Ingestion complete — ✅ inserted: %d  |  ❌ failed: %d  |  total: %d",
        success, failed, total,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest funders into Supabase.")
    parser.add_argument(
        "--input",
        type=Path,
        default=PROJECT_ROOT / "data" / "funders.json",
        help="Path to the funders JSON file.",
    )
    args = parser.parse_args()
    ingest(args.input)
