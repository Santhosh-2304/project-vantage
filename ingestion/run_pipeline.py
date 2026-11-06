import json
import logging
import subprocess
import sys

from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.cloud import bigquery


# --------------------------------------------------
# Project configuration
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

GCP_PROJECT = "vantage-2304"
BQ_DATASET = "vantage_raw"
BQ_TABLE = "xauusd_candles"

TARGET_TABLE = f"{GCP_PROJECT}.{BQ_DATASET}.{BQ_TABLE}"

RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
PIPELINE_REPORT_DIR = PROJECT_ROOT / "data" / "pipeline_reports"
VALIDATION_REPORT_DIR = PROJECT_ROOT / "data" / "validation_reports"

PIPELINE_REPORT_DIR.mkdir(parents=True, exist_ok=True)

# Two 30-minute candles of overlap.
OVERLAP_MINUTES = 60


# --------------------------------------------------
# Logging
# --------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


# --------------------------------------------------
# BigQuery watermark
# --------------------------------------------------

def get_latest_loaded_timestamp():
    """
    Read the latest successfully persisted candle timestamp.

    BigQuery is the source of truth for the watermark.
    """

    client = bigquery.Client(project=GCP_PROJECT)

    query = f"""
        SELECT MAX(datetime) AS latest_candle
        FROM `{TARGET_TABLE}`
    """

    result = list(client.query(query).result())

    latest_candle = result[0].latest_candle

    if latest_candle is None:
        raise RuntimeError(
            "The BigQuery target table is empty. "
            "Run the historical bootstrap process first."
        )

    if latest_candle.tzinfo is None:
        latest_candle = latest_candle.replace(
            tzinfo=timezone.utc
        )

    return latest_candle.astimezone(timezone.utc)


def verify_latest_loaded_timestamp(previous_watermark):
    """
    Confirm that the target table has not regressed
    after the BigQuery loading stage.
    """

    current_watermark = get_latest_loaded_timestamp()

    if current_watermark < previous_watermark:
        raise RuntimeError(
            "BigQuery watermark regressed after loading. "
            f"Before: {previous_watermark.isoformat()}, "
            f"After: {current_watermark.isoformat()}"
        )

    return current_watermark


# --------------------------------------------------
# Helper functions
# --------------------------------------------------

def get_raw_files():
    """Return raw API response files, excluding report files."""

    return {
        path.resolve()
        for path in RAW_DATA_DIR.glob("xauusd_30min_*.json")
        if not path.stem.endswith("_report")
    }


def load_json_report(report_path):
    """Load a JSON report if it exists."""

    if not report_path.exists():
        return {}

    with report_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def run_stage(stage_name, command):
    """Execute a pipeline stage and log its result."""

    logger.info("Starting stage: %s", stage_name)

    subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=True
    )

    logger.info("Completed stage: %s", stage_name)


# --------------------------------------------------
# Main pipeline
# --------------------------------------------------

