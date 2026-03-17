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

### EMERALDS — Hybrid Sniper + Dynamic Penny Maker

**Fair value:** hardcoded at **10,000**.

**Phase 1 — Taker (Sniper):**
- Scans `sell_orders` sorted lowest-first. Takes any ask **below** 10,000, up to remaining buy capacity.
- Scans `buy_orders` sorted highest-first. Takes any bid **above** 10,000, up to remaining sell capacity.
- Virtual position is updated after each fill so subsequent snipes and maker quotes never exceed the ±20 limit.

**Phase 2 — Maker (Dynamic Pennying):**
- After sniping, reads the remaining book and places dynamic penny quotes for leftover capacity:
  - `bid_price = min(best_bid + 1, EMERALD_FAIR - 1)` — penny the best bid, clamped below fair value
  - `ask_price = max(best_ask - 1, EMERALD_FAIR + 1)` — penny the best ask, clamped above fair value
  - Fallback to `9998` / `10002` if the book is empty on either side

**Tunable constants:**

| Constant | Default | Description |
|---|---|---|
| `EMERALD_FAIR` | `10000` | Hard-coded fair value |
| `EMERALD_DEFAULT_SPREAD` | `2` | Fallback half-spread when book is empty |

---

### TOMATOES — WAP + Inventory Skew Market Maker

A microstructure-aware passive market maker using WAP as fair value with inventory skew.

#### 1. Weighted Average Price (WAP)
Base fair value using Level 1 order book volumes:

```
wap = (best_bid × best_ask_vol + best_ask × best_bid_vol) / (best_bid_vol + best_ask_vol)
```

#### 2. Inventory Skew
Shifts quotes to lean against the current position, reducing inventory risk:

```
inventory_shift = -(position / 20.0) × TOMATO_INV_MAX_SHIFT
```

At max long (+20): quotes shift **−3** ticks (cheaper ask, unattractive bid).
At max short (−20): quotes shift **+3** ticks (cheaper bid, unattractive ask).

#### 3. Final Order Pricing

```
target_price = wap + inventory_shift
bid_price    = int(round(target_price)) - TOMATO_SPREAD
ask_price    = int(round(target_price)) + TOMATO_SPREAD
```

Both sides are sized at maximum available quantity via `PositionManager`.

**Tunable constants:**

| Constant | Default | Description |
|---|---|---|
| `TOMATO_WAP_PERIOD` | `20` | Rolling WAP window length |
| `TOMATO_INV_MAX_SHIFT` | `3` | Max inventory skew in ticks |
| `TOMATO_SPREAD` | `3` | Fixed half-spread around target price |

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
