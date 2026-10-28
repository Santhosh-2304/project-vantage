# Project Vantage

### An End-to-End Market Data Engineering Pipeline

Project Vantage is a data engineering portfolio project that builds a reliable pipeline for collecting, validating, processing, and analyzing historical XAU/USD (gold versus the US dollar) market data.

The project demonstrates practical data engineering skills using Python, Google Cloud Platform, BigQuery, dbt, and Apache Airflow.

## Objectives

- Ingest historical market data from Twelve Data.
- Validate timestamps and OHLC price relationships.
- Build a reproducible data cleaning pipeline.
- Store raw data separately from processed analytical data.
- Transform and test datasets using dbt.
- Orchestrate pipeline execution.
- Build an analytics dashboard.

## Technology Stack

| Technology | Purpose |
|---|---|
| Python | Data ingestion, validation, and processing |
| pandas | Data manipulation |
| pytest | Automated testing |
| Git and GitHub | Version control |
| Google Cloud Storage | Raw data storage |
| BigQuery | Cloud data warehouse |
| dbt | SQL transformations and data tests |
| Apache Airflow | Workflow orchestration |
| Looker Studio | Data visualization |

## Current Progress

- Historical XAU/USD 30-minute sample obtained from Twelve Data.
- Data cleaning and validation implemented.
- Weekend and provisional maintenance-break filtering implemented.
- Optional market calendar support implemented.
- Candle gap analysis implemented.
- Seven automated tests passing.
- Data contract documented.
- GitHub repository established.

## Data Quality

The current sample contains 5,000 raw records and 3,412 processed records.

The processed dataset has been checked for duplicate timestamps, missing values, weekend records, and records within the configured maintenance-break window.

The maintenance-break schedule remains provisional and requires verification against the data provider's actual trading-session behavior.

## Planned Architecture

Twelve Data API  
→ Python ingestion and validation  
→ Google Cloud Storage  
→ BigQuery  
→ dbt transformations  
→ Looker Studio dashboard

Apache Airflow will be introduced later to orchestrate the pipeline.

## Repository Structure

```text
vantage/
├── data/
│   ├── raw/
│   ├── processed/
│   └── reference/
├── docs/
│   └── data_contract.md
├── ingestion/
│   ├── clean_data.py
│   ├── check_gaps.py
│   ├── check_price_pattern.py
│   ├── analyse_market_hours.py
│   └── inspect_data.py
└── tests/
    └── test_clean_data.py
```

Raw and processed datasets are excluded from Git. The data folders are maintained locally, while reference configuration and project code can be version-controlled.

## Project Status

**Phase 1: Local data engineering foundations — in progress**

The next milestone is cloud storage and warehouse integration.