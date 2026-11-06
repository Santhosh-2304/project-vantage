
{{ config(materialized='view') }}

WITH staging AS (

    SELECT *
    FROM {{ ref('stg_xauusd_candles') }}

),

lagged AS (

    SELECT
        *,
        LAG(close) OVER (
            ORDER BY candle_timestamp
        ) AS previous_close

    FROM staging

),

metrics AS (

    SELECT
        candle_timestamp,
        candle_date,
        candle_time,

        open,
        high,
        low,
        close,

        candle_range,
        candle_body_size,

        -- Candle direction
        CASE
            WHEN close > open THEN 'bullish'
            WHEN close < open THEN 'bearish'
            ELSE 'neutral'
        END AS candle_direction,

        -- Price movement
        previous_close,

        close - previous_close AS price_change,

        SAFE_DIVIDE(
            close - previous_close,
            previous_close
        ) * 100 AS price_change_pct,

        -- Candle anatomy
        high - GREATEST(open, close) AS upper_wick,
        LEAST(open, close) - low AS lower_wick,

        SAFE_DIVIDE(
            candle_body_size,
            candle_range
        ) * 100 AS body_percentage,

        -- Time dimensions
        candle_year,
        candle_month,
        day_of_week,

        -- Ingestion metadata
        ingestion_timestamp,
        source_file

    FROM lagged

)

SELECT *
FROM metrics
