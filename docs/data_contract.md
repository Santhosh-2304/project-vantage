# Project Vantage — Data Contract

## 1. Purpose

Define the expected structure, validation rules, and filtering assumptions for the XAU/USD 30-minute historical market-data pipeline.

## 2. Data Source

- Provider: Twelve Data
- Instrument: XAU/USD
- Interval: 30 minutes
- Timestamp convention: UTC
- Raw input: `data/raw/xauusd_sample.json`

The raw source response is preserved separately from the processed dataset.

## 3. Processed Dataset

Output file: `data/processed/xauusd_cleaned.csv`

| Column | Type | Description |
|---|---|---|
| `datetime` | UTC timestamp | Candle opening timestamp |
| `open` | Numeric | Opening price |
| `high` | Numeric | Highest price during the candle |
| `low` | Numeric | Lowest price during the candle |
| `close` | Numeric | Closing price |

## 4. Validation Rules

A record must satisfy these conditions:

- Timestamp can be parsed successfully.
- Open, high, low, and close are numeric and non-null.
- High is greater than or equal to open, close, and low.
- Low is less than or equal to open, close, and high.
- Only one record is retained per timestamp.
- Records are sorted chronologically.

When duplicate timestamps occur, the current implementation retains the last record after sorting. The source does not currently provide an explicit conflict-resolution policy.

## 5. Market-Hours Filtering

- Saturday and Sunday records are excluded.
- Records whose opening timestamps fall within 21:00–21:59 UTC are excluded.
- The daily maintenance-break window is provisional and requires verification against the actual feed.
- Full-day and early closures can be specified through `data/reference/market_calendar.csv`.
- Calendar entries must represent verified closures relevant to the instrument and feed.

The processed dataset may contain gaps between consecutive timestamps. Gaps are not automatically treated as data errors.

## 6. Data Quality Checks

The current local validation process checks:

- Missing values
- Duplicate timestamps
- Weekend records
- Daily-break records
- OHLC relationships
- Time gaps between consecutive candles
- Expected behavior of the cleaning rules through automated tests

## 7. Current Baseline

Based on the current sample:

- Raw records: 5,000
- Processed records: 3,412
- Duplicate timestamps in processed data: 0
- Weekend records in processed data: 0
- Daily-break records in processed data: 0
- Missing values in processed data: 0
- Gaps greater than 30 minutes: 89
- Automated tests: 7 passed

These figures describe the current sample and may change when the input data changes.

## 8. Known Limitations

- The daily maintenance-break schedule has not yet been verified against the source feed.
- Gap classification is based on timestamp patterns and does not independently prove that every gap is expected.
- The calendar is manually maintained.
- No cloud ingestion, warehouse loading, or dbt transformations have been implemented yet.

## 9. Change Management

Changes to validation rules or market-hours assumptions should be accompanied by updated automated tests and an update to this document where relevant.