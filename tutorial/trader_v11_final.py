"""
trader.py — IMC Prosperity 4 | V13
EMERALDS: LIMIT=80, snipe threshold stays ±15 (V11), penny + 160k endgame.
TOMATOES: LIMIT=80, inv_shift threshold stays ±15 (V11), compressed spread
          contrarian taking + mispriced cross taking + position-aware sizing.
"""

import json
from datamodel import Order, OrderDepth, TradingState


class Trader:

    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        prev = json.loads(state.traderData) if state.traderData else {}
        orders: dict[str, list[Order]] = {}

        if "EMERALDS" in state.order_depths:
            orders["EMERALDS"] = self._trade_emeralds(state)

        tom_data: dict = {}
        if "TOMATOES" in state.order_depths:
            orders["TOMATOES"], tom_data = self._trade_tomatoes(state, prev)

        return orders, 0, json.dumps(tom_data)

    # ── EMERALDS ──────────────────────────────────────────────────────

    def _trade_emeralds(self, state: TradingState) -> list[Order]:
        LIMIT = 80
        depth: OrderDepth = state.order_depths["EMERALDS"]
        position = state.position.get("EMERALDS", 0)
        orders: list[Order] = []

        # Phase 0: FLATTEN AT FAIR VALUE — take any 10000 event toward pos=0
        if position > 0 and 10000 in depth.buy_orders:
            vol = min(position, depth.buy_orders[10000])
            if vol > 0:
                orders.append(Order("EMERALDS", 10000, -vol))
                position -= vol

        if position < 0 and 10000 in depth.sell_orders:
            vol = min(-position, abs(depth.sell_orders[10000]))
            if vol > 0:
                orders.append(Order("EMERALDS", 10000, vol))
                position += vol

        # Phase 1: SNIPE — threshold kept at ±15 (V11)
        if position >= 15:
            for bid_price in sorted(depth.buy_orders.keys(), reverse=True):
                if bid_price >= 10000:
                    vol = min(position + LIMIT, depth.buy_orders[bid_price])
                    if vol > 0:
                        orders.append(Order("EMERALDS", bid_price, -vol))
                        position -= vol

        if position <= -15:
            for ask_price in sorted(depth.sell_orders.keys()):
                if ask_price <= 10000:
                    vol = min(LIMIT - position, abs(depth.sell_orders[ask_price]))
                    if vol > 0:
                        orders.append(Order("EMERALDS", ask_price, vol))
                        position += vol

        # Phase 2: MAKE — penny with end-game flattening (160k)
        best_bid = max(depth.buy_orders) if depth.buy_orders else 9990
        best_ask = min(depth.sell_orders) if depth.sell_orders else 10010

        if state.timestamp > 160000:
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

        buy_qty = max(0, LIMIT - position)
        sell_qty = max(0, position + LIMIT)
        if buy_qty > 0:
            orders.append(Order("EMERALDS", bid_price, buy_qty))
        if sell_qty > 0:
            orders.append(Order("EMERALDS", ask_price, -sell_qty))

        return orders

    # ── TOMATOES ─────────────────────────────────────────────────────

    def _trade_tomatoes(self, state: TradingState, prev: dict) -> tuple[list[Order], dict]:
        LIMIT = 80
        depth: OrderDepth = state.order_depths["TOMATOES"]
        position = state.position.get("TOMATOES", 0)

        if not depth.buy_orders or not depth.sell_orders:
            return [], prev

        best_bid = max(depth.buy_orders)
        best_ask = min(depth.sell_orders)
        bid_vol = depth.buy_orders[best_bid]
        ask_vol = abs(depth.sell_orders[best_ask])
        spread = best_ask - best_bid
        wap = (best_bid * ask_vol + best_ask * bid_vol) / (bid_vol + ask_vol)
        wap_int = int(round(wap))

        prev_best_bid = prev.get("pbb", None)
        prev_best_ask = prev.get("pba", None)

        orders: list[Order] = []

        # Phase 0: COMPRESSED SPREAD CONTRARIAN TAKING (spread ≤ 7)
        # Insider orders are contrarian 95% of the time on compressed spreads.
        # Ask dropped 2+ ticks → someone sold aggressively → mid will rise → BUY.
        # Bid jumped 2+ ticks → someone bought aggressively → mid will drop → SELL.
        if spread <= 7 and prev_best_bid is not None and prev_best_ask is not None:
            if best_ask <= prev_best_ask - 2:
                # Ask insider: buy the ask
                take_qty = min(ask_vol, LIMIT - position)
                if take_qty > 0:
                    orders.append(Order("TOMATOES", best_ask, take_qty))
                    position += take_qty
            elif best_bid >= prev_best_bid + 2:
                # Bid insider: sell the bid
                take_qty = min(bid_vol, position + LIMIT)
                if take_qty > 0:
                    orders.append(Order("TOMATOES", best_bid, -take_qty))
                    position -= take_qty

        # Phase 1: MISPRICED CROSS TAKING
        # If best_ask < wap → underpriced ask, buy it. If best_bid > wap → overpriced bid, sell it.
        if best_ask < wap_int:
            take_qty = min(ask_vol, LIMIT - position)
            if take_qty > 0:
                orders.append(Order("TOMATOES", best_ask, take_qty))
                position += take_qty

        if best_bid > wap_int:
            take_qty = min(bid_vol, position + LIMIT)
            if take_qty > 0:
                orders.append(Order("TOMATOES", best_bid, -take_qty))
                position -= take_qty

        # Phase 2: PENNY MAKER (V6 pricing, inv_shift threshold kept at ±15)
        if position > 15:
            inv_shift = -1
        elif position < -15:
            inv_shift = 1
        else:
            inv_shift = 0

        bid_price = best_bid + 1 + inv_shift
        ask_price = best_ask - 1 + inv_shift

        imbalance = bid_vol - ask_vol
        if imbalance >= 3:
            bid_price += 1
            ask_price += 1
        elif imbalance <= -3:
            bid_price -= 1
            ask_price -= 1

        bid_price = min(bid_price, wap_int - 1)
        ask_price = max(ask_price, wap_int + 1)
        if bid_price >= ask_price:
            bid_price = wap_int - 1
            ask_price = wap_int + 1

        # Position-aware quote sizing: max(0, LIMIT ± position) naturally shrinks
        # the opening side as position grows. No extra logic needed.
        buy_qty = max(0, LIMIT - position)
        sell_qty = max(0, position + LIMIT)

        if buy_qty > 0:
            orders.append(Order("TOMATOES", bid_price, buy_qty))
        if sell_qty > 0:
            orders.append(Order("TOMATOES", ask_price, -sell_qty))

        # Persist for next tick
        new_data = {"pbb": best_bid, "pba": best_ask}
        return orders, new_data
