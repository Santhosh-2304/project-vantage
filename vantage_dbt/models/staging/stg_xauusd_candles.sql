
{{ config(materialized='view') }}

WITH source_data AS (

    SELECT *
    FROM {{ source('vantage_raw', 'xauusd_candles') }}

),

standardized AS (

    SELECT
        SAFE_CAST(datetime AS TIMESTAMP) AS candle_timestamp,

        SAFE_CAST(open AS NUMERIC) AS open,
        SAFE_CAST(high AS NUMERIC) AS high,
        SAFE_CAST(low AS NUMERIC) AS low,
        SAFE_CAST(close AS NUMERIC) AS close,

        SAFE_CAST(ingestion_timestamp AS TIMESTAMP)
            AS ingestion_timestamp,

        source_file

    FROM source_data

),

enriched AS (

    SELECT
        candle_timestamp,
        open,
        high,
        low,
        close,
        ingestion_timestamp,
        source_file,

        DATE(candle_timestamp) AS candle_date,
        TIME(candle_timestamp) AS candle_time,
        EXTRACT(YEAR FROM candle_timestamp) AS candle_year,
        EXTRACT(MONTH FROM candle_timestamp) AS candle_month,
        EXTRACT(DAYOFWEEK FROM candle_timestamp) AS day_of_week,

        high - low AS candle_range,
        ABS(close - open) AS candle_body_size

    FROM standardized

)


SELECT
    -- Business key
    candle_timestamp,

    -- Time dimensions
    candle_date,
    candle_time,

    -- Original market metrics
    open,
    high,
    low,
    close,

    -- Derived market metrics
    candle_range,
    candle_body_size,

    -- Additional time dimensions
    candle_year,
    candle_month,
    day_of_week,

    -- Ingestion metadata
    ingestion_timestamp,
    source_file

FROM enriched
