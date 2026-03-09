from enum import Enum


class __BaseInstrument:
    def __init__(self, asset_type, symbol):
        self._assetType = asset_type
        self._symbol = symbol


class EquityInstrument(__BaseInstrument):
    """Represents an equity when creating order legs."""

    def __init__(self, symbol):
        super().__init__("EQUITY", symbol)


class OptionInstrument(__BaseInstrument):
    """Represents an option when creating order legs."""

    def __init__(self, symbol):
        super().__init__("OPTION", symbol)


class InvalidOrderException(Exception):
    """Raised when attempting to build an incomplete order"""

    pass


class Duration(Enum):
    """
    Length of time over which the trade will be active.
    """

    #: Cancel the trade at the end of the trading day. Note if the order cannot
    #: be filled all at once, you may see partial executions throughout the day.
    DAY = "DAY"

    #: Keep the trade open for six months, or until the end of the cancel date,
    #: whichever is shorter. Note if the order cannot be filled all at once, you
    #: may see partial executions over the lifetime of the order.
    GOOD_TILL_CANCEL = "GOOD_TILL_CANCEL"

    #: Either execute the order immediately at the specified price, or cancel it
    #: immediately.
    FILL_OR_KILL = "FILL_OR_KILL"

    #: Execute the order immediately; any portion that cannot be filled is cancelled.
    IMMEDIATE_OR_CANCEL = "IMMEDIATE_OR_CANCEL"

    #: Order remains active until the end of the current trading week.
    END_OF_WEEK = "END_OF_WEEK"

    #: Order remains active until the end of the current calendar month.
    END_OF_MONTH = "END_OF_MONTH"

    #: Order remains active until the end of the following calendar month.
    NEXT_END_OF_MONTH = "NEXT_END_OF_MONTH"


class Session(Enum):
    """
    The market session during which the order trade should be executed.
    """

    #: Normal market hours, from 9:30am to 4:00pm Eastern.
    NORMAL = "NORMAL"

    #: Premarket session, from 8:00am to 9:30am Eastern.
    AM = "AM"

    #: After-market session, from 4:00pm to 8:00pm Eastern.
    PM = "PM"

    #: Orders are active during all trading sessions except the overnight
    #: session. This is the union of ``NORMAL``, ``AM``, and ``PM``.
    SEAMLESS = "SEAMLESS"


class OrderType(Enum):
    """
    Type of order to place.
    """

    #: Execute the order immediately at the best-available price.
    #: `More Info <https://www.investopedia.com/terms/m/marketorder.asp>`__.
    MARKET = "MARKET"

    #: Execute the order at your price or better.
    #: `More info <https://www.investopedia.com/terms/l/limitorder.asp>`__.
    LIMIT = "LIMIT"

    #: Wait until the price reaches the stop price, and then immediately place a
    #: market order.
    #: `More Info <https://www.investopedia.com/terms/l/limitorder.asp>`__.
    STOP = "STOP"

    #: Wait until the price reaches the stop price, and then immediately place a
    #: limit order at the specified price. `More Info
    #: <https://www.investopedia.com/terms/s/stop-limitorder.asp>`__.
    STOP_LIMIT = "STOP_LIMIT"

    #: Similar to ``STOP``, except if the price moves in your favor, the stop
    #: price is adjusted in that direction. Places a market order if the stop
    #: condition is met.
    #: `More info <https://www.investopedia.com/terms/t/trailingstop.asp>`__.
    TRAILING_STOP = "TRAILING_STOP"

    #: A limit order to sell at a very low price (usually $0.01) to close a worthless position.
    CABINET = "CABINET"

    #: An order that is not immediately executable at current market prices.
    NON_MARKETABLE = "NON_MARKETABLE"

    #: Place the order at the closing price immediately upon market close.
    #: `More info <https://www.investopedia.com/terms/m/marketonclose.asp>`__
    MARKET_ON_CLOSE = "MARKET_ON_CLOSE"

    #: Request to exercise an option contract.
    EXERCISE = "EXERCISE"

    #: Similar to ``STOP_LIMIT``, except if the price moves in your favor, the
    #: stop price is adjusted in that direction. Places a limit order at the
    #: specified price if the stop condition is met.
    #: `More info <https://www.investopedia.com/terms/t/trailingstop.asp>`__.
    TRAILING_STOP_LIMIT = "TRAILING_STOP_LIMIT"

    #: Place an order for an options spread resulting in a net payment (debit).
    #: `More info <https://www.investopedia.com/ask/answers/042215/
    #: whats-difference-between-credit-spread-and-debt-spread.asp>`__
    NET_DEBIT = "NET_DEBIT"

    #: Place an order for an options spread resulting in a net receipt (credit).
    #: `More info <https://www.investopedia.com/ask/answers/042215/
    #: whats-difference-between-credit-spread-and-debt-spread.asp>`__
    NET_CREDIT = "NET_CREDIT"

    #: Place an order for an options spread resulting in neither a credit nor a
    #: debit (even money).
    #: `More info <https://www.investopedia.com/ask/answers/042215/
    #: whats-difference-between-credit-spread-and-debt-spread.asp>`__
    NET_ZERO = "NET_ZERO"

    #: A limit order to be executed as close to the market close as possible.
    LIMIT_ON_CLOSE = "LIMIT_ON_CLOSE"


