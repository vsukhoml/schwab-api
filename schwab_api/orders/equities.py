from enum import Enum

from .common import Duration, Session
from .generic import OrderBuilder

##########################################################################
# Buy orders


def equity_buy_market(symbol: str, quantity: int) -> "OrderBuilder":
    """
    Returns a pre-filled :class:`~schwab_api.orders.generic.OrderBuilder` for an equity
    buy market order.
    """
    from .common import (Duration, EquityInstruction, OrderStrategyType,
                         OrderType, Session)
    from .generic import OrderBuilder

    return (
        OrderBuilder()
        .set_order_type(OrderType.MARKET)
        .set_session(Session.NORMAL)
        .set_duration(Duration.DAY)
        .set_order_strategy_type(OrderStrategyType.SINGLE)
        .add_equity_leg(EquityInstruction.BUY, symbol, quantity)
    )


def equity_buy_limit(symbol: str, quantity: int, price: float) -> "OrderBuilder":
    """
    Returns a pre-filled :class:`~schwab_api.orders.generic.OrderBuilder` for an equity
    buy limit order.
    """
    from .common import (Duration, EquityInstruction, OrderStrategyType,
                         OrderType, Session)
    from .generic import OrderBuilder

    return (
        OrderBuilder()
        .set_order_type(OrderType.LIMIT)
        .set_price(price)
        .set_session(Session.NORMAL)
        .set_duration(Duration.DAY)
        .set_order_strategy_type(OrderStrategyType.SINGLE)
        .add_equity_leg(EquityInstruction.BUY, symbol, quantity)
    )


##########################################################################
# Sell orders


def equity_sell_market(symbol: str, quantity: int) -> "OrderBuilder":
    """
    Returns a pre-filled :class:`~schwab_api.orders.generic.OrderBuilder` for an equity
    sell market order.
    """
    from .common import (Duration, EquityInstruction, OrderStrategyType,
                         OrderType, Session)
    from .generic import OrderBuilder

    return (
        OrderBuilder()
        .set_order_type(OrderType.MARKET)
        .set_session(Session.NORMAL)
        .set_duration(Duration.DAY)
        .set_order_strategy_type(OrderStrategyType.SINGLE)
        .add_equity_leg(EquityInstruction.SELL, symbol, quantity)
    )


def equity_sell_limit(symbol: str, quantity: int, price: float) -> "OrderBuilder":
    """
    Returns a pre-filled :class:`~schwab_api.orders.generic.OrderBuilder` for an equity
    sell limit order.
    """
    from .common import (Duration, EquityInstruction, OrderStrategyType,
                         OrderType, Session)
    from .generic import OrderBuilder

    return (
        OrderBuilder()
        .set_order_type(OrderType.LIMIT)
        .set_price(price)
        .set_session(Session.NORMAL)
        .set_duration(Duration.DAY)
        .set_order_strategy_type(OrderStrategyType.SINGLE)
        .add_equity_leg(EquityInstruction.SELL, symbol, quantity)
    )


##########################################################################
# Short sell orders


def equity_sell_short_market(symbol: str, quantity: int) -> "OrderBuilder":
    """
    Returns a pre-filled :class:`~schwab_api.orders.generic.OrderBuilder` for an equity
    short sell market order.
    """
    from .common import (Duration, EquityInstruction, OrderStrategyType,
                         OrderType, Session)
    from .generic import OrderBuilder

    return (
        OrderBuilder()
        .set_order_type(OrderType.MARKET)
        .set_session(Session.NORMAL)
        .set_duration(Duration.DAY)
        .set_order_strategy_type(OrderStrategyType.SINGLE)
        .add_equity_leg(EquityInstruction.SELL_SHORT, symbol, quantity)
    )


def equity_sell_short_limit(symbol: str, quantity: int, price: float) -> "OrderBuilder":
    """
    Returns a pre-filled :class:`~schwab_api.orders.generic.OrderBuilder` for an equity
    short sell limit order.
    """
    from .common import (Duration, EquityInstruction, OrderStrategyType,
                         OrderType, Session)
    from .generic import OrderBuilder

    return (
        OrderBuilder()
        .set_order_type(OrderType.LIMIT)
        .set_price(price)
        .set_session(Session.NORMAL)
        .set_duration(Duration.DAY)
        .set_order_strategy_type(OrderStrategyType.SINGLE)
        .add_equity_leg(EquityInstruction.SELL_SHORT, symbol, quantity)
    )


##########################################################################
# Buy to cover orders


def equity_buy_to_cover_market(symbol: str, quantity: int) -> "OrderBuilder":
    """
    Returns a pre-filled :class:`~schwab_api.orders.generic.OrderBuilder` for an equity
    buy-to-cover market order.
    """
    from .common import (Duration, EquityInstruction, OrderStrategyType,
                         OrderType, Session)
    from .generic import OrderBuilder

    return (
        OrderBuilder()
        .set_order_type(OrderType.MARKET)
        .set_session(Session.NORMAL)
        .set_duration(Duration.DAY)
        .set_order_strategy_type(OrderStrategyType.SINGLE)
        .add_equity_leg(EquityInstruction.BUY_TO_COVER, symbol, quantity)
    )


def equity_buy_to_cover_limit(
    symbol: str, quantity: int, price: float
) -> "OrderBuilder":
    """
    Returns a pre-filled :class:`~schwab_api.orders.generic.OrderBuilder` for an equity
    buy-to-cover limit order.
    """
    from .common import (Duration, EquityInstruction, OrderStrategyType,
                         OrderType, Session)
    from .generic import OrderBuilder

    return (
        OrderBuilder()
        .set_order_type(OrderType.LIMIT)
        .set_price(price)
        .set_session(Session.NORMAL)
        .set_duration(Duration.DAY)
        .set_order_strategy_type(OrderStrategyType.SINGLE)
        .add_equity_leg(EquityInstruction.BUY_TO_COVER, symbol, quantity)
    )
