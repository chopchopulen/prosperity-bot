"""
trader.py — IMC Prosperity 4 | V6
EMERALDS: snipe at 10000 when stuck + penny + end-game flattening.
TOMATOES: penny + threshold inv_shift + L1 imbalance skew.
"""

import json
from datamodel import Order, OrderDepth, TradingState


class Trader:

    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        orders: dict[str, list[Order]] = {}

        if "EMERALDS" in state.order_depths:
            orders["EMERALDS"] = self._trade_emeralds(state)

        if "TOMATOES" in state.order_depths:
            orders["TOMATOES"] = self._trade_tomatoes(state)

        return orders, 0, json.dumps({})

    def _trade_emeralds(self, state: TradingState) -> list[Order]:
        depth: OrderDepth = state.order_depths["EMERALDS"]
        position = state.position.get("EMERALDS", 0)
        orders: list[Order] = []

        # Phase 1: SNIPE — when stuck, take any 10000 event to free capacity
        if position >= 15:
            for bid_price in sorted(depth.buy_orders.keys(), reverse=True):
                if bid_price >= 10000:
                    vol = min(position + 20, depth.buy_orders[bid_price])
                    if vol > 0:
                        orders.append(Order("EMERALDS", bid_price, -vol))
                        position -= vol

        if position <= -15:
            for ask_price in sorted(depth.sell_orders.keys()):
                if ask_price <= 10000:
                    vol = min(20 - position, abs(depth.sell_orders[ask_price]))
                    if vol > 0:
                        orders.append(Order("EMERALDS", ask_price, vol))
                        position += vol

        # Phase 2: MAKE — penny with end-game flattening
        best_bid = max(depth.buy_orders) if depth.buy_orders else 9990
        best_ask = min(depth.sell_orders) if depth.sell_orders else 10010

        if state.timestamp > 170000:
            if position > 0:
                bid_price = 9993
                ask_price = 10001
            elif position < 0:
                bid_price = 9999
                ask_price = 10007
            else:
                bid_price = min(best_bid + 1, 9999)
                ask_price = max(best_ask - 1, 10001)
        else:
            bid_price = min(best_bid + 1, 9999)
            ask_price = max(best_ask - 1, 10001)

        buy_qty = max(0, 20 - position)
        sell_qty = max(0, position + 20)
        if buy_qty > 0:
            orders.append(Order("EMERALDS", bid_price, buy_qty))
        if sell_qty > 0:
            orders.append(Order("EMERALDS", ask_price, -sell_qty))

        return orders

    def _trade_tomatoes(self, state: TradingState) -> list[Order]:
        depth: OrderDepth = state.order_depths["TOMATOES"]
        position = state.position.get("TOMATOES", 0)

        if not depth.buy_orders or not depth.sell_orders:
            return []

        best_bid = max(depth.buy_orders)
        best_ask = min(depth.sell_orders)
        bid_vol = depth.buy_orders[best_bid]
        ask_vol = abs(depth.sell_orders[best_ask])
        wap = (best_bid * ask_vol + best_ask * bid_vol) / (bid_vol + ask_vol)
        wap_int = int(round(wap))

        # Threshold inventory shift: neutral below ±15, 1-tick shift above
        if position > 15:
            inv_shift = -1
        elif position < -15:
            inv_shift = 1
        else:
            inv_shift = 0

        # Base penny quotes
        bid_price = best_bid + 1 + inv_shift
        ask_price = best_ask - 1 + inv_shift

        # L1 imbalance skew: shift both quotes in predicted direction
        imbalance = bid_vol - ask_vol
        if imbalance >= 3:
            bid_price += 1
            ask_price += 1
        elif imbalance <= -3:
            bid_price -= 1
            ask_price -= 1

        # Safety clamps
        bid_price = min(bid_price, wap_int - 1)
        ask_price = max(ask_price, wap_int + 1)
        if bid_price >= ask_price:
            bid_price = wap_int - 1
            ask_price = wap_int + 1

        orders: list[Order] = []
        buy_qty = max(0, 20 - position)
        sell_qty = max(0, position + 20)
        if buy_qty > 0:
            orders.append(Order("TOMATOES", bid_price, buy_qty))
        if sell_qty > 0:
            orders.append(Order("TOMATOES", ask_price, -sell_qty))

        return orders
