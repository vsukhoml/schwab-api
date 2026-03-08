import warnings
from enum import Enum
from typing import Any, Dict, List, Union

import requests

from . import common


def _build_object(obj: Any) -> Any:
    # Literals are passed straight through
    if isinstance(obj, (str, int, float)):
        return obj

    # Extract value from Enums
    elif isinstance(obj, Enum):
        return obj.value

    # Dicts and lists are iterated over, with keys intact
    elif isinstance(obj, dict):
        return dict((key, _build_object(value)) for key, value in obj.items())
    elif isinstance(obj, list):
        return [_build_object(i) for i in obj]

    # Objects have their variables translated into keys
    else:
        ret = {}
        for name, value in vars(obj).items():
            if value is None or name[0] != "_":
                continue

            name = name[1:]
            ret[name] = _build_object(value)
        return ret


def truncate_float(flt: float) -> str:
    # truncate without rounding by converting to string and slicing
    s = f"{flt:.6f}"
    if "." in s:
        integer_part, decimal_part = s.split(".")
        if abs(flt) < 1 and flt != 0.0:
            return f"{integer_part}.{decimal_part[:4]}"
        else:
            return f"{integer_part}.{decimal_part[:2]}"
    return s


class OrderBuilder:
    """
    Helper class to create arbitrarily complex orders. Note this class simply
    implements the order schema defined in the `documentation
    <https://developer.schwabmeritrade.com/account-access/apis/post/accounts/
    %7BaccountId%7D/orders-0>`__, with no attempts to validate the result.
    Orders created using this class may be rejected or may never fill. Use at
    your own risk.
    """

    def __init__(self):
        self._session = None
        self._duration = None
        self._orderType = None
        self._complexOrderStrategyType = None
        self._quantity = None
        self._destinationLinkName = None
        self._stopPrice = None
        self._stopPriceLinkBasis = None
        self._stopPriceLinkType = None
        self._stopPriceOffset = None
        self._stopType = None
        self._priceLinkBasis = None
        self._priceLinkType = None
        self._price = None
        self._orderLegCollection = None
        self._activationPrice = None
        self._specialInstruction = None
        self._orderStrategyType = None
        self._childOrderStrategies = None

    # Session
    def set_session(self, session: Union[common.Session, str]):
        """
        Set the order session. Expected values (from Session enum):
        'NORMAL', 'AM', 'PM', 'SEAMLESS'
        """
        self._session = session
        return self

    def clear_session(self):
        """
        Clear the order session.
        """
        self._session = None
        return self

    # Duration
    def set_duration(self, duration: Union[common.Duration, str]):
        """
        Set the order duration. Expected values (from Duration enum):
        'DAY', 'GOOD_TILL_CANCEL', 'FILL_OR_KILL', 'IMMEDIATE_OR_CANCEL',
        'END_OF_WEEK', 'END_OF_MONTH', 'NEXT_END_OF_MONTH'
        """
        self._duration = duration
        return self

    def clear_duration(self):
        """
        Clear the order duration.
        """
        self._duration = None
        return self

    # OrderType
    def set_order_type(self, order_type: Union[common.OrderType, str]):
        """
        Set the order type. Expected values (from OrderType enum):
        'MARKET', 'LIMIT', 'STOP', 'STOP_LIMIT', 'TRAILING_STOP', 'CABINET',
        'NON_MARKETABLE', 'MARKET_ON_CLOSE', 'EXERCISE', 'TRAILING_STOP_LIMIT',
        'NET_DEBIT', 'NET_CREDIT', 'NET_ZERO', 'LIMIT_ON_CLOSE'
        """
        self._orderType = order_type
        return self

    def clear_order_type(self):
        """
        Clear the order type.
        """
        self._orderType = None
        return self

    # ComplexOrderStrategyType
    def set_complex_order_strategy_type(
        self, complex_order_strategy_type: Union[common.ComplexOrderStrategyType, str]
    ):
        """
        Set the complex order strategy type. Expected values (from ComplexOrderStrategyType enum):
        'NONE', 'COVERED', 'VERTICAL', 'BACK_RATIO', 'CALENDAR', 'DIAGONAL', 'STRADDLE',
        'STRANGLE', 'COLLAR_SYNTHETIC', 'BUTTERFLY', 'CONDOR', 'IRON_CONDOR', 'VERTICAL_ROLL',
        'COLLAR_WITH_STOCK', 'DOUBLE_DIAGONAL', 'UNBALANCED_BUTTERFLY', 'UNBALANCED_CONDOR',
        'UNBALANCED_IRON_CONDOR', 'UNBALANCED_VERTICAL_ROLL', 'MUTUAL_FUND_SWAP', 'CUSTOM'
        """
        self._complexOrderStrategyType = complex_order_strategy_type
        return self

    def clear_complex_order_strategy_type(self):
        """
        Clear the complex order strategy type.
        """
        self._complexOrderStrategyType = None
        return self

    # Quantity
    def set_quantity(self, quantity: float):
        """
        Exact semantics unknown. See :ref:`undocumented_quantity` for a
        discussion.
        """
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        self._quantity = quantity
        return self

    def clear_quantity(self):
        """
        Clear the order-level quantity. Note this does not affect order legs.
        """
        self._quantity = None
        return self

    # DestinationLinkName
    def set_destination_link_name(
        self, destination_link_name: Union[common.Destination, str]
    ):
        """
        Set the destination link name. Expected values (from Destination enum):
        'INET', 'ECN_ARCA', 'CBOE', 'AMEX', 'PHLX', 'ISE', 'BOX', 'NYSE', 'NASDAQ',
        'BATS', 'C2', 'AUTO'
        """
        self._destinationLinkName = destination_link_name
        return self

    def clear_destination_link_name(self):
        """
        Clear the destination link name
        """
        self._destinationLinkName = None
        return self

    # StopPrice
    def set_stop_price(self, stop_price: Union[float, str]):
        """
        Set the stop price. Note price can be passed as either a `float` or an
        `str`. See :ref:`number_truncation`.
        """
        if isinstance(stop_price, str):
            self._stopPrice = stop_price
        else:
            self._stopPrice = truncate_float(stop_price)
        return self

    def copy_stop_price(self, stop_price: Union[float, str]):
        """
        Directly set the stop price, avoiding all the validation and truncation
        logic from :func:`set_stop_price`.
        """
        self._stopPrice = stop_price
        return self

    def clear_stop_price(self):
        """
        Clear the stop price.
        """
        self._stopPrice = None
        return self

    # StopPriceLinkBasis
    def set_stop_price_link_basis(
        self, stop_price_link_basis: Union[common.StopPriceLinkBasis, str]
    ):
        """
        Set the stop price link basis. Expected values (from StopPriceLinkBasis enum):
        'MANUAL', 'BASE', 'TRIGGER', 'LAST', 'BID', 'ASK', 'ASK_BID', 'MARK', 'AVERAGE'
        """
        self._stopPriceLinkBasis = stop_price_link_basis
        return self

    def clear_stop_price_link_basis(self):
        """
        Clear the stop price link basis.
        """
        self._stopPriceLinkBasis = None
        return self

    # StopPriceLinkType
    def set_stop_price_link_type(
        self, stop_price_link_type: Union[common.StopPriceLinkType, str]
    ):
        """
        Set the stop price link type. Expected values (from StopPriceLinkType enum):
        'VALUE', 'PERCENT', 'TICK'
        """
        self._stopPriceLinkType = stop_price_link_type
        return self

    def clear_stop_price_link_type(self):
        """
        Clear the stop price link type.
        """
        self._stopPriceLinkType = None
        return self

    # StopPriceOffset
    def set_stop_price_offset(self, stop_price_offset: float):
        """
        Set the stop price offset.
        """
        self._stopPriceOffset = stop_price_offset
        return self

    def clear_stop_price_offset(self):
        """
        Clear the stop price offset.
        """
        self._stopPriceOffset = None
        return self

    # StopType
    def set_stop_type(self, stop_type: Union[common.StopType, str]):
        """
        Set the stop type. Expected values (from StopType enum):
        'STANDARD', 'BID', 'ASK', 'LAST', 'MARK'
        """
        self._stopType = stop_type
        return self

    def clear_stop_type(self):
        """
        Clear the stop type.
        """
        self._stopType = None
        return self

    # PriceLinkBasis
    def set_price_link_basis(self, price_link_basis: Union[common.PriceLinkBasis, str]):
        """
        Set the price link basis. Expected values (from PriceLinkBasis enum):
        'MANUAL', 'BASE', 'TRIGGER', 'LAST', 'BID', 'ASK', 'ASK_BID', 'MARK', 'AVERAGE'
        """
        self._priceLinkBasis = price_link_basis
        return self

    def clear_price_link_basis(self):
        """
        Clear the price link basis.
        """
        self._priceLinkBasis = None
        return self

    # PriceLinkType
    def set_price_link_type(self, price_link_type: Union[common.PriceLinkType, str]):
        """
        Set the price link type. Expected values (from PriceLinkType enum):
        'VALUE', 'PERCENT', 'TICK'
        """
        self._priceLinkType = price_link_type
        return self

    def clear_price_link_type(self):
        """
        Clear the price link basis.
        """
        self._priceLinkType = None
        return self

    # Price
    def set_price(self, price: Union[float, str]):
        """
        Set the order price. Note price can be passed as either a `float` or an
        `str`. See :ref:`number_truncation`.
        """
        if isinstance(price, str):
            self._price = price
        else:
            self._price = truncate_float(price)
        return self

    def copy_price(self, price: Union[float, str]):
        """
        Directly set the stop price, avoiding all the validation and truncation
        logic from :func:`set_price`.
        """
        self._price = price
        return self

    def clear_price(self):
        """
        Clear the order price
        """
        self._price = None
        return self

    # ActivationPrice
    def set_activation_price(self, activation_price: float):
        """
        Set the activation price.
        """
        if activation_price <= 0.0:
            raise ValueError("activation price must be positive")
        self._activationPrice = activation_price
        return self

    def clear_activation_price(self):
        """
        Clear the activation price.
        """
        self._activationPrice = None
        return self

    # SpecialInstruction
    def set_special_instruction(
        self, special_instruction: Union[common.SpecialInstruction, str]
    ):
        """
        Set the special instruction. Expected values (from SpecialInstruction enum):
        'ALL_OR_NONE', 'DO_NOT_REDUCE', 'ALL_OR_NONE_DO_NOT_REDUCE'
        """
        self._specialInstruction = special_instruction
        return self

    def clear_special_instruction(self):
        """
        Clear the special instruction.
        """
        self._specialInstruction = None
        return self

    # OrderStrategyType
    def set_order_strategy_type(
        self, order_strategy_type: Union[common.OrderStrategyType, str]
    ):
        """
        Set the order strategy type. Expected values (from OrderStrategyType enum):
        'SINGLE', 'CANCEL', 'RECALL', 'PAIR', 'FLATTEN', 'TWO_DAY_SWAP', 'BLAST_ALL', 'OCO', 'TRIGGER'
        """
        self._orderStrategyType = order_strategy_type
        return self

    def clear_order_strategy_type(self):
        """
        Clear the order strategy type.
        """
        self._orderStrategyType = None
        return self

    # ChildOrderStrategies
    def add_child_order_strategy(
        self, child_order_strategy: Union["OrderBuilder", Dict]
    ):
        if isinstance(child_order_strategy, requests.Response):
            raise ValueError(
                "Child order cannot be a response. See here for "
                + "details: https://schwab-api.readthedocs.io/en/latest/"
                + "order-templates.html#utility-methods"
            )

        if not isinstance(child_order_strategy, OrderBuilder) and not isinstance(
            child_order_strategy, dict
        ):
            raise ValueError("child order must be OrderBuilder or dict")

        if self._childOrderStrategies is None:
            self._childOrderStrategies = []

        self._childOrderStrategies.append(child_order_strategy)
        return self

    def clear_child_order_strategies(self):
        self._childOrderStrategies = None
        return self

    # OrderLegCollection
    def __add_order_leg(self, instruction: Any, instrument: Any, quantity: float):
        # instruction is assumed to have been verified

        if quantity <= 0:
            raise ValueError("quantity must be positive")

        if self._orderLegCollection is None:
            self._orderLegCollection = []

        self._orderLegCollection.append(
            {
                "instruction": instruction,
                "instrument": instrument,
                "quantity": quantity,
            }
        )

        return self

    def add_equity_leg(
        self,
        instruction: Union[common.EquityInstruction, str],
        symbol: str,
        quantity: float,
    ):
        """
        Add an equity order leg.

        :param instruction: Instruction for the leg. Expected values:
                            'BUY', 'SELL', 'SELL_SHORT', 'BUY_TO_COVER'
        :param symbol: Equity symbol
        :param quantity: Number of shares for the order
        """
        return self.__add_order_leg(
            instruction, common.EquityInstrument(symbol), quantity
        )

    def add_option_leg(
        self,
        instruction: Union[common.OptionInstruction, str],
        symbol: str,
        quantity: float,
    ):
        """
        Add an option order leg.

        :param instruction: Instruction for the leg. Expected values:
                            'BUY_TO_OPEN', 'SELL_TO_CLOSE', 'SELL_TO_OPEN', 'BUY_TO_CLOSE'
        :param symbol: Option symbol
        :param quantity: Number of contracts for the order
        """
        return self.__add_order_leg(
            instruction, common.OptionInstrument(symbol), quantity
        )

    def clear_order_legs(self):
        """
        Clear all order legs.
        """
        self._orderLegCollection = None
        return self

    # Build

    def build(self) -> Dict[str, Any]:
        return _build_object(self)
