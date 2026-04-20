# Round 1 Knowledge Transfer

## Products

### INTARIAN_PEPPER_ROOT
- Drifts +0.1076/tick = +995 pts/day. Starts each day where previous ended.
- Max drawdown: 12–14 pts only. Effectively monotone upward.
- L1 vol ~11.6, spread 13.
- **Optimal strategy: sweep L1 asks to +80, hold forever.**
- L2 sweeping costs ~97 extra PnL. Rotation loses money (no cheap rebuys in monotone drift).

### ASH_COATED_OSMIUM
- Stationary, FV=10,000 confirmed by 3-day VWAP.
- Spread distribution: 16 (63%), 18–19 (27%), ≤12 compressed (~7%).
- L1 vol ~14. Autocorrelation −0.49 (strong mean reversion at lag 1).

## Budget System (critical invariant)

The sim evaluates all orders simultaneously against real position. If Phase 0 and Phase 1 both independently compute their order sizes against `position`, total volume can exceed ±80 → violations.

**Fix:** Track Phase 0 volume in `took_buy`/`took_sell`. Phase 1 capacity = `max_buy/sell − took_*`.

```python
max_buy = LIMIT - position
max_sell = position + LIMIT
took_buy = 0
took_sell = 0
# ... Phase 0 loops update took_buy/took_sell ...
mm_buy = max_buy - took_buy   # Phase 1 sees only what's left
mm_sell = max_sell - took_sell
```

Breaking this causes hundreds of violations per sim.

## Size Management (Phase 1)

Two layers applied sequentially:

**1. Inventory tiered suppression**
```
|pos| ≤ 10: accumulating side × 1.0
|pos| ≤ 25: accumulating side × 0.5
|pos| ≤ 50: accumulating side × 0.2
|pos| > 50: accumulating side × 0.0
```
Rationale: position >±10 has 75% worse fill quality. Protect the ±10 high-quality zone.

**2. WAP-gated size asymmetry**
```
WAP > FV + 0.5: sell_size × 0.5  (don't sell cheap into up-move)
WAP < FV − 0.5: buy_size  × 0.5  (don't buy dear into down-move)
```
WAP = `(best_bid × ask_vol + best_ask × bid_vol) / (bid_vol + ask_vol)`

**Critical:** WAP is only safe as a SIZE signal. Using it as a PRICE shift causes adverse selection — tested at 74/91/97% accuracy, all lost money.

## Proven Failures

| Approach | Why it fails |
|----------|-------------|
| Price-shift quotes on any signal | Adverse selection: fills concentrate on ticks where prediction is wrong |
| Pepper rotation | Max drawdown 12–14 pts; drift outruns any rebuy opportunity |
| Multi-level quoting | Price priority fills the worse level first |
| bb+2/ba−2 penny quotes | Worse prices, identical fill rate |
| Phase 0 extension beyond FV | Spread cost (1 tick) doesn't exceed edge at normal spreads |
| WAP-gated Phase 0 skips | Skips genuinely profitable trades |
| Position cap without edge filter | Caps profitable takes along with unprofitable ones indiscriminately |
