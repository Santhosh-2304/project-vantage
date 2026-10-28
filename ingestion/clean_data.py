import json
from pathlib import Path

import pandas as pd

RAW_FILE = Path("data/raw/xauusd_sample.json")
OUTPUT_FILE = Path("data/processed/xauusd_cleaned.csv")
CALENDAR_FILE = Path("data/reference/market_calendar.csv")

PRICE_COLUMNS = ["open", "high", "low", "close"]


def clean_data(df, calendar=None):
    """Validate, clean, and filter XAU/USD candle records."""
    df = df.copy()

    # Parse timestamps and price columns.
    df["datetime"] = pd.to_datetime(
        df["datetime"],
        format="%Y-%m-%d %H:%M:%S",
        errors="coerce",
        utc=True,
    )

    for column in PRICE_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    # Remove records with invalid timestamps or prices.
    df = df.dropna(subset=["datetime"] + PRICE_COLUMNS)

    # Validate OHLC relationships.
    valid_ohlc = (
        (df["high"] >= df[["open", "close", "low"]].max(axis=1))
        & (df["low"] <= df[["open", "close", "high"]].min(axis=1))
    )
    df = df[valid_ohlc]

    # Sort chronologically and retain one record per timestamp.
    df = df.sort_values("datetime")
    df = df.drop_duplicates(subset=["datetime"], keep="last")

    # Exclude Saturday and Sunday.
    df = df[df["datetime"].dt.day_of_week < 5]

    # Exclude the provisional 21:00–22:00 UTC maintenance break.
    df = df[df["datetime"].dt.hour != 21]

    # Apply the optional market calendar.
    if calendar is not None and not calendar.empty:
        calendar = calendar.copy()
        calendar["date"] = pd.to_datetime(
            calendar["date"], errors="raise"
        ).dt.date

        # Exclude full-day closures.
        full_closure_dates = set(
            calendar.loc[
                calendar["status"] == "full_close", "date"
            ]
        )

        df = df[
            ~df["datetime"].dt.date.isin(full_closure_dates)
        ]

        # Exclude candles opening at or after an early closing time.
        early_closures = calendar[
            calendar["status"] == "early_close"
        ]

        for _, closure in early_closures.iterrows():
            if pd.isna(closure["close_time_utc"]):
                raise ValueError(
                    f"Missing close_time_utc for {closure['date']}"
                )

            close_hour, close_minute = map(
                int, closure["close_time_utc"].split(":")
            )

            close_timestamp = pd.Timestamp(
                f"{closure['date']} "
                f"{close_hour:02d}:{close_minute:02d}",
                tz="UTC",
            )

            df = df[
                ~(
                    (df["datetime"].dt.date == closure["date"])
                    & (df["datetime"] + pd.Timedelta(minutes=30) > close_timestamp)
                )
            ]

    return df.reset_index(drop=True)


def main():
    # Load the original API response.
    with RAW_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    raw_df = pd.DataFrame(data["values"])
    original_count = len(raw_df)

    # Load the calendar if it exists and contains entries.
    calendar = None
    if CALENDAR_FILE.exists():
        loaded_calendar = pd.read_csv(CALENDAR_FILE)
        if not loaded_calendar.empty:
            calendar = loaded_calendar

    cleaned_df = clean_data(raw_df, calendar=calendar)

    # Save the processed dataset.
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    cleaned_df.to_csv(OUTPUT_FILE, index=False)

    print("=== Project Vantage: Data Cleaning ===")
    print(f"Original records: {original_count}")
    print(f"Final records: {len(cleaned_df)}")
    print(f"Records removed: {original_count - len(cleaned_df)}")
    print(f"Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()