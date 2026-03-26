# IMC Prosperity 4 — Trading Bot

Tutorial Round bot for IMC Prosperity 4.
Trades **EMERALDS** and **TOMATOES** under strict constraints: pure Python, no external libraries, ±20 position limit per symbol.

---

## Version History

| Version | EMERALDS | TOMATOES | TOTAL | Key Change |
|---------|----------|----------|-------|------------|
| V5 | 959 | 1287 | 2246 | Penny maker + WAP fair value + gentle continuous inv_shift |
| V6 | 959 | 1383 | 2342 | Threshold inv_shift (±1 at ±15) + L1 imbalance skew (±1 at ±3) |
| V7 | **1050** | -890 | 160 | Emeralds: threshold-free 10000 flattening. Tomato compressed-spread taking = disaster |
| V8 | 1050 | 1313 | 2363 | Reverted tomato to V6 base + mean reversion quote skew → adverse selection |
| V9 | 1050 | 1158 | 2208 | Inventory ladder (asymmetric thresholds + one-sided quoting) → killed throughput |
| V10 | 1050 | ~1440 | ~2490 | V7 emeralds + V6 tomatoes + tomato 180k endgame flattening |
| **V11** | **1050** | **1383** | **~2433** | V7 emeralds + V6 tomatoes exactly (cleanest stable combo) |

---

## What We Learned (Failure Log)

These were tested and definitively ruled out:

| Strategy | Result | Why |
|----------|--------|-----|
| Compressed spread taking (both sides) | -7216 on tomatoes | Taking bid AND ask simultaneously = guaranteed round-trip loss |
| Mean reversion quote skew (shift both prices) | -70 vs V6 | Shifts both bid+ask → adverse selection: fills concentrate on wrong-prediction ticks |
| L1 imbalance threshold at ±2 (down from ±3) | Worse | More false positives, adverse selection |
| Combined signal boost (L1 + mean_rev agree) | No benefit | Fires too rarely; underlying skew mechanism is flawed |
| Inventory ladder (asymmetric A/B/C) | -225 vs V6 | One-sided quoting at \|pos\|>8 too aggressive, collapses throughput |
| MA crossover (5/20) | -4628 | Trend-following on mean-reverting asset |
| Adaptive spread / spread=2 everywhere | Worse | Adverse selection eats the edge |
| Multi-level emerald quotes | Worse | Splits fills, gives counterparty better prices |
| Panic/urgency liquidation | Worse | Selling at 10001 = terrible prices |
| OU/SDE/Feynman-Kac fair value | Negligible | Shifts price <1 point, pure overhead |
| Aggressive SMA-based taking | Worse | SMA lags; "mispriced" orders aren't mispriced |
| OBI (full book) prediction | 2.8% accuracy | Worse than random |

---

## Current Strategy (V11)

### EMERALDS — V7 Logic (1050, theoretical ceiling)

Fair value: **10,000** (hardcoded).

**Phase 0 — Flatten at fair value:**
Every tick, if there's a resting order at exactly 10000 and we have a position, take it to move toward zero. This is zero-cost since 10000 = MtM price. Only flattens toward zero, never overshoots.

**Phase 1 — Snipe when stuck:**
When position ≥ 15 (or ≤ -15), aggressively sweep any 10000+ bids (or 10000- asks) to free up capacity for penny fills.

**Phase 2 — Penny maker with endgame:**
Quote `best_bid + 1` / `best_ask - 1`, clamped to 9999 / 10001.
After timestamp 160,000: switch to closing-biased quotes (9993/10001 when long, 9999/10007 when short) to flatten position before sim end.

---

### TOMATOES — V6 Logic (1383, best proven)

Fair value: **WAP** — `(best_bid × ask_vol + best_ask × bid_vol) / (bid_vol + ask_vol)`.

**Penny maker:**
```
bid_price = best_bid + 1 + inv_shift + l1_skew
ask_price = best_ask - 1 + inv_shift + l1_skew
```

**Inventory shift:** `±1 tick` when `|position| > 15`. Neutral otherwise. Applied to both quotes.

**L1 imbalance skew:** When `bid_vol - ask_vol ≥ 3`, shift both quotes +1. When `≤ -3`, shift -1.

**Safety clamps:** `bid < wap_int`, `ask > wap_int`. If they cross, reset to `wap ± 1`.

---

## Files

| File | Description |
|------|-------------|
| `trader.py` | Main submission (V11) |
| `trader2.py` | V6 reference |
| `trader_a.py` | Experiment: SPREAD=2, OBI_WEIGHT=10 |
| `trader_b.py` | Experiment: SPREAD=2, OBI disabled |
| `trader_c.py` | Experiment: SPREAD=2, aggressive inv shift |
| `offline_analyzer.py` | Local backtester using CSV price/trade data |
| `prices_round_0_day_-1.csv` | Market data for backtesting |
| `prices_round_0_day_-2.csv` | Market data for backtesting |

---

## Constraints

- Pure Python only — no `pandas`, `numpy`, or any external library
- All order prices must be integers
- Position hard limit: **±20** per symbol, enforced on every order path
- Return signature: `(orders: dict[str, list[Order]], conversions: int, traderData: str)`
- Single file delivery: `trader.py`
