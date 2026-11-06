
import json
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

RAW_FILE = (
    PROJECT_ROOT
    / "data/raw/xauusd_30min_20261104T104304Z.json"
)

OUTPUT_DIR = PROJECT_ROOT / "data/bigquery"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / "xauusd_candles.ndjson"

ingestion_timestamp = datetime.now(timezone.utc).isoformat()

with RAW_FILE.open("r", encoding="utf-8") as file:
    data = json.load(file)

records = data["values"]

with OUTPUT_FILE.open("w", encoding="utf-8") as file:
    for record in records:
        row = {
            "datetime": record["datetime"],
            "open": record["open"],
            "high": record["high"],
            "low": record["low"],
            "close": record["close"],
            "ingestion_timestamp": ingestion_timestamp,
            "source_file": RAW_FILE.name
        }

        file.write(json.dumps(row) + "\n")

print(f"Records prepared: {len(records)}")
print(f"Output file: {OUTPUT_FILE}")
