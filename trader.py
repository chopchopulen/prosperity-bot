import json
from datamodel import Order, OrderDepth, TradingState


class RollingAverage:
    """Fixed-window rolling average using a plain list."""

    def __init__(self, period: int, data: list[float] | None = None):
        self.period = period
        self.data = data if data is not None else []

    def update(self, value: float) -> None:
        self.data.append(value)
        if len(self.data) > self.period:
            self.data.pop(0)

    def average(self) -> float | None:
        if len(self.data) < self.period:
            return None
        return sum(self.data) / self.period

    def to_list(self) -> list[float]:
        return self.data


class PositionManager:
    """Enforces position limits on every order."""

    @staticmethod
    def max_buy_quantity(position: int, limit: int = 20) -> int:
        return limit - position

    @staticmethod
    def max_sell_quantity(position: int, limit: int = 20) -> int:
        return position + limit


class Trader:
    EMERALD_FAIR = 10_000
    EMERALD_DEFAULT_SPREAD = 2  # fallback half-spread when book is empty
    TOMATO_WAP_PERIOD = 20
    TOMATO_INV_MAX_SHIFT = 3   # max inventory skew in price ticks
    TOMATO_OBI_THRESHOLD = 0.5  # OBI magnitude to trigger momentum shift
    TOMATO_VOL_THRESHOLD = 10   # WAP range threshold for wide spread
    TOMATO_SPREAD_TIGHT = 2
    TOMATO_SPREAD_WIDE = 4

    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        # --- Deserialize persistent state ---
        data = json.loads(state.traderData) if state.traderData else {}
        tomato_wap = RollingAverage(self.TOMATO_WAP_PERIOD, data.get("tomato_window", []))

        orders: dict[str, list[Order]] = {}

        # --- EMERALDS: Market Making ---
        if "EMERALDS" in state.order_depths:
            orders["EMERALDS"] = self._market_make_emeralds(state)

        # --- TOMATOES: Mean-Reversion Market Making ---
        if "TOMATOES" in state.order_depths:
            orders["TOMATOES"] = self._market_make_tomatoes(state, tomato_wap)

        # --- Serialize persistent state ---
        trader_data = json.dumps({
            "tomato_window": tomato_wap.to_list(),
        })

        return orders, 0, trader_data

    # ------------------------------------------------------------------ #
    #  EMERALDS — hybrid: sniper taker + passive maker at fair 10,000   #
    # ------------------------------------------------------------------ #

    def _market_make_emeralds(self, state: TradingState) -> list[Order]:
        depth: OrderDepth = state.order_depths["EMERALDS"]
        position = state.position.get("EMERALDS", 0)
        result: list[Order] = []

        # --- Sniper: buy underpriced sell orders (price < fair value) ---
        for price in sorted(depth.sell_orders.keys()):
            if price >= self.EMERALD_FAIR:
                break
            available = PositionManager.max_buy_quantity(position)
            if available <= 0:
                break
            qty = min(available, abs(depth.sell_orders[price]))
            result.append(Order("EMERALDS", price, qty))
            position += qty

        # --- Sniper: sell overpriced buy orders (price > fair value) ---
        for price in sorted(depth.buy_orders.keys(), reverse=True):
            if price <= self.EMERALD_FAIR:
                break
            available = PositionManager.max_sell_quantity(position)
            if available <= 0:
                break
            qty = min(available, depth.buy_orders[price])
            result.append(Order("EMERALDS", price, -qty))
            position -= qty

        # --- Maker: passive quotes for remaining capacity ---
        buy_qty = PositionManager.max_buy_quantity(position)
        if buy_qty > 0:
            result.append(Order("EMERALDS", self.EMERALD_FAIR - self.EMERALD_DEFAULT_SPREAD, buy_qty))

        sell_qty = PositionManager.max_sell_quantity(position)
        if sell_qty > 0:
            result.append(Order("EMERALDS", self.EMERALD_FAIR + self.EMERALD_DEFAULT_SPREAD, -sell_qty))

        return result

    # ------------------------------------------------------------------ #
    #  TOMATOES — alpha equation: WAP + OBI momentum + inventory skew   #
    # ------------------------------------------------------------------ #

    def _market_make_tomatoes(
        self,
        state: TradingState,
        tomato_wap: RollingAverage,
    ) -> list[Order]:
        depth: OrderDepth = state.order_depths["TOMATOES"]
        position = state.position.get("TOMATOES", 0)

        best_bid = max(depth.buy_orders) if depth.buy_orders else None
        best_ask = min(depth.sell_orders) if depth.sell_orders else None

        if best_bid is None or best_ask is None:
            return []

        best_bid_vol = depth.buy_orders[best_bid]
        best_ask_vol = abs(depth.sell_orders[best_ask])
        total_vol = best_bid_vol + best_ask_vol

        # 1. WAP as base fair value
        wap = (best_bid * best_ask_vol + best_ask * best_bid_vol) / total_vol
        tomato_wap.update(wap)

        # 2. OBI momentum shift
        obi = (best_bid_vol - best_ask_vol) / total_vol
        if obi > self.TOMATO_OBI_THRESHOLD:
            momentum_shift = 1
        elif obi < -self.TOMATO_OBI_THRESHOLD:
            momentum_shift = -1
        else:
            momentum_shift = 0

        # 3. Inventory skew
        inventory_shift = -(position / 20.0) * self.TOMATO_INV_MAX_SHIFT

        # 4. Dynamic spread based on WAP volatility
        wap_list = tomato_wap.to_list()
        if len(wap_list) >= 2:
            volatility = max(wap_list) - min(wap_list)
            spread = self.TOMATO_SPREAD_WIDE if volatility > self.TOMATO_VOL_THRESHOLD else self.TOMATO_SPREAD_TIGHT
        else:
            spread = self.TOMATO_SPREAD_TIGHT

        # 5. Final prices
        target_price = wap + momentum_shift + inventory_shift
        bid_price = int(round(target_price)) - spread
        ask_price = int(round(target_price)) + spread

        result: list[Order] = []

        buy_qty = PositionManager.max_buy_quantity(position)
        if buy_qty > 0:
            result.append(Order("TOMATOES", bid_price, buy_qty))

        sell_qty = PositionManager.max_sell_quantity(position)
        if sell_qty > 0:
            result.append(Order("TOMATOES", ask_price, -sell_qty))

        return result
