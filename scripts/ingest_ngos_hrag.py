"""
scripts/ingest_ngos_hrag.py
---------------------------
Ingests NGO data from a HRAG-format JSON file into the Supabase `ngos` table.

Data file: Json/ngo.json  (relative to project root)

HRAG Hierarchy used:
  H1 → document root   (ignored, serves as entry point only)
  H2 → city / region   (`city` + `semantic_summary` fields)
  H3 → NGO entry       (`title` field = registration number / NGO name)
  chunks[]             → (`content` + `source_id` fields)

Usage:
  python scripts/ingest_ngos_hrag.py
  python scripts/ingest_ngos_hrag.py --input Json/ngo.json
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# ── Allow importing from project root ────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openai import OpenAI
from supabase import create_client

from modules.config import get_settings

# ── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("ingest_ngos_hrag")

# ── Constants ─────────────────────────────────────────────────────────
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS  = 1536
BATCH_DELAY_SEC = 0.25      # gentle rate-limit buffer between OpenAI calls
TABLE_NAME      = "ngos"


# ═══════════════════════════════════════════════════════════════════════
# STEP 1 — Flatten the HRAG hierarchy into a list of chunk dicts
# ═══════════════════════════════════════════════════════════════════════

def flatten_ngo_hrag(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Recursively traverse the HRAG JSON and extract one dict per chunk.

    Hierarchy traversal:
      H1 (document root)
      └── H2 (city / region)
              city             = H2["title"]
              semantic_summary = H2["semantic_summary"]
          └── H3 (NGO registration number / name)
                  title        = H3["title"]
              └── chunks[]
                      content  = chunk["text"]
                      source_id= chunk["source_id"]

    Each extracted dict maps 1-to-1 with a row in the `ngos` table.
    """
    records: List[Dict[str, Any]] = []

    def _traverse_h2(h2_node: Dict[str, Any]) -> None:
        """Handle an H2 node (city/region). Recurse into its H3 children."""
        # ── Extract city-level metadata from H2 ──────────────────────
        city             = h2_node.get("title", "Unknown City")
        semantic_summary = h2_node.get("semantic_summary", "")

        logger.debug("  H2 → city=%r  |  summary=%r", city, semantic_summary[:60])

        # ── Recurse into H3 children ──────────────────────────────────
        for h3_node in h2_node.get("children", []):
            _traverse_h3(h3_node, city, semantic_summary)

    def _traverse_h3(
        h3_node: Dict[str, Any],
        city: str,
        semantic_summary: str,
    ) -> None:
        """Handle an H3 node (individual NGO). Extract its chunks."""
        # ── Extract NGO-level title from H3 ───────────────────────────
        ngo_title = h3_node.get("title", "Unknown NGO")
        level     = h3_node.get("level", "H3")

        logger.debug("    H3 → title=%r", ngo_title)

        # ── Extract each chunk (usually one per NGO) ───────────────────
        for chunk in h3_node.get("chunks", []):
            content   = chunk.get("text", "").strip()
            source_id = chunk.get("source_id", "")

            if not content:
                logger.warning("      Skipping empty chunk in '%s'", ngo_title)
                continue

            records.append(
                {
                    # Hierarchy metadata
                    "level":            level,
                    "title":            ngo_title,
                    "semantic_summary": semantic_summary,
                    # Chunk payload
                    "content":          content,
                    "source_id":        source_id,
                    # Filter dimension (from H2)
                    "city":             city,
                    # `embedding` filled in Step 2
                }
            )

    # ── Entry point: walk H1 → H2 ────────────────────────────────────
    for h1_node in data.get("document_structure", []):
        logger.info("H1 → %r", h1_node.get("title", ""))
        for h2_node in h1_node.get("children", []):
            _traverse_h2(h2_node)

    return records


# ═══════════════════════════════════════════════════════════════════════
# STEP 2 — Generate OpenAI embedding for a text string
# ═══════════════════════════════════════════════════════════════════════

def get_embedding(client: OpenAI, text: str) -> List[float]:
    """
    Call OpenAI Embeddings API and return a 1536-dim float list.

    Strategy: embed "{title}: {content}" so the vector captures both
    the NGO identifier and what it does / where it operates.

    Returns an empty list on failure (caller will skip the chunk).
    """
    try:
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=[text.replace("\n", " ")],
            dimensions=EMBEDDING_DIMS,
        )
        return response.data[0].embedding
    except Exception as exc:
        logger.error("Embedding API error: %s", exc)
        return []


# ═══════════════════════════════════════════════════════════════════════
# STEP 3 — Insert records into Supabase `ngos` table
# ═══════════════════════════════════════════════════════════════════════

def ingest(input_path: Path) -> None:
    """Full ingestion pipeline: load → flatten → embed → upsert."""

    # ── Initialise clients ────────────────────────────────────────────
    settings      = get_settings()
    supabase      = create_client(settings.supabase_url, settings.supabase_key)
    openai_client = OpenAI(api_key=settings.openai_api_key)

    # ── Load JSON ─────────────────────────────────────────────────────
    logger.info("Loading HRAG data from: %s", input_path)
    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    # ── Flatten hierarchy → list of chunk dicts ───────────────────────
    records = flatten_ngo_hrag(data)
    logger.info("Extracted %d chunk(s) from HRAG structure.", len(records))

    if not records:
        logger.warning("No records to ingest. Check the JSON structure.")
        return

    # ── Embed + insert each record ────────────────────────────────────
    success = 0
    failed  = 0

    for i, record in enumerate(records, start=1):
        ngo_name = record["title"]
        city     = record["city"]

        # Build the text to embed: "{NGO title}: {chunk content}"
        text_to_embed = f"{ngo_name}: {record['content']}"

        logger.info(
            "[%d/%d] Embedding '%s' (city: %s) ...",
            i, len(records), ngo_name, city,
        )

        # ── Generate embedding ────────────────────────────────────────
        vector = get_embedding(openai_client, text_to_embed)
        if not vector:
            logger.error("  ❌ Skipping '%s' — embedding failed.", ngo_name)
            failed += 1
            continue

        # Attach embedding to the record
        record["embedding"] = vector

        # ── Insert into Supabase ──────────────────────────────────────
        try:
            supabase.table(TABLE_NAME).insert(record).execute()
            logger.info("  ✅ Inserted '%s' — city: %s", ngo_name, city)
            success += 1
        except Exception as exc:
            logger.error("  ❌ DB insert failed for '%s': %s", ngo_name, exc)
            failed += 1

        # Gentle rate-limit buffer
        time.sleep(BATCH_DELAY_SEC)

    # ── Summary ───────────────────────────────────────────────────────
    logger.info("─" * 60)
    logger.info(
        "Ingestion complete — ✅ inserted: %d  |  ❌ failed: %d  |  total: %d",
        success, failed, len(records),
    )


# ═══════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest HRAG-format NGO JSON into the Supabase `ngos` table."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/ngos.json"),
        help="Path to the HRAG NGO JSON file (default: data/ngos.json)",
    )
    args = parser.parse_args()

    if not args.input.exists():
        logger.error("Input file not found: %s", args.input.resolve())
        sys.exit(1)

    ingest(args.input)


if __name__ == "__main__":
    main()
