# IMC Prosperity 4 — Trading Bot

Round 1 baseline ("Gold Standard") for the IMC Prosperity 4 competition.
Trades two symbols — **EMERALDS** and **TOMATOES** — under strict constraints:
pure Python, no external libraries, no persistent instance variables.

**Round 0 result:** ~1,550 PnL

---

## Architecture

### `RollingStats`
Fixed-window rolling statistics backed by a plain list. Upgraded from the
Tutorial Round `RollingAverage` — adds higher-order statistics for future
Bollinger Band / Z-score strategies.

| Method | Returns | Notes |
|---|---|---|
| `update(value)` | — | Appends value; evicts oldest when over `period` |
| `average()` | `float \| None` | Population mean; `None` until window full |
| `variance()` | `float \| None` | Σ(x−μ)²/N; `None` until window full |
| `std_dev()` | `float \| None` | √variance; `None` until window full |
| `z_score(value)` | `float \| None` | (value−μ)/σ; `None` if window not full or σ=0 |
| `to_list()` | `list[float]` | Raw window for traderData serialisation |

### `PositionManager`
Static helpers enforcing the ±20 position hard limit on every order path.

| Method | Returns |
|---|---|
| `max_buy_quantity(position, limit=20)` | `limit - position` |
| `max_sell_quantity(position, limit=20)` | `position + limit` |

### `Trader`
Main class. The engine calls `run(state)` every tick.

**Return signature:** `(orders: dict[str, list[Order]], conversions: int, traderData: str)`

State is persisted across ticks via the `traderData` JSON string — the only
form of memory available in this environment. The `run()` method acts as a
**symbol router**, dispatching each asset to its dedicated strategy function.

---

## Strategies

### EMERALDS — Hybrid Sniper + Dynamic Penny Maker

**Fair value:** hardcoded at **10,000**.

**Phase 1 — Taker (Sniper):**
- Scans `sell_orders` sorted lowest-first. Takes any ask **below** 10,000 up to remaining buy capacity.
- Scans `buy_orders` sorted highest-first. Takes any bid **above** 10,000 up to remaining sell capacity.
- Virtual position is updated after each fill so subsequent snipes and maker quotes never breach ±20.

**Phase 2 — Maker (Dynamic Pennying):**
After sniping, reads the remaining book and places penny quotes for leftover capacity:
```
bid_price = min(best_bid + 1, EMERALD_FAIR - 1)   # penny the bid, clamped below fair value
ask_price = max(best_ask - 1, EMERALD_FAIR + 1)   # penny the ask, clamped above fair value
```
Falls back to `9998` / `10002` if either side of the book is empty.

**Tunable constants:**

| Constant | Default | Description |
|---|---|---|
| `EMERALD_FAIR` | `10000` | Hard-coded fair value |
| `EMERALD_DEFAULT_SPREAD` | `2` | Fallback half-spread when book is empty |

---

### TOMATOES — Velocity-Based Regime Switch

A microstructure-aware strategy that detects trending vs. ranging conditions
using a **5-tick WAP velocity** thermostat and switches execution logic accordingly.

#### 1. Weighted Average Price (WAP)
Base fair value using Level 1 order book volumes:
```
wap = (best_bid × best_ask_vol + best_ask × best_bid_vol) / (best_bid_vol + best_ask_vol)
```

#### 2. Velocity Thermostat
```
velocity = wap[now] − wap[5 ticks ago]
```
A 20-period `RollingStats` window tracks WAP history. The 5-tick lookback
balances responsiveness against micro-noise.

#### 3. Regime Switch

| Condition | Regime | Action |
|---|---|---|
| `velocity > 8` | **Bull breakout** | Aggressive bid at `round(wap) − 1`; no asks |
| `velocity < −8` | **Bear breakout** | Aggressive ask at `round(wap) + 1`; no bids |
| `−8 ≤ velocity ≤ 8` | **Ranging** | WAP + inventory-skew passive market maker |

**Ranging market maker:**
```
inventory_shift = -(position / 20.0) × TOMATO_INV_MAX_SHIFT
target_price    = wap + inventory_shift
bid_price       = int(round(target_price)) - TOMATO_SPREAD
ask_price       = int(round(target_price)) + TOMATO_SPREAD
```

At max long (+20): quotes shift −3 ticks (lowers ask, raises bid cost → discourages more buying).  
At max short (−20): quotes shift +3 ticks (lowers bid cost, raises ask → discourages more selling).

**Tunable constants:**

| Constant | Default | Description |
|---|---|---|
| `TOMATO_WAP_PERIOD` | `20` | Rolling WAP window length |
| `TOMATO_INV_MAX_SHIFT` | `3` | Max inventory skew in ticks |
| `TOMATO_SPREAD` | `3` | Fixed half-spread in ranging regime |
| `VELOCITY_THRESHOLD` | `8` | 5-tick WAP delta to trigger breakout regime |

---

### PAIRS TRADING — Skeleton (Round 1)

`_run_pairs_trading(state, asset_a, asset_b, spread_stats)` is wired into
the router but commented out pending Round 1 asset confirmation.

**Planned logic:**
- Compute mid-price spread: `current_spread = mid_a − mid_b`
- Track spread in a 20-period `RollingStats` window
- Execute on Z-score extremes:
  - `spread_z > 2.0` → Short A, Buy B (spread reverts down)
  - `spread_z < −2.0` → Buy A, Short B (spread reverts up)

---

## State Persistence (`traderData`)

```json
{
  "tomato_window": [float, ...],
  "spread_window": [float, ...]
}
```

Both rolling windows are serialised as JSON each tick and deserialised at
the start of the next tick. EMERALDS logic is stateless.

---

## Constraints

- Pure Python only — no `pandas`, `numpy`, or any external library (`math` from stdlib is allowed)
- All order prices must be integers (`int(round(...))`)
- Position hard limit: **±20** per symbol, enforced on every order path
- Single file delivery: `trader.py`
