"""
trader.py — IMC Prosperity 4 | Round 1 Baseline ("Gold Standard")

Architecture
------------
RollingStats   : Fixed-window descriptive statistics (mean, variance, std_dev, z_score).
PositionManager: Static helpers enforcing the ±20 position hard limit.
Trader         : Main engine. run() is called every tick by the Prosperity simulator.

Strategies
----------
EMERALDS  : Hybrid Sniper + Dynamic Penny Maker around hard-coded fair value 10,000.
              Phase 1 sweeps mispriced orders that cross fair value (risk-free PnL).
              Phase 2 penny-quotes remaining capacity, clamped to never cross fair value.

TOMATOES  : Velocity-based Regime Switch.
              Velocity = 5-tick change in WAP (thermostat).
              - Bull breakout  (velocity >  8): aggressive taker bid only; suppress asks.
              - Bear breakout  (velocity < -8): aggressive taker ask only; suppress bids.
              - Ranging market (|velocity| ≤ 8): WAP + inventory-skew passive maker.

Round 1 Hooks
-------------
_run_pairs_trading() is a skeleton ready to be populated once correlated assets appear.
"""

import json
import math
from datamodel import Order, OrderDepth, TradingState


# ---------------------------------------------------------------------------
# Math Engine
# ---------------------------------------------------------------------------

class RollingStats:
    """
    Fixed-window rolling statistics backed by a plain Python list.

    All statistical methods return None when the window is not yet full,
    so callers can safely guard with ``if value is not None``.

    Parameters
    ----------
    period : int
        Number of observations to keep in the window.
    data : list[float] | None
        Pre-populated window (used for deserialisation from traderData).
    """

    def __init__(self, period: int, data: list[float] | None = None):
        self.period = period
        self.data: list[float] = data if data is not None else []

    def update(self, value: float) -> None:
        """Append a new observation; evict the oldest when over ``period``."""
        self.data.append(value)
        if len(self.data) > self.period:
            self.data.pop(0)

    def average(self) -> float | None:
        """Population mean. Returns None until the window is full."""
        if len(self.data) < self.period:
            return None
        return sum(self.data) / len(self.data)

    def variance(self) -> float | None:
        """Population variance: Σ(x − μ)² / N. Returns None until window is full."""
        mean = self.average()
        if mean is None:
            return None
        return sum((x - mean) ** 2 for x in self.data) / len(self.data)

    def std_dev(self) -> float | None:
        """Population standard deviation (√variance). Returns None until window is full."""
        var = self.variance()
        if var is None:
            return None
        return math.sqrt(var)

    def z_score(self, value: float) -> float | None:
        """
        Standardised distance of ``value`` from the rolling mean.

        Returns None when the window is not full or std_dev is zero
        (flat price series produces a degenerate distribution).
        """
        mean = self.average()
        sd = self.std_dev()
        if mean is None or sd is None or sd == 0:
            return None
        return (value - mean) / sd

    def to_list(self) -> list[float]:
        """Return the raw window (used for traderData serialisation)."""
        return self.data


# ---------------------------------------------------------------------------
# Position Manager
# ---------------------------------------------------------------------------

class PositionManager:
    """
    Static helpers that enforce the ±20 position hard limit on every order.

    Usage
    -----
    buy_qty  = PositionManager.max_buy_quantity(position)
    sell_qty = PositionManager.max_sell_quantity(position)
    """

    @staticmethod
    def max_buy_quantity(position: int, limit: int = 20) -> int:
        """Maximum additional long units before hitting the +limit ceiling."""
        return limit - position

    @staticmethod
    def max_sell_quantity(position: int, limit: int = 20) -> int:
        """Maximum additional short units before hitting the -limit floor."""
        return position + limit


# ---------------------------------------------------------------------------
# Trader
# ---------------------------------------------------------------------------

