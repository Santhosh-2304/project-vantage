import json
from datetime import datetime
from pathlib import Path


# 1. Define where our input data is stored.
PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = PROJECT_DIR / "data" / "raw" / "xauusd_sample.json"

# The API request used 30-minute candles.
EXPECTED_INTERVAL_MINUTES = 30

# These fields should exist in every candle.
REQUIRED_FIELDS = ["datetime", "open", "high", "low", "close"]


def load_data(file_path):
    """Load the original JSON response from disk."""

    with file_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def inspect_data(data):
    """Check the structure and basic quality of the candle records."""

    # 2. Extract metadata and candle records.
    metadata = data.get("meta", {})
    candles = data.get("values", [])

    print("\n=== Vantage: XAU/USD Data Inspection ===\n")

    print(f"Symbol: {metadata.get('symbol', 'Unknown')}")
    print(f"Interval: {metadata.get('interval', 'Unknown')}")
    print(f"Records received: {len(candles)}")

    # 3. Check whether the response contains candle records.
    if not candles:
        print("\nERROR: No candle records were found.")
        return

    # 4. Check required fields and OHLC relationships.
    invalid_records = []
    valid_timestamps = []
    duplicate_timestamps = []
    seen_timestamps = set()

    for row_number, candle in enumerate(candles, start=1):
        missing_fields = [
            field
            for field in REQUIRED_FIELDS
            if field not in candle or candle[field] is None
        ]

        if missing_fields:
            invalid_records.append(
                f"Row {row_number}: missing fields {missing_fields}"
            )
            continue

        try:
            open_price = float(candle["open"])
            high_price = float(candle["high"])
            low_price = float(candle["low"])
            close_price = float(candle["close"])

            if not all(
                value == value and abs(value) != float("inf")
                for value in [
                    open_price,
                    high_price,
                    low_price,
                    close_price,
                ]
            ):
                raise ValueError("Price contains a non-finite number")

            if min(
                open_price, high_price, low_price, close_price
            ) <= 0:
                raise ValueError("Price must be positive")

        except (ValueError, TypeError, OverflowError) as error:
            invalid_records.append(
                f"Row {row_number}: invalid price - {error}"
            )
            continue

        # A valid candle's high and low must contain its open and close.
        if (
            high_price < max(open_price, close_price)
            or low_price > min(open_price, close_price)
            or high_price < low_price
        ):
            invalid_records.append(
                f"Row {row_number}: impossible OHLC relationship"
            )

        # Parse the timestamp so we can compare candle times.
        try:
            timestamp = datetime.strptime(
                candle["datetime"], "%Y-%m-%d %H:%M:%S"
            )
        except (ValueError, TypeError) as error:
            invalid_records.append(
                f"Row {row_number}: invalid datetime - {error}"
            )
            continue

        valid_timestamps.append(timestamp)

        if timestamp in seen_timestamps:
            duplicate_timestamps.append(timestamp)
        else:
            seen_timestamps.add(timestamp)

    # 5. Sort timestamps before checking intervals.
    # The API response may list newest candles first.
    sorted_timestamps = sorted(seen_timestamps)

    gaps = []

    for previous_time, current_time in zip(
        sorted_timestamps, sorted_timestamps[1:]
    ):
        difference_minutes = (
            current_time - previous_time
        ).total_seconds() / 60

        if difference_minutes > EXPECTED_INTERVAL_MINUTES:
            gaps.append(
                (
                    previous_time,
                    current_time,
                    difference_minutes,
                )
            )

    # 6. Print the inspection results.
    print(f"\nValid timestamp records: {len(valid_timestamps)}")
    print(f"Invalid records: {len(invalid_records)}")
    print(f"Duplicate timestamps: {len(duplicate_timestamps)}")
    print(f"Intervals longer than 30 minutes: {len(gaps)}")

    if sorted_timestamps:
        print(f"\nOldest timestamp: {sorted_timestamps[0]}")
        print(f"Newest timestamp: {sorted_timestamps[-1]}")

    if gaps:
        print("\nFirst few longer intervals:")

        for previous_time, current_time, minutes in gaps[:5]:
            print(
                f"  {previous_time} -> {current_time} "
                f"({minutes:.0f} minutes)"
            )

    if invalid_records:
        print("\nFirst few invalid records:")

        for error in invalid_records[:5]:
            print(f"  {error}")

    print("\nInspection complete.")
    print("Note: Timestamp gaps require investigation; they are not")
    print("automatically proof of missing data.")


def main():
    """Run the inspection."""

    if not DATA_FILE.exists():
        print(f"ERROR: Could not find the data file: {DATA_FILE}")
        return

    try:
        data = load_data(DATA_FILE)
    except (json.JSONDecodeError, OSError) as error:
        print(f"ERROR: Could not read the JSON file: {error}")
        return

    if not isinstance(data, dict):
        print("ERROR: Expected a JSON object at the top level.")
        return

    inspect_data(data)


if __name__ == "__main__":
    main()