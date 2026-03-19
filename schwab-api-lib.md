# Schwab API Python Library Documentation

A lightweight, robust, and highly efficient Python client for the Charles Schwab Trading API. It relies on minimal core dependencies (`requests`, `websockets`, `cryptography`) while optionally supporting advanced libraries like `pandas` (for data manipulation) and `curl_cffi` (to mimic browser fingerprints for WAF evasion).

## Features

- **Automated Authentication:** A temporary local HTTP server automatically catches the OAuth redirect to extract the authorization code.
- **Robust Token Management:** Tokens are persisted in JSON files with cross-platform file locks (fcntl/msvcrt) for cross-process safety, automatically refreshed, and securely encrypted at rest (AES-GCM-256).
- **Declarative Order Builder:** Fully type-hinted templates for building complex orders (equities, multi-leg options) reliably.
- **Resilient Streaming:** Synchronous and native `asyncio` WebSocket clients with automatic reconnection, re-authentication, and state recovery.
- **Granular Error Handling:** HTTP errors are translated into specific Python exceptions (e.g., `RateLimitError`).
- **Algorithmic Utilities:** `PositionAnalyzer` and `OptionChainAnalyzer` help programmatically analyze portfolios and discover trades.
- **Mathematical Options Analysis:** Built-in `BlackScholesPricer` for theoretical Greeks, `calculate_gamma_exposure` (GEX) for dealer positioning, and Model-Free Implied Volatility (MFIV) calculations.

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

**Install All Extras:**
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

# Get account details (balances and positions)
details = client.account_details(account_hash, fields="positions").json()

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

You can fetch quotes, historical prices, and option chains. The library maps Yahoo Finance ticker formats (e.g., `BRK.B`) to Schwab's format (`BRK/B`) automatically when using utility functions.

```python
# Get a quote
quote = client.quote("AAPL").json()
print(f"AAPL Last Price: {quote['AAPL']['quote']['lastPrice']}")

# Get daily price history as a Pandas DataFrame (requires 'pandas')
df = client.get_daily_price_history("NVDA")
print(df.tail())

# Fetch an option chain
chain_json = client.option_chains("MSFT", contractType="PUT", strikeCount=15).json()
```

### 4. Placing Orders

The `OrderBuilder` module uses strict ENUM typing and provides templates to eliminate runtime errors when placing complex orders.

```python
from schwab_api.orders.equities import equity_buy_market
from schwab_api.orders.options import option_buy_to_open_limit, bull_put_vertical_open

# Buy 10 shares of AAPL at market price
order = equity_buy_market("AAPL", 10).build()
response = client.place_order(account_hash, order)

# Buy a Call Option using Schwab's specific symbol format (RRRRRRYYMMDDsWWWWWddd)
option_symbol = "GOOG  240809C00150000"
order = option_buy_to_open_limit(option_symbol, quantity=1, limit_price=5.00).build()
response = client.place_order(account_hash, order)

# Construct a complex Bull Put Credit Spread
spread_order = bull_put_vertical_open(
    long_put_symbol="MSFT  241115P00400000",
    short_put_symbol="MSFT  241115P00405000",
    quantity=1,
    net_credit=1.50
).build()
response = client.place_order(account_hash, spread_order)
```

### 5. WebSocket Streaming

The Streamer API provides real-time market data and account activity. It uses `curl_cffi` (if installed) or falls back to pure `websockets`.

#### Synchronous Streaming

```python
from schwab_api import StreamClient
import time

def on_message(message):
    print(f"Received: {message}")

stream = StreamClient(client)
stream.start(receiver=on_message) # Runs in a background daemon thread

# Subscribe using human-readable fields instead of numeric IDs
req = stream.level_one_equities(
    keys=["AAPL", "GOOG"], 
    fields=["symbol", "bid_price", "ask_price", "last_price"]
)
stream.send(req)

time.sleep(10)
stream.stop()
```

#### Stream Handlers

For modular applications, use `StreamResponseHandler` to route messages.

