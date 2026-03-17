# IMC Prosperity 4 — Trading Bot

A single-file algorithmic trading bot for the IMC Prosperity 4 competition (Tutorial Round). Trades two symbols — **EMERALDS** and **TOMATOES** — under strict constraints: pure Python, no external libraries, no persistent instance variables.

---

## Architecture

### `RollingAverage`
Fixed-window rolling average backed by a plain list.

| Method | Description |
|---|---|
| `update(value)` | Appends value, evicts oldest when over `period` |
| `average()` | Returns mean when window is full, else `None` |
| `to_list()` | Returns raw window for serialization |

### `PositionManager`
Static helpers that enforce the ±20 position hard limit on every order.

| Method | Returns |
|---|---|
| `max_buy_quantity(position, limit=20)` | `limit - position` |
| `max_sell_quantity(position, limit=20)` | `position + limit` |

### `Trader`
Main class. The engine calls `run(state)` every tick.

**Return signature:** `(orders: dict[str, list[Order]], conversions: int, traderData: str)`

State is persisted across ticks via the `traderData` JSON string — the only form of memory available in this environment.

---

## Strategies

### EMERALDS — Hybrid Sniper + Passive Maker

**Fair value:** hardcoded at **10,000**.

**Phase 1 — Taker (Sniper):**
- Scans `sell_orders` sorted lowest-first. Takes any ask **below** 10,000, up to remaining buy capacity.
- Scans `buy_orders` sorted highest-first. Takes any bid **above** 10,000, up to remaining sell capacity.
- Virtual position is updated after each fill so subsequent snipes and maker quotes never exceed the ±20 limit.

**Phase 2 — Maker (Passive):**
- After sniping, quotes the remaining capacity passively:
  - Bid: `9998` (`EMERALD_FAIR - EMERALD_DEFAULT_SPREAD`)
  - Ask: `10002` (`EMERALD_FAIR + EMERALD_DEFAULT_SPREAD`)

**Tunable constants:**

| Constant | Default | Description |
|---|---|---|
| `EMERALD_FAIR` | `10000` | Hard-coded fair value |
| `EMERALD_DEFAULT_SPREAD` | `2` | Passive quote half-spread |

---

### TOMATOES — Alpha Equation Market Maker

A microstructure-aware passive market maker. Fair value and spread are dynamically computed each tick from five signal components.

#### 1. Weighted Average Price (WAP)
Base fair value using Level 1 order book volumes:

```
wap = (best_bid × best_ask_vol + best_ask × best_bid_vol) / (best_bid_vol + best_ask_vol)
```

The WAP is added to a 20-period rolling window for volatility calculation.

#### 2. OBI Momentum Shift
Order Book Imbalance detects short-term directional pressure:

```
obi = (best_bid_vol - best_ask_vol) / (best_bid_vol + best_ask_vol)

momentum_shift = +1  if obi >  0.5   (buy pressure)
momentum_shift = -1  if obi < -0.5   (sell pressure)
momentum_shift =  0  otherwise
```

#### 3. Inventory Skew
Shifts quotes to lean against the current position, reducing inventory risk:

```
inventory_shift = -(position / 20.0) × TOMATO_INV_MAX_SHIFT
```

At max long (+20): quotes shift **−3** ticks (cheaper ask, unattractive bid).
At max short (−20): quotes shift **+3** ticks (cheaper bid, unattractive ask).

#### 4. Dynamic Spread (Volatility Filter)
Spread widens automatically during high-volatility regimes:

```
volatility = max(wap_window) - min(wap_window)

spread = TOMATO_SPREAD_WIDE (4)  if volatility > 10
spread = TOMATO_SPREAD_TIGHT (2) otherwise
```

#### 5. Final Order Pricing

```
target_price = wap + momentum_shift + inventory_shift
bid_price    = int(round(target_price)) - spread
ask_price    = int(round(target_price)) + spread
```

Both sides are sized at maximum available quantity via `PositionManager`.

**Tunable constants:**

| Constant | Default | Description |
|---|---|---|
| `TOMATO_WAP_PERIOD` | `20` | Rolling window length for WAP / volatility |
| `TOMATO_INV_MAX_SHIFT` | `3` | Max inventory skew in ticks |
| `TOMATO_OBI_THRESHOLD` | `0.5` | OBI level to trigger momentum shift |
| `TOMATO_VOL_THRESHOLD` | `10` | WAP range to switch to wide spread |
| `TOMATO_SPREAD_TIGHT` | `2` | Half-spread in normal conditions |
| `TOMATO_SPREAD_WIDE` | `4` | Half-spread in high-volatility conditions |

---

## State Persistence (`traderData`)

```json
{
  "tomato_window": [float, ...]
}
```

The 20-period WAP window is serialized as JSON each tick and deserialized at the start of the next tick. No other state is needed — EMERALDS logic is stateless.

---

## Constraints

- Pure Python only — no `pandas`, `numpy`, or any external library
- All order prices must be integers (`int(round(...))`)
- Position hard limit: **±20** per symbol, enforced on every order path
- Single file delivery: `trader.py`
