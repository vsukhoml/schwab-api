---
name: schwab-api
description: >
  Reference guide for the schwab_api Python library — a Charles Schwab Trading API client.
  Load automatically when: writing or reviewing code in schwab_api/, answering questions about
  its authentication, REST endpoints, streaming, order builder, option chain analysis, math
  utilities (MFIV, GEX, VIX-like index, Black-Scholes), AccountManager, PositionAnalyzer,
  IronCondor screening, or any Client method. Use as the authoritative source for method
  signatures, DataFrame column schemas, and architectural decisions before reading source code.
user-invocable: true
argument-hint: "[topic]"
allowed-tools: Read, Grep, Glob
---

# Schwab API Python Library Documentation

A lightweight, robust, and highly efficient Python client for the Charles Schwab Trading API. It relies on minimal core dependencies (`requests`, `websockets`, `cryptography`, `pytz`) while optionally supporting advanced libraries like `pandas` (for data manipulation) and `curl_cffi` (to mimic browser fingerprints for WAF evasion).

## Features

- **Automated Authentication:** A temporary local HTTPS server automatically catches the OAuth redirect to extract the authorization code. Falls back to manual input on headless servers.
- **Robust Token Management:** Tokens are persisted in JSON files with cross-platform file locks (`fcntl`/`msvcrt`) for cross-process safety, automatically refreshed, and securely encrypted at rest (AES-GCM-256).
- **Built-in Rate Limiting:** A thread-safe sliding-window rate limiter enforces the 120 requests/minute Schwab limit automatically. No application-level throttling required.
- **Transient Retry Decorator:** `retry_on_transient` wraps any function with configurable exponential backoff and jitter for `ServerError` and `RateLimitError`.
- **Declarative Order Builder:** Fully type-hinted templates for building complex orders (equities, multi-leg options) reliably.
- **Resilient Streaming:** Synchronous and native `asyncio` WebSocket clients with automatic reconnection, re-authentication, and state recovery. Typed field values (prices as `float`, sizes as `int`, booleans as `bool`) after a single-pass field map translation.
- **Granular Error Handling:** HTTP errors are translated into specific Python exceptions (e.g., `RateLimitError`, `ServerError`, `AuthError`).
- **Automatic Symbology:** Transparently converts Yahoo Finance tickers (e.g., `^SPX`, `BRK.B`) to Schwab formats (`$SPX`, `BRK/B`) within `price_history`, `instruments`, `option_chains`, `get_daily_price_history`, and `get_fundamentals`. Note: `quotes` and `quote` require Schwab-format symbols directly.
- **Algorithmic Utilities:** Helpers to extract positions (`extract_positions`), determine market-aware dates (`get_last_complete_trading_day`), and parse API responses into normalized Pandas DataFrames (`parse_option_chain_to_df`, `parse_options_expiration_to_df`, `parse_price_history_to_df`).
- **Mathematical Options Analysis:** Built-in `BlackScholesPricer` for theoretical Greeks, `calculate_gamma_exposure` (GEX) for dealer positioning, Model-Free Implied Volatility (`calculate_mfiv_from_df`), and VIX-style 30-day IV interpolation (`calculate_vix_like_index`).
- **Iron Condor Screening:** `OptionChainAnalyzer.get_iron_condors()` enumerates all valid Iron Condor candidates from a parsed option chain, computing net credit, max loss, credit-to-width ratio, and break-evens per combination.

## Installation

You can install the library directly from GitHub.

**Core Library:**
```bash
pip install git+https://github.com/vsukhoml/schwab-api.git
```

**With `curl_cffi` (Recommended for Anti-WAF Resilience):**
Mimics real browser TLS/JA3 fingerprints.
```bash
pip install "schwab-api[curl_cffi] @ git+https://github.com/vsukhoml/schwab-api.git"
```

**With Pandas (For Data Analysis):**
```bash
pip install "schwab-api[pandas] @ git+https://github.com/vsukhoml/schwab-api.git"
```

**Install All Extras (includes `curl_cffi`, `pandas`, `scipy`, `numpy`):**
```bash
pip install "schwab-api[all] @ git+https://github.com/vsukhoml/schwab-api.git"
```

## Getting Started

