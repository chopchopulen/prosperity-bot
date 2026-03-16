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
    TOMATO_FAST_PERIOD = 5
    TOMATO_SLOW_PERIOD = 20
    TOMATO_ORDER_SIZE = 5

    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        # --- Deserialize persistent state ---
        data = json.loads(state.traderData) if state.traderData else {}
        fast_ma = RollingAverage(self.TOMATO_FAST_PERIOD, data.get("tomato_fast", []))
        slow_ma = RollingAverage(self.TOMATO_SLOW_PERIOD, data.get("tomato_slow", []))
        prev_fast: float | None = data.get("prev_fast")
        prev_slow: float | None = data.get("prev_slow")

        orders: dict[str, list[Order]] = {}

        # --- EMERALDS: Market Making ---
        if "EMERALDS" in state.order_depths:
            orders["EMERALDS"] = self._market_make_emeralds(state)

        # --- TOMATOES: MA Crossover ---
        if "TOMATOES" in state.order_depths:
            orders["TOMATOES"] = self._trade_tomatoes(
                state, fast_ma, slow_ma, prev_fast, prev_slow
            )

        # --- Serialize persistent state ---
        trader_data = json.dumps({
            "tomato_fast": fast_ma.to_list(),
            "tomato_slow": slow_ma.to_list(),
            "prev_fast": fast_ma.average(),
            "prev_slow": slow_ma.average(),
        })

        return orders, 0, trader_data

    # ------------------------------------------------------------------ #
    #  EMERALDS — penny-the-spread market maker around fair value 10,000  #
    # ------------------------------------------------------------------ #

    def _market_make_emeralds(self, state: TradingState) -> list[Order]:
        depth: OrderDepth = state.order_depths["EMERALDS"]
        position = state.position.get("EMERALDS", 0)
        result: list[Order] = []

        # Best bid / ask from the book (may be empty)
        best_bid = max(depth.buy_orders) if depth.buy_orders else None
        best_ask = min(depth.sell_orders) if depth.sell_orders else None

        # --- Bid side ---
        if best_bid is not None:
            bid_price = min(best_bid + 1, self.EMERALD_FAIR - 1)  # penny but stay below fair
        else:
            bid_price = self.EMERALD_FAIR - self.EMERALD_DEFAULT_SPREAD

        buy_qty = PositionManager.max_buy_quantity(position)
        if buy_qty > 0:
            result.append(Order("EMERALDS", bid_price, buy_qty))

        # --- Ask side ---
        if best_ask is not None:
            ask_price = max(best_ask - 1, self.EMERALD_FAIR + 1)  # penny but stay above fair
        else:
            ask_price = self.EMERALD_FAIR + self.EMERALD_DEFAULT_SPREAD

        sell_qty = PositionManager.max_sell_quantity(position)
        if sell_qty > 0:
            result.append(Order("EMERALDS", ask_price, -sell_qty))

        return result

    # ------------------------------------------------------------------ #
    #  TOMATOES — dual MA crossover with incremental entry                #
    # ------------------------------------------------------------------ #

    def _trade_tomatoes(
        self,
        state: TradingState,
        fast_ma: RollingAverage,
        slow_ma: RollingAverage,
        prev_fast: float | None,
        prev_slow: float | None,
    ) -> list[Order]:
        depth: OrderDepth = state.order_depths["TOMATOES"]
        position = state.position.get("TOMATOES", 0)

        best_bid = max(depth.buy_orders) if depth.buy_orders else None
        best_ask = min(depth.sell_orders) if depth.sell_orders else None

        # Need both sides to compute mid-price
        if best_bid is None or best_ask is None:
            return []

        mid = (best_bid + best_ask) / 2
        fast_ma.update(mid)
        slow_ma.update(mid)

        fast_avg = fast_ma.average()
        slow_avg = slow_ma.average()

        # Not enough data yet for both MAs
        if fast_avg is None or slow_avg is None:
            return []

        # Detect crossover relative to previous tick
        if prev_fast is None or prev_slow is None:
            return []

        result: list[Order] = []

        # Bullish crossover: fast crosses above slow
        if prev_fast <= prev_slow and fast_avg > slow_avg:
            qty = min(self.TOMATO_ORDER_SIZE, PositionManager.max_buy_quantity(position))
            if qty > 0:
                result.append(Order("TOMATOES", best_ask, qty))

        # Bearish crossover: fast crosses below slow
        elif prev_fast >= prev_slow and fast_avg < slow_avg:
            qty = min(self.TOMATO_ORDER_SIZE, PositionManager.max_sell_quantity(position))
            if qty > 0:
                result.append(Order("TOMATOES", best_bid, -qty))

        return result