class ComplexOrderStrategyType(Enum):
    """
    Explicit order strategies for executing multi-leg options orders.
    """

    #: No complex order strategy. This is the default.
    NONE = "NONE"

    #: Strategy consisting of writing a call that is covered by an equivalent long stock position.
    #: `More info <https://www.optionseducation.org/strategies/all-strategies/covered-call-buy-write>`__
    COVERED = "COVERED"

    #: Strategy consisting of buying one option and selling another of the same type with a different strike.
    #: `More info <https://www.optionseducation.org/strategies/all-strategies/bull-call-spread-debit-call-spread>`__
    VERTICAL = "VERTICAL"

    #: A high-delta strategy using different numbers of long and short options.
    #: `More info <https://www.optionseducation.org/strategies/all-strategies/long-ratio-call-spread>`__
    BACK_RATIO = "BACK_RATIO"

    #: Strategy using the same strike price but different expiration months.
    #: `More info <https://www.optionseducation.org/strategies/all-strategies/long-call-calendar-spread-call-horizontal>`__
    CALENDAR = "CALENDAR"

    #: Strategy using different strikes AND different expiration months.
    #: `More info <https://www.optionseducation.org/strategies/all-strategies/diagonal-call-spread>`__
    DIAGONAL = "DIAGONAL"

    #: Strategy consisting of buying/selling both a call and a put with the same strike and expiration.
    #: `More info <https://www.optionseducation.org/strategies/all-strategies/long-straddle>`__
    STRADDLE = "STRADDLE"

    #: Strategy consisting of buying/selling both a call and a put with different strikes but same expiration.
    #: `More info <https://www.optionseducation.org/strategies/all-strategies/long-strangle-long-combination>`__
    STRANGLE = "STRANGLE"

    #: A synthetic position combining options to mimic a collar.
    COLLAR_SYNTHETIC = "COLLAR_SYNTHETIC"

    #: A neutral strategy using four options of the same expiration with three different strike prices.
    #: `More info <https://www.optionseducation.org/strategies/all-strategies/long-call-butterfly>`__
    BUTTERFLY = "BUTTERFLY"

    #: A neutral strategy similar to a butterfly but with four different strike prices.
    #: `More info <https://www.optionseducation.org/strategies/all-strategies/long-call-condor>`__
    CONDOR = "CONDOR"

    #: A limited-risk, limited-reward strategy using two spreads (put and call) to profit from low volatility.
    #: `More info <https://www.optionseducation.org/strategies/all-strategies/short-condor>`__
    IRON_CONDOR = "IRON_CONDOR"

    #: Moving an existing vertical spread to a different expiration or strike.
    #: `More info <https://www.schwab.com/learn/story/three-options-trading-adjustment-strategies>`__
    VERTICAL_ROLL = "VERTICAL_ROLL"

    #: Hedging a long stock position by buying an OTM put and selling an OTM call.
    #: `More info <https://www.optionseducation.org/strategies/all-strategies/collar-protective-collar>`__
    COLLAR_WITH_STOCK = "COLLAR_WITH_STOCK"

    #: A strategy combining two diagonal spreads.
    #: `More info <https://optionstradingiq.com/the-ultimate-guide-to-double-diagonal-spreads/>`__
    DOUBLE_DIAGONAL = "DOUBLE_DIAGONAL"

    #: A butterfly spread with asymmetric wings, creating a directional bias.
    #: `More info <https://www.schwab.com/learn/story/unbalanced-butterfly-and-strong-directional-bias>`__
    UNBALANCED_BUTTERFLY = "UNBALANCED_BUTTERFLY"

    #: A condor spread with asymmetric wings.
    #: `More info https://optionstradingiq.com/asymmetric-condor/`
    UNBALANCED_CONDOR = "UNBALANCED_CONDOR"

    #: An iron condor spread with asymmetric wings.
    #: `More info https://optionstradingiq.com/what-is-an-unbalanced-iron-condor/`
    UNBALANCED_IRON_CONDOR = "UNBALANCED_IRON_CONDOR"

    #: Rolling an existing vertical spread into a new position with different ratios.
    UNBALANCED_VERTICAL_ROLL = "UNBALANCED_VERTICAL_ROLL"

    #: A strategy for exchanging one mutual fund for another.
    MUTUAL_FUND_SWAP = "MUTUAL_FUND_SWAP"

    #: A custom multi-leg order strategy defined by the user.
    CUSTOM = "CUSTOM"