### 1. Initialization and Authentication

You must register an application on the [Schwab Developer Portal](https://developer.schwab.com/) to obtain an App Key and Secret. Ensure your callback URL (e.g., `https://127.0.0.1:8182`) matches exactly.

The client automatically handles the OAuth flow on the first run by opening your browser and capturing the callback on the specified port. Tokens and certificates are stored in `~/.config/schwab-api/`.

```python
from schwab_api import Client

client = Client(
    app_key="YOUR_APP_KEY",
    app_secret="YOUR_APP_SECRET",
    callback_url="https://127.0.0.1:8182"
)
```

#### Remote Authentication (Cloud / Headless Servers)
When running code on a headless cloud server, you can handle periodic manual logins in two ways:

1. **Callback Hook (`call_for_auth`):** You can pass a custom function to the `Client` to block execution and signal you (e.g., via a Telegram bot) when manual login is required.
   ```python
   def my_custom_auth_flow(auth_url: str, callback_url: str) -> str:
       # E.g., send `auth_url` to your phone via Telegram, wait for a reply,
       # and return the final redirected `https://127.0.0.1:8182/?code=...` URL.
       return "<URL_FROM_USER>"

   client = Client(..., call_for_auth=my_custom_auth_flow)
   ```

2. **The SCP File-Drop Approach:** Since the local laptop and cloud server use the exact same Schwab App Key and Secret, the derived AES-GCM encryption key is identical on both machines. You can run the initial automated flow locally, then securely copy your tokens:
   ```bash
   scp ~/.config/schwab-api/tokens.json user@cloud-server:~/.config/schwab-api/tokens.json
   ```
   The cloud script can gracefully catch the `AuthError`, wait for the SCP upload, and instantiate a new `Client` to load the refreshed tokens from disk.

### 2. Working with Accounts

Almost all endpoints require an encrypted "Account Hash" rather than the raw account number. You must retrieve these hashes first.

```python
# Get linked accounts and their hashes
accounts = client.linked_accounts().json()
account_hash = accounts[0]['hashValue']

# Get account details (balances and positions) for a single account
details = client.account_details(account_hash, fields="positions").json()

# Get account details for ALL linked accounts at once
all_details = client.account_details_all(fields="positions").json()

# Get recent working orders, utilizing automatic date parsing
from schwab_api.utils import decode_schwab_dates
import datetime

thirty_days_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
orders = client.account_orders(
    account_hash,
    status="WORKING",
    fromEnteredTime=thirty_days_ago,
    toEnteredTime=datetime.datetime.now(datetime.timezone.utc)
).json(object_hook=decode_schwab_dates)
```

### 3. Market Data

You can fetch quotes, historical prices, and option chains. The library maps Yahoo Finance ticker formats (e.g., `BRK.B`, `^SPX`) to Schwab's internal format (`BRK/B`, `$SPX`) automatically within `price_history`, `instruments`, `option_chains`, `get_daily_price_history`, and `get_fundamentals`. Pass Schwab-format symbols directly to `quotes` and `quote`.

```python
# Get a single quote (symbol must be in Schwab format)
quote = client.quote("AAPL").json()
print(f"AAPL Last Price: {quote['AAPL']['quote']['lastPrice']}")

# Get multiple quotes at once
quotes = client.quotes(["AAPL", "MSFT", "$SPX"]).json()

# Get daily price history as a Pandas DataFrame (requires 'pandas')
# Symbol is automatically converted from Yahoo Finance format
df = client.get_daily_price_history("NVDA")
print(df.tail())

# Fetch an option chain (Yahoo Finance format is auto-converted)
chain_json = client.option_chains("MSFT", contractType="PUT", strikeCount=15).json()

# Fetch an option expiration chain and parse it to a DataFrame
from schwab_api.utils import parse_options_expiration_to_df
exp_chain = client.option_expiration_chain("AAPL").json()
df_exp = parse_options_expiration_to_df(exp_chain)
print(df_exp.head())

# Get index movers
movers = client.movers("$SPX").json()

# Check market hours
hours = client.market_hours_for_market("equity").json()
```

### 4. Placing and Managing Orders

The `OrderBuilder` module uses strict ENUM typing and provides templates to eliminate runtime errors when placing complex orders. Use `OptionSymbol` to programmatically construct option symbol strings.

```python
from schwab_api.orders.equities import equity_buy_market, equity_buy_limit, equity_sell_market
from schwab_api.orders.options import (
    option_buy_to_open_limit, option_sell_to_close_limit,
    bull_put_vertical_open, OptionSymbol
)

# Buy 10 shares of AAPL at market price
order = equity_buy_market("AAPL", 10).build()
response = client.place_order(account_hash, order)

# Limit buy
order = equity_buy_limit("AAPL", 5, limit_price=175.00).build()
response = client.place_order(account_hash, order)

# Construct an option symbol programmatically
import datetime
sym = OptionSymbol("AAPL", datetime.date(2024, 8, 9), is_put=False, strike_price=150.0).build()
# Returns: "AAPL  240809C00150000"

# Buy a Call Option using the symbol format (RRRRRRYYMMDDsWWWWWddd)
order = option_buy_to_open_limit(sym, quantity=1, limit_price=5.00).build()
response = client.place_order(account_hash, order)

# Construct a complex Bull Put Credit Spread
spread_order = bull_put_vertical_open(
    long_put_symbol="MSFT  241115P00400000",
    short_put_symbol="MSFT  241115P00405000",
    quantity=1,
    net_credit=1.50
).build()
response = client.place_order(account_hash, spread_order)

# Cancel or replace an order
client.cancel_order(account_hash, order_id=12345678)
client.replace_order(account_hash, order_id=12345678, order=new_order.build())

# Preview an order before placing (no actual execution)
preview = client.preview_order(account_hash, order)
```

### 5. Resilient API Calls with `retry_on_transient`

Wrap any function with exponential backoff and jitter for transient failures (`ServerError`, `RateLimitError`). Permanent errors (401, 400, 404) are never retried.

```python
from schwab_api import retry_on_transient

@retry_on_transient(max_attempts=5, base_delay=1.0, max_delay=60.0, jitter=True)
def fetch_chain():
    return client.option_chains("AAPL", strikeCount=20).json()

chain = fetch_chain()  # Automatically retries on 500s or 429s
```

You can also pass custom exception types:
```python
from schwab_api import retry_on_transient, ServerError, RateLimitError

@retry_on_transient(retryable=(ServerError, RateLimitError), max_attempts=3)
def place_with_retry():
    return client.place_order(account_hash, order)
```

### 6. WebSocket Streaming

The Streamer API provides real-time market data and account activity. It uses `curl_cffi` (if installed) or falls back to pure `websockets`. All numeric fields are automatically cast to their correct Python types (prices → `float`, sizes → `int`, booleans → `bool`).

#### Synchronous Streaming

```python
from schwab_api import StreamClient
import time

def on_message(message):
    print(f"Received: {message}")

stream = StreamClient(client)
stream.start(receiver=on_message)  # Runs in a background daemon thread

# Subscribe using human-readable fields instead of numeric IDs
req = stream.level_one_equities(
    keys=["AAPL", "GOOG"],
    fields=["symbol", "bid_price", "ask_price", "last_price"]
)
stream.send(req)

# Other available subscription types:
# stream.level_one_options(keys=["AAPL  240809C00150000"], fields=["symbol", "delta", "bid_price"])
# stream.level_one_futures(keys=["/ES"], fields=["symbol", "bid_price", "ask_price"])
# stream.level_one_futures_options(keys=["/ESH25C5000"], fields=["symbol", "delta"])
# stream.level_one_forex(keys=["EUR/USD"], fields=["symbol", "bid_price", "ask_price"])
# stream.chart_equity(keys=["AAPL"], fields=["symbol", "open_price", "close_price", "volume"])
# stream.chart_futures(keys=["/ES"], fields=["symbol", "open_price", "close_price"])
# stream.nyse_book(keys=["AAPL"], fields=["symbol"])
# stream.nasdaq_book(keys=["QQQ"], fields=["symbol"])
# stream.options_book(keys=["AAPL  240809C00150000"], fields=["symbol"])
# stream.screener_equity(keys=["$SPX"], fields=["symbol", "volume"])
# stream.screener_option(keys=["$SPX"], fields=["symbol", "volume"])
# stream.account_activity(keys=[correl_id], fields=["0", "1", "2", "3"])

time.sleep(10)
stream.stop()
```

#### Async Streaming

```python
from schwab_api import StreamClientAsync
import asyncio

async def main():
    async with StreamClientAsync(client, receiver=on_message) as stream:
        req = stream.level_one_equities(["AAPL"], ["symbol", "last_price"])
        await stream.send(req)
        await asyncio.sleep(10)

asyncio.run(main())
```

#### Stream Handlers

For modular applications, subclass `StreamResponseHandler` to route messages by type. Override only the `on_*` methods you need, then pass `.handle` as the receiver.

```python
from schwab_api import StreamResponseHandler, StreamClient

class MyHandler(StreamResponseHandler):
    def on_level_one_equity(self, update):
        # update values are already typed: last_price is float, bid_size is int
        print(f"Equity: {update['symbol']} last={update.get('last_price'):.2f}")

    def on_level_one_option(self, update):
        print(f"Option: {update['symbol']} delta={update.get('delta'):.3f}")

    def on_account_activity(self, update):
        print(f"Activity: type={update.get('message_type')}")

handler = MyHandler()
stream = StreamClient(client)
stream.start(receiver=handler.handle)
```

To chain multiple independent handlers on the same stream, use `add_handler`:

```python
handler = StreamResponseHandler()
handler.add_handler(portfolio_tracker)   # AccountManager subclass
handler.add_handler(alert_notifier)      # custom logic
stream.start(receiver=handler.handle)
```

### 7. Auto-Updating Portfolio (AccountManager)

`AccountManager` simplifies tracking live P&L. It fetches account nicknames, types, balances, and positions on `update()`. When attached to a `StreamClient`, it automatically subscribes to Level 1 streaming quotes for all open positions and listens to `ACCT_ACTIVITY` for order fills to auto-refresh quantities.

```python
from schwab_api import Client, StreamClient, AccountManager, StreamResponseHandler
import time

client = Client(app_key="...", app_secret="...")
stream_client = StreamClient(client)

manager = AccountManager(client, stream_client)
handler = StreamResponseHandler()
handler.add_handler(manager)

# Pull initial balances and positions (also fetches account nicknames)
manager.update()

# Starts stream; manager auto-subscribes to portfolio tickers
stream_client.start(receiver=handler.handle)
time.sleep(5)

# Inspect accounts with user-assigned names
for acc_num, acc in manager.accounts.items():
    primary = " [PRIMARY]" if acc["primaryAccount"] else ""
    print(f"  {acc_num}{primary}: {acc['nickName']!r} | liq=${acc['liquidationValue']:.2f}")

# Retrieve live aggregated totals (across all linked accounts)
aapl_stats = manager.get_position_totals("AAPL")
print(f"Total AAPL Exposure: ${aapl_stats['marketValue']:.2f}")

# Access cached streaming quotes
last_price = manager.quotes.get("AAPL", {}).get("last_price")

stream_client.stop()
```

Key attributes:
- `manager.accounts` — `Dict[int, {hashValue, type, cashBalance, liquidationValue, nickName, primaryAccount}]`
- `manager.positions` — `Dict[symbol, Dict[account_id, {longQuantity, shortQuantity, marketValue, ...}]]`
- `manager.quotes` — streaming price cache `Dict[symbol, {last_price, bid_price, ask_price, mark_price}]`

### 8. Algorithmic Data Analyzers

With the `pandas` extra installed, use built-in analyzers to evaluate your portfolio or parse option chains instantly.

```python
from schwab_api import OptionChainAnalyzer, PositionAnalyzer
from schwab_api.utils import extract_positions, parse_option_chain_to_df

# --- Portfolio Analysis ---
positions_response = client.account_details(account_hash, fields="positions").json()
raw_positions = positions_response.get('securitiesAccount', {}).get('positions', [])

analyzer = PositionAnalyzer(raw_positions)

# Get all options as a DataFrame
df_positions = analyzer.to_df()

# Find options that have hit a 50% profit target
winners = analyzer.get_winning_options(min_profit_percentage=50.0)

# Find short puts in danger (>50% loss, <14 DTE) — candidates for rolling
losers = analyzer.get_losing_short_puts(max_loss_percentage=-50.0, max_dte=14)

# Extract a flattened positions dict across multiple accounts
all_details = client.account_details_all(fields="positions").json()
positions_dict = extract_positions(all_details, format="dict")
# format="tuple" returns (longQty, shortQty, avgPrice, settledLongQty, settledShortQty)

# --- Option Chain Analysis ---
chain_json = client.option_chains("AAPL", strikeCount=20).json()
df_chain = parse_option_chain_to_df(chain_json)
chain = OptionChainAnalyzer(df_chain)

# Find Cash-Secured Put candidates (Wheel strategy)
put_candidates = chain.get_put_candidates(
    min_dte=30, max_dte=45,
    min_delta=0.20, max_delta=0.30,
    min_premium_percentage=0.01
)

# Find Covered Call candidates
call_candidates = chain.get_call_candidates(
    min_dte=21, max_dte=45,
    min_delta=0.20, max_delta=0.35,
)

# Custom filter (all parameters optional)
custom = chain.filter_options(
    is_put=True,
    min_dte=7, max_dte=30,
    min_open_interest=100,
    min_volume=10,
    max_bid_ask_spread=0.10,
)
```

#### Iron Condor Screening

`get_iron_condors()` enumerates every valid Iron Condor combination (short put spread + short call spread, same expiry) and returns them sorted by `credit_to_width_ratio` descending.

```python
# Fetch a broad chain covering both puts and calls
chain_json = client.option_chains("SPY", strikeCount=30).json()
df_chain = parse_option_chain_to_df(chain_json)
chain = OptionChainAnalyzer(df_chain)

condors = chain.get_iron_condors(
    min_dte=21, max_dte=45,
    min_short_delta=0.16, max_short_delta=0.25,  # short legs ~16-25 delta
    min_wing_width=5.0,                           # at least $5 wide wings
    min_credit_to_width_ratio=0.25,               # collect ≥25% of wing width
    min_open_interest=100,
    symmetric_wings=True,                         # equal-width put and call spreads
)
print(condors[["short_put_strike", "short_call_strike",
               "net_credit", "max_loss", "credit_to_width_ratio",
               "break_even_lower", "break_even_upper"]].head())
```

Returned columns per Iron Condor:

| Column | Description |
|--------|-------------|
| `short_put_strike` / `long_put_strike` | Put spread strikes |
| `short_call_strike` / `long_call_strike` | Call spread strikes |
| `short_put_delta` / `short_call_delta` | Signed deltas of short legs |
| `put_width` / `call_width` | Width of each spread in dollars |
| `net_credit` | Total premium collected (`short marks − long marks`) |
| `max_loss` | `max(put_width, call_width) − net_credit` |
| `credit_to_width_ratio` | `net_credit / min(put_width, call_width)` |
| `break_even_lower` | `short_put_strike − net_credit` |
| `break_even_upper` | `short_call_strike + net_credit` |

### 9. Mathematical & Advanced Options Analysis

The `schwab_api.math` module provides powerful quantitative tools that run locally without additional API calls. Requires `scipy` and `numpy` (included in the `[all]` extra).

```python
import datetime
from schwab_api.math import (
    BlackScholesPricer,
    calculate_gamma_exposure,
    calculate_mfiv_from_df,
    calculate_vix_like_index,
)

# 1. Theoretical Options Pricing
expiration = datetime.date.today() + datetime.timedelta(days=30)
pricer = BlackScholesPricer(
    stock_price=145.0,
    strike_price=150.0,
    expiration_date=expiration,
    is_put=False,
    volatility=0.25
)
print(f"Theoretical Delta: {pricer.delta():.4f}")
greeks = pricer.compute_all()  # returns dict: delta, gamma, theta, vega, rho

# 2. Dealer Gamma Exposure (GEX)
# Requires df_chain from parse_option_chain_to_df
df_gex = calculate_gamma_exposure(df_chain, plot_strikes=50, net_exposure=True)
print(df_gex.head())

# 3. Model-Free Implied Volatility (single expiry)
# Use parse_option_chain_to_df to get df_chain, then filter to one expiry
near_df = df_chain[df_chain["expiration_date"] == "2025-04-17"]
mfiv = calculate_mfiv_from_df(near_df, time_to_maturity=27/365.0, risk_free_rate=0.05)
print(f"Near-term MFIV: {mfiv:.4f}")

# 4. VIX-style 30-day implied volatility — one-liner convenience method
iv = client.get_implied_volatility("GOOG", target_days=30, strike_count=30, risk_free_rate=0.05)
print(f"GOOG 30-day IV: {iv:.4f}  ({iv*100:.1f}%)")
# → e.g. "GOOG 30-day IV: 0.3405  (34.0%)"

# The method handles expiry selection automatically:
#   - fetches the expiration chain
#   - picks the two expirations that bracket target_days
#   - fetches both option chains (fromDate==toDate per expiry)
#   - interpolates using the CBOE VIX formula
# Falls back to single-expiry MFIV if only one side of the bracket is available.

# Lower-level: manually select expiries and call calculate_vix_like_index
near_json = client.option_chains("SPY", fromDate="2025-04-17", toDate="2025-04-17", strikeCount=30).json()
far_json  = client.option_chains("SPY", fromDate="2025-05-16", toDate="2025-05-16", strikeCount=30).json()
near_df   = parse_option_chain_to_df(near_json)
far_df    = parse_option_chain_to_df(far_json)

vix_like = calculate_vix_like_index(
    near_df=near_df,
    far_df=far_df,
    t1=27/365.0,   # time to near expiry in years
    t2=56/365.0,   # time to far expiry in years
    risk_free_rate=0.05,
    target_days=30,
)
print(f"30-day MFIV (VIX-style): {vix_like:.4f}  ({vix_like*100:.1f}%)")
```

## Advanced & Maintenance Notes

- **Built-in Rate Limiting:** The client enforces a sliding-window limit of 120 requests/60 s automatically. Calls block (sleep) transparently when the budget is exhausted. No application-level throttling is required, but you should still catch `RateLimitError` for unexpected 429s from Schwab's backend.
- **Transient Retries:** Use `@retry_on_transient` to add resilient backoff to any function. It retries only `ServerError` and `RateLimitError`; permanent errors (401, 400, 404) propagate immediately.
- **Use of curl_cffi:** Both REST and WebSocket connections share the same Chrome TLS fingerprint when `curl_cffi` is installed, defeating Cloudflare/WAF bot-detection. Recommended for production deployments.
- **Concurrency Control:** Token data is persisted in a JSON file using cross-platform file locking (`fcntl`/`msvcrt`), making it safe for multiple independent Python scripts to share the same authenticated tokens concurrently without race conditions invalidating the 7-day refresh token.
- **Sporadic 500 Errors:** Be prepared to catch `ServerError` exceptions. The Trader API occasionally returns HTTP 500s during unannounced backend maintenance.
- **Account Activity Stream:** The `keys` parameter for `account_activity()` must be the `schwabClientCorrelId` from `client.user_preferences().json()["streamerInfo"][0]`, not a string literal. `AccountManager` handles this automatically.
- **Option Symbol Format:** Schwab uses a specific format: `RRRRRRYYMMDDSWWWWWDDD` (e.g., `AAPL  240809C00150000`). Use `OptionSymbol(...).build()` to construct these, or `parse_schwab_option_symbol()` to decompose them.
- **Streaming Field Types:** After parsing, equity/option/futures fields are automatically cast: prices → `float`, sizes and timestamps → `int`, boolean flags → `bool`. Fields with `-1=NULL` sentinel values (e.g., `hard_to_borrow`, `shortable`) are kept as `int`. Access `SERVICE_TYPE_MAPS` to inspect the type mapping for any service.
- **Iron Condor Combinatorics:** `get_iron_condors()` cross-joins all valid put spreads with all valid call spreads per expiry. Use `min_wing_width`, `max_wing_width`, and `min_short_delta`/`max_short_delta` to bound the search space and keep results manageable on wide chains.
- **VIX Interpolation Inputs:** `calculate_vix_like_index` requires the target horizon (`target_days`) to fall strictly within the `[t1, t2]` bracket. For a standard 30-day VIX you need one expiry shorter than 30 days and one longer. Raises `ValueError` if the bracket is violated.
