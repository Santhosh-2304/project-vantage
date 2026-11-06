
import argparse
import json
import logging
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
REPORT_DIR = PROJECT_ROOT / "data" / "validation_reports"

REPORT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ["datetime", "open", "high", "low", "close"]
EXPECTED_INTERVAL_MINUTES = 30


def find_latest_raw_file():
    """Find the latest API response, excluding ingestion reports."""

    files = sorted(
        RAW_DATA_DIR.glob("xauusd_30min_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True
    )

    files = [
        path for path in files
        if not path.stem.endswith("_report")
    ]

    if not files:
        raise FileNotFoundError("No API raw data files found.")

    return files[0]


def validate_data(file_path):
    """Validate actual API records without modifying the raw file."""

    logger.info("Validating file: %s", file_path.name)

    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError("API response must be a JSON object.")

    records = data.get("values")

    if not isinstance(records, list):
        raise ValueError("API response does not contain a valid values list.")

    issues = Counter()
    valid_timestamps = []
    valid_records = 0

    for index, record in enumerate(records):

        if not isinstance(record, dict):
            issues["invalid_record_structure"] += 1
            continue

        record_valid = True

        # Required field checks
        for field in REQUIRED_FIELDS:
            if field not in record:
                issues[f"missing_{field}"] += 1
                record_valid = False
            elif record[field] is None or record[field] == "":
                issues[f"null_{field}"] += 1
                record_valid = False

        # Timestamp validation
        timestamp = None

        if "datetime" in record and record["datetime"]:
            try:
                timestamp = pd.to_datetime(
                    record["datetime"],
                    errors="raise",
                    utc=True
                )

                valid_timestamps.append(timestamp)

            except (ValueError, TypeError):
                issues["invalid_datetime"] += 1
                record_valid = False

        # Numeric validation
        prices = {}

        for field in ["open", "high", "low", "close"]:

            if field not in record or record[field] in (None, ""):
                continue

            try:
                value = float(record[field])

                if not math.isfinite(value):
                    issues["non_finite_" + field] += 1
                    record_valid = False
                else:
                    prices[field] = value

            except (ValueError, TypeError):
                issues["invalid_numeric_" + field] += 1
                record_valid = False

        # OHLC consistency checks
        if len(prices) == 4:

            if prices["high"] < max(
                prices["open"],
                prices["close"],
                prices["low"]
            ):
                issues["invalid_high"] += 1
                record_valid = False

            if prices["low"] > min(
                prices["open"],
                prices["close"],
                prices["high"]
            ):
                issues["invalid_low"] += 1
                record_valid = False

        if record_valid:
            valid_records += 1

    # Duplicate timestamp checks
    timestamp_counts = Counter(valid_timestamps)

    duplicate_timestamps = sum(
        count - 1
        for count in timestamp_counts.values()
        if count > 1
    )

    issues["duplicate_timestamps"] = duplicate_timestamps

    # Ordering check
    # Source ordering check
    timestamps_ascending = (
        valid_timestamps == sorted(valid_timestamps)
    )

    timestamps_descending = (
        valid_timestamps == sorted(valid_timestamps, reverse=True)
    )

    source_order = (
        "ascending" if timestamps_ascending
        else "descending" if timestamps_descending
        else "mixed"
    )

    if source_order == "mixed":
        issues["timestamp_order_violations"] += 1

    # Time-gap analysis
    unique_timestamps = sorted(set(valid_timestamps))

    gaps_over_expected = 0

    for previous, current in zip(
        unique_timestamps,
        unique_timestamps[1:]
    ):
        gap_minutes = (
            current - previous
        ).total_seconds() / 60

        if gap_minutes > EXPECTED_INTERVAL_MINUTES:
            gaps_over_expected += 1

    issues["gaps_over_30_minutes"] = gaps_over_expected

    total_records = len(records)

    # A record is counted as valid only if it has no detected
    # record-level validation issue. Ordering and gap checks
    # are dataset-level diagnostics.
    record_issue_keys = [
        key for key in issues
        if key not in {
            "duplicate_timestamps",
            "timestamp_order_violations",
            "gaps_over_30_minutes"
        }
    ]

    validation_passed = (
        valid_records == total_records
        and duplicate_timestamps == 0
        and source_order != "mixed"
    )

    report = {
        "validation_timestamp_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "source_file": str(file_path.relative_to(PROJECT_ROOT)),
        "symbol": data.get("meta", {}).get("symbol"),
        "interval": data.get("meta", {}).get("interval"),
        "total_records": total_records,
        "valid_records": valid_records,
        "records_with_validation_issues": (
            total_records - valid_records
        ),
        "validation_passed": validation_passed,
        "source_order": source_order,
        "unique_timestamps": len(unique_timestamps),
        "quality_issues": dict(issues),
        "gaps_over_30_minutes": gaps_over_expected
    }

    report_file = REPORT_DIR / (
        file_path.stem + "_validation_report.json"
    )

    with open(report_file, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)

    logger.info("Total records: %s", total_records)
    logger.info("Valid records: %s", valid_records)
    logger.info(
        "Records with validation issues: %s",
        total_records - valid_records
    )
    logger.info("Validation passed: %s", validation_passed)
    logger.info("Quality issues: %s", dict(issues))
    logger.info("Report saved: %s", report_file)

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Validate Twelve Data XAU/USD raw records."
    )

    parser.add_argument(
        "--file",
        help="Path to a specific raw JSON file."
    )

    args = parser.parse_args()

    file_path = (
        Path(args.file).resolve()
        if args.file
        else find_latest_raw_file()
    )

    report = validate_data(file_path)

    if not report["validation_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
