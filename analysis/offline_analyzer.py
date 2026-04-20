"""
offline_analyzer.py (Fixed Version)
Reads a Prosperity CSV, filters TOMATOES, and detects massive 15+ point 
swings regardless of whether the day starts with a crash or a spike.
"""

import csv
import sys

CSV_PATH = sys.argv[1] if len(sys.argv) > 1 else "data.csv"
SMA_WINDOW = 5
SWING_THRESHOLD = 15.0

def load_tomato_rows(path: str):
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            if row["product"].strip() == "TOMATOES":
                rows.append((int(row["timestamp"]), float(row["mid_price"])))
    rows.sort(key=lambda x: x[0])
    return rows

def sma(prices, window):
    return [sum(prices[i - window + 1 : i + 1]) / window for i in range(window - 1, len(prices))]

def better_detect_extremes(smoothed, sma_timestamps, threshold):
    if len(smoothed) < 3:
        return {}
    
    oracle = {}
    last_peak = smoothed[0]
    last_valley = smoothed[0]
    
    # FIX: Dynamically track whether the first move is a crash or a spike
    state = "UNKNOWN" 
    
    for i in range(1, len(smoothed) - 1):
        price = smoothed[i]
        is_local_max = price > smoothed[i - 1] and price > smoothed[i + 1]
        is_local_min = price < smoothed[i - 1] and price < smoothed[i + 1]
        
        if state == "UNKNOWN":
            if is_local_max and (price - smoothed[0]) >= threshold:
                oracle[sma_timestamps[i]] = -20
                last_peak = price
                state = "LOOKING_FOR_VALLEY"
            elif is_local_min and (smoothed[0] - price) >= threshold:
                oracle[sma_timestamps[i]] = 20
                last_valley = price
                state = "LOOKING_FOR_PEAK"
                
        elif state == "LOOKING_FOR_PEAK":
            if is_local_max and (price - last_valley) >= threshold:
                oracle[sma_timestamps[i]] = -20
                last_peak = price
                state = "LOOKING_FOR_VALLEY"
                
        elif state == "LOOKING_FOR_VALLEY":
            if is_local_min and (last_peak - price) >= threshold:
                oracle[sma_timestamps[i]] = 20
                last_valley = price
                state = "LOOKING_FOR_PEAK"

    return oracle

if __name__ == "__main__":
    rows = load_tomato_rows(CSV_PATH)

    if len(rows) < SMA_WINDOW + 2:
        print("self.ORACLE_TRADES = {}")
        sys.exit(0)

    timestamps = [r[0] for r in rows]
    prices = [r[1] for r in rows]

    smoothed = sma(prices, SMA_WINDOW)
    sma_timestamps = timestamps[SMA_WINDOW - 1:]

    oracle = better_detect_extremes(smoothed, sma_timestamps, SWING_THRESHOLD)

    if not oracle:
        print(f"# No swings found.", file=sys.stderr)
        print("self.ORACLE_TRADES = {}")
    else:
        print(f"# Found {len(oracle)} massive swings!", file=sys.stderr)
        print("self.ORACLE_TRADES = {")
        for ts, pos in sorted(oracle.items()):
            print(f"    {ts}: {pos},")
        print("}")