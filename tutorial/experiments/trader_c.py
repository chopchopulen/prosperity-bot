"""
trader_c.py — IMC Prosperity 4 | Tomato Experiment: Variant C
Change: SPREAD=2, INV_MAX_SHIFT=5. Hypothesis: stronger inv pressure cycles position faster.
EMERALDS: +798 baseline penny maker (unchanged).
TOMATOES: WAP+OBI+aggressive_inv_skew, SPREAD=2.
"""

import json
from datamodel import Order, OrderDepth, TradingState

# TOMATOES constants
SPREAD = 2
INV_MAX_SHIFT = 5
OBI_WEIGHT = 10.0


class Trader:
    EMERALD_FAIR: int = 10_000

    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        json.loads(state.traderData) if state.traderData else {}
        orders: dict[str, list[Order]] = {}

        if "EMERALDS" in state.order_depths:
            orders["EMERALDS"] = self._trade_emeralds(state)

        if "TOMATOES" in state.order_depths:
            orders["TOMATOES"] = self._trade_tomatoes(state)

        return orders, 0, json.dumps({})

    def _trade_emeralds(self, state: TradingState) -> list[Order]:
        depth: OrderDepth = state.order_depths["EMERALDS"]
        position = state.position.get("EMERALDS", 0)

        best_bid = max(depth.buy_orders) if depth.buy_orders else 9990
        best_ask = min(depth.sell_orders) if depth.sell_orders else 10010
        bid_price = min(best_bid + 1, 9999)
        ask_price = max(best_ask - 1, 10001)

        orders: list[Order] = []
        buy_qty = 20 - position
        sell_qty = position + 20
        if buy_qty > 0:
            orders.append(Order("EMERALDS", bid_price, buy_qty))
        if sell_qty > 0:
            orders.append(Order("EMERALDS", ask_price, -sell_qty))
        return orders

    def _trade_tomatoes(self, state: TradingState) -> list[Order]:
        depth: OrderDepth = state.order_depths["TOMATOES"]
        position = state.position.get("TOMATOES", 0)

        best_bid = max(depth.buy_orders) if depth.buy_orders else None
        best_ask = min(depth.sell_orders) if depth.sell_orders else None
        if best_bid is None or best_ask is None:
            return []

        bid_vol = depth.buy_orders[best_bid]
        ask_vol = abs(depth.sell_orders[best_ask])
        total_vol = bid_vol + ask_vol
        wap = (best_bid * ask_vol + best_ask * bid_vol) / total_vol

        total_bid_vol = sum(depth.buy_orders.values())
        total_ask_vol = sum(abs(v) for v in depth.sell_orders.values())
        total = total_bid_vol + total_ask_vol
        obi = (total_bid_vol - total_ask_vol) / total if total > 0 else 0.0

        inventory_shift = -(position / 20.0) * INV_MAX_SHIFT
        obi_skew = obi * OBI_WEIGHT
        target = wap + inventory_shift + obi_skew
        bid_price = int(round(target)) - SPREAD
        ask_price = int(round(target)) + SPREAD

        orders: list[Order] = []
        buy_qty = 20 - position
        sell_qty = position + 20
        if buy_qty > 0:
            orders.append(Order("TOMATOES", bid_price, buy_qty))
        if sell_qty > 0:
            orders.append(Order("TOMATOES", ask_price, -sell_qty))
        return orders
