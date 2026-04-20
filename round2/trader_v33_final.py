"""
trader.py — IMC Prosperity 4 | R2 V33

Single change vs V30 (submission 283945.py):
  Dynamic FV for Osmium Phase 0 triggers, computed from a 10-tick rolling
  mid-price average clamped to [9997, 10003].

  Motivation: live seeds drift from 10000 (observed ~10003+). Static FV=10000
  triggers zero-edge fills at bid=10000 (58 vol in V30 live, all zero edge).
  Dynamic FV skips those fills when the center drifts. Phase 1 anchor stays
  static at 10000 — its dynamic quoting already adapts, changing its anchor
  would break the penny-clamp logic.

Everything else is V30 verbatim:
  - Pepper: L1 sweep + passive bb+1 bid + HODL at +80
  - Osmium Phase 0 cap ±50
  - Osmium Phase 1: dynamic bb+1/ba-1 clamped to 9999/10001
  - inv_scale tiered suppression
  - WAP-gated size asymmetry (wap_shift vs static 10000)
"""

import json
from datamodel import Order, OrderDepth, TradingState

LIMIT = 80


class Trader:

    def bid(self) -> int:
        """MAF blind auction bid. 1,500 XIRECs — top 50% + positive EV."""
        return 1500

    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        # --- Parse traderData for rolling mid history (Osmium Phase 0 dyn_fv) ---
        try:
            td = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            td = {}
        mid_history: list = td.get("mid_history", [])

        orders: dict[str, list[Order]] = {}

        if "INTARIAN_PEPPER_ROOT" in state.order_depths:
            orders["INTARIAN_PEPPER_ROOT"] = self._trade_pepper_root(state)

        if "ASH_COATED_OSMIUM" in state.order_depths:
            orders["ASH_COATED_OSMIUM"] = self._trade_ash_osmium(state, mid_history)

        # Persist mid_history (already updated inside _trade_ash_osmium)
        return orders, 0, json.dumps({"mid_history": mid_history})

    # ── PEPPER: L1 sweep + passive bid + HODL (V30 unchanged) ─────────
    def _trade_pepper_root(self, state: TradingState) -> list[Order]:
        depth = state.order_depths["INTARIAN_PEPPER_ROOT"]
        position = state.position.get("INTARIAN_PEPPER_ROOT", 0)
        orders = []

        if position >= LIMIT:
            return orders

        remaining = LIMIT - position

        # L1 sweep only
        if depth.sell_orders:
            best_ask = min(depth.sell_orders)
            vol = min(remaining, abs(depth.sell_orders[best_ask]))
            if vol > 0:
                orders.append(Order("INTARIAN_PEPPER_ROOT", best_ask, vol))
                remaining -= vol

        # Passive bid for any remaining capacity
        if remaining > 0 and depth.buy_orders:
            best_bid = max(depth.buy_orders)
            if depth.sell_orders:
                best_ask = min(depth.sell_orders)
                bid_price = min(best_bid + 1, best_ask - 1)
            else:
                bid_price = best_bid + 1
            orders.append(Order("INTARIAN_PEPPER_ROOT", bid_price, remaining))

        return orders

    # ── OSMIUM: Phase 0 (dynamic FV trigger, cap=50) + Phase 1 MM ─────
    # V33 change: Phase 0 sell/buy triggers use dyn_fv (10-tick rolling
    # mid, clamped [9997, 10003]) instead of static 10000.
    # Phase 1 anchor stays static at 10000 (penny clamps 9999/10001).
    # ─────────────────────────────────────────────────────────────────
    def _trade_ash_osmium(self, state: TradingState, mid_history: list) -> list[Order]:
        depth = state.order_depths["ASH_COATED_OSMIUM"]
        position = state.position.get("ASH_COATED_OSMIUM", 0)
        orders = []
        fv = 10000  # static anchor — used for Phase 1 clamps and WAP comparison

        max_buy = LIMIT - position
        max_sell = position + LIMIT
        took_buy = 0
        took_sell = 0

        # --- Compute dynamic FV for Phase 0 triggers ---
        if depth.buy_orders and depth.sell_orders:
            current_mid = (max(depth.buy_orders) + min(depth.sell_orders)) / 2
            mid_history.append(current_mid)
            if len(mid_history) > 10:
                mid_history[:] = mid_history[-10:]

        if len(mid_history) >= 10:
            raw = sum(mid_history) / len(mid_history)
            dyn_fv = int(round(max(9997, min(10003, raw))))
        else:
            dyn_fv = fv  # fallback until we have 10 samples

        # === PHASE 0: AGGRESSIVE TAKING (cap=50, V30; dyn_fv trigger, V33) ===
        phase0_max_sell = max(0, 50 + position)
        phase0_max_buy  = max(0, 50 - position)

        if depth.buy_orders:
            for bp in sorted(depth.buy_orders.keys(), reverse=True):
                if bp < dyn_fv:  # V33: was `fv`
                    break
                avail = min(max_sell - took_sell, phase0_max_sell - took_sell)
                if avail <= 0:
                    break
                vol = min(avail, depth.buy_orders[bp])
                if vol > 0:
                    orders.append(Order("ASH_COATED_OSMIUM", bp, -vol))
                    took_sell += vol

        if depth.sell_orders:
            for ap in sorted(depth.sell_orders.keys()):
                if ap > dyn_fv:  # V33: was `fv`
                    break
                avail = min(max_buy - took_buy, phase0_max_buy - took_buy)
                if avail <= 0:
                    break
                vol = min(avail, abs(depth.sell_orders[ap]))
                if vol > 0:
                    orders.append(Order("ASH_COATED_OSMIUM", ap, vol))
                    took_buy += vol

        # === BUDGET HANDOFF ===
        mm_buy = max_buy - took_buy
        mm_sell = max_sell - took_sell

        # === PHASE 1: PENNY MM (V30 unchanged — static fv=10000 anchor) ===

        # One-sided book fallback
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

        # Dynamic penny prices clamped to static FV±1 (V30 unchanged)
        bid_price = min(best_bid + 1, fv - 1)
        ask_price = max(best_ask - 1, fv + 1)

        if bid_price >= ask_price:
            bid_price = fv - 1
            ask_price = fv + 1

        # --- Inventory tiered suppression (V30 unchanged) ---
        def inv_scale(pos: int, side: str) -> float:
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

        # --- WAP-gated size asymmetry vs static 10000 (V30 unchanged) ---
        bid_vol = sum(depth.buy_orders.values())
        ask_vol = sum(abs(v) for v in depth.sell_orders.values())
        total_vol = bid_vol + ask_vol
        if total_vol > 0:
            wap = (best_bid * ask_vol + best_ask * bid_vol) / total_vol
            wap_shift = wap - fv  # static 10000 — do not substitute dyn_fv here
            if wap_shift > 0.5:
                sell_size *= 0.5
            elif wap_shift < -0.5:
                buy_size *= 0.5

        buy_size = max(0, int(round(buy_size)))
        sell_size = max(0, int(round(sell_size)))

        if buy_size > 0:
            orders.append(Order("ASH_COATED_OSMIUM", bid_price, buy_size))
        if sell_size > 0:
            orders.append(Order("ASH_COATED_OSMIUM", ask_price, -sell_size))

        return orders
