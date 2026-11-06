
import argparse
import json
import logging
import uuid

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from google.cloud import bigquery


# --------------------------------------------------
# Configuration
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

GCP_PROJECT = "vantage-2304"
BQ_DATASET = "vantage_raw"
BQ_TABLE = "xauusd_candles"

TARGET_TABLE = (
    f"{GCP_PROJECT}.{BQ_DATASET}.{BQ_TABLE}"
)

CANDLE_INTERVAL_MINUTES = 30
COMPLETION_DELAY_SECONDS = 60

RECENT_CORRECTION_WINDOW_HOURS = 24

LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------
# Logging
# --------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(
            LOG_DIR / "bigquery_loading.log",
            encoding="utf-8"
        ),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


# --------------------------------------------------
# BigQuery schema
# --------------------------------------------------

BQ_SCHEMA = [
    bigquery.SchemaField("datetime", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("open", "NUMERIC"),
    bigquery.SchemaField("high", "NUMERIC"),
    bigquery.SchemaField("low", "NUMERIC"),
    bigquery.SchemaField("close", "NUMERIC"),
    bigquery.SchemaField("ingestion_timestamp", "TIMESTAMP"),
    bigquery.SchemaField("source_file", "STRING"),
]


# --------------------------------------------------
# Timestamp handling
# --------------------------------------------------

def parse_candle_timestamp(value):
    """Parse a Twelve Data candle timestamp as UTC."""

    timestamp = datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(
            tzinfo=timezone.utc
        )

    return timestamp.astimezone(timezone.utc)


def is_completed_candle(timestamp, ingestion_timestamp):
    """Check whether the candle has closed with a safety delay."""

    candle_close_time = timestamp + timedelta(
        minutes=CANDLE_INTERVAL_MINUTES
    )

    safe_completion_time = candle_close_time + timedelta(
        seconds=COMPLETION_DELAY_SECONDS
    )

    return safe_completion_time <= ingestion_timestamp


# --------------------------------------------------
# OHLC validation
# --------------------------------------------------

def validate_ohlc(record):
    """Validate numerical OHLC values and candle consistency."""

    try:
        prices = {
            field: Decimal(str(record[field]))
            for field in ("open", "high", "low", "close")
        }

    except (KeyError, InvalidOperation, ValueError, TypeError):
        raise ValueError(
            f"Missing or invalid OHLC values: {record}"
        )

    for field, value in prices.items():
        if not value.is_finite():
            raise ValueError(
                f"Non-finite {field} value: {value}"
            )

    open_price = prices["open"]
    high_price = prices["high"]
    low_price = prices["low"]
    close_price = prices["close"]

    if high_price < max(open_price, low_price, close_price):
        raise ValueError(
            f"Invalid candle high: {record}"
        )

    if low_price > min(open_price, high_price, close_price):
        raise ValueError(
            f"Invalid candle low: {record}"
        )

    return prices


# --------------------------------------------------
# Read and prepare records
# --------------------------------------------------

def prepare_records(raw_file):
    """Read API response and retain validated completed candles."""

    with raw_file.open("r", encoding="utf-8") as file:
        data = json.load(file)

    values = data.get("values")

    if not isinstance(values, list):
        raise ValueError(
            "Raw API response does not contain a valid values list."
        )

    report_file = raw_file.with_name(
        raw_file.stem + "_report.json"
    )

    if not report_file.exists():
        raise FileNotFoundError(
            f"Ingestion report not found: {report_file}"
        )

    with report_file.open("r", encoding="utf-8") as file:
        ingestion_report = json.load(file)

    if ingestion_report.get("status") != "success":
        raise ValueError(
            "Ingestion report does not indicate success."
        )

    ingestion_timestamp = datetime.fromisoformat(
        ingestion_report["ingestion_timestamp"]
    )

    if ingestion_timestamp.tzinfo is None:
        ingestion_timestamp = ingestion_timestamp.replace(
            tzinfo=timezone.utc
        )

    ingestion_timestamp = ingestion_timestamp.astimezone(
        timezone.utc
    )

    source_file = str(
        raw_file.resolve().relative_to(PROJECT_ROOT.resolve())
    )

    completed_records = {}

    for record in values:

        timestamp = parse_candle_timestamp(
            record["datetime"]
        )

        if not is_completed_candle(
            timestamp,
            ingestion_timestamp
        ):
            logger.info(
                "Skipping forming or recently closed candle: %s",
                timestamp.isoformat()
            )
            continue

        prices = validate_ohlc(record)

        prepared_record = {
            "datetime": timestamp.isoformat(),
            "open": str(prices["open"]),
            "high": str(prices["high"]),
            "low": str(prices["low"]),
            "close": str(prices["close"]),
            "ingestion_timestamp": ingestion_timestamp.isoformat(),
            "source_file": source_file
        }

        # Keep one record per candle timestamp.
        # Retain the last source occurrence if duplicates exist.
        completed_records[timestamp] = prepared_record

    records = [
        completed_records[timestamp]
        for timestamp in sorted(completed_records)
    ]

    logger.info(
        "Received %s records; %s completed candles are eligible.",
        len(values),
        len(records)
    )

    if records:
        logger.info(
            "Eligible candle range: %s to %s",
            records[0]["datetime"],
            records[-1]["datetime"]
        )

    return records


# --------------------------------------------------
# BigQuery loading
# --------------------------------------------------

def load_to_bigquery(
    records,
    dry_run=False,
    correction_window_hours=RECENT_CORRECTION_WINDOW_HOURS
):

    if not records:
        logger.info(
            "No completed candles to load. Skipping BigQuery MERGE."
        )
        return

    if correction_window_hours < 1:
        raise ValueError(
            "Correction window must be at least one hour."
        )

    if dry_run:
        logger.info(
            "DRY RUN: No BigQuery writes will be performed."
        )
        logger.info(
            "Completed candles prepared: %s",
            len(records)
        )
        return

    client = bigquery.Client(
        project=GCP_PROJECT
    )

    temporary_table = (
        f"{GCP_PROJECT}.{BQ_DATASET}."
        f"_xauusd_load_{uuid.uuid4().hex}"
    )

    try:

        logger.info(
            "Loading %s completed candles into temporary table.",
            len(records)
        )

        job_config = bigquery.LoadJobConfig(
            schema=BQ_SCHEMA,
            write_disposition="WRITE_TRUNCATE"
        )

        load_job = client.load_table_from_json(
            records,
            temporary_table,
            job_config=job_config
        )

        load_job.result()

        logger.info(
            "Temporary table loaded successfully."
        )

        merge_sql = f"""
        MERGE `{TARGET_TABLE}` AS target

        USING `{temporary_table}` AS source

        ON target.datetime = source.datetime

        WHEN MATCHED
        AND target.datetime >= TIMESTAMP_SUB(
            CURRENT_TIMESTAMP(),
            INTERVAL {correction_window_hours} HOUR
        )
        AND (
            target.open IS DISTINCT FROM source.open
            OR target.high IS DISTINCT FROM source.high
            OR target.low IS DISTINCT FROM source.low
            OR target.close IS DISTINCT FROM source.close
        )
        THEN UPDATE SET
            open = source.open,
            high = source.high,
            low = source.low,
            close = source.close,
            ingestion_timestamp = source.ingestion_timestamp,
            source_file = source.source_file

        WHEN NOT MATCHED THEN
            INSERT (
                datetime,
                open,
                high,
                low,
                close,
                ingestion_timestamp,
                source_file
            )
            VALUES (
                source.datetime,
                source.open,
                source.high,
                source.low,
                source.close,
                source.ingestion_timestamp,
                source.source_file
            )
        """

        logger.info(
            "Merging completed candles into %s.",
            TARGET_TABLE
        )

        merge_job = client.query(merge_sql)
        merge_job.result()

        affected_rows = merge_job.num_dml_affected_rows or 0

        logger.info(
            "BigQuery MERGE completed successfully. "
            "Total rows inserted or updated: %s",
            affected_rows,
        )

    finally:

        # Always attempt cleanup, even if the load or MERGE fails.
        try:
            client.delete_table(
                temporary_table,
                not_found_ok=True
            )

            logger.info(
                "Temporary table cleanup completed."
            )

        except Exception:
            logger.exception(
                "Temporary table cleanup failed: %s",
                temporary_table
            )


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():

    parser = argparse.ArgumentParser(
        description="Load completed XAU/USD candles into BigQuery."
    )

    parser.add_argument(
        "--file",
        required=True,
        help="Path to the extracted raw JSON file."
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Prepare records without writing to BigQuery."
    )

    parser.add_argument(
        "--correction-window-hours",
        type=int,
        default=RECENT_CORRECTION_WINDOW_HOURS,
        help="Age window in hours for updating existing candles."
    )

    args = parser.parse_args()

    if args.correction_window_hours < 1:
        parser.error(
            "--correction-window-hours must be at least 1."
        )

    raw_file = Path(args.file)

    if not raw_file.is_absolute():
        raw_file = PROJECT_ROOT / raw_file

    raw_file = raw_file.resolve()

    if not raw_file.exists():
        raise FileNotFoundError(
            f"Raw file not found: {raw_file}"
        )

    logger.info(
        "Starting BigQuery loading for %s",
        raw_file.name
    )

    records = prepare_records(raw_file)

    load_to_bigquery(
        records,
        dry_run=args.dry_run,
        correction_window_hours=args.correction_window_hours
    )

    logger.info(
        "BigQuery loading process completed."
    )


if __name__ == "__main__":
    main()