class Trader:
    """
    Main trading engine for IMC Prosperity 4.

    The Prosperity simulator calls ``run(state)`` once per market tick and
    expects a 3-tuple:
        (orders: dict[str, list[Order]], conversions: int, traderData: str)

    ``traderData`` is the only form of cross-tick memory — serialised to JSON
    here and deserialised at the start of the next tick.
    """

    # --- EMERALDS constants ---
    EMERALD_FAIR: int = 10_000
    EMERALD_DEFAULT_SPREAD: int = 2    # fallback half-spread when book is empty

    # --- TOMATOES constants ---
    TOMATO_WAP_PERIOD: int = 20
    TOMATO_INV_MAX_SHIFT: int = 3      # max inventory skew in price ticks
    TOMATO_SPREAD: int = 3
    VELOCITY_THRESHOLD: int = 8        # 5-tick WAP delta required to declare a breakout

    # ---------------------------------------------------------------------------

    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        """
        Top-level router called every tick.

        Deserialises rolling windows from traderData, dispatches each symbol
        to its strategy function, then re-serialises state for the next tick.
        """
        # --- Deserialise persistent state ---
        data: dict = json.loads(state.traderData) if state.traderData else {}
        tomato_wap = RollingStats(self.TOMATO_WAP_PERIOD, data.get("tomato_window", []))
        spread_stats = RollingStats(20, data.get("spread_window", []))

        orders: dict[str, list[Order]] = {}

        # --- Symbol router ---
        for symbol in state.order_depths:
            if symbol == "EMERALDS":
                orders["EMERALDS"] = self._trade_emeralds(state)
            elif symbol == "TOMATOES":
                orders["TOMATOES"] = self._trade_tomatoes(state, tomato_wap)

        # Pairs trading — activate when correlated Round 1 assets are confirmed
        # pairs_orders = self._run_pairs_trading(state, "ASSET_A", "ASSET_B", spread_stats)
        # orders.update(pairs_orders)

        # --- Serialise persistent state ---
        trader_data = json.dumps({
            "tomato_window": tomato_wap.to_list(),
            "spread_window": spread_stats.to_list(),
        })

        return orders, 0, trader_data

    # ------------------------------------------------------------------ #
    #  EMERALDS — Hybrid Sniper + Dynamic Penny Maker                    #
    #                                                                    #
    #  Phase 1 (Taker): sweep mispriced orders that cross fair value     #
    #  10,000 on either side — each fill is risk-free PnL.              #
    #  Phase 2 (Maker): penny the remaining best bid/ask for leftover    #
    #  capacity, clamped so quotes never cross fair value.               #
    # ------------------------------------------------------------------ #

    def _trade_emeralds(self, state: TradingState) -> list[Order]:
        """
        EMERALDS: Hybrid Sniper + Dynamic Penny Maker.

        Fair value is hardcoded at 10,000. The sniper phase locks in
        risk-free edge; the penny maker captures the spread on residual
        capacity using dynamic book-relative pricing.
        """
        depth: OrderDepth = state.order_depths["EMERALDS"]
        position = state.position.get("EMERALDS", 0)
        result: list[Order] = []

        # Phase 1a — Sniper: take underpriced asks (ask < fair value)
        for price in sorted(depth.sell_orders):
            if price >= self.EMERALD_FAIR:
                break
            available = PositionManager.max_buy_quantity(position)
            if available <= 0:
                break
            qty = min(available, abs(depth.sell_orders[price]))
            result.append(Order("EMERALDS", price, qty))
            position += qty

        # Phase 1b — Sniper: take overpriced bids (bid > fair value)
        for price in sorted(depth.buy_orders, reverse=True):
            if price <= self.EMERALD_FAIR:
                break
            available = PositionManager.max_sell_quantity(position)
            if available <= 0:
                break
            qty = min(available, depth.buy_orders[price])
            result.append(Order("EMERALDS", price, -qty))
            position -= qty

        # Phase 2 — Maker: dynamic penny quotes on remaining capacity
        best_bid = max(depth.buy_orders) if depth.buy_orders else None
        best_ask = min(depth.sell_orders) if depth.sell_orders else None

        bid_price = (
            min(best_bid + 1, self.EMERALD_FAIR - 1)
            if best_bid is not None
            else self.EMERALD_FAIR - self.EMERALD_DEFAULT_SPREAD
        )
        ask_price = (
            max(best_ask - 1, self.EMERALD_FAIR + 1)
            if best_ask is not None
            else self.EMERALD_FAIR + self.EMERALD_DEFAULT_SPREAD
        )

        buy_qty = PositionManager.max_buy_quantity(position)
        if buy_qty > 0:
            result.append(Order("EMERALDS", bid_price, buy_qty))

        sell_qty = PositionManager.max_sell_quantity(position)
        if sell_qty > 0:
            result.append(Order("EMERALDS", ask_price, -sell_qty))

        return result

    # ------------------------------------------------------------------ #
    #  TOMATOES — Velocity-Based Regime Switch                           #
    #                                                                    #
    #  Velocity = WAP[now] − WAP[5 ticks ago] (5-tick momentum).        #
    #  |velocity| > VELOCITY_THRESHOLD → breakout: one-sided taker.     #
    #  |velocity| ≤ VELOCITY_THRESHOLD → ranging: inventory-skew maker. #
    # ------------------------------------------------------------------ #

    def _trade_tomatoes(
        self,
        state: TradingState,
        tomato_wap: RollingStats,
    ) -> list[Order]:
        """
        TOMATOES: Velocity-based Regime Switch.

        The 5-tick WAP velocity acts as a thermostat separating breakout
        from ranging regimes:
          - Bull breakout  (velocity >  VELOCITY_THRESHOLD): aggressive bid,
            no asks — ride the wave up.
          - Bear breakout  (velocity < -VELOCITY_THRESHOLD): aggressive ask,
            no bids — ride the crash down.
          - Ranging market (|velocity| ≤ VELOCITY_THRESHOLD): symmetric
            inventory-skewed passive market maker around WAP.

        Breakout prices (WAP ± 1) cross the spread to guarantee taker fills
        during fast directional moves.
        """
        depth: OrderDepth = state.order_depths["TOMATOES"]
        position = state.position.get("TOMATOES", 0)

        best_bid = max(depth.buy_orders) if depth.buy_orders else None
        best_ask = min(depth.sell_orders) if depth.sell_orders else None

        if best_bid is None or best_ask is None:
            return []

        best_bid_vol = depth.buy_orders[best_bid]
        best_ask_vol = abs(depth.sell_orders[best_ask])
        total_vol = best_bid_vol + best_ask_vol

        # Step 1: Weighted Average Price as base fair value
        wap = (best_bid * best_ask_vol + best_ask * best_bid_vol) / total_vol
        tomato_wap.update(wap)

        # Step 2: 5-tick velocity thermostat
        wap_history = tomato_wap.to_list()
        velocity = wap - wap_history[-5] if len(wap_history) >= 5 else 0

        result: list[Order] = []
        buy_qty = PositionManager.max_buy_quantity(position)
        sell_qty = PositionManager.max_sell_quantity(position)

        # Step 3: Regime switch
        if velocity > self.VELOCITY_THRESHOLD:
            # Bull breakout — ride the wave up; suppress all asks
            if buy_qty > 0:
                result.append(Order("TOMATOES", int(round(wap)) - 1, buy_qty))

        elif velocity < -self.VELOCITY_THRESHOLD:
            # Bear breakout — ride the crash down; suppress all bids
            if sell_qty > 0:
                result.append(Order("TOMATOES", int(round(wap)) + 1, -sell_qty))

        else:
            # Ranging market — inventory-skewed passive market maker
            inventory_shift = -(position / 20.0) * self.TOMATO_INV_MAX_SHIFT
            target_price = wap + inventory_shift
            bid_price = int(round(target_price)) - self.TOMATO_SPREAD
            ask_price = int(round(target_price)) + self.TOMATO_SPREAD

            if buy_qty > 0:
                result.append(Order("TOMATOES", bid_price, buy_qty))
            if sell_qty > 0:
                result.append(Order("TOMATOES", ask_price, -sell_qty))

        return result

    # ------------------------------------------------------------------ #
    #  PAIRS TRADING — Skeleton (Round 1 ready)                         #
    # ------------------------------------------------------------------ #

    def _run_pairs_trading(
        self,
        state: TradingState,
        asset_a: str,
        asset_b: str,
        spread_stats: RollingStats,
    ) -> dict[str, list[Order]]:
        """
        Pairs trading skeleton using spread Z-score mean reversion.

        Execution logic (to implement when assets are confirmed):
          - spread_z >  2.0 → Short A, Buy B  (spread reverts down)
          - spread_z < -2.0 → Buy A, Short B  (spread reverts up)
          - |spread_z| ≤ 2.0 → Hold / no action

        Returns an empty dict until activated.
        """
        depth_a = state.order_depths.get(asset_a)
        depth_b = state.order_depths.get(asset_b)

        if depth_a is None or depth_b is None:
            return {}

        # Mid-prices
        best_bid_a = max(depth_a.buy_orders) if depth_a.buy_orders else None
        best_ask_a = min(depth_a.sell_orders) if depth_a.sell_orders else None
        best_bid_b = max(depth_b.buy_orders) if depth_b.buy_orders else None
        best_ask_b = min(depth_b.sell_orders) if depth_b.sell_orders else None

        if None in (best_bid_a, best_ask_a, best_bid_b, best_ask_b):
            return {}

        mid_a = (best_bid_a + best_ask_a) / 2
        mid_b = (best_bid_b + best_ask_b) / 2

        # Spread Z-score (window warms up over 20 ticks)
        current_spread = mid_a - mid_b
        spread_stats.update(current_spread)
        # spread_z = spread_stats.z_score(current_spread)

        # TODO: implement execution once asset pair is confirmed for Round 1
        # IF spread_z >  2.0: sell asset_a, buy  asset_b
        # IF spread_z < -2.0: buy  asset_a, sell asset_b

        return {}
