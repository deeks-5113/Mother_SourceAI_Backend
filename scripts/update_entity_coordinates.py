"""
scripts/update_entity_coordinates.py
------------------------------------
Bulk update latitude/longitude in `entities` from a CSV file.

Usage:
    python scripts/update_entity_coordinates.py --input data/entity_coordinates.csv

CSV columns required:
    entity_id,latitude,longitude
"""

import argparse
import csv
import logging
import sys
from pathlib import Path

from supabase import create_client

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("update_entity_coordinates")


def _parse_float(raw: str, field_name: str, row_num: int) -> float:
    try:
        return float(raw)
    except Exception as exc:
        raise ValueError(
            f"Row {row_num}: invalid {field_name} value '{raw}'."
        ) from exc


def update_coordinates(input_csv: Path, dry_run: bool = False) -> None:
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_key)

    with input_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"entity_id", "latitude", "longitude"}
        missing_cols = required - set(reader.fieldnames or [])
        if missing_cols:
            raise ValueError(
                f"Missing required CSV columns: {sorted(missing_cols)}"
            )

        success = 0
        failed = 0
        skipped = 0

        for row_num, row in enumerate(reader, start=2):
            entity_id = (row.get("entity_id") or "").strip()
            if not entity_id:
                logger.warning("Row %d skipped: missing entity_id.", row_num)
                skipped += 1
                continue

            try:
                lat = _parse_float((row.get("latitude") or "").strip(), "latitude", row_num)
                lng = _parse_float((row.get("longitude") or "").strip(), "longitude", row_num)
            except ValueError as exc:
                logger.warning(str(exc))
                failed += 1
                continue

            if dry_run:
                logger.info("[DRY RUN] Would update %s -> lat=%s, lng=%s", entity_id, lat, lng)
                success += 1
                continue

            try:
                response = (
                    supabase.table("entities")
                    .update({"latitude": lat, "longitude": lng})
                    .eq("id", entity_id)
                    .execute()
                )
                if not response.data:
                    logger.warning("No entity found for id=%s", entity_id)
                    failed += 1
                    continue
                success += 1
            except Exception as exc:
                logger.error("Update failed for id=%s: %s", entity_id, exc)
                failed += 1

    logger.info(
        "Coordinate update complete â€” success=%d failed=%d skipped=%d",
        success,
        failed,
        skipped,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bulk update entity coordinates from CSV."
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to CSV with entity_id,latitude,longitude columns.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate CSV and print updates without writing to DB.",
    )
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Input CSV not found: {args.input}")

    update_coordinates(args.input, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
