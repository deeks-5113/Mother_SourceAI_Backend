"""
scripts/ingest_hrag.py
----------------------
CLI tool to ingest HRAG JSON files into Supabase.

Usage:
    py scripts/ingest_hrag.py data/ngo.json
    py scripts/ingest_hrag.py data/ngo.json --environment Urban
    py scripts/ingest_hrag.py data/hospitals.json --district "East Godavari" --environment Urban
"""

import json
import os
import sys
import argparse
import logging
from typing import List, Dict, Any
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from modules.config import get_settings
from openai import OpenAI
from supabase import create_client, Client

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s"
)
logger = logging.getLogger("ingest_hrag")


def get_embedding(client: OpenAI, text: str, model: str, dimensions: int) -> List[float]:
    """Generate embedding for a given text using OpenAI."""
    try:
        response = client.embeddings.create(
            input=[text.replace("\n", " ")],
            model=model,
            dimensions=dimensions
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error("Error generating embedding: %s", e)
        return []


def flatten_hrag_structure(
    data: Dict[str, Any],
    override_district: str | None = None,
    override_environment: str | None = None,
    source_type: str = "hospital",
) -> List[Dict[str, Any]]:
    """Flatten the nested HRAG structure into individual chunks with metadata.

    District is auto-detected from the H2 title of each branch unless
    `override_district` is provided.  Environment defaults to 'General'
    unless `override_environment` is provided or the node carries its own.
    """
    flattened_data: List[Dict[str, Any]] = []
    default_env = override_environment or "General"

    def traverse(node: Dict[str, Any], inherited_district: str, inherited_env: str):
        current_level = node.get("level", "")
        current_title = node.get("title", "")
        current_summary = node.get("semantic_summary", "")

        # H2 nodes represent a district/region heading — use it as district
        district = inherited_district
        if current_level == "H2" and not override_district:
            district = current_title

        env = inherited_env

        # If this node has chunks, add them
        if "chunks" in node:
            for chunk in node["chunks"]:
                item = {
                    "level": current_level,
                    "title": current_title,
                    "semantic_summary": current_summary,
                    "content": chunk.get("text", ""),
                    "source_id": chunk.get("source_id", ""),
                    "district": district,
                    "environment": env,
                    "source_type": source_type,
                }
                flattened_data.append(item)

        # Recurse into children
        if "children" in node:
            for child in node["children"]:
                traverse(child, district, env)

    for entry in data.get("document_structure", []):
        initial_district = override_district or entry.get("title", "Unknown")
        traverse(entry, initial_district, default_env)

    return flattened_data


def ingest_file(
    file_path: str,
    supabase: Client,
    openai_client: OpenAI,
    settings: Any,
    override_district: str | None = None,
    override_environment: str | None = None,
    source_type: str = "hospital",
):
    """Process and ingest a single HRAG JSON file."""
    logger.info("Processing file: %s", file_path)

    if not os.path.exists(file_path):
        logger.error("File not found: %s", file_path)
        sys.exit(1)

    with open(file_path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    flattened_items = flatten_hrag_structure(data, override_district, override_environment, source_type)
    total = len(flattened_items)
    logger.info("Found %d chunks to ingest from %s", total, file_path)

    if total == 0:
        logger.warning("No chunks found — check your JSON structure.")
        return

    # Show a summary of districts detected
    districts = set(item["district"] for item in flattened_items)
    logger.info("Districts detected: %s", ", ".join(sorted(districts)))

    success = 0
    for i, item in enumerate(flattened_items, 1):
        text_to_embed = f"{item['title']}: {item['content']}"
        embedding = get_embedding(
            openai_client,
            text_to_embed,
            settings.embedding_model,
            settings.embedding_dimensions,
        )

        if not embedding:
            logger.error("[%d/%d] Skipping chunk %s — embedding failed.", i, total, item["source_id"])
            continue

        item["embedding"] = embedding

        try:
            supabase.table("entities").insert(item).execute()
            success += 1
            if success % 10 == 0 or i == total:
                logger.info("[%d/%d] Ingested %d chunks so far...", i, total, success)
        except Exception as e:
            logger.error("[%d/%d] Error inserting chunk %s: %s", i, total, item["source_id"], e)

    logger.info("Ingestion complete — %d/%d chunks inserted successfully.", success, total)


def main():
    parser = argparse.ArgumentParser(
        description="Ingest an HRAG JSON file into Supabase."
    )
    parser.add_argument(
        "file",
        help="Path to the JSON file to ingest (e.g. data/ngo.json)",
    )
    parser.add_argument(
        "--district",
        default=None,
        help="Override district for ALL chunks (default: auto-detect from H2 titles)",
    )
    parser.add_argument(
        "--environment",
        default=None,
        help="Override environment for ALL chunks (default: 'General')",
    )
    parser.add_argument(
        "--source-type",
        default="hospital",
        choices=["hospital", "phc", "medical_college"],
        help="Tag all chunks with this source type (default: 'hospital')",
    )
    args = parser.parse_args()

    settings = get_settings()

    if not all([settings.supabase_url, settings.supabase_key, settings.openai_api_key]):
        logger.error("Missing configuration. Check SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY in .env")
        sys.exit(1)

    supabase = create_client(settings.supabase_url, settings.supabase_key)
    openai_client = OpenAI(api_key=settings.openai_api_key)

    ingest_file(
        file_path=args.file,
        supabase=supabase,
        openai_client=openai_client,
        settings=settings,
        override_district=args.district,
        override_environment=args.environment,
        source_type=args.source_type,
    )


if __name__ == "__main__":
    main()
