from pathlib import Path

import pandas as pd

INPUT_FILE = Path("data/processed/xauusd_cleaned.csv")
EXPECTED_INTERVAL = pd.Timedelta(minutes=30)


def main():
    df = pd.read_csv(INPUT_FILE, parse_dates=["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)

    df["previous_datetime"] = df["datetime"].shift(1)
    df["time_gap"] = df["datetime"].diff()

    gaps = df[df["time_gap"] > EXPECTED_INTERVAL].copy()

    print("=== Project Vantage: Candle Gap Analysis ===")
    print(f"Total candles: {len(df)}")
    print(f"Gaps greater than 30 minutes: {len(gaps)}")

    if gaps.empty:
        print("No gaps found.")
        return

    print("\nLargest gaps, with preceding timestamps:")

    largest_gaps = gaps.nlargest(15, "time_gap")

    print(
        largest_gaps[
            ["previous_datetime", "datetime", "time_gap"]
        ].to_string(index=False)
    )

    print("\nGap duration distribution:")

    print(
        gaps["time_gap"]
        .value_counts()
        .sort_index()
        .to_string()
    )


if __name__ == "__main__":
    main()