```python
from schwab_api import StreamResponseHandler

class MyEquityHandler(StreamResponseHandler):
    def on_level_one_equity(self, update):
        print(f"Equity: {update['symbol']} is at {update.get('last_price')}")

handler = StreamResponseHandler()
handler.add_handler(MyEquityHandler())

stream.start(receiver=handler.handle)
```

### 6. Auto-Updating Portfolio (AccountManager)

`AccountManager` simplifies tracking live P&L. By attaching it to a stream, it automatically subscribes to Level 1 streaming quotes for all open positions and listens to `ACCT_ACTIVITY` for order fills to auto-refresh quantities.

```python
from schwab_api import Client, StreamClient, AccountManager, StreamResponseHandler
import time

client = Client(app_key="...", app_secret="...")
stream_client = StreamClient(client)

manager = AccountManager(client, stream_client)
handler = StreamResponseHandler()
handler.add_handler(manager)

# Pull initial balances and positions
manager.update()

# Starts stream; manager auto-subscribes to portfolio tickers
stream_client.start(receiver=handler.handle)
time.sleep(5) 

# Retrieve live aggregated totals
aapl_stats = manager.get_position_totals("AAPL")
print(f"Total AAPL Exposure: ${aapl_stats['marketValue']:.2f}")

stream_client.stop()
```

### 7. Algorithmic Data Analyzers

With the `pandas` extra installed, use built-in analyzers to evaluate your portfolio or parse option chains instantly.

```python
from schwab_api import OptionChainAnalyzer, PositionAnalyzer

# --- Portfolio Analysis ---
positions = client.account_details(account_hash, fields="positions").json()
raw_positions = positions.get('securitiesAccount', {}).get('positions', [])

analyzer = PositionAnalyzer(raw_positions)
# Find options that have hit a 50% profit target
winners = analyzer.get_winning_options(min_profit_percentage=50.0)
print("Options to close:", winners)

# --- Option Chain Analysis ---
from schwab_api.utils import parse_option_chain_to_df

chain_json = client.option_chains("AAPL", contractType="PUT", strikeCount=15).json()
df_chain = parse_option_chain_to_df(chain_json)
chain = OptionChainAnalyzer(df_chain)

# Find Cash-Secured Put candidates (e.g., 30-45 DTE, 0.20-0.30 Delta)
candidates = chain.get_put_candidates(
    min_dte=30, max_dte=45, 
    min_delta=0.20, max_delta=0.30,
    min_premium_percentage=0.01
)
print("Put Candidates:\n", candidates.head())
```

### 8. Mathematical & Advanced Options Analysis

The `schwab_api.math` module provides powerful quantitative tools that run locally without additional API calls.

```python
import datetime
from schwab_api.math import BlackScholesPricer, calculate_gamma_exposure

# 1. Theoretical Options Pricing
# Calculate Greeks for a 150-strike Call expiring in 30 days
expiration = datetime.date.today() + datetime.timedelta(days=30)
pricer = BlackScholesPricer(
    stock_price=145.0, 
    strike_price=150.0, 
    expiration_date=expiration, 
    is_put=False, 
    volatility=0.25
)
print(f"Theoretical Delta: {pricer.delta():.4f}")

# 2. Dealer Gamma Exposure (GEX)
# (Requires `df_chain` from parse_option_chain_to_df)
# df_gex = calculate_gamma_exposure(df_chain, plot_strikes=50, net_exposure=True)
# print(df_gex.head())
```

## Advanced & Maintenance Notes

- **Anti-WAF Resilience:** When using `curl_cffi`, the HTTP requests and WebSockets impersonate Chrome's TLS fingerprint to bypass aggressive Cloudflare/WAF bot protection.
- **Concurrency Control:** Token data is persisted in a JSON file using cross-platform file locking (`fcntl`/`msvcrt`), making it safe for multiple independent Python scripts to share the same authenticated tokens concurrently without race conditions invalidating the 7-day refresh token.
- **Rate Limits:** Schwab enforces a hard limit of 120 API requests/minute. The library exposes a `RateLimitError` for HTTP 429s. Implementing backoff logic (`time.sleep()`) at the application level is required.
- **Sporadic 500 Errors:** Be prepared to catch `ServerError` exceptions. The Trader API occasionally returns HTTP 500s during unannounced backend maintenance.