import json
from collections import Counter
from pathlib import Path

file_path = Path("data/raw/xauusd_sample.json")

with file_path.open("r", encoding="utf-8") as file:
    data = json.load(file)

candles = sorted(
    data["values"],
    key=lambda candle: candle["datetime"]
)

opens = [float(candle["open"]) for candle in candles]
highs = [float(candle["high"]) for candle in candles]
lows = [float(candle["low"]) for candle in candles]
closes = [float(candle["close"]) for candle in candles]

print("=== Vantage: Full Dataset Price Check ===")
print(f"Total candles: {len(candles)}")

print(f"Unique open prices: {len(set(opens))}")
print(f"Unique high prices: {len(set(highs))}")
print(f"Unique low prices: {len(set(lows))}")
print(f"Unique close prices: {len(set(closes))}")

print("\nMost common opening prices:")
for price, count in Counter(opens).most_common(10):
    print(f"{price:.5f}: {count} candles")

# Count consecutive candles with the same open.
longest_run = 1
current_run = 1

for previous, current in zip(opens, opens[1:]):
    if previous == current:
        current_run += 1
        longest_run = max(longest_run, current_run)
    else:
        current_run = 1

print(f"\nLongest consecutive run with identical opens: {longest_run}")

print("\nEarliest and latest records:")
print(candles[0])
print(candles[-1])

print("\nPrice ranges across the complete sample:")
print(f"Open:  {min(opens):.5f} to {max(opens):.5f}")
print(f"High:  {min(highs):.5f} to {max(highs):.5f}")
print(f"Low:   {min(lows):.5f} to {max(lows):.5f}")
print(f"Close: {min(closes):.5f} to {max(closes):.5f}")