def run_pipeline():

    started_at = datetime.now(timezone.utc)
    run_id = started_at.strftime("%Y%m%dT%H%M%S%fZ")

    report = {
        "run_id": run_id,
        "pipeline_name": "xauusd_ingestion",
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": None,
        "duration_seconds": None,
        "status": "running",
        "watermark_before": None,
        "extraction_start": None,
        "extraction_end": None,
        "watermark_after": None,
        "raw_file": None,
        "records_extracted": 0,
        "records_validated": 0,
        "validation_passed": False,
        "stages": {},
        "error": None
    }

    try:

        # ------------------------------------------
        # Stage 0: Read watermark
        # ------------------------------------------

        logger.info("Reading BigQuery ingestion watermark.")

        watermark_before = get_latest_loaded_timestamp()

        extraction_start = (
            watermark_before - timedelta(
                minutes=OVERLAP_MINUTES
            )
        )

        extraction_end = datetime.now(timezone.utc)

        if extraction_start >= extraction_end:
            raise RuntimeError(
                "Calculated extraction start is not earlier "
                "than extraction end."
            )

        report["watermark_before"] = (
            watermark_before.isoformat()
        )

        report["extraction_start"] = (
            extraction_start.isoformat()
        )

        report["extraction_end"] = (
            extraction_end.isoformat()
        )

        report["stages"]["watermark"] = {
            "status": "success",
            "latest_loaded_timestamp": watermark_before.isoformat(),
            "overlap_minutes": OVERLAP_MINUTES,
            "extraction_start": extraction_start.isoformat(),
            "extraction_end": extraction_end.isoformat()
        }

        logger.info(
            "Latest loaded candle: %s",
            watermark_before.isoformat()
        )

        logger.info(
            "Extraction window: %s to %s",
            extraction_start.isoformat(),
            extraction_end.isoformat()
        )

        # ------------------------------------------
        # Stage 1: Extraction
        # ------------------------------------------

        raw_files_before = get_raw_files()

        run_stage(
            "extraction",
            [
                sys.executable,
                "ingestion/fetch_data.py",
                "--start-date",
                extraction_start.strftime("%Y-%m-%dT%H:%M:%S"),
                "--end-date",
                extraction_end.strftime("%Y-%m-%dT%H:%M:%S")
            ]
        )

        raw_files_after = get_raw_files()

        new_raw_files = raw_files_after - raw_files_before

        if len(new_raw_files) != 1:
            raise RuntimeError(
                "Expected exactly one new raw JSON file, "
                f"but found {len(new_raw_files)}."
            )

        raw_file = next(iter(new_raw_files))

        report["raw_file"] = str(
            raw_file.relative_to(PROJECT_ROOT)
        )

        ingestion_report_path = raw_file.with_name(
            raw_file.stem + "_report.json"
        )

        ingestion_report = load_json_report(
            ingestion_report_path
        )

        if ingestion_report.get("status") != "success":
            raise RuntimeError(
                "Ingestion report is missing or unsuccessful."
            )

        report["records_extracted"] = ingestion_report.get(
            "records_received", 0
        )

        report["stages"]["extraction"] = {
            "status": "success",
            "raw_file": report["raw_file"],
            "records_extracted": report["records_extracted"],
            "ingestion_report": str(
                ingestion_report_path.relative_to(PROJECT_ROOT)
            )
        }

        logger.info(
            "Extraction completed. Records received: %s",
            report["records_extracted"]
        )

        # ------------------------------------------
        # Stage 2: Validation
        # ------------------------------------------

        run_stage(
            "validation",
            [
                sys.executable,
                "ingestion/validate_data.py",
                "--file",
                str(raw_file)
            ]
        )

        validation_report_path = (
            VALIDATION_REPORT_DIR
            / f"{raw_file.stem}_validation_report.json"
        )

        validation_report = load_json_report(
            validation_report_path
        )

        if not validation_report:
            raise RuntimeError(
                "Validation report was not generated."
            )

        report["records_validated"] = validation_report.get(
            "valid_records", 0
        )

        report["validation_passed"] = validation_report.get(
            "validation_passed", False
        )

        report["stages"]["validation"] = {
            "status": (
                "success"
                if report["validation_passed"]
                else "failed"
            ),
            "records_validated": report["records_validated"],
            "validation_report": str(
                validation_report_path.relative_to(PROJECT_ROOT)
            ),
            "quality_issues": validation_report.get(
                "quality_issues", {}
            )
        }

        if not report["validation_passed"]:
            raise RuntimeError(
                "Data validation failed. "
                "Check the validation report."
            )

        logger.info(
            "Validation passed. Valid records: %s",
            report["records_validated"]
        )

        # ------------------------------------------
        # Stage 3: BigQuery loading
        # ------------------------------------------

        run_stage(
            "bigquery_loading",
            [
                sys.executable,
                "ingestion/load_to_bigquery.py",
                "--file",
                str(raw_file)
            ]
        )

        report["stages"]["bigquery_loading"] = {
            "status": "success",
            "target_table": TARGET_TABLE
        }

        # ------------------------------------------
        # Stage 4: Verify watermark
        # ------------------------------------------

        watermark_after = verify_latest_loaded_timestamp(
            watermark_before
        )

        report["watermark_after"] = (
            watermark_after.isoformat()
        )

        report["stages"]["watermark_verification"] = {
            "status": "success",
            "latest_loaded_timestamp": watermark_after.isoformat()
        }

        logger.info(
            "Updated BigQuery watermark: %s",
            watermark_after.isoformat()
        )

        # ------------------------------------------
        # Pipeline completed successfully
        # ------------------------------------------

        report["status"] = "success"

    except subprocess.CalledProcessError as error:

        report["status"] = "failed"

        report["error"] = (
            f"Stage command failed with exit code "
            f"{error.returncode}: {error.cmd}"
        )

        report["failed_command"] = error.cmd

        logger.exception("Pipeline stage execution failed.")

    except Exception as error:

        report["status"] = "failed"
        report["error"] = str(error)

        logger.exception("Pipeline execution failed.")

    finally:

        finished_at = datetime.now(timezone.utc)

        report["finished_at_utc"] = finished_at.isoformat()

        report["duration_seconds"] = (
            finished_at - started_at
        ).total_seconds()

        report_file = (
            PIPELINE_REPORT_DIR
            / f"pipeline_{run_id}.json"
        )

        temporary_report_file = report_file.with_suffix(
            ".tmp"
        )

        with temporary_report_file.open(
            "w",
            encoding="utf-8"
        ) as file:
            json.dump(report, file, indent=2)

        temporary_report_file.replace(report_file)

        logger.info("----------------------------------------")
        logger.info("Pipeline status: %s", report["status"])
        logger.info(
            "Records extracted: %s",
            report["records_extracted"]
        )
        logger.info(
            "Records validated: %s",
            report["records_validated"]
        )
        logger.info(
            "Duration: %.2f seconds",
            report["duration_seconds"]
        )
        logger.info("Pipeline report: %s", report_file)
        logger.info("----------------------------------------")

    if report["status"] != "success":
        raise SystemExit(1)


if __name__ == "__main__":
    run_pipeline()
