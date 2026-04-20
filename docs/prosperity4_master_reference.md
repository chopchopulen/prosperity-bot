# IMC Prosperity 4 — Master Reference

## Competition Mechanics

- Pure Python only (no numpy/pandas)
- Stateless AWS Lambda — persist state via `traderData` JSON string (50k char limit)
- Return signature: `(dict[str, list[Order]], int, str)` — orders, conversions, traderData
- R1 sim: 1,000 ticks. R2 sim: 10,000 ticks/day.
- Position limits: ±80 for all R1/R2 products
- R2 adds `bid() -> int` for the Market Access Fee (MAF) blind auction — top 50% win 25% extra flow

## Universal Rules (tested across all rounds)

**Never use price shifts on directional signals.**
Shifting both bid and ask by ±1 on any signal causes adverse selection. The signal predicts direction but fills concentrate on the ticks where the prediction is wrong. Tested at 74%, 91%, 97% accuracy — all lost money. Only safe uses of signals: size changes, which-side suppression, whether-to-quote decisions.

**Budget system is mandatory for multi-phase strategies.**
Any strategy with Phase 0 aggressive taking + Phase 1 market making must subtract Phase 0 volume from Phase 1 capacity. The sim processes all orders against real position simultaneously.

**Single-seed backtest noise is high.**
R1: ±500–1,000 variance. R2: ±1,500–4,500 variance. Don't optimize on single-seed diffs under these thresholds. Always test on 3+ seeds or 3 historical days.

## Products Reference

### INTARIAN_PEPPER_ROOT (R1 & R2)
| Property | Value |
|----------|-------|
| Drift | +0.1076/tick = +995 pts/day |
| Max drawdown | 12–14 pts |
| Spread | ~13 (day −1), ~14 (day 0), ~15 (day 1) |
| L1 vol | ~11.6 |
| Autocorrelation | −0.49 |
| Position limit | ±80 |

**Optimal strategy:** Sweep L1 asks to +80, hold forever.

### ASH_COATED_OSMIUM (R1 & R2)
| Property | Value |
|----------|-------|
| Fair value | 10,000 (confirmed 3-day VWAP) |
| Spread | 16 (63%), 18–19 (27%), ≤12 (7%) |
| L1 vol | ~14 |
| Autocorrelation | −0.49 |
| Position limit | ±80 |

**Optimal strategy:** Phase 0 FV-crossing takes + Phase 1 penny MM with budget system + inventory tiered suppression + WAP size gating.

## MAF Auction (R2)

- Blind auction, one-time fee at R2 start
- Top 50% of bids win 25% extra order flow
- Bid 1,500 XIRECs: comfortably in top 50%, EV = +2,400–3,500 extra Osmium PnL
- Pepper is already at position limit (+80) so extra flow provides no pepper benefit

## traderData Usage

```python
# Parse at start of run()
try:
    td = json.loads(state.traderData) if state.traderData else {}
except Exception:
    td = {}

# Return at end of run()
return orders, 0, json.dumps(td)
```

Keep stored data small — 10 floats = ~120 chars, well under 50k limit.