class Destination(Enum):
    """
    Specific exchanges or routing destinations for orders.
    """

    #: Island ECN
    INET = "INET"
    #: Archipelago ECN (NYSE Arca)
    ECN_ARCA = "ECN_ARCA"
    #: Chicago Board Options Exchange
    CBOE = "CBOE"
    #: American Stock Exchange
    AMEX = "AMEX"
    #: Philadelphia Stock Exchange
    PHLX = "PHLX"
    #: International Securities Exchange
    ISE = "ISE"
    #: Boston Options Exchange
    BOX = "BOX"
    #: New York Stock Exchange
    NYSE = "NYSE"
    #: NASDAQ Stock Market
    NASDAQ = "NASDAQ"
    #: BATS Global Markets
    BATS = "BATS"
    #: CBOE C2 Options Exchange
    C2 = "C2"
    #: Automatic routing (default)
    AUTO = "AUTO"


class StopPriceLinkBasis(Enum):
    """
    The price basis used to calculate a dynamic stop price.
    """

    #: Manually specified price.
    MANUAL = "MANUAL"
    #: Base price of the security.
    BASE = "BASE"
    #: Price that triggers the order.
    TRIGGER = "TRIGGER"
    #: Most recent trade price.
    LAST = "LAST"
    #: Current best bid price.
    BID = "BID"
    #: Current best ask price.
    ASK = "ASK"
    #: Midpoint between bid and ask.
    ASK_BID = "ASK_BID"
    #: Mark price (midpoint of NBBO).
    MARK = "MARK"
    #: Average price.
    AVERAGE = "AVERAGE"


class StopPriceLinkType(Enum):
    """
    The mathematical method used for the stop price link.
    """

    #: Absolute dollar value.
    VALUE = "VALUE"
    #: Percentage offset.
    PERCENT = "PERCENT"
    #: Price increment (tick) offset.
    TICK = "TICK"


class StopType(Enum):
    """
    The price condition used to trigger a stop order.
    """

    #: Standard stop trigger logic.
    STANDARD = "STANDARD"
    #: Triggered by the bid price.
    BID = "BID"
    #: Triggered by the ask price.
    ASK = "ASK"
    #: Triggered by the last trade price.
    LAST = "LAST"
    #: Triggered by the mark price.
    MARK = "MARK"


class PriceLinkBasis(Enum):
    """
    The price basis used to calculate a dynamic limit price.
    """

    #: Manually specified price.
    MANUAL = "MANUAL"
    #: Base price of the security.
    BASE = "BASE"
    #: Price that triggers the order.
    TRIGGER = "TRIGGER"
    #: Most recent trade price.
    LAST = "LAST"
    #: Current best bid price.
    BID = "BID"
    #: Current best ask price.
    ASK = "ASK"
    #: Midpoint between bid and ask.
    ASK_BID = "ASK_BID"
    #: Mark price (midpoint of NBBO).
    MARK = "MARK"
    #: Average price.
    AVERAGE = "AVERAGE"


class PriceLinkType(Enum):
    """
    The mathematical method used for the limit price link.
    """

    #: Absolute dollar value.
    VALUE = "VALUE"
    #: Percentage offset.
    PERCENT = "PERCENT"
    #: Price increment (tick) offset.
    TICK = "TICK"


