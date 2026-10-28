import json
from collections import Counter
from datetime import datetime
from pathlib import Path

SOURCE_FILE = Path("data/raw/xauusd_sample.json")


def main():
    with SOURCE_FILE.open() as file:
        data = json.load(file)

    candles = data["values"]
    weekday_counts = Counter()
    hourly_counts = Counter()
    weekend_candles = []

    for candle in candles:
        timestamp = datetime.strptime(
            candle["datetime"], "%Y-%m-%d %H:%M:%S"
        )

        # This analysis assumes the timestamps represent UTC.
        weekday_counts[timestamp.strftime("%A")] += 1
        hourly_counts[timestamp.hour] += 1

        if timestamp.weekday() >= 5:
            weekend_candles.append(candle)

    print("=== Vantage: Market Hours Investigation ===")
    print(f"Total candles: {len(candles)}")

    print("\nCandles by UTC weekday:")
    for day in [
        "Monday", "Tuesday", "Wednesday",
        "Thursday", "Friday", "Saturday", "Sunday"
    ]:
        print(f"{day}: {weekday_counts[day]}")

    print("\nCandles by UTC hour:")
    for hour in range(24):
        print(f"{hour:02d}:00–{hour:02d}:59: {hourly_counts[hour]}")

    print(f"\nWeekend candles: {len(weekend_candles)}")

    print("\nFirst 10 weekend records:")
    for candle in weekend_candles[:10]:
        print(
            f"{candle['datetime']} | "
            f"O={candle['open']} H={candle['high']} "
            f"L={candle['low']} C={candle['close']}"
        )

    print("\nAnalysis complete.")
    print("This is a diagnostic report, not an exclusion rule.")


if __name__ == "__main__":
    main()
