# IMC Prosperity 4 — Solo Trading Bot

Algorithmic trading bot for IMC Prosperity 4 competition (April 2026).

## Results

| Round    | Score (XIRECs) | Position | Strategy                                    |
|----------|---------------|----------|---------------------------------------------|
| Tutorial | ~2598 PnL    | —        | Emeralds penny MM + Tomatoes WAP MM         |
| Round 1  | 93,061        | 3,777th  | Pepper drift HODL + Osmium penny MM         |
| Round 2  | 97,392        | 492th      | TBD                                         |

## Structure

```
prosperity-bot/
├── tutorial/                        # Tutorial round code and data
│   ├── trader_v11_final.py          # Final tutorial submission (V11)
│   ├── experiments/                 # Earlier tutorial experiments (V6, A, B, C)
│   └── data/                        # Tutorial round price/trade CSVs
├── round1/
│   └── trader_v29_final.py          # R1 final submission
├── round2/
│   └── trader_v33_final.py          # R2 final submission
├── analysis/
│   ├── offline_analyzer.py          # Local backtesting script
│   ├── backtests/                   # Backtest output logs
│   └── prosperity_rust_backtester/  # Rust-based backtester
└── docs/
    ├── round1_knowledge_transfer.md
    └── prosperity4_master_reference.md
```

## Constraints (both rounds)

- Pure Python only (no numpy/pandas)
- Stateless execution — persist state via `traderData` JSON string (50k char limit)
- Position limits: ±80 per product

---

## Tutorial Round — Strategy Summary

**Products:** EMERALDS (FV=10,000, stationary), TOMATOES (mean-reverting with drift)

### Version History

| Version | Change | Total PnL |
|---------|--------|-----------|
| V5 | Penny maker + WAP FV + continuous inv_shift | 2,246 |
| V6 | Threshold inv_shift (±1 at \|pos\|≥15) + L1 imbalance skew | 2,342 |
| V7 | Emeralds: FV-flattening + sniper. Tomatoes: compressed-spread disaster | 160 |
| V8 | Reverted tomatoes to V6; tested mean reversion skew → adverse selection | 2,363 |
| V9 | Inventory ladder → killed throughput | 2,208 |
| V10 | V7 emeralds + V6 tomatoes + endgame flattening | ~2,490 |
| **V11** | V7 emeralds + V6 tomatoes (cleanest stable combo) | **~2,433** |

---

## Round 1 — Strategy Summary

**Products:** INTARIAN_PEPPER_ROOT, ASH_COATED_OSMIUM  
**Sim length:** 1,000 ticks. **Position limit:** ±80.

### INTARIAN_PEPPER_ROOT
Drifts +0.1/tick monotonically. Strategy: sweep L1 asks to reach +80 ASAP, then hold forever. L2 sweeping costs ~97 extra PnL (consistently worse prices). Rotation (selling and rebuying) loses money — drift is monotone up, max drawdown only 12–14 pts, no cheap rebuys exist.

### ASH_COATED_OSMIUM
Stationary mean-reverting product (FV=10,000, spread ~16). Two-phase strategy:

- **Phase 0** — aggressive taking: sell into any bid ≥ FV, buy from any ask ≤ FV
- **Phase 1** — penny market making: quote bb+1 / ba−1, clamped to 9,999/10,001

**Budget system (critical):** Phase 0 volume is tracked in `took_buy`/`took_sell`. Phase 1 capacity = `LIMIT − position − took_*`. This prevents position limit violations when the sim evaluates all orders simultaneously against real position.

**Phase 1 size layers:**
1. Inventory tiered suppression — accumulating side scaled: ≤10 → 1.0, ≤25 → 0.5, ≤50 → 0.2, >50 → 0.0
2. WAP-gated size asymmetry — cut weaker side 50% when WAP drifts >0.5 tick from FV

### R1 Iteration History

| Version | Change | Result |
|---------|--------|--------|
| V27 | L1-only pepper sweep | +97 PnL vs V26 L2 sweep |
| V28 | Clean rewrite; inv_shift ±30 price shift; baseline | ~2,594 osmium |
| V29 | WAP size tilt + inventory tiered suppression; removed inv_shift | ~2,768 osmium; position leaked to [−54, +26] |
| V30 | Banded policy: inv_shift re-added at \|pos\|≥21, size suppression at 31+, WAP skip on reducing side; Phase 0 cap ±60 | Fixed position leak |
| V31 | Pepper rotation attempt (3 bugs: violations, spread-crossing rebuys, slow ramp) | −684 regression |
| V32 | Two-mode pepper (accumulate pos<75 / rotate pos≥75) | −328 vs HODL; threshold caused Mode 1 re-entry |
| V33 | Latch fix: ROTATION_THRESHOLD=30 + sell cap 5 units | Concept abandoned |
| **Final (V29)** | V29 restored as submission | **93,061 total** |

### Proven Failures — R1

- Directional price shifts on any signal → adverse selection, tested at 74/91/97% accuracy, all lost money
- Pepper rotation of any kind → drift outruns rebuy cost
- Multi-level quoting → price priority fills worst level first
- Tighter osmium quotes (bb+2/ba−2) → worse prices, same fill rate
- Aggressive Phase 0 extension beyond FV → spread cost exceeds signal edge

---

## Round 2 — Strategy Summary

**Products:** Same two products. **Sim length:** 10,000 ticks/day (10× R1). **Position limit:** ±80.

R2 adds a `bid()` method for the Market Access Fee blind auction — top 50% of bids win 25% extra order flow. Bid: **1,500 XIRECs**.

Expected PnL at 10k ticks:
- Pepper HODL: ~79,000 (80 units × 995-pt drift − ~730 spread cost)
- Osmium MM: ~20,000–27,000
- **Total: ~95,000–105,000** before MAF

### R2 Iteration History

| Version | Change | Notes |
|---------|--------|-------|
| Baseline | V29 faithful port + `bid()` + toggleable Arch2 (`ENABLE_ARCH2=False`) | Clean starting point |
| V31 | Progressive edge filter for Phase 0 (0/1/2 tick edge req. by \|pos\|) | +38% on historical CSVs; hurt live ~300 |
| V32 | Fixed 9995/10005 Phase 1 quotes + pepper imbalance skip; edge filter reverted | Tested |
| **V33 (Final)** | Dynamic FV for Phase 0 via 10-tick rolling mid, clamped [9997, 10003]; Phase 1 stays static 10000 | Submitted |

### Proven Failures — R2

All R1 failures carry over, plus:
- Progressive edge filter → theoretical gain doesn't survive live seed variance
- Fixed Phase 1 quotes (9995/10005) → wider spread reduces fill rate
- WAP-gated Phase 0 skips → skips genuinely profitable trades
