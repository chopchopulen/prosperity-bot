"""
trader.py — IMC Prosperity 4 | V29 (WAP-size + Inventory suppression)

PEPPER: V27's L1-only sweep (spread cost 729 vs V26's 826 = +97 PnL). Hold.

OSMIUM (target 3200-4000):
  Phase 0: Aggressive taking at FV crossings (unchanged from V26/V28).
  Phase 1: Penny MM with two-layer size management (IDEAS 1 + 4):

  IDEA 1 — WAP-gated size asymmetry:
    Shift SIZE, not price (price shifts trigger proven adverse selection).
    WAP > FV+0.5 → cut sell size 50% (don't sell cheap into up-move).
    WAP < FV-0.5 → cut buy size 50% (don't buy dear into down-move).
    |WAP - FV| <= 0.5 → symmetric.

  IDEA 4 — Inventory-aware tiered suppression:
    Position > +10 has 75% worse fill quality. Protect the ±10 zone.
    Accumulating side scale: ≤10 → 1.0, ≤25 → 0.5, ≤50 → 0.2, >50 → 0.0.
    Reducing side always posts at full capacity.

  Deferred (need backtest confirmation first):
    Idea 2: Spread-compression contrarian pulse (+250-400 est.)
    Idea 3: Dynamic FV re-centering via traderData (+150-300 est.)
    Idea 5: NPC magnet bunching detector (+200-500 est.)

Expected: Pepper ~7383 + Osmium ~3200-4000 = ~10583-11383
"""

import json
from datamodel import Order, OrderDepth, TradingState

LIMIT = 80

