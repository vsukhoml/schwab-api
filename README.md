# Schwab API Python Client

A lightweight, efficient, and reliable Python client for the Charles Schwab Trading API.

## Features

- **Automated Authentication:** Built-in local HTTP server automatically captures OAuth callbacks, eliminating the need for manual copy-pasting (with manual fallback for remote/headless setups).
- **Robust Token Management:** Thread-safe and process-safe token persistence using native OS file locks. Tokens are automatically refreshed and securely encrypted at rest using AES-GCM-256 derived from your App Secret.
- **Advanced Order Builder:** Declarative `OrderBuilder` and templates for equities and complex multi-leg options.
- **WebSocket Streaming:** Both synchronous (background thread) and asynchronous (`asyncio`) streaming clients with auto-reconnect, exponential backoff, and state recovery.
- **Utility Functions:** Conversion of Yahoo Finance tickers to Schwab, direct fetch of daily price histories, and fundamentals as Pandas DataFrames (if pandas is installed).

## Installation

### Installation from GitHub (Latest)
You can install the library directly from GitHub:

```bash
pip install git+https://github.com/vsukhoml/schwab-api.git
```

### Installation with curl_cffi
Installs `curl_cffi` to mimic real browser TLS/JA3 fingerprints to bypass WAFs. Since I use it in combination with [yfinance](https://pypi.org/project/yfinance/) which is built using `curl_cffi`, I decided to allow its use as it is a little faster.

```bash
pip install "schwab-api[curl_cffi] @ git+https://github.com/vsukhoml/schwab-api.git"
```

### Installation with Pandas Support
For data analysis, fetching price history as DataFrames.

```bash
pip install "schwab-api[pandas] @ git+https://github.com/vsukhoml/schwab-api.git"
```

### Install Everything

```bash
pip install "schwab-api[all] @ git+https://github.com/vsukhoml/schwab-api.git"
```

## Quick Start

### 1. Initialize the Client

```python
from schwab_api import Client

# The client will automatically handle the OAuth flow on first run
# by opening your browser and capturing the callback on 127.0.0.1:8182.
# Tokens and certificates are saved by default to ~/.config/schwab-api/
client = Client(
    app_key="YOUR_APP_KEY", 
    app_secret="YOUR_APP_SECRET", 
    callback_url="https://127.0.0.1:8182"
)

# Get linked accounts
accounts = client.linked_accounts().json()
account_hash = accounts[0]['hashValue']

# Get account details
details = client.account_details(account_hash).json()
print(details)
```

### 2. Market Data & Date Parsing

```python
from schwab_api.utils import decode_schwab_dates

# Get a quote
quote = client.quote("AAPL").json()
print(quote["AAPL"]["quote"]["lastPrice"])

# Optional: Use the provided JSON object_hook to automatically parse 
# Schwab's string dates into timezone-aware Python datetime objects
orders = client.account_orders(account_hash).json(object_hook=decode_schwab_dates)

# Get price history as a Pandas DataFrame (requires `pandas` extra)
df = client.get_daily_price_history("NVDA")
print(df.tail())
```

### 3. Placing Orders

The library includes advanced tools for constructing complex orders.

```python
from schwab_api.orders.equities import equity_buy_market
from schwab_api.orders.options import option_buy_to_open_limit

# Buy 10 shares of AAPL at market price
order = equity_buy_market("AAPL", 10).build()
response = client.place_order(account_hash, order)

# Buy 1 contract of GOOG 150 Call at $5.00 limit
option_symbol = "GOOG  240809C00150000" # Use Schwab's option symbol format
order = option_buy_to_open_limit(option_symbol, 1, 5.00).build()
response = client.place_order(account_hash, order)
```

### 4. Streaming Real-Time Data (WebSockets)

Stream data using the synchronous wrapper (runs in a background daemon thread).

```python
from schwab_api import StreamClient
import time

def on_message(message):
    print(f"Received: {message}")

stream = StreamClient(client)

# Start the stream in a background thread
stream.start(receiver=on_message)

# Subscribe to level 1 equities
req = stream.level_one_equities(keys=["AAPL", "GOOG"], fields="0,1,2,3")
stream.send(req)

# Wait and listen
time.sleep(10)

# Cleanly stop the stream
stream.stop()
```

For asynchronous applications (FastAPI, discord bots, etc.), use `StreamClientAsync` inside your event loop.

```python
import asyncio
from schwab_api import StreamClientAsync

async def main():
    stream = StreamClientAsync(client)
    
    async def on_message(msg):
        print(msg)

    # Starts stream in the current asyncio event loop
    await stream.start(receiver=on_message)
    
    req = stream.level_one_equities(keys=["AAPL"], fields="0,1,2,3")
    await stream.send(req)
    
    await asyncio.sleep(10)
    await stream.stop()

asyncio.run(main())
```

### 5. Auto-Trading Utilities

The library includes built-in analyzers for parsing positions and option chains, making it easy to build automated trading algorithms (like the Options Wheel Strategy). Requires `pandas` (`pip install "schwab-api[pandas] @ git+https://github.com/vsukhoml/schwab-api.git"`).

```python
from schwab_api import OptionChainAnalyzer, PositionAnalyzer

# 1. Analyze your current portfolio
positions = client.account_details(account_hash, fields="positions").json()
analyzer = PositionAnalyzer(positions.get('securitiesAccount', {}).get('positions', []))

# Find options that have hit a 50% profit target
winners = analyzer.get_winning_options(min_profit_percentage=50.0)
print(f"Options to close: {winners}")

# 2. Find new options to sell (The Wheel)
chain_json = client.option_chains("AAPL").json()
chain = OptionChainAnalyzer(chain_json)

# Find Cash-Secured Put candidates (30-45 Days to Expiration, 0.20-0.30 Delta)
candidates = chain.get_put_candidates(
    min_dte=30, max_dte=45, 
    min_delta=0.20, max_delta=0.30,
    min_premium_percentage=0.01
)
print(candidates.head())
```

## Architecture Notes

* **OAuth Server:** The `auth.py` module spins up a temporary `http.server` on `127.0.0.1` to catch the OAuth redirect code automatically. It automatically generates and saves localhost SSL certificates into `~/.config/schwab-api/certs/` to meet Schwab's strict HTTPS requirement.
* **Token Management:** Tokens are saved to `~/.config/schwab-api/tokens.json`. They are automatically encrypted at rest using `AES-GCM-256` derived natively from your App Secret using HKDF. Cross-process safety is guaranteed via atomic OS file locks (`fcntl` on Unix, `msvcrt` on Windows).
* **Symbol Conversion:** Use `client.get_daily_price_history("BRK.B")` with Yahoo Finance ticker formats; the library automatically maps them to Schwab's internal formatting (e.g. `BRK/B`).

## License

MIT License