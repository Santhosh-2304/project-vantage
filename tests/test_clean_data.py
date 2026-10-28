import pandas as pd

from ingestion.clean_data import clean_data


def make_df(*records):
    """Build a small DataFrame from timestamp and OHLC tuples."""
    return pd.DataFrame(
        records,
        columns=["datetime", "open", "high", "low", "close"],
    )


def test_weekend_candles_are_removed():
    df = make_df(
        ("2026-10-26 10:00:00", 100, 105, 95, 102),  # Monday
        ("2026-10-31 10:00:00", 100, 105, 95, 102),  # Saturday
        ("2026-11-01 10:00:00", 100, 105, 95, 102),  # Sunday
    )

    result = clean_data(df)

    assert len(result) == 1
    assert result.iloc[0]["datetime"].day_of_week == 0


def test_daily_break_candles_are_removed():
    df = make_df(
        ("2026-10-26 20:30:00", 100, 105, 95, 102),
        ("2026-10-26 21:00:00", 100, 105, 95, 102),
        ("2026-10-26 21:30:00", 100, 105, 95, 102),
        ("2026-10-26 22:00:00", 100, 105, 95, 102),
    )

    result = clean_data(df)

    assert list(result["datetime"].dt.strftime("%H:%M")) == [
        "20:30",
        "22:00",
    ]


def test_duplicate_timestamps_keep_last_record():
    df = make_df(
        ("2026-10-26 10:00:00", 100, 105, 95, 102),
        ("2026-10-26 10:00:00", 101, 106, 96, 103),
    )

    result = clean_data(df)

    assert len(result) == 1
    assert result.iloc[0]["open"] == 101


def test_invalid_ohlc_record_is_removed():
    df = make_df(
        ("2026-10-26 10:00:00", 100, 105, 95, 102),
        # Invalid: high is below the opening price.
        ("2026-10-26 10:30:00", 110, 105, 95, 102),
    )

    result = clean_data(df)

    assert len(result) == 1
    assert result.iloc[0]["datetime"].strftime(
        "%Y-%m-%d %H:%M:%S"
    ) == "2026-10-26 10:00:00"


def test_full_day_closure_is_removed():
    df = make_df(
        ("2026-10-26 10:00:00", 100, 105, 95, 102),
        ("2026-10-27 10:00:00", 100, 105, 95, 102),
    )

    calendar = pd.DataFrame(
        [
            {
                "date": "2026-10-26",
                "status": "full_close",
                "close_time_utc": "",
                "reason": "Test closure",
            }
        ]
    )

    result = clean_data(df, calendar=calendar)

    assert len(result) == 1
    assert result.iloc[0]["datetime"].day == 27

def test_early_close_removes_candles_extending_past_close():
    df = make_df(
        ("2026-10-26 14:00:00", 100, 105, 95, 102),
        ("2026-10-26 14:30:00", 100, 105, 95, 102),
        ("2026-10-26 15:00:00", 100, 105, 95, 102),
    )

    calendar = pd.DataFrame(
        [
            {
                "date": "2026-10-26",
                "status": "early_close",
                "close_time_utc": "14:45",
                "reason": "Test early close",
            }
        ]
    )

    result = clean_data(df, calendar=calendar)

    assert list(result["datetime"].dt.strftime("%H:%M")) == [
        "14:00"
    ]

def test_daily_break_creates_expected_90_minute_gap():
    df = make_df(
        ("2026-10-26 20:30:00", 100, 105, 95, 102),
        ("2026-10-26 21:00:00", 100, 105, 95, 102),
        ("2026-10-26 21:30:00", 100, 105, 95, 102),
        ("2026-10-26 22:00:00", 100, 105, 95, 102),
    )

    result = clean_data(df)

    gaps = result["datetime"].diff().dropna()

    assert pd.Timedelta(minutes=90) in gaps.values