class TaxLotMethod(Enum):
    """
    Methods for selecting which tax lots to sell for capital gains purposes.
    """

    #: First-In, First-Out: Sell the oldest shares first.
    FIFO = "FIFO"
    #: Last-In, First-Out: Sell the newest shares first.
    LIFO = "LIFO"
    #: Sell the shares with the highest purchase price first.
    HIGH_COST = "HIGH_COST"
    #: Sell the shares with the lowest purchase price first.
    LOW_COST = "LOW_COST"
    #: Sell shares based on their average cost.
    AVERAGE_COST = "AVERAGE_COST"
    #: Manually select specific lots to sell (Note: Currently unimplemented by Schwab API).
    SPECIFIC_LOT = "SPECIFIC_LOT"
    #: Automatically select lots to minimize tax liability.
    LOSS_HARVESTER = "LOSS_HARVESTER"


class EquityInstruction(Enum):
    """
    Instructions for opening and closing equity positions.
    """

    #: Open a long equity position by purchasing shares.
    BUY = "BUY"

    #: Close a long equity position by selling shares.
    SELL = "SELL"

    #: Open a short equity position by selling borrowed shares.
    SELL_SHORT = "SELL_SHORT"

    #: Close a short equity position by purchasing shares to return.
    BUY_TO_COVER = "BUY_TO_COVER"


class OptionInstruction(Enum):
    """
    Instructions for opening and closing options positions.
    """

    #: Enter a new long option position by buying contracts.
    BUY_TO_OPEN = "BUY_TO_OPEN"

    #: Exit an existing long option position by selling contracts.
    SELL_TO_CLOSE = "SELL_TO_CLOSE"

    #: Enter a short position in an option by writing (selling) contracts.
    SELL_TO_OPEN = "SELL_TO_OPEN"

    #: Exit an existing short position in an option by buying back contracts.
    BUY_TO_CLOSE = "BUY_TO_CLOSE"


class SpecialInstruction(Enum):
    """
    Special handling instructions for trade execution.
    """

    #: Disallow partial order execution; the entire order must be filled or nothing.
    #: `More info <https://www.investopedia.com/terms/a/aon.asp>`__.
    ALL_OR_NONE = "ALL_OR_NONE"

    #: Do not reduce the limit price in response to cash dividends.
    #: `More info <https://www.investopedia.com/terms/d/dnr.asp>`__.
    DO_NOT_REDUCE = "DO_NOT_REDUCE"

    #: Combined instruction: entire order must fill AND price won't be reduced for dividends.
    ALL_OR_NONE_DO_NOT_REDUCE = "ALL_OR_NONE_DO_NOT_REDUCE"


class OrderStrategyType(Enum):
    """
    Rules for multi-order sequences and conditional logic.
    """

    #: No chaining, only a single order is submitted.
    SINGLE = "SINGLE"

    #: Order to cancel an existing order.
    CANCEL = "CANCEL"
    #: Order to recall a mutual fund.
    RECALL = "RECALL"
    #: Pair trading strategy.
    PAIR = "PAIR"
    #: Order to flatten (close) all positions in a security.
    FLATTEN = "FLATTEN"
    #: A two-day swap order.
    TWO_DAY_SWAP = "TWO_DAY_SWAP"
    #: Simultaneously submit multiple independent orders.
    BLAST_ALL = "BLAST_ALL"

    #: One-Cancels-Other: Execution of one order cancels the others in the group.
    OCO = "OCO"

    #: One-Triggers-Other: Execution of one order triggers placement of the next.
    TRIGGER = "TRIGGER"


def one_cancels_other(order1, order2):
    """
    If one of the orders is executed, immediately cancel the other.
    """
    from .generic import OrderBuilder

    return (
        OrderBuilder()
        .set_order_strategy_type(OrderStrategyType.OCO)
        .add_child_order_strategy(order1)
        .add_child_order_strategy(order2)
    )


def first_triggers_second(first_order, second_order):
    """
    If ``first_order`` is executed, immediately place ``second_order``.
    """
    from .generic import OrderBuilder

    return first_order.set_order_strategy_type(
        OrderStrategyType.TRIGGER
    ).add_child_order_strategy(second_order)