class Trader:

    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        orders: dict[str, list[Order]] = {}

        if "INTARIAN_PEPPER_ROOT" in state.order_depths:
            orders["INTARIAN_PEPPER_ROOT"] = self._trade_pepper_root(state)

        if "ASH_COATED_OSMIUM" in state.order_depths:
            orders["ASH_COATED_OSMIUM"] = self._trade_ash_osmium(state)

        return orders, 0, json.dumps({})

    # ----------------------------------------------------------------
    # PEPPER ROOT — L1-only sweep + HODL (from V27, +97 vs V26)
    # ----------------------------------------------------------------
    def _trade_pepper_root(self, state: TradingState) -> list[Order]:
        depth = state.order_depths["INTARIAN_PEPPER_ROOT"]
        position = state.position.get("INTARIAN_PEPPER_ROOT", 0)
        orders = []

        if position >= LIMIT:
            return orders

        remaining = LIMIT - position

        if depth.sell_orders:
            best_ask = min(depth.sell_orders)
            vol = min(remaining, abs(depth.sell_orders[best_ask]))
            if vol > 0:
                orders.append(Order("INTARIAN_PEPPER_ROOT", best_ask, vol))
                remaining -= vol

        if remaining > 0 and depth.buy_orders:
            best_bid = max(depth.buy_orders)
            if depth.sell_orders:
                best_ask = min(depth.sell_orders)
                bid_price = min(best_bid + 1, best_ask - 1)
            else:
                bid_price = best_bid + 1
            orders.append(Order("INTARIAN_PEPPER_ROOT", bid_price, remaining))

        return orders

    # ----------------------------------------------------------------
    # ASH_COATED_OSMIUM — V29 (Ideas 1 + 4)
    # Phase 0: Aggressive taking at FV crossings
    # Phase 1: Penny MM with WAP-size tilt + inventory tier suppression
    # Budget: Phase 0 takes subtracted from Phase 1 capacity
    # ----------------------------------------------------------------
    def _trade_ash_osmium(self, state: TradingState) -> list[Order]:
        depth = state.order_depths["ASH_COATED_OSMIUM"]
        position = state.position.get("ASH_COATED_OSMIUM", 0)
        orders = []
        fv = 10000

        max_buy = LIMIT - position
        max_sell = position + LIMIT
        took_buy = 0
        took_sell = 0

        # === PHASE 0: AGGRESSIVE TAKING ===
        if depth.buy_orders:
            for bp in sorted(depth.buy_orders.keys(), reverse=True):
                if bp < fv:
                    break
                avail = max_sell - took_sell
                if avail <= 0:
                    break
                vol = min(avail, depth.buy_orders[bp])
                if vol > 0:
                    orders.append(Order("ASH_COATED_OSMIUM", bp, -vol))
                    took_sell += vol

        if depth.sell_orders:
            for ap in sorted(depth.sell_orders.keys()):
                if ap > fv:
                    break
                avail = max_buy - took_buy
                if avail <= 0:
                    break
                vol = min(avail, abs(depth.sell_orders[ap]))
                if vol > 0:
                    orders.append(Order("ASH_COATED_OSMIUM", ap, vol))
                    took_buy += vol

        # === PHASE 1: PENNY MARKET MAKING ===
        mm_buy = max_buy - took_buy
        mm_sell = max_sell - took_sell

        if not depth.buy_orders or not depth.sell_orders:
            if depth.buy_orders and mm_sell > 0:
                bb = max(depth.buy_orders)
                orders.append(Order("ASH_COATED_OSMIUM", max(bb + 1, fv + 1), -mm_sell))
            elif depth.sell_orders and mm_buy > 0:
                ba = min(depth.sell_orders)
                orders.append(Order("ASH_COATED_OSMIUM", min(ba - 1, fv - 1), mm_buy))
            return orders

        best_bid = max(depth.buy_orders)
        best_ask = min(depth.sell_orders)

        # Penny prices — no price-based inventory shift (superseded by size management)
        bid_price = min(best_bid + 1, fv - 1)
        ask_price = max(best_ask - 1, fv + 1)

        if bid_price >= ask_price:
            bid_price = fv - 1
            ask_price = fv + 1

        # === IDEA 4: Inventory-aware tiered size suppression ===
        # Position > +10 has 75% worse fill quality — keep us near 0.
        # Suppress the accumulating side based on |position|.
        def inv_scale(pos: int, side: str) -> float:
            """Scale factor for the accumulating side; reducing side always 1.0."""
            if side == "buy":
                accumulating = pos > 0
            else:
                accumulating = pos < 0
            if not accumulating:
                return 1.0
            abs_pos = abs(pos)
            if abs_pos <= 10:
                return 1.0
            elif abs_pos <= 25:
                return 0.5
            elif abs_pos <= 50:
                return 0.2
            else:
                return 0.0

        buy_size = mm_buy * inv_scale(position, "buy")
        sell_size = mm_sell * inv_scale(position, "sell")

        # === IDEA 1: WAP-gated size asymmetry ===
        # Shift SIZE (not price) based on WAP signal — invisible to bots,
        # avoids the proven adverse-selection trap of price shifts.
        # WAP = (best_bid * ask_vol + best_ask * bid_vol) / (bid_vol + ask_vol)
        bid_vol = sum(depth.buy_orders.values())
        ask_vol = sum(abs(v) for v in depth.sell_orders.values())
        total_vol = bid_vol + ask_vol
        if total_vol > 0:
            wap = (best_bid * ask_vol + best_ask * bid_vol) / total_vol
            wap_shift = wap - fv
            if wap_shift > 0.5:
                # Market biased up — cut sell size (we don't want to sell cheap)
                sell_size *= 0.5
            elif wap_shift < -0.5:
                # Market biased down — cut buy size (we don't want to buy expensive)
                buy_size *= 0.5

        buy_size = max(0, int(round(buy_size)))
        sell_size = max(0, int(round(sell_size)))

        if buy_size > 0:
            orders.append(Order("ASH_COATED_OSMIUM", bid_price, buy_size))
        if sell_size > 0:
            orders.append(Order("ASH_COATED_OSMIUM", ask_price, -sell_size))

        return orders