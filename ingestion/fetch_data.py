
import os
import json
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path

import requests


# --------------------------------------------------
# Project paths
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
LOG_DIR = PROJECT_ROOT / "logs"

RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------
# Logging
# --------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(
            LOG_DIR / "ingestion.log",
            encoding="utf-8"
        ),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


# --------------------------------------------------
# API configuration
# --------------------------------------------------

API_URL = "https://api.twelvedata.com/time_series"

DEFAULT_OUTPUTSIZE = 20
MAX_OUTPUTSIZE = 5000

SYMBOL = "XAU/USD"
INTERVAL = "30min"


# --------------------------------------------------
# Date handling
# --------------------------------------------------

def parse_api_datetime(value):
    """
    Parse a date/time supplied through the command line.

    Naive timestamps are interpreted as UTC.
    Timezone-aware timestamps are converted to UTC.
    """

    try:
        parsed = datetime.fromisoformat(
            value.strip().replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ValueError(
            f"Invalid date/time: {value}. "
            "Use YYYY-MM-DDTHH:MM:SS."
        ) from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


# --------------------------------------------------
# API extraction
# --------------------------------------------------

def fetch_data(
    outputsize=None,
    start_date=None,
    end_date=None
):
    """
    Fetch XAU/USD 30-minute candles.

    Supports:
    1. Latest-record extraction using outputsize.
    2. Historical extraction using start_date and end_date.
    """

    api_key = os.getenv("TWELVE_DATA_API_KEY")

    if not api_key:
        raise ValueError(
            "TWELVE_DATA_API_KEY environment variable is missing."
        )

    historical_mode = (
        start_date is not None or end_date is not None
    )

    if historical_mode and not (
        start_date and end_date
    ):
        raise ValueError(
            "Both start_date and end_date are required "
            "for historical extraction."
        )

    params = {
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "timezone": "UTC",
        "apikey": api_key
    }

    if historical_mode:

        start = parse_api_datetime(start_date)
        end = parse_api_datetime(end_date)

        if start >= end:
            raise ValueError(
                "start_date must be earlier than end_date."
            )

        params["start_date"] = (
            start.strftime("%Y-%m-%d %H:%M:%S")
        )

        params["end_date"] = (
            end.strftime("%Y-%m-%d %H:%M:%S")
        )

        request_details = {
            "mode": "historical",
            "start_date": start.isoformat(),
            "end_date": end.isoformat()
        }

        logger.info(
            "Starting historical extraction: %s to %s",
            params["start_date"],
            params["end_date"]
        )

    else:

        if outputsize is None:
            outputsize = DEFAULT_OUTPUTSIZE

        if not 1 <= outputsize <= MAX_OUTPUTSIZE:
            raise ValueError(
                f"outputsize must be between 1 and {MAX_OUTPUTSIZE}."
            )

        params["outputsize"] = outputsize

        request_details = {
            "mode": "incremental",
            "outputsize": outputsize
        }

        logger.info(
            "Starting incremental extraction. "
            "Requested records: %s",
            outputsize
        )

    try:
        response = requests.get(
            API_URL,
            params=params,
            timeout=30
        )

        response.raise_for_status()
        data = response.json()

    except requests.exceptions.RequestException:
        logger.exception("Twelve Data API request failed.")
        raise

    except ValueError:
        logger.exception("Twelve Data returned invalid JSON.")
        raise

    if not isinstance(data, dict):
        raise ValueError(
            "Unexpected API response format."
        )

    if data.get("status") == "error" or "code" in data:
        message = data.get(
            "message",
            "Unknown API error"
        )

        raise ValueError(
            f"Twelve Data API error: {message}"
        )

    values = data.get("values")

    if not isinstance(values, list) or not values:
        raise ValueError(
            "API response contains no candle records."
        )

    credits_used = response.headers.get(
        "api-credits-used"
    )

    credits_left = response.headers.get(
        "api-credits-left"
    )

    logger.info(
        "Received %s candle records.",
        len(values)
    )

    logger.info(
        "API credits used: %s | Credits remaining: %s",
        credits_used or "Not provided",
        credits_left or "Not provided"
    )

    api_usage = {
        "credits_used": credits_used,
        "credits_left": credits_left
    }

    return data, api_usage, request_details


# --------------------------------------------------
# Raw data storage
# --------------------------------------------------

def save_raw_data(data, ingestion_timestamp):
    """Save the original API response without modification."""

    filename_timestamp = ingestion_timestamp.strftime(
        "%Y%m%dT%H%M%S%fZ"
    )

    raw_file = RAW_DATA_DIR / (
        f"xauusd_30min_{filename_timestamp}.json"
    )

    with raw_file.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)

    logger.info(
        "Raw response saved to %s",
        raw_file
    )

    return raw_file


# --------------------------------------------------
# Ingestion report
# --------------------------------------------------

def save_ingestion_report(
    data,
    raw_file,
    ingestion_timestamp,
    api_usage,
    request_details
):
    """Save metadata about the extraction."""

    values = data["values"]

    candle_timestamps = [
        record["datetime"]
        for record in values
        if record.get("datetime")
    ]

    report = {
        "ingestion_timestamp": ingestion_timestamp.isoformat(),
        "symbol": data.get("meta", {}).get("symbol"),
        "interval": data.get("meta", {}).get("interval"),
        "request": request_details,
        "records_received": len(values),
        "earliest_candle": min(candle_timestamps),
        "latest_candle": max(candle_timestamps),
        "raw_file": str(
            raw_file.relative_to(PROJECT_ROOT)
        ),
        "api_credits_used": api_usage["credits_used"],
        "api_credits_left": api_usage["credits_left"],
        "status": "success"
    }

    report_file = raw_file.with_name(
        raw_file.stem + "_report.json"
    )

    with report_file.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)

    logger.info(
        "Ingestion report saved to %s",
        report_file
    )


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():

    parser = argparse.ArgumentParser(
        description="Fetch XAU/USD 30-minute market candles."
    )

    parser.add_argument(
        "--outputsize",
        type=int,
        default=DEFAULT_OUTPUTSIZE,
        help="Number of latest candles to retrieve (default: 20)."
    )

    parser.add_argument(
        "--start-date",
        type=str,
        help="Historical extraction start timestamp in UTC."
    )

    parser.add_argument(
        "--end-date",
        type=str,
        help="Historical extraction end timestamp in UTC."
    )

    args = parser.parse_args()

    if bool(args.start_date) != bool(args.end_date):
        parser.error(
            "--start-date and --end-date must be provided together."
        )

    try:

        ingestion_timestamp = datetime.now(timezone.utc)

        if args.start_date and args.end_date:

            data, api_usage, request_details = fetch_data(
                start_date=args.start_date,
                end_date=args.end_date
            )

        else:

            data, api_usage, request_details = fetch_data(
                outputsize=args.outputsize
            )

        raw_file = save_raw_data(
            data,
            ingestion_timestamp
        )

        save_ingestion_report(
            data,
            raw_file,
            ingestion_timestamp,
            api_usage,
            request_details
        )

        logger.info(
            "Ingestion completed successfully."
        )

    except Exception:
        logger.exception(
            "Ingestion failed."
        )
        raise


if __name__ == "__main__":
    main()
