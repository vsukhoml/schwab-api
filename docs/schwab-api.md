---
name: schwab-api
description: Use this skill when building applications using Charles Schwab Trading API.
---

# Schwab API Guide

## Table of Contents
1. [Authentication & Security](#authentication--security)
2. [General API Rules & Quirks](#general-api-rules--quirks)
3. [Accounts, Orders & Transactions](#accounts-orders--transactions)
4. [Market Data API](#market-data-api)
5. [Streaming Data (WebSocket)](#streaming-data-websocket)
6. [Common HTTP Error Responses](#common-http-error-responses)
7. [Schemas](#schemas)

## Authentication & Security (OAuth 2.0)

Schwab uses OAuth 2.0 to provide secure, delegated access to user data without exposing credentials. This guide follows the standard Three-Legged OAuth workflow required for the Trader API.

### **1. Application Registration**

Register your application on the [Schwab Developer Portal](https://developer.schwab.com/).

*   **App Status:** New or modified apps enter an `Approved - Pending` state. You cannot use the API until this status changes to `Ready for Use` (typically takes several business days).
*   **Callback URL (redirect_uri):** A Callback URL is required when creating an App. This URL is used in the OAuth flow to redirect the user back to your application after they grant consent.
    *   **Requirements & Recommendations:**
        *   **Secure Scheme:** Most Lines of Business (LOBs) require `HTTPS`. While some may support `HTTP` or other schemes, `HTTPS` is the standard recommendation.
        *   **Validation:** All URLs are validated for basic structure and must not contain special or unsupported characters.
        *   **Exact Match:** The `redirect_uri` sent during the OAuth flow **must be identical** to one of the Callback URLs registered with your App (including scheme, host, port, and path).
        *   **Host & Port:** Use `127.0.0.1` instead of `localhost` for local development. Use a non-standard port higher than `1024` (e.g., `https://127.0.0.1:8182`). Avoid ports `80` or `443` to circumvent permission and firewall issues.
    *   **Multiple Callback URLs:**
        *   You can register multiple URLs for a single App by separating them with a **comma** (no spaces).
        *   *Example:* `https://127.0.0.1:8182,https://www.example.com/callback`
        *   **Character Limit:** The field is currently limited to **256 characters**. Contact support if your use case exceeds this.
        *   **Defaulting:** If no `redirect_uri` is sent during OAuth, it defaults to the registered URL. If multiple are registered and none is specified in the request, an error will occur.
*   **Common Callback URL Errors:**

| **Registered URL** | **URL Sent in OAuth** | **Result / Reason** |
| :--- | :--- | :--- |
| `https://host/path` | `https://host/path` | **Successful** |
| `https://host/path` | `myapp://blah/bam` | **Error:** Scheme mismatch (`https` vs `myapp`) |
| `https://host/path` | `http://host/path` | **Error:** Scheme mismatch (`https` vs `http`) |
| `myapp://this/that` | `myapp://host/path` | **Error:** Path mismatch |

*   **Credentials:** You will receive a **Client ID** (App Key) and **Client Secret**. Keep these secure.

### **2. The OAuth Flow**

#### **Step A: Generate Authorization URL**
Construct the URL to redirect the user to Schwab's Login Micro Site (LMS).

**URL:** `https://api.schwabapi.com/v1/oauth/authorize`
**Query Parameters:**
* `client_id`: Your App Key.
* `redirect_uri`: Must exactly match your registered callback URL.

```python
import urllib.parse

app_key = "YOUR_APP_KEY"
callback_url = "https://127.0.0.1:8182"

params = {"client_id": app_key, "redirect_uri": callback_url}
auth_url = (
    f"https://api.schwabapi.com/v1/oauth/authorize?{urllib.parse.urlencode(params)}"
)
print(f"Open this URL in your browser: {auth_url}")
```

#### **Step B: Handle Callback & Extract Code**
After the user approves access, they are redirected to your `redirect_uri` with a `code` parameter. 
*Example:* `https://127.0.0.1:8182/?code=DEF...&session=XYZ...`

**Important:** The `code` must be **URL decoded** (e.g., changing `%40` back to `@`) before use in the next step.

#### **Step C: Exchange Code for Tokens**
Exchange the authorization code for an `access_token` and `refresh_token`.

**Endpoint:** `POST https://api.schwabapi.com/v1/oauth/token`
**Authentication:** Requires `Basic` auth header: `Base64(AppKey:AppSecret)`.

```python
import httpx
import base64


def get_tokens(app_key, app_secret, code, callback_url):
    # Construct Basic Auth Header
    auth_str = f"{app_key}:{app_secret}"
    auth_header = base64.b64encode(auth_str.encode()).decode()

    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": callback_url,
    }

    response = httpx.post(
        "https://api.schwabapi.com/v1/oauth/token", headers=headers, data=data
    )
    return response.json()
```

### **3. Token Management & Refresh**

#### **Token Lifecycles**
*   **Access Token:** Valid for **30 minutes**.
*   **Refresh Token:** Valid for **7 days**. 

#### **Proactive Refresh Best Practices**
*   **Access Token:** Refresh when within **60 seconds** of expiration to ensure seamless execution of long-running tasks.
*   **Refresh Token:** Schwab will invalidate the client if the 7-day window expires. Proactively refresh or re-authenticate at **6.5 days**.
*   **Concurrency Control:** If multiple processes share a token, use atomic locking (e.g., cross-platform file locks via `fcntl`/`msvcrt`) during refresh. If two processes attempt to refresh simultaneously, Schwab may invalidate the refresh token.

#### **How to Refresh**
```python
def refresh_access_token(app_key, app_secret, refresh_token):
    auth_str = f"{app_key}:{app_secret}"
    auth_header = base64.b64encode(auth_str.encode()).decode()

    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    data = {"grant_type": "refresh_token", "refresh_token": refresh_token}

    response = httpx.post(
        "https://api.schwabapi.com/v1/oauth/token", headers=headers, data=data
    )
    return response.json()
```

### **4. Troubleshooting Common Errors**

*   **`401 Unauthorized` during login:** Usually indicates the app is still in `Approved - Pending` status.
*   **`invalid_client`:** The refresh token has expired (over 7 days old) or was invalidated by a subsequent refresh. You must restart the flow from Step A.
*   **SSL Warnings:** When using a local server to capture the callback (like `schwab-py` does), you may see "self-signed certificate" warnings. This is expected for `https://127.0.0.1` as CA-signed certs cannot be issued for localhost. Verify the domain in the address bar before proceeding.

## General API Rules & Quirks

Before placing orders or utilizing the API heavily, you should be aware of several strict limitations and data formatting quirks enforced by Schwab:

* **Account Hashes vs. Account Numbers:** Almost all endpoints related to account balances, positions, and order placement require an **Account Hash** rather than your actual account number. You must first call the `GET /accounts/accountNumbers` endpoint to securely map your raw account number to its hashed counterpart, and pass this hash in the URI paths.
* **Strict Rate Limits:** The API enforces hard rate limits:
 * **120 API requests per minute.**
 * **4000 order-related API calls per day.**
 * **Maximum of 500 concurrently streamed tickers.**
 Exceeding these limits will result in `HTTP 429 (Too Many Requests)` errors.
* **Fractional Shares:** Fractional share orders are strictly not supported by the API.
* **Date & Time Requirements:** When filtering by date ranges (e.g. `account_orders` or `transactions`), Schwab requires you to pass the `fromEnteredTime` and `toEnteredTime` parameters formatted specifically in `ISO_8601` format (e.g. `YYYY-MM-DDThh:mm:ss.000Z`). Failing to provide these parameters or providing them incorrectly will result in an `HTTP 400 Bad Request`.
* **Request Tracking (Correlation ID):** Every API response includes a `Schwab-Client-CorrelId` header. This unique GUID tracks an individual service call throughout its lifetime across Schwab's systems. It is mandatory to provide this ID when contacting Schwab support for any specific request failure. The library automatically logs this ID at the `DEBUG` level and includes it in exception messages.
* **Sporadic Outages (HTTP 500):** The Trader API (`/trader/v1/...`) has been known to experience unannounced backend outages or weekend maintenance windows where endpoints like `/accounts/{hash}` or `/orders` will return `HTTP 500 Server Error: {"message":"Application encountered unexpected error that prevented fulfilling this request"}`. During these periods, the Market Data API (`/marketdata/v1/...`) often remains fully functional. Ensure your bots catch `ServerError` exceptions to fail gracefully instead of crashing.

## Accounts, Orders & Transactions

### Accounts

#### **GET** `/trader/v1/accounts/accountNumbers`
Get list of account numbers and their encrypted values.

Account numbers in plain text cannot be used outside of headers or request/response bodies. As the first step, consumers must invoke this service to retrieve the list of plain text/encrypted value pairs, and use the **`hashValue`** for all subsequent calls for any account-specific request.

#### Parameters
No parameters.

#### Responses
**Success Response (200)**: List of account number and hash value pairs.

**Schema on success**:
```json
[
    {
        "accountNumber": "43003695",
        "hashValue": "417C2D1EA08E18E0847BF58F2F91B13C3D402FD404152C6142C5756ACE8C20F1"
    }
]
```


#### **GET** `/trader/v1/accounts/`
Get linked account(s) balances and positions for the logged-in user.

Balances are displayed by default. Positions are included only if the `fields=positions` parameter is provided.

#### Parameters

* `fields` (string (query)): Optional. Use `positions` to include position data in the response.

#### Responses
**Success Response (200)**: List of valid accounts.

**Schema on success**:
```json
[
    {
        "securitiesAccount": {
            "type": "MARGIN",
            "accountNumber": "97485470",
            "roundTrips": 0,
            "isDayTrader": false,
            "isClosingOnlyRestricted": false,
            "positions": [
                {
                    "shortQuantity": 0.0,
                    "averagePrice": 430.306,
                    "longQuantity": 5.0,
                    "instrument": {
                        "assetType": "COLLECTIVE_INVESTMENT",
                        "symbol": "VOO",
                        "description": "VANGUARD S&P 500 ETF"
                    },
                    "marketValue": 3092.15
                }
            ],
            "currentBalances": {
                "availableFunds": 1234.56,
                "equity": 5678.9
            }
        }
    }
]
```

#### **GET** `/trader/v1/accounts/{accountNumber}`
Get a specific account balance and positions for the logged-in user.

Specific account information with balances and positions. Balances are displayed by default. Positions are included only if the `fields=positions` parameter is provided.

#### Parameters

* `accountNumber` (string (path), required): The encrypted ID of the account (`hashValue`).
* `fields` (string (query)): Optional. Use `positions` to include position data in the response.

#### Responses
**Success Response (200)**: A valid account response.

**Schema on success**:
```json
{
    "securitiesAccount": {
        "type": "CASH",
        "accountNumber": "43003695",
        "roundTrips": 0,
        "isDayTrader": false,
        "isClosingOnlyRestricted": false,
        "positions": [
            {
                "symbol": "FCX",
                "longQuantity": 31.6836,
                "averagePrice": 35.4356,
                "marketValue": 1880.74
            }
        ],
        "currentBalances": {
            "cashAvailableForTrading": 1000.0,
            "liquidationValue": 5000.0
        }
    }
}
```




### Orders

#### **GET** `/trader/v1/accounts/{accountNumber}/orders`
Get all orders for a specific account.

Orders can be filtered by time range and status. The maximum date range is 1 year.

#### Parameters

* `accountNumber` (string (path), required): The encrypted ID of the account (`hashValue`).
* `fromEnteredTime` (string (query), required if `toEnteredTime` is set): Start time in ISO-8601 format (e.g., `2024-03-29T00:00:00.000Z`).
* `toEnteredTime` (string (query), required if `fromEnteredTime` is set): End time in ISO-8601 format (e.g., `2024-04-28T23:59:59.000Z`).
* `maxResults` (integer (query)): Max number of orders to retrieve (default: 3000).
* `status` (string (query)): Filter by status.
    * *Values:* `AWAITING_PARENT_ORDER`, `AWAITING_CONDITION`, `AWAITING_STOP_CONDITION`, `AWAITING_MANUAL_REVIEW`, `ACCEPTED`, `AWAITING_UR_OUT`, `PENDING_ACTIVATION`, `QUEUED`, `WORKING`, `REJECTED`, `PENDING_CANCEL`, `CANCELED`, `PENDING_REPLACE`, `REPLACED`, `FILLED`, `EXPIRED`, `NEW`, `AWAITING_RELEASE_TIME`, `PENDING_ACKNOWLEDGEMENT`, `PENDING_RECALL`, `UNKNOWN`.

#### Responses
**Success Response (200)**: A list of orders for the account.

**Schema on success**:
```json
[
    {
        "orderId": 123456789,
        "status": "FILLED",
        "orderType": "LIMIT",
        "session": "NORMAL",
        "duration": "DAY",
        "price": 150.0,
        "quantity": 10,
        "filledQuantity": 10,
        "remainingQuantity": 0,
        "enteredTime": "2024-04-20T14:30:00.000Z",
        "orderLegCollection": [
            {
                "orderLegType": "EQUITY",
                "instruction": "BUY",
                "instrument": {
                    "symbol": "AAPL",
                    "assetType": "EQUITY"
                }
            }
        ]
    }
]
```



#### **POST** `/trader/v1/accounts/{accountNumber}/orders`
Place an order for a specific account.

#### Parameters

* `accountNumber` (string (path), required): The encrypted ID of the account (`hashValue`).

#### **Request Body**
The order object following the required schema.

**Example: Buying 10 shares of AAPL at Market price**
```json
{
    "orderType": "MARKET",
    "session": "NORMAL",
    "duration": "DAY",
    "orderStrategyType": "SINGLE",
    "orderLegCollection": [
        {
            "instruction": "BUY",
            "quantity": 10,
            "instrument": {
                "symbol": "AAPL",
                "assetType": "EQUITY"
            }
        }
    ]
}
```

#### Responses
**Success Response (201)**: Empty response body. Includes a `Location` header with a URI pointing to the newly created order. The `orderId` can be extracted from this URI.


#### **POST** `/trader/v1/accounts/{accountNumber}/previewOrder`
Preview an order for a specific account.

#### Parameters

* `accountNumber` (string (path), required): The encrypted ID of the account (`hashValue`).

#### **Request Body**
The order object following the required schema.

#### Responses
**Success Response (200)**: An order object including validation results and estimated commissions.

**Schema on success**:
```json
{
    "orderId": 0,
    "orderStrategy": {
        "accountNumber": "97485470",
        "orderStrategyType": "SINGLE",
        "orderLegs": [
            {
                "symbol": "AAPL",
                "instruction": "BUY",
                "quantity": 10
            }
        ]
    },
    "orderValidationResult": {
        "alerts": [],
        "accepts": [],
        "rejects": []
    },
    "commissionAndFee": {
        "commission": {
            "commissionLegs": [
                {
                    "commissionValues": [
                        {
                            "value": 0,
                            "type": "COMMISSION"
                        }
                    ]
                }
            ]
        }
    }
}
```


#### **GET** `/trader/v1/accounts/{accountNumber}/orders/{orderId}`
Get a specific order by its ID, for a specific account.

#### Parameters

* `accountNumber` (string (path), required): The encrypted ID of the account (`hashValue`).
* `orderId` (integer (path), required): The ID of the order being retrieved.

#### Responses
**Success Response (200)**: A single order object.

**Schema on success**:
```json
{
    "orderId": 123456789,
    "status": "FILLED",
    "orderType": "LIMIT",
    "session": "NORMAL",
    "duration": "DAY",
    "price": 150.0,
    "quantity": 10,
    "filledQuantity": 10,
    "remainingQuantity": 0,
    "enteredTime": "2024-04-20T14:30:00.000Z",
    "orderLegCollection": [
        {
            "orderLegType": "EQUITY",
            "instruction": "BUY",
            "instrument": {
                "symbol": "AAPL",
                "assetType": "EQUITY"
            }
        }
    ]
}
```



#### **DELETE** `/trader/v1/accounts/{accountNumber}/orders/{orderId}`
Cancel a specific order for a specific account.

#### Parameters

* `accountNumber` (string (path), required): The encrypted ID of the account (`hashValue`).
* `orderId` (integer (path), required): The ID of the order to cancel.

#### Responses
**Success Response (200)**: Empty response body.

**Error Response (400)**: Validation problem with the request.
```json
{
    "message": "string",
    "errors": [
        "string"
    ]
}
```

#### **PUT** `/trader/v1/accounts/{accountNumber}/orders/{orderId}`
Replace an existing order for an account. The existing order will be replaced by the new order. Once replaced, the old order will be canceled and a new order will be created.

#### Parameters

* `accountNumber` (string (path), required): The encrypted ID of the account (`hashValue`).
* `orderId` (integer (path), required): The ID of the order to replace.

#### **Request Body**
The new order object.

#### Responses
**Success Response (201)**: Empty response body. Includes a `Location` header with a URI pointing to the newly created replacement order.


#### **GET** `/trader/v1/orders`
Get all orders for all linked accounts.

Orders can be filtered by time range and status. The date must be within 60 days from today.

#### Parameters

* `fromEnteredTime` (string (query), required if `toEnteredTime` is set): Start time in ISO-8601 format.
* `toEnteredTime` (string (query), required if `fromEnteredTime` is set): End time in ISO-8601 format.
* `maxResults` (integer (query)): Max number of orders to retrieve (default: 3000).
* `status` (string (query)): Filter by status.

#### Responses
**Success Response (200)**: A list of orders for all linked accounts.

**Schema on success**:
```json
[
    {
        "orderId": 123456789,
        "accountNumber": "97485470",
        "status": "FILLED",
        "orderType": "LIMIT",
        "price": 150.0,
        "quantity": 10,
        "enteredTime": "2024-04-20T14:30:00.000Z"
    }
]
```



#### **POST** `/accounts/{accountNumber}/previewOrder`

Preview an order for a specific account.

##### Parameters

No parameters

##### Request body

**application/json**

The Order Object.

**Example Value**

```json
{
    "orderId": 0,
    "orderStrategy": {
        "accountNumber": "string",
        "advancedOrderType": "NONE",
        "closeTime": "2025-11-08T22:40:38.951Z",
        "enteredTime": "2025-11-08T22:40:38.951Z",
        "orderBalance": {
            "orderValue": 0,
            "projectedAvailableFund": 0,
            "projectedBuyingPower": 0,
            "projectedCommission": 0
        },
        "orderStrategyType": "SINGLE",
        "orderVersion": 0,
        "session": "NORMAL",
        "status": "AWAITING_PARENT_ORDER",
        "allOrNone": true,
        "discretionary": true,
        "duration": "DAY",
        "filledQuantity": 0,
        "orderType": "MARKET",
        "orderValue": 0,
        "price": 0,
        "quantity": 0,
        "remainingQuantity": 0,
        "sellNonMarginableFirst": true,
        "settlementInstruction": "REGULAR",
        "strategy": "NONE",
        "amountIndicator": "DOLLARS",
        "orderLegs": [
            {
                "askPrice": 0,
                "bidPrice": 0,
                "lastPrice": 0,
                "markPrice": 0,
                "projectedCommission": 0,
                "quantity": 0,
                "finalSymbol": "string",
                "legId": 0,
                "assetType": "EQUITY",
                "instruction": "BUY"
            }
        ]
    },
    "orderValidationResult": {
        "alerts": [
            {
                "validationRuleName": "string",
                "message": "string",
                "activityMessage": "string",
                "originalSeverity": "ACCEPT",
                "overrideName": "string",
                "overrideSeverity": "ACCEPT"
            }
        ],
        "accepts": [
            {
                "validationRuleName": "string",
                "message": "string",
                "activityMessage": "string",
                "originalSeverity": "ACCEPT",
                "overrideName": "string",
                "overrideSeverity": "ACCEPT"
            }
        ],
        "rejects": [
            {
                "validationRuleName": "string",
                "message": "string",
                "activityMessage": "string",
                "originalSeverity": "ACCEPT",
                "overrideName": "string",
                "overrideSeverity": "ACCEPT"
            }
        ],
        "reviews": [
            {
                "validationRuleName": "string",
                "message": "string",
                "activityMessage": "string",
                "originalSeverity": "ACCEPT",
                "overrideName": "string",
                "overrideSeverity": "ACCEPT"
            }
        ],
        "warns": [
            {
                "validationRuleName": "string",
                "message": "string",
                "activityMessage": "string",
                "originalSeverity": "ACCEPT",
                "overrideName": "string",
                "overrideSeverity": "ACCEPT"
            }
        ]
    },
    "commissionAndFee": {
        "commission": {
            "commissionLegs": [
                {
                    "commissionValues": [
                        {
                            "value": 0,
                            "type": "COMMISSION"
                        }
                    ]
                }
            ]
        },
        "fee": {
            "feeLegs": [
                {
                    "feeValues": [
                        {
                            "value": 0,
                            "type": "COMMISSION"
                        }
                    ]
                }
            ]
        },
        "trueCommission": {
            "commissionLegs": [
                {
                    "commissionValues": [
                        {
                            "value": 0,
                            "type": "COMMISSION"
                        }
                    ]
                }
            ]
        }
    }
}
```

##### Responses

**Success Response (200)**: An order object, matching the input parameters

**Schema on success**:
```json
{
    "orderId": 0,
    "orderStrategy": {
        "accountNumber": "string",
        "advancedOrderType": "NONE",
        "closeTime": "2025-11-08T22:40:38.954Z",
        "enteredTime": "2025-11-08T22:40:38.954Z",
        "orderBalance": {
            "orderValue": 0,
            "projectedAvailableFund": 0,
            "projectedBuyingPower": 0,
            "projectedCommission": 0
        },
        "orderStrategyType": "SINGLE",
        "orderVersion": 0,
        "session": "NORMAL",
        "status": "AWAITING_PARENT_ORDER",
        "allOrNone": true,
        "discretionary": true,
        "duration": "DAY",
        "filledQuantity": 0,
        "orderType": "MARKET",
        "orderValue": 0,
        "price": 0,
        "quantity": 0,
        "remainingQuantity": 0,
        "sellNonMarginableFirst": true,
        "settlementInstruction": "REGULAR",
        "strategy": "NONE",
        "amountIndicator": "DOLLARS",
        "orderLegs": [
            {
                "askPrice": 0,
                "bidPrice": 0,
                "lastPrice": 0,
                "markPrice": 0,
                "projectedCommission": 0,
                "quantity": 0,
                "finalSymbol": "string",
                "legId": 0,
                "assetType": "EQUITY",
                "instruction": "BUY"
            }
        ]
    },
    "orderValidationResult": {
        "alerts": [
            {
                "validationRuleName": "string",
                "message": "string",
                "activityMessage": "string",
                "originalSeverity": "ACCEPT",
                "overrideName": "string",
                "overrideSeverity": "ACCEPT"
            }
        ],
        "accepts": [
            {
                "validationRuleName": "string",
                "message": "string",
                "activityMessage": "string",
                "originalSeverity": "ACCEPT",
                "overrideName": "string",
                "overrideSeverity": "ACCEPT"
            }
        ],
        "rejects": [
            {
                "validationRuleName": "string",
                "message": "string",
                "activityMessage": "string",
                "originalSeverity": "ACCEPT",
                "overrideName": "string",
                "overrideSeverity": "ACCEPT"
            }
        ],
        "reviews": [
            {
                "validationRuleName": "string",
                "message": "string",
                "activityMessage": "string",
                "originalSeverity": "ACCEPT",
                "overrideName": "string",
                "overrideSeverity": "ACCEPT"
            }
        ],
        "warns": [
            {
                "validationRuleName": "string",
                "message": "string",
                "activityMessage": "string",
                "originalSeverity": "ACCEPT",
                "overrideName": "string",
                "overrideSeverity": "ACCEPT"
            }
        ]
    },
    "commissionAndFee": {
        "commission": {
            "commissionLegs": [
                {
                    "commissionValues": [
                        {
                            "value": 0,
                            "type": "COMMISSION"
                        }
                    ]
                }
            ]
        },
        "fee": {
            "feeLegs": [
                {
                    "feeValues": [
                        {
                            "value": 0,
                            "type": "COMMISSION"
                        }
                    ]
                }
            ]
        },
        "trueCommission": {
            "commissionLegs": [
                {
                    "commissionValues": [
                        {
                            "value": 0,
                            "type": "COMMISSION"
                        }
                    ]
                }
            ]
        }
    }
}
```




### Transactions

#### **GET** `/trader/v1/accounts/{accountNumber}/transactions`
Get all transactions for a specific account.

Transactions can be filtered by date range, type, and symbol. Maximum 3000 transactions. Maximum date range is 1 year.

#### Parameters

* `accountNumber` (string (path), required): The encrypted ID of the account (`hashValue`).
* `startDate` (string (query), required): Start date in ISO-8601 format.
* `endDate` (string (query), required): End date in ISO-8601 format.
* `types` (string (query), required): Comma-separated list of transaction types.
    * *Values:* `TRADE`, `RECEIVE_AND_DELIVER`, `DIVIDEND_OR_INTEREST`, `ACH_RECEIPT`, `ACH_DISBURSEMENT`, `CASH_RECEIPT`, `CASH_DISBURSEMENT`, `ELECTRONIC_FUND`, `WIRE_OUT`, `WIRE_IN`, `JOURNAL`, `MEMORANDUM`, `MARGIN_CALL`, `MONEY_MARKET`, `SMA_ADJUSTMENT`.
* `symbol` (string (query)): Filter by symbol.

#### Responses
**Success Response (200)**: A list of transactions.

**Schema on success**:
```json
[
    {
        "activityId": 93401981092,
        "time": "2025-03-07T22:34:50+0000",
        "description": "PFIZER INC",
        "accountNumber": "99415888",
        "type": "TRADE",
        "status": "VALID",
        "subAccount": "MARGIN",
        "tradeDate": "2025-03-07T05:00:00+0000",
        "settlementDate": "2025-03-07T05:00:00+0000",
        "positionId": 2103987573,
        "netAmount": -51.35,
        "transferItems": [
            {
                "instrument": {
                    "assetType": "EQUITY",
                    "symbol": "PFE",
                    "description": "PFIZER INC"
                },
                "amount": 1.9191,
                "cost": -51.35,
                "price": 26.75702,
                "positionEffect": "OPENING"
            }
        ]
    }
]
```

#### **GET** `/trader/v1/accounts/{accountNumber}/transactions/{transactionId}`
Get specific transaction information for a specific account.

#### Parameters

* `accountNumber` (string (path), required): The encrypted ID of the account (`hashValue`).
* `transactionId` (integer (path), required): The ID of the transaction being retrieved.

#### Responses
**Success Response (200)**: A list containing the specific transaction object.

**Schema on success**:
```json
[
    {
        "activityId": 93401981092,
        "time": "2025-03-07T22:34:50+0000",
        "description": "PFIZER INC",
        "accountNumber": "99415888",
        "type": "TRADE",
        "status": "VALID",
        "subAccount": "MARGIN",
        "tradeDate": "2025-03-07T05:00:00+0000",
        "settlementDate": "2025-03-07T05:00:00+0000",
        "positionId": 2103987573,
        "netAmount": -51.35,
        "transferItems": [
            {
                "instrument": {
                    "assetType": "EQUITY",
                    "symbol": "PFE",
                    "description": "PFIZER INC"
                },
                "amount": 1.9191,
                "cost": -51.35,
                "price": 26.75702,
                "positionEffect": "OPENING"
            }
        ]
    }
]
```




### User Preference

#### **GET** `/trader/v1/userPreference`
Get user preference information for the logged-in user.

Includes account nicknames, streamer connection details, and market data permissions.

#### Parameters
No parameters.

#### Responses
**Success Response (200)**: A list containing user preference values.

**Schema on success**:
```json
[
    {
        "accounts": [
            {
                "accountNumber": "97485470",
                "primaryAccount": true,
                "type": "MARGIN",
                "nickName": "My Trading Account"
            }
        ],
        "streamerInfo": [
            {
                "streamerSocketUrl": "wss://...",
                "schwabClientCustomerId": "...",
                "schwabClientCorrelId": "..."
            }
        ],
        "offers": [
            {
                "level2Permissions": true,
                "mktDataPermission": "PRO"
            }
        ]
    }
]
```

**Error Responses**:
*   **400 Bad Request**: Invalid request format.
*   **401 Unauthorized**: Invalid or expired token.




## Market Data API

### Schwab Symbology
When requesting market data, Schwab uses specific prefixes and naming conventions for different asset classes:

#### **Indices**
Indices are typically prefixed with a `$`.
- **$DJI**: Dow Jones Industrial Average
- **$COMPX**: NASDAQ Composite
- **$SPX**: S&P 500 Index
- **$VIX**: CBOE Volatility Index
- **$RUT**: Russell 2000 Index
- **$NDX**: NASDAQ 100 Index
- **$TRAN**: Dow Jones Transportation Average
- **$SOX**: PHLX Semiconductor Index
- **$OEX**: S&P 100 Index
- **$MID**: S&P MidCap 400 Index
- **$NYA**: NYSE Composite Index
- **$XAU**: Gold & Silver Index
- **$XOI**: AMEX Oil Index
- **$XAL**: AMEX Aluminum Index
- **XAX**: NYSE Amex Composite
- **$XDB, $XDE, $XDA**: Other AMEX Indices

#### **Futures**
Futures symbols follow the format: `/` + `Root` + `Month Code` + `Year Code`.
- **Month Codes**: F(Jan), G(Feb), H(Mar), J(Apr), K(May), M(Jun), N(Jul), Q(Aug), U(Sep), V(Oct), X(Nov), Z(Dec).
- **Common Roots**:
    - **/ES**: E-Mini S&P 500 (Index: `$SPX`)
    - **/NQ**: E-Mini Nasdaq 100 (Index: `$NDX`)
    - **/YM**: E-Mini Dow Jones (Index: `$DJI`)
    - **/RTY**: E-Mini Russell 2000 (Index: `$RUT`)
    - **/GC**: Gold (Index: `$XAU`)
    - **/SI**: Silver
    - **/HG**: Copper
    - **/CL**: Crude Oil
    - **/NG**: Natural Gas
    - **/ZB**: 30-Year Treasury Bond
    - **/ZN**: 10-Year Treasury Note
    - **/ZW**: Wheat
    - **/ZC**: Corn
- **Example**: `/ESH25` (S&P 500 Futures, March 2025)

---

The Market Data API provides endpoints for quotes, price history, option chains, and instrument fundamentals. These endpoints are accessible under the `https://api.schwabapi.com/marketdata/v1` base URL.

## Quotes

### **GET** `/marketdata/v1/quotes`
Get quotes for a list of one or more symbols.

#### Parameters

* `symbols` (string (query), required): A comma-separated list of one or more symbols to look up.
    * *Example:* `AAPL,BAC,$DJI,$SPX,AMZN  230317C01360000`
* `fields` (string (query)): Optional. Comma-separated list of root nodes to return.
    * *Possible Values:* `quote`, `fundamental`, `extended`, `reference`, `regular`.
    * *Default:* `all`.
* `indicative` (boolean (query)): Optional. Include indicative symbol quotes for ETF symbols in the request.
    * *Default:* `false`.

#### Responses
**Success Response (200)**: A map of symbols to their quote data.

**Schema on success**:
```json
{
    "AAPL": {
        "assetMainType": "EQUITY",
        "symbol": "AAPL",
        "quoteType": "NBBO",
        "realtime": true,
        "ssid": 1973757747,
        "reference": {
            "cusip": "037833100",
            "description": "Apple Inc",
            "exchange": "Q",
            "exchangeName": "NASDAQ"
        },
        "quote": {
            "52WeekHigh": 169,
            "52WeekLow": 1.1,
            "askPrice": 168.41,
            "askSize": 400,
            "bidPrice": 168.4,
            "bidSize": 400,
            "lastPrice": 168.405,
            "mark": 168.405,
            "netChange": -9.165,
            "netPercentChange": -5.1613,
            "quoteTime": 1644854683672,
            "securityStatus": "Normal",
            "totalVolume": 22361159
        },
        "fundamental": {
            "avg10DaysVolume": 1,
            "divYield": 1.1,
            "peRatio": 1.1
        }
    }
}
```

### **GET** `/marketdata/v1/{symbol}/quotes`
Get a quote for a single symbol.

#### Parameters

* `symbol` (string (path), required): The symbol to retrieve a quote for (e.g., `TSLA`).
* `fields` (string (query)): Optional. Comma-separated list of root nodes to return (`quote`, `fundamental`, `extended`, `reference`, `regular`).

#### Responses
**Success Response (200)**: Quote data for the requested symbol.

> [!IMPORTANT]
> **Documentation Discrepancy:** The official Schwab documentation currently shows a "Price History" (candles) schema for this endpoint's example. However, empirical testing (see `e2e_dumps/quote.json`) confirms that this endpoint returns a standard quote object keyed by the symbol, identical to the plural `/quotes` endpoint but containing only one entry.

**Official Documentation Example (showing unexpected candle data):**
```json
{
    "symbol": "AAPL",
    "empty": false,
    "previousClose": 174.56,
    "previousCloseDate": 1639029600000,
    "candles": [
        {
            "open": 175.01,
            "high": 175.15,
            "low": 175.01,
            "close": 175.04,
            "volume": 10719,
            "datetime": 1639137600000
        }
    ]
}
```

**Actual Observed Schema (Recommended for developers):**
```json
{
    "AAPL": {
        "assetMainType": "EQUITY",
        "symbol": "AAPL",
        "quoteType": "NBBO",
        "realtime": true,
        "quote": {
            "52WeekHigh": 288.62,
            "52WeekLow": 169.2101,
            "askPrice": 257.0,
            "bidPrice": 256.65,
            "lastPrice": 256.65,
            "mark": 257.46,
            "netChange": -3.64,
            "quoteTime": 1772845139628
        }
    }
}
```

## Price History

### **GET** `/marketdata/v1/pricehistory`
Get historical price data (candles) for a specific symbol.

#### Parameters

* `symbol` (string (query), required): The symbol to retrieve price history for (e.g., `AAPL`).
* `periodType` (string (query)): The chart period being requested (`day`, `month`, `year`, `ytd`).
* `period` (integer (query)): The number of chart period types.
    * *Valid values for `day`:* 1, 2, 3, 4, 5, 10
    * *Valid values for `month`:* 1, 2, 3, 6
    * *Valid values for `year`:* 1, 2, 3, 5, 10, 15, 20
    * *Valid values for `ytd`:* 1
* `frequencyType` (string (query)): The frequency with which a new candle is formed (`minute`, `daily`, `weekly`, `monthly`).
    * *If `periodType` is `day`:* `minute` is the only valid value.
    * *If `periodType` is `month`:* `daily`, `weekly`.
    * *If `periodType` is `year`:* `daily`, `weekly`, `monthly`.
    * *If `periodType` is `ytd`:* `daily`, `weekly`.
* `frequency` (integer (query)): The time frequency duration.
    * *If `frequencyType` is `minute`:* 1, 5, 10, 15, 30.
    * *If `frequencyType` is `daily`, `weekly`, or `monthly`:* 1.
* `startDate` (integer (query)): Start date as milliseconds since the UNIX epoch.
* `endDate` (integer (query)): End date as milliseconds since the UNIX epoch. Default is the market close of the previous business day.
* `needExtendedHoursData` (boolean (query)): If `true`, returns extended hours data.
* `needPreviousClose` (boolean (query)): If `true`, includes the previous day's close price and date.

#### Responses
**Success Response (200)**: Historical price data containing an array of candles.

**Schema on success**:
```json
{
    "candles": [
        {
            "open": 175.01,
            "high": 175.15,
            "low": 175.01,
            "close": 175.04,
            "volume": 10719,
            "datetime": 1639137600000
        }
    ],
    "symbol": "AAPL",
    "empty": false,
    "previousClose": 174.56,
    "previousCloseDate": 1639029600000
}
```

## Option Chains

### **GET** `/marketdata/v1/chains`
Get an option chain for a specific underlying symbol.

#### Parameters

* `symbol` (string (query), required): The underlying symbol (e.g., `AAPL`).
* `contractType` (string (query)): Type of contracts to return. Valid values: `CALL`, `PUT`, `ALL`.
* `strikeCount` (integer (query)): The number of strikes to return above and below the at-the-money price.
* `includeUnderlyingQuote` (boolean (query)): Include the underlying symbol's quote in the response.
* `strategy` (string (query)): Strategy for the chain. Default is `SINGLE`.
    * *Options:* `SINGLE`, `ANALYTICAL`, `COVERED`, `VERTICAL`, `CALENDAR`, `STRANGLE`, `STRADDLE`, `BUTTERFLY`, `CONDOR`, `DIAGONAL`, `COLLAR`, `ROLL`.
    * *Note:* `ANALYTICAL` allows using `volatility`, `underlyingPrice`, `interestRate`, and `daysToExpiration` for theoretical calculations.
* `interval` (number (query)): Strike interval for spread strategy chains.
* `strike` (number (query)): Return options only at this specific strike price.
* `range` (string (query)): Range filter.
    * *Options:* `ITM` (In-the-Money), `NTM` (Near-the-Money), `OTM` (Out-of-the-Money), `SAK` (Strikes Above Market), `SBK` (Strikes Below Market), `SNK` (Strikes Near Market), `ALL` (All strikes).
* `fromDate` (string (query)): Only return expirations after this date. Format: `yyyy-MM-dd`.
* `toDate` (string (query)): Only return expirations before this date. Format: `yyyy-MM-dd`.
* `volatility` (number (query)): Volatility to use in `ANALYTICAL` calculations.
* `underlyingPrice` (number (query)): Underlying price to use in `ANALYTICAL` calculations.
* `interestRate` (number (query)): Interest rate to use in `ANALYTICAL` calculations.
* `daysToExpiration` (integer (query)): Days to expiration to use in `ANALYTICAL` calculations.
* `expMonth` (string (query)): Return only options expiring in the specified month.
    * *Values:* `JAN`, `FEB`, `MAR`, `APR`, `MAY`, `JUN`, `JUL`, `AUG`, `SEP`, `OCT`, `NOV`, `DEC`, `ALL`.
* `optionType` (string (query)): Type of option contracts to return.
    * *Values:* `S` (Standard), `NS` (Non-Standard), `ALL`.
* `entitlement` (string (query)): Applicable only for retail tokens.
    * *Values:* `PP` (PayingPro), `NP` (NonPro), `PN` (NonPayingPro).

#### Responses
**Success Response (200)**: A valid option chain response.

**Schema on success**:
```json
{
    "symbol": "AAPL",
    "status": "SUCCESS",
    "underlying": {
        "symbol": "AAPL",
        "description": "APPLE INC",
        "last": 257.46,
        "mark": 257.46,
        "bid": 256.65,
        "ask": 257.0,
        "totalVolume": 41120042,
        "delayed": false
    },
    "strategy": "SINGLE",
    "underlyingPrice": 257.46,
    "volatility": 29.0,
    "daysToExpiration": 2.0,
    "callExpDateMap": {
        "2026-03-09:2": {
            "252.5": [
                {
                    "putCall": "CALL",
                    "symbol": "AAPL  260309C00252500",
                    "description": "AAPL 03/09/2026 252.50 C",
                    "bid": 5.75,
                    "ask": 6.1,
                    "last": 6.25,
                    "mark": 5.93,
                    "strikePrice": 252.5,
                    "expirationDate": "2026-03-09T20:00:00.000+00:00",
                    "daysToExpiration": 2,
                    "multiplier": 100.0,
                    "inTheMoney": true
                }
            ]
        }
    },
    "putExpDateMap": { ... }
}

```

### **GET** `/marketdata/v1/expirationchain`
Get an option expiration chain for a specific underlying symbol.

#### Parameters

* `symbol` (string (query), required): The underlying symbol (e.g., `AAPL`).

#### Responses
**Success Response (200)**: A list of option expirations.

**Schema on success**:
```json
{
    "expirationList": [
        {
            "expirationDate": "2026-03-09",
            "daysToExpiration": 2,
            "expirationType": "W",
            "settlementType": "P",
            "optionRoots": "AAPL",
            "standard": true
        }
    ]
}
```

## Movers

### **GET** `/marketdata/v1/movers/{symbol}`
Get a list of top 10 securities movement for a specific index.

#### Parameters

* `symbol` (string (path), required): The index symbol.
    * *Values:* `$DJI`, `$COMPX`, `$SPX`, `NYSE`, `NASDAQ`, `OTCBB`, `INDEX_ALL`, `EQUITY_ALL`, `OPTION_ALL`, `OPTION_PUT`, `OPTION_CALL`.
* `sort` (string (query)): Attribute to sort by.
    * *Values:* `VOLUME`, `TRADES`, `PERCENT_CHANGE_UP`, `PERCENT_CHANGE_DOWN`.
* `frequency` (integer (query)): To return movers with specified directions of up or down.
    * *Values:* `0`, `1`, `5`, `10`, `30`, `60`.
    * *Default:* `0`.

#### Responses
**Success Response (200)**: Analytics for the symbol was returned successfully.

**Schema on success**:
```json
{
    "screeners": [
        {
            "symbol": "NVDA",
            "description": "NVIDIA CORP",
            "lastPrice": 119.26,
            "netChange": 3.68,
            "netPercentChange": 0.0318,
            "volume": 65591131,
            "totalVolume": 473944635,
            "marketShare": 13.84,
            "trades": 522082
        }
    ]
}
```

## Market Hours

### **GET** `/marketdata/v1/markets`
Get Market Hours for different markets.

#### Parameters

* `markets` (array[string], required): List of markets.
    * *Values:* `equity`, `option`, `bond`, `future`, `forex`.
* `date` (string (query)): Valid date range is from current date to 1 year from today. Defaults to current day. Format: `YYYY-MM-DD`.

#### Responses
**Success Response (200)**: OK

**Schema on success**:
```json
{
    "equity": {
        "EQ": {
            "date": "2022-04-14",
            "marketType": "EQUITY",
            "product": "EQ",
            "productName": "equity",
            "isOpen": true,
            "sessionHours": {
                "preMarket": [
                    {
                        "start": "2022-04-14T07:00:00-04:00",
                        "end": "2022-04-14T09:30:00-04:00"
                    }
                ],
                "regularMarket": [
                    {
                        "start": "2022-04-14T09:30:00-04:00",
                        "end": "2022-04-14T16:00:00-04:00"
                    }
                ],
                "postMarket": [
                    {
                        "start": "2022-04-14T16:00:00-04:00",
                        "end": "2022-04-14T20:00:00-04:00"
                    }
                ]
            }
        }
    },
    "option": {
        "EQO": {
            "date": "2022-04-14",
            "marketType": "OPTION",
            "product": "EQO",
            "productName": "equity option",
            "isOpen": true,
            "sessionHours": {
                "regularMarket": [
                    {
                        "start": "2022-04-14T09:30:00-04:00",
                        "end": "2022-04-14T16:00:00-04:00"
                    }
                ]
            }
        }
    }
}
```

### **GET** `/marketdata/v1/markets/{market_id}`
Get Market Hours for a single market.

#### Parameters

* `market_id` (string (path), required): The market ID.
    * *Values:* `equity`, `option`, `bond`, `future`, `forex`.
* `date` (string (query)): Valid date range is from current date to 1 year from today. Defaults to current day. Format: `YYYY-MM-DD`.

#### Responses
**Success Response (200)**: OK

**Schema on success**:
```json
{
    "equity": {
        "EQ": {
            "date": "2022-04-14",
            "marketType": "EQUITY",
            "product": "EQ",
            "productName": "equity",
            "isOpen": true,
            "sessionHours": {
                "preMarket": [
                    {
                        "start": "2022-04-14T07:00:00-04:00",
                        "end": "2022-04-14T09:30:00-04:00"
                    }
                ],
                "regularMarket": [
                    {
                        "start": "2022-04-14T09:30:00-04:00",
                        "end": "2022-04-14T16:00:00-04:00"
                    }
                ],
                "postMarket": [
                    {
                        "start": "2022-04-14T16:00:00-04:00",
                        "end": "2022-04-14T20:00:00-04:00"
                    }
                ]
            }
        }
    }
}
```

## Instruments

### **GET** `/marketdata/v1/instruments`
Get instrument details by symbols and projections.

#### Parameters

* `symbol` (string (query), required): Symbol of a security or search term. Can be a comma-separated list.
* `projection` (string (query), required): Search type.
    * *Values:* `symbol-search`, `symbol-regex`, `desc-search`, `desc-regex`, `search`, `fundamental`.

#### Responses
**Success Response (200)**: OK

**Schema on success**:
```json
{
    "instruments": [
        {
            "cusip": "037833100",
            "symbol": "AAPL",
            "description": "Apple Inc",
            "exchange": "NASDAQ",
            "assetType": "EQUITY"
        }
    ]
}
```

> [!TIP]
> When using `projection=fundamental`, each instrument object will also contain a `fundamental` key with detailed data (e.g., `high52`, `peRatio`, `dividendAmount`, etc.).

### **GET** `/marketdata/v1/instruments/{cusip_id}`
Get instrument details by CUSIP.

#### Parameters

* `cusip_id` (string (path), required): The CUSIP of the instrument.

#### Responses
**Success Response (200)**: OK

**Schema on success**:
```json
{
    "cusip": "037833100",
    "symbol": "AAPL",
    "description": "Apple Inc",
    "exchange": "NASDAQ",
    "assetType": "EQUITY"
}
```

## Streaming Data (WebSocket)

The Streamer API enables real-time market data and account activity streaming via WebSockets. Authentication is provided via the standard OAuth access token.

### **1. Connection & Authentication**

1.  **Get Streamer Info:** Call `GET /userPreference` to retrieve `streamerSocketUrl`, `schwabClientCustomerId`, `schwabClientCorrelId`, `schwabClientChannel`, and `schwabClientFunctionId`.
2.  **Connect:** Establish a WebSocket connection to the `streamerSocketUrl`.
3.  **Login:** Send an `ADMIN LOGIN` request immediately after connecting.

**Login Request Example:**
```json
{
    "requests": [
        {
            "requestid": "1",
            "service": "ADMIN",
            "command": "LOGIN",
            "SchwabClientCustomerId": "YOUR_CUSTOMER_ID",
            "SchwabClientCorrelId": "YOUR_SESSION_ID",
            "parameters": {
                "Authorization": "YOUR_ACCESS_TOKEN",
                "SchwabClientChannel": "N9",
                "SchwabClientFunctionId": "APIAPP"
            }
        }
    ]
}
```

### **2. Services & Delivery Types**

| Service Name | Description | Delivery Type |
| :--- | :--- | :--- |
| `LEVELONE_EQUITIES` | Level 1 Equities | Change (Deltas) |
| `LEVELONE_OPTIONS` | Level 1 Options | Change (Deltas) |
| `LEVELONE_FUTURES` | Level 1 Futures | Change (Deltas) |
| `LEVELONE_FUTURES_OPTIONS` | Level 1 Futures Options | Change (Deltas) |
| `LEVELONE_FOREX` | Level 1 Forex | Change (Deltas) |
| `NYSE_BOOK` | Level 2 Book (NYSE) | Whole (Overwrite) |
| `NASDAQ_BOOK` | Level 2 Book (NASDAQ) | Whole (Overwrite) |
| `OPTIONS_BOOK` | Level 2 Book (Options) | Whole (Overwrite) |
| `CHART_EQUITY` | Equity Candles (1-min) | All Sequence |
| `CHART_FUTURES` | Futures Candles (1-min) | All Sequence |
| `SCREENER_EQUITY` | Equity Gainers/Losers | Whole |
| `SCREENER_OPTION` | Option Gainers/Losers | Whole |
| `ACCT_ACTIVITY` | Account Fills/Activity | All Sequence |

*   **Change:** Only updated fields are sent. First response contains the full state.
*   **Whole:** The entire snapshot is sent with every update.
*   **All Sequence:** Every data point is sent with a sequence number; data is not conflated.

### **3. Commands**

*   **`SUBS`**: Subscribe to symbols. **Overwrites** previous subscriptions for that service.
*   **`ADD`**: Adds symbols to the current subscription list for a service.
*   **`UNSUBS`**: Removes specific symbols.
*   **`VIEW`**: Changes the field subscription for a service (applies to all symbols).
*   **`LOGOUT`**: Closes the connection.

### **4. Symbol Formats**

*   **Options:** `RRRRRRYYMMDDsWWWWWddd` (Space-filled root, YYMMDD, C/P, Whole Strike, Decimal Strike).
    *   *Example:* `AAPL  251219C00200000`
*   **Futures:** `/` + `Root` + `Month Code` + `Year Code`.
    *   *Month Codes:* F(Jan), G(Feb), H(Mar), J(Apr), K(May), M(Jun), N(Jul), Q(Aug), U(Sep), V(Oct), X(Nov), Z(Dec).
    *   *Example:* `/ESZ24`
*   **Futures Options:** `./` + `Root` + `Month` + `Year` + `C/P` + `Strike`.
    *   *Example:* `./OZCZ23C565`

### **5. Response Field Reference**

Numeric keys in the `content` block map to the following fields:

#### **LEVELONE_EQUITIES**
| Key | Field | Key | Field |
| :--- | :--- | :--- | :--- |
| 0 | Symbol | 1 | Bid Price |
| 2 | Ask Price | 3 | Last Price |
| 4 | Bid Size (Lots) | 5 | Ask Size (Lots) |
| 8 | Total Volume | 10 | High Price |
| 11 | Low Price | 12 | Close Price |
| 13 | Exchange ID | 15 | Description |
| 18 | Net Change | 19 | 52 Week High |
| 20 | 52 Week Low | 32 | Security Status |
| 33 | Mark Price | 42 | Net % Change |

#### **LEVELONE_OPTIONS**
| Key | Field | Key | Field |
| :--- | :--- | :--- | :--- |
| 0 | Symbol | 2 | Bid Price |
| 3 | Ask Price | 4 | Last Price |
| 8 | Total Volume | 9 | Open Interest |
| 10 | Volatility | 11 | Intrinsic Value |
| 20 | Strike Price | 27 | Days to Expiration |
| 28 | Delta | 30 | Theta |

#### **CHART_EQUITY**
| Key | Field | Key | Field |
| :--- | :--- | :--- | :--- |
| 0 | Key | 1 | Open Price |
| 2 | High Price | 3 | Low Price |
| 4 | Close Price | 5 | Volume |
| 6 | Sequence | 7 | Chart Time |

#### **SCREENER_EQUITY / SCREENER_OPTION**
The `keys` for screeners follow the format: `(PREFIX)_(SORTFIELD)_(FREQUENCY)`.
*   *Prefix:* `$DJI`, `$COMPX`, `$SPX`, `INDEX_ALL`, `NYSE`, `NASDAQ`, `OTCBB`, `EQUITY_ALL`, `OPTION_PUT`, `OPTION_CALL`, `OPTION_ALL`.
*   *Sort:* `VOLUME`, `TRADES`, `PERCENT_CHANGE_UP`, `PERCENT_CHANGE_DOWN`.
*   *Frequency:* `0`, `1`, `5`, `10`, `30`, `60`.

**Response Fields:**
| Key | Field | Key | Field |
| :--- | :--- | :--- | :--- |
| 0 | Symbol | 1 | Timestamp |
| 2 | Sort Field | 3 | Frequency |
| 4 | Items (Array) | | |

**Item Fields (within key 4):**
`symbol`, `description`, `lastPrice`, `netChange`, `netPercentChange`, `volume`, `totalVolume`, `marketShare`, `trades`.

#### **ACCT_ACTIVITY**
| Key | Field | Description |
| :--- | :--- | :--- |
| `seq` | Sequence | Message number for tracking. |
| `key` | Key | Subscription identifier. Use `schwabClientCorrelId` from user preferences as the subscription key. |
| 0 | Subscription Key | Passed back to the client from the request to identify a subscription this response belongs to. |
| 1 | Account | The Account Hash where activity occurred. |
| 2 | Message Type | Type of activity (e.g., `OrderCreated`, `OrderAccepted`, `CancelAccepted`, `ExecutionCreated`, `OrderUROutCompleted`). |
| 3 | Message Data | The core JSON data for the activity update. |

**Important Note on Order Prices in ACCT_ACTIVITY:**
Within the `Message Data` JSON, Schwab's Order Management System (ngOMS) transmits numerical values like `LimitPrice`, `Quantity`, and `PriceImprovement` using a fixed-point integer dictionary representation rather than standard floating point numbers, to prevent rounding errors.
Format: `{"lo": "511800000", "signScale": 12}`

To calculate the actual floating-point value, divide the `lo` value by `1,000,000` (10^6).
*   *Example Limit Price:* `{"lo": "511800000"}` ➔ $511.80
*   *Example Quantity:* `{"lo": "1000000"}` ➔ 1
*   *Example Price Improvement:* `{"lo": "10900"}` ➔ $0.0109

### **6. Response Codes**

| Code | Name | Description |
| :--- | :--- | :--- |
| 0 | `SUCCESS` | Request successful. |
| 3 | `LOGIN_DENIED` | Token invalid or expired. |
| 12 | `CLOSE_CONNECTION` | Max connections reached (Limit: 1). |
| 19 | `SYMBOL_LIMIT` | Reached max subscription limit. |
| 20 | `CONN_NOT_FOUND` | CustomerId or CorrelId mismatch. |
| 30 | `STOP_STREAMING` | Terminated due to slowness or inactivity. |


## Common HTTP Error Responses

Most API endpoints return a standardized error response when a request fails. The error body typically contains an `errors` array with detailed information.

### **Error Schema**
```json
{
    "errors": [
        {
            "id": "6808262e-52bb-4421-9d31-6c0e762e7dd5",
            "status": "400",
            "title": "Bad Request",
            "detail": "Missing header",
            "source": {
                "header": "Authorization"
            }
        }
    ]
}
```

### **Common Error Codes**
* **400 (Bad Request)**: The request was invalid (e.g., missing parameters, invalid values).
* **401 (Unauthorized)**: Authorization token is invalid or missing.
* **403 (Forbidden)**: Access is denied for the requested resource.
* **404 (Not Found)**: The requested resource does not exist.
* **429 (Too Many Requests)**: Rate limit exceeded.
* **500 (Internal Server Error)**: An unexpected error occurred on the server.
* **503 (Service Unavailable)**: The server is temporarily unable to handle the request.

### **Response Headers**
* `Schwab-Client-CorrelId`: A unique ID for tracking the individual service call.
* `Schwab-Resource-Version`: The version of the API resource.

# Schemas

```typescript

export interface AccountNumberHash {
 accountNumber?: string;
 hashValue?: string;
}

/** The market session during which the order trade should be executed. */
export type session = 'NORMAL' /* Normal market hours, from 9:30am to 4:00pm Eastern. */ | 'AM' /* Premarket session, from 8:00am to 9:30am Eastern. */ | 'PM' /* After-market session, from 4:00pm to 8:00pm Eastern. */ | 'SEAMLESS' /* Orders are active during all trading sessions except the overnight session. This is the union of NORMAL, AM, and PM. */;

/** Length of time over which the trade will be active. */
export type duration = 'DAY';

/** Type of order to place. */
export type orderType = 'MARKET' /* Execute the order immediately at the best-available price. More Info < */ | 'LIMIT' /* Execute the order at your price or better. More info < */ | 'STOP' /* Wait until the price reaches the stop price, and then immediately place a market order. More Info < */ | 'STOP_LIMIT' /* Wait until the price reaches the stop price, and then immediately place a limit order at the specified price. More Info < */ | 'TRAILING_STOP' /* Similar to STOP, except if the price moves in your favor, the stop price is adjusted in that direction. Places a market order if the stop condition is met. More info < */ | 'CABINET' | 'NON_MARKETABLE' | 'MARKET_ON_CLOSE' /* Place the order at the closing price immediately upon market close. More info <>__ */ | 'EXERCISE' /* Exercise an option. */ | 'TRAILING_STOP_LIMIT' /* Similar to STOP_LIMIT, except if the price moves in your favor, the stop price is adjusted in that direction. Places a limit order at the specified price if the stop condition is met. More info < */ | 'NET_DEBIT' /* Place an order for an options spread resulting in a net debit. More info < whats-difference-between-credit-spread-and-debt-spread.asp>__ */ | 'NET_CREDIT' /* Place an order for an options spread resulting in a net credit. More info < whats-difference-between-credit-spread-and-debt-spread.asp>__ */ | 'NET_ZERO' /* Place an order for an options spread resulting in neither a credit nor a debit. More info < whats-difference-between-credit-spread-and-debt-spread.asp>__ */ | 'LIMIT_ON_CLOSE' | 'UNKNOWN';

/** Same as orderType, but does not have UNKNOWN since this type is not allowed as an input Type of order to place. */
export type orderTypeRequest = 'MARKET' /* Execute the order immediately at the best-available price. More Info < */ | 'LIMIT' /* Execute the order at your price or better. More info < */ | 'STOP' /* Wait until the price reaches the stop price, and then immediately place a market order. More Info < */ | 'STOP_LIMIT' /* Wait until the price reaches the stop price, and then immediately place a limit order at the specified price. More Info < */ | 'TRAILING_STOP' /* Similar to STOP, except if the price moves in your favor, the stop price is adjusted in that direction. Places a market order if the stop condition is met. More info < */ | 'CABINET' | 'NON_MARKETABLE' | 'MARKET_ON_CLOSE' /* Place the order at the closing price immediately upon market close. More info <>__ */ | 'EXERCISE' /* Exercise an option. */ | 'TRAILING_STOP_LIMIT' /* Similar to STOP_LIMIT, except if the price moves in your favor, the stop price is adjusted in that direction. Places a limit order at the specified price if the stop condition is met. More info < */ | 'NET_DEBIT' /* Place an order for an options spread resulting in a net debit. More info < whats-difference-between-credit-spread-and-debt-spread.asp>__ */ | 'NET_CREDIT' /* Place an order for an options spread resulting in a net credit. More info < whats-difference-between-credit-spread-and-debt-spread.asp>__ */ | 'NET_ZERO' /* Place an order for an options spread resulting in neither a credit nor a debit. More info < whats-difference-between-credit-spread-and-debt-spread.asp>__ */ | 'LIMIT_ON_CLOSE';

/** Explicit order strategies for executing multi-leg options orders. */
export type complexOrderStrategyType = 'NONE' /* No complex order strategy. This is the default. */ | 'COVERED' /* Covered call < selling-covered-call-options-strategy-income-hedging-15135>__ */ | 'VERTICAL' /* Vertical spread < vertical-credit-spreads-high-probability-15846>__ */ | 'BACK_RATIO' /* Ratio backspread < pricey-stocks-ratio-spreads-15306>__ */ | 'CALENDAR' /* Calendar spread < calendar-spreads-trading-primer-15095>__ */ | 'DIAGONAL' /* Diagonal spread < love-your-diagonal-spread-15030>__ */ | 'STRADDLE' /* Straddle spread < straddle-strangle-option-volatility-16208>__ */ | 'STRANGLE' /* Strandle spread < straddle-strangle-option-volatility-16208>__ */ | 'COLLAR_SYNTHETIC' | 'BUTTERFLY' /* Butterfly spread < butterfly-spread-options-15976>__ */ | 'CONDOR' /* Condor spread < condorspread.asp>__ */ | 'IRON_CONDOR' /* Iron condor spread < iron-condor-options-spread-your-trading-wings-15948>__ */ | 'VERTICAL_ROLL' /* Roll a vertical spread < exit-winning-losing-trades-16685>__ */ | 'COLLAR_WITH_STOCK' /* Collar strategy < stock-hedge-options-collars-15529>__ */ | 'DOUBLE_DIAGONAL' /* Double diagonal spread < the-ultimate-guide-to-double-diagonal-spreads/>__ */ | 'UNBALANCED_BUTTERFLY' /* Unbalanced butterfy spread < trading/unbalanced-butterfly-strong-directional-bias-15913>__ */ | 'UNBALANCED_CONDOR' | 'UNBALANCED_IRON_CONDOR' | 'UNBALANCED_VERTICAL_ROLL' | 'MUTUAL_FUND_SWAP' /* Mutual fund swap */ | 'CUSTOM' /* A custom multi-leg order strategy. */;

/** By default, Schwab sends trades to whichever exchange provides the best price. This field allows you to request a destination exchange for your trade, although whether your order is actually executed there is up to Schwab. Destinations for when you want to request a specific destination for your order. */
export type requestedDestination = 'INET' | 'ECN_ARCA' | 'CBOE' | 'AMEX' | 'PHLX' | 'ISE' | 'BOX' | 'NYSE' | 'NASDAQ' | 'BATS' | 'C2' | 'AUTO';

export type stopPriceLinkBasis = 'MANUAL' | 'BASE' | 'TRIGGER' | 'LAST' | 'BID' | 'ASK' | 'ASK_BID' | 'MARK' | 'AVERAGE';

export type stopPriceLinkType = 'VALUE' | 'PERCENT' | 'TICK';

export type stopType = 'STANDARD' | 'BID' | 'ASK' | 'LAST' | 'MARK';

export type priceLinkBasis = 'MANUAL' | 'BASE' | 'TRIGGER' | 'LAST' | 'BID' | 'ASK' | 'ASK_BID' | 'MARK' | 'AVERAGE';

export type priceLinkType = 'VALUE' | 'PERCENT' | 'TICK';

export type taxLotMethod = 'FIFO' | 'LIFO' | 'HIGH_COST' | 'LOW_COST' | 'AVERAGE_COST' | 'SPECIFIC_LOT' | 'LOSS_HARVESTER';

/** Special instruction for trades. */
export type specialInstruction = 'ALL_OR_NONE' /* Disallow partial order execution. More info < */ | 'DO_NOT_REDUCE' /* Do not reduce order size in response to cash dividends. More info < */ | 'ALL_OR_NONE_DO_NOT_REDUCE' /* Combination of ALL_OR_NONE and DO_NOT_REDUCE. */;

/** Rules for composite orders. */
export type orderStrategyType = 'SINGLE' /* No chaining, only a single order is submitted */ | 'CANCEL' | 'RECALL' | 'PAIR' | 'FLATTEN' | 'TWO_DAY_SWAP' | 'BLAST_ALL' | 'OCO' /* Execution of one order cancels the other */ | 'TRIGGER' /* Execution of one order triggers placement of the other */;

/** Order statuses passed to :meth:`get_orders_for_account` and
 :meth:`get_orders_for_all_linked_accounts` */
export type status = 'AWAITING_PARENT_ORDER' | 'AWAITING_CONDITION' | 'AWAITING_STOP_CONDITION' | 'AWAITING_MANUAL_REVIEW' | 'ACCEPTED' | 'AWAITING_UR_OUT' | 'PENDING_ACTIVATION' | 'QUEUED' | 'WORKING' | 'REJECTED' | 'PENDING_CANCEL' | 'CANCELED' | 'PENDING_REPLACE' | 'REPLACED' | 'FILLED' | 'EXPIRED' | 'NEW' | 'AWAITING_RELEASE_TIME' | 'PENDING_ACKNOWLEDGEMENT' | 'PENDING_RECALL' | 'UNKNOWN';

export type amountIndicator = 'DOLLARS' | 'SHARES' | 'ALL_SHARES' | 'PERCENTAGE' | 'UNKNOWN';

export type settlementInstruction = 'REGULAR' | 'CASH' | 'NEXT_DAY' | 'UNKNOWN';

export interface OrderStrategy {
 accountNumber?: string;
 advancedOrderType?: 'NONE' | 'OTO' | 'OCO' | 'OTOCO' | 'OT2OCO' | 'OT3OCO' | 'BLAST_ALL' | 'OTA' | 'PAIR';
 closeTime?: string;
 enteredTime?: string;
 orderBalance?: OrderBalance;
 orderStrategyType?: orderStrategyType;
 orderVersion?: number;
 session?: session;
 /** Restrict query to orders with this status. See :class:`Order.Status` for options. */
 status?: apiOrderStatus;
 allOrNone?: boolean;
 discretionary?: boolean;
 duration?: duration;
 filledQuantity?: number;
 orderType?: orderType;
 orderValue?: number;
 price?: number;
 /** Number of contracts for the order */
 quantity?: number;
 remainingQuantity?: number;
 sellNonMarginableFirst?: boolean;
 settlementInstruction?: settlementInstruction;
 /** If passed, returns a Strategy Chain. See :class:`Options.Strategy` for choices. */
 strategy?: complexOrderStrategyType;
 amountIndicator?: amountIndicator;
 orderLegs?: OrderLeg[];
}

export interface OrderLeg {
 askPrice?: number;
 bidPrice?: number;
 lastPrice?: number;
 markPrice?: number;
 projectedCommission?: number;
 /** Number of contracts for the order */
 quantity?: number;
 finalSymbol?: string;
 legId?: number;
 assetType?: assetType;
 /** Instruction for the leg. See :class:`~schwab.orders.common.OptionInstruction` for valid options. */
 instruction?: instruction;
}

export interface OrderBalance {
 orderValue?: number;
 projectedAvailableFund?: number;
 projectedBuyingPower?: number;
 projectedCommission?: number;
}

export interface OrderValidationResult {
 alerts?: OrderValidationDetail[];
 accepts?: OrderValidationDetail[];
 rejects?: OrderValidationDetail[];
 reviews?: OrderValidationDetail[];
 warns?: OrderValidationDetail[];
}

export interface OrderValidationDetail {
 validationRuleName?: string;
 message?: string;
 activityMessage?: string;
 originalSeverity?: APIRuleAction;
 overrideName?: string;
 overrideSeverity?: APIRuleAction;
}

/** string Enum: [ ACCEPT, ALERT, REJECT, REVIEW, UNKNOWN ] */
export type APIRuleAction = 'ACCEPT' | 'ALERT' | 'REJECT' | 'REVIEW' | 'UNKNOWN';

export interface CommissionAndFee {
 commission?: Commission;
 fee?: Fees;
 trueCommission?: Commission;
}

export interface Commission {
 commissionLegs?: any;
}

export interface CommissionLeg {
 commissionValues?: any;
}

export interface CommissionValue {
 value?: number;
 type?: FeeType;
}

export interface Fees {
 feeLegs?: any;
}

export interface FeeLeg {
 feeValues?: any;
}

export interface FeeValue {
 value?: number;
 type?: FeeType;
}

export type FeeType = 'COMMISSION' | 'SEC_FEE' | 'STR_FEE' | 'R_FEE' | 'CDSC_FEE' | 'OPT_REG_FEE' | 'ADDITIONAL_FEE' | 'MISCELLANEOUS_FEE' | 'FTT' | 'FUTURES_CLEARING_FEE' | 'FUTURES_DESK_OFFICE_FEE' | 'FUTURES_EXCHANGE_FEE' | 'FUTURES_GLOBEX_FEE' | 'FUTURES_NFA_FEE' | 'FUTURES_PIT_BROKERAGE_FEE' | 'FUTURES_TRANSACTION_FEE' | 'LOW_PROCEEDS_COMMISSION' | 'BASE_CHARGE' | 'GENERAL_CHARGE' | 'GST_FEE' | 'TAF_FEE' | 'INDEX_OPTION_FEE' | 'TEFRA_TAX' | 'STATE_TAX' | 'UNKNOWN';

export interface Account {
 securitiesAccount?: SecuritiesAccount;
}

export interface DateParam {
 /** Date for which to return market hours. Accepts values up to one year from today. Accepts ``datetime.date``. */
 date?: string;
}

export interface Order {
 session?: session;
 duration?: duration;
 orderType?: orderType;
 cancelTime?: string;
 complexOrderStrategyType?: complexOrderStrategyType;
 /** Number of contracts for the order */
 quantity?: number;
 filledQuantity?: number;
 remainingQuantity?: number;
 requestedDestination?: requestedDestination;
 destinationLinkName?: string;
 releaseTime?: string;
 stopPrice?: number;
 stopPriceLinkBasis?: stopPriceLinkBasis;
 stopPriceLinkType?: stopPriceLinkType;
 stopPriceOffset?: number;
 stopType?: stopType;
 priceLinkBasis?: priceLinkBasis;
 priceLinkType?: priceLinkType;
 price?: number;
 taxLotMethod?: taxLotMethod;
 orderLegCollection?: any;
 activationPrice?: number;
 specialInstruction?: specialInstruction;
 orderStrategyType?: orderStrategyType;
 orderId?: number;
 cancelable?: boolean;
 editable?: boolean;
 /** Restrict query to orders with this status. See :class:`Order.Status` for options. */
 status?: status;
 enteredTime?: string;
 closeTime?: string;
 tag?: string;
 accountNumber?: number;
 orderActivityCollection?: any;
 replacingOrderCollection?: OrderedMap[];
 childOrderStrategies?: any;
 statusDescription?: string;
}

export interface OrderRequest {
 session?: session;
 duration?: duration;
 orderType?: orderTypeRequest;
 cancelTime?: string;
 complexOrderStrategyType?: complexOrderStrategyType;
 /** Number of contracts for the order */
 quantity?: number;
 filledQuantity?: number;
 remainingQuantity?: number;
 destinationLinkName?: string;
 releaseTime?: string;
 stopPrice?: number;
 stopPriceLinkBasis?: stopPriceLinkBasis;
 stopPriceLinkType?: stopPriceLinkType;
 stopPriceOffset?: number;
 stopType?: stopType;
 priceLinkBasis?: priceLinkBasis;
 priceLinkType?: priceLinkType;
 price?: number;
 taxLotMethod?: taxLotMethod;
 orderLegCollection?: any;
 activationPrice?: number;
 specialInstruction?: specialInstruction;
 orderStrategyType?: orderStrategyType;
 orderId?: number;
 cancelable?: boolean;
 editable?: boolean;
 /** Restrict query to orders with this status. See :class:`Order.Status` for options. */
 status?: status;
 enteredTime?: string;
 closeTime?: string;
 accountNumber?: number;
 orderActivityCollection?: any;
 replacingOrderCollection?: OrderedMap[];
 childOrderStrategies?: OrderedMap[];
 statusDescription?: string;
}

export interface PreviewOrder {
 orderId?: number;
 orderStrategy?: OrderStrategy;
 orderValidationResult?: OrderValidationResult;
 commissionAndFee?: CommissionAndFee;
}

export interface OrderActivity {
 activityType?: 'EXECUTION' | 'ORDER_ACTION';
 executionType?: 'FILL';
 /** Number of contracts for the order */
 quantity?: number;
 orderRemainingQuantity?: number;
 executionLegs?: any;
}

export interface ExecutionLeg {
 legId?: number;
 price?: number;
 /** Number of contracts for the order */
 quantity?: number;
 mismarkedQuantity?: number;
 instrumentId?: number; /** A unique numeric identifier assigned by Schwab internally. Not required when submitting an order. */
 time?: string;
}

export interface Position {
 shortQuantity?: number;
 averagePrice?: number;
 currentDayProfitLoss?: number;
 currentDayProfitLossPercentage?: number;
 longQuantity?: number;
 settledLongQuantity?: number;
 settledShortQuantity?: number;
 agedQuantity?: number;
 instrument?: AccountsInstrument;
 marketValue?: number;
 maintenanceRequirement?: number;
 averageLongPrice?: number;
 averageShortPrice?: number;
 taxLotAverageLongPrice?: number;
 taxLotAverageShortPrice?: number;
 longOpenProfitLoss?: number;
 shortOpenProfitLoss?: number;
 previousSessionLongQuantity?: number;
 previousSessionShortQuantity?: number;
 currentDayCost?: number;
}

export interface ServiceError {
 message?: string;
 errors?: string[];
}

export interface OrderLegCollection {
 orderLegType?: 'EQUITY' | 'OPTION' | 'INDEX' | 'MUTUAL_FUND' | 'CASH_EQUIVALENT' | 'FIXED_INCOME' | 'CURRENCY' | 'COLLECTIVE_INVESTMENT';
 legId?: number;
 instrument?: AccountsInstrument;
 /** Instruction for the leg. See :class:`~schwab.orders.common.OptionInstruction` for valid options. */
 instruction?: instruction;
 positionEffect?: 'OPENING' | 'CLOSING' | 'AUTOMATIC';
 /** Number of contracts for the order */
 quantity?: number;
 quantityType?: 'ALL_SHARES' | 'DOLLARS' | 'SHARES';
 divCapGains?: 'REINVEST' | 'PAYOUT';
 toSymbol?: string;
}

export type SecuritiesAccount = MarginAccount | CashAccount;

export interface SecuritiesAccountBase {
 type?: 'CASH' | 'MARGIN';
 accountNumber?: string;
 roundTrips?: number;
 isDayTrader?: boolean;
 isClosingOnlyRestricted?: boolean;
 pfcbFlag?: boolean;
 positions?: any;
}

export interface MarginAccount {
 type?: 'CASH' | 'MARGIN';
 accountNumber?: string;
 roundTrips?: number;
 isDayTrader?: boolean;
 isClosingOnlyRestricted?: boolean;
 pfcbFlag?: boolean;
 positions?: any;
 initialBalances?: MarginInitialBalance;
 currentBalances?: MarginBalance;
 projectedBalances?: MarginBalance;
}

export interface MarginInitialBalance {
 accruedInterest?: number;
 availableFundsNonMarginableTrade?: number;
 bondValue?: number;
 buyingPower?: number;
 cashBalance?: number;
 cashAvailableForTrading?: number;
 cashReceipts?: number;
 dayTradingBuyingPower?: number;
 dayTradingBuyingPowerCall?: number;
 dayTradingEquityCall?: number;
 equity?: number;
 equityPercentage?: number;
 liquidationValue?: number;
 longMarginValue?: number;
 longOptionMarketValue?: number;
 longStockValue?: number;
 maintenanceCall?: number;
 maintenanceRequirement?: number;
 margin?: number;
 marginEquity?: number;
 moneyMarketFund?: number;
 mutualFundValue?: number;
 regTCall?: number;
 shortMarginValue?: number;
 shortOptionMarketValue?: number;
 shortStockValue?: number;
 totalCash?: number;
 isInCall?: number;
 unsettledCash?: number;
 pendingDeposits?: number;
 marginBalance?: number;
 shortBalance?: number;
 accountValue?: number;
}

export interface MarginBalance {
 availableFunds?: number;
 availableFundsNonMarginableTrade?: number;
 buyingPower?: number;
 buyingPowerNonMarginableTrade?: number;
 dayTradingBuyingPower?: number;
 dayTradingBuyingPowerCall?: number;
 equity?: number;
 equityPercentage?: number;
 longMarginValue?: number;
 maintenanceCall?: number;
 maintenanceRequirement?: number;
 marginBalance?: number;
 regTCall?: number;
 shortBalance?: number;
 shortMarginValue?: number;
 sma?: number;
 isInCall?: number;
 stockBuyingPower?: number;
 optionBuyingPower?: number;
}

export interface CashAccount {
 type?: 'CASH' | 'MARGIN';
 accountNumber?: string;
 roundTrips?: number;
 isDayTrader?: boolean;
 isClosingOnlyRestricted?: boolean;
 pfcbFlag?: boolean;
 positions?: any;
 initialBalances?: CashInitialBalance;
 currentBalances?: CashBalance;
 projectedBalances?: CashBalance;
}

export interface CashInitialBalance {
 accruedInterest?: number;
 cashAvailableForTrading?: number;
 cashAvailableForWithdrawal?: number;
 cashBalance?: number;
 bondValue?: number;
 cashReceipts?: number;
 liquidationValue?: number;
 longOptionMarketValue?: number;
 longStockValue?: number;
 moneyMarketFund?: number;
 mutualFundValue?: number;
 shortOptionMarketValue?: number;
 shortStockValue?: number;
 isInCall?: number;
 unsettledCash?: number;
 cashDebitCallValue?: number;
 pendingDeposits?: number;
 accountValue?: number;
}

export interface CashBalance {
 cashAvailableForTrading?: number;
 cashAvailableForWithdrawal?: number;
 cashCall?: number;
 longNonMarginableMarketValue?: number;
 totalCash?: number;
 cashDebitCallValue?: number;
 unsettledCash?: number;
}

export interface TransactionBaseInstrument {
 assetType: 'EQUITY' | 'OPTION' | 'INDEX' | 'MUTUAL_FUND' | 'CASH_EQUIVALENT' | 'FIXED_INCOME' | 'CURRENCY' | 'COLLECTIVE_INVESTMENT';
 /** String representing CUSIP of instrument for which to fetch data. Note leading zeroes must be preserved. */
 cusip?: string;
 /** For ``FUNDAMENTAL`` projection, the symbol for which to get fundamentals. For other projections, a search term. See below for details. */
 symbol?: string;
 description?: string;
 instrumentId?: number;
 netChange?: number;
}

export interface AccountsBaseInstrument {
 assetType: 'EQUITY' | 'OPTION' | 'INDEX' | 'MUTUAL_FUND' | 'CASH_EQUIVALENT' | 'FIXED_INCOME' | 'CURRENCY' | 'COLLECTIVE_INVESTMENT';
 /** String representing CUSIP of instrument for which to fetch data. Note leading zeroes must be preserved. */
 cusip?: string;
 /** For ``FUNDAMENTAL`` projection, the symbol for which to get fundamentals. For other projections, a search term. See below for details. */
 symbol?: string;
 description?: string;
 instrumentId?: number;
 netChange?: number;
}

export interface AccountsInstrument {
 // oneOf: AccountOption | AccountCashEquivalent | AccountEquity | AccountFixedIncome | AccountMutualFund
}

export interface TransactionInstrument {
 // oneOf: Currency | Index | Future | Forex | TransactionEquity | TransactionOption | Product | TransactionMutualFund | TransactionCashEquivalent | CollectiveInvestment | TransactionFixedIncome
}

export interface TransactionCashEquivalent {
 assetType: 'EQUITY' | 'OPTION' | 'INDEX' | 'MUTUAL_FUND' | 'CASH_EQUIVALENT' | 'FIXED_INCOME' | 'CURRENCY' | 'COLLECTIVE_INVESTMENT';
 /** String representing CUSIP of instrument for which to fetch data. Note leading zeroes must be preserved. */
 cusip?: string;
 /** For ``FUNDAMENTAL`` projection, the symbol for which to get fundamentals. For other projections, a search term. See below for details. */
 symbol?: string;
 description?: string;
 instrumentId?: number;
 netChange?: number;
 type?: 'SWEEP_VEHICLE' | 'SAVINGS' | 'MONEY_MARKET_FUND' | 'UNKNOWN';
}

export interface CollectiveInvestment {
 assetType: 'EQUITY' | 'OPTION' | 'INDEX' | 'MUTUAL_FUND' | 'CASH_EQUIVALENT' | 'FIXED_INCOME' | 'CURRENCY' | 'COLLECTIVE_INVESTMENT';
 /** String representing CUSIP of instrument for which to fetch data. Note leading zeroes must be preserved. */
 cusip?: string;
 /** For ``FUNDAMENTAL`` projection, the symbol for which to get fundamentals. For other projections, a search term. See below for details. */
 symbol?: string;
 description?: string;
 instrumentId?: number;
 netChange?: number;
 type?: 'UNIT_INVESTMENT_TRUST' | 'EXCHANGE_TRADED_FUND' | 'CLOSED_END_FUND' | 'INDEX' | 'UNITS';
}

export type instruction = 'BUY_TO_OPEN';

export type assetType = 'EQUITY' | 'MUTUAL_FUND' | 'OPTION' | 'FUTURE' | 'FOREX' | 'INDEX' | 'CASH_EQUIVALENT' | 'FIXED_INCOME' | 'PRODUCT' | 'CURRENCY' | 'COLLECTIVE_INVESTMENT';

export interface Currency {
 assetType: 'EQUITY' | 'OPTION' | 'INDEX' | 'MUTUAL_FUND' | 'CASH_EQUIVALENT' | 'FIXED_INCOME' | 'CURRENCY' | 'COLLECTIVE_INVESTMENT';
 /** String representing CUSIP of instrument for which to fetch data. Note leading zeroes must be preserved. */
 cusip?: string;
 /** For ``FUNDAMENTAL`` projection, the symbol for which to get fundamentals. For other projections, a search term. See below for details. */
 symbol?: string;
 description?: string;
 instrumentId?: number;
 netChange?: number;
}

export interface TransactionEquity {
 assetType: 'EQUITY' | 'OPTION' | 'INDEX' | 'MUTUAL_FUND' | 'CASH_EQUIVALENT' | 'FIXED_INCOME' | 'CURRENCY' | 'COLLECTIVE_INVESTMENT';
 /** String representing CUSIP of instrument for which to fetch data. Note leading zeroes must be preserved. */
 cusip?: string;
 /** For ``FUNDAMENTAL`` projection, the symbol for which to get fundamentals. For other projections, a search term. See below for details. */
 symbol?: string;
 description?: string;
 instrumentId?: number;
 netChange?: number;
 type?: 'COMMON_STOCK' | 'PREFERRED_STOCK' | 'DEPOSITORY_RECEIPT' | 'PREFERRED_DEPOSITORY_RECEIPT' | 'RESTRICTED_STOCK' | 'COMPONENT_UNIT' | 'RIGHT' | 'WARRANT' | 'CONVERTIBLE_PREFERRED_STOCK' | 'CONVERTIBLE_STOCK' | 'LIMITED_PARTNERSHIP' | 'WHEN_ISSUED' | 'UNKNOWN';
}

export interface TransactionFixedIncome {
 assetType: 'EQUITY' | 'OPTION' | 'INDEX' | 'MUTUAL_FUND' | 'CASH_EQUIVALENT' | 'FIXED_INCOME' | 'CURRENCY' | 'COLLECTIVE_INVESTMENT';
 /** String representing CUSIP of instrument for which to fetch data. Note leading zeroes must be preserved. */
 cusip?: string;
 /** For ``FUNDAMENTAL`` projection, the symbol for which to get fundamentals. For other projections, a search term. See below for details. */
 symbol?: string;
 description?: string;
 instrumentId?: number;
 netChange?: number;
 type?: 'BOND_UNIT' | 'CERTIFICATE_OF_DEPOSIT' | 'CONVERTIBLE_BOND' | 'COLLATERALIZED_MORTGAGE_OBLIGATION' | 'CORPORATE_BOND' | 'GOVERNMENT_MORTGAGE' | 'GNMA_BONDS' | 'MUNICIPAL_ASSESSMENT_DISTRICT' | 'MUNICIPAL_BOND' | 'OTHER_GOVERNMENT' | 'SHORT_TERM_PAPER' | 'US_TREASURY_BOND' | 'US_TREASURY_BILL' | 'US_TREASURY_NOTE' | 'US_TREASURY_ZERO_COUPON' | 'AGENCY_BOND' | 'WHEN_AS_AND_IF_ISSUED_BOND' | 'ASSET_BACKED_SECURITY' | 'UNKNOWN';
 maturityDate?: string;
 factor?: number;
 multiplier?: number;
 variableRate?: number;
}

export interface Forex {
 assetType: 'EQUITY' | 'OPTION' | 'INDEX' | 'MUTUAL_FUND' | 'CASH_EQUIVALENT' | 'FIXED_INCOME' | 'CURRENCY' | 'COLLECTIVE_INVESTMENT';
 /** String representing CUSIP of instrument for which to fetch data. Note leading zeroes must be preserved. */
 cusip?: string;
 /** For ``FUNDAMENTAL`` projection, the symbol for which to get fundamentals. For other projections, a search term. See below for details. */
 symbol?: string;
 description?: string;
 instrumentId?: number;
 netChange?: number;
 type?: 'STANDARD' | 'NBBO' | 'UNKNOWN';
 baseCurrency?: Currency;
 counterCurrency?: Currency;
}

export interface Future {
 activeContract?: boolean;
 type?: 'STANDARD' | 'UNKNOWN';
 expirationDate?: string;
 lastTradingDate?: string;
 firstNoticeDate?: string;
 multiplier?: number;
 // oneOf: Currency | Index | Forex | TransactionEquity | TransactionOption | Product | TransactionMutualFund | TransactionCashEquivalent | CollectiveInvestment | TransactionFixedIncome
}

export interface Index {
 activeContract?: boolean;
 type?: 'BROAD_BASED' | 'NARROW_BASED' | 'UNKNOWN';
 // oneOf: Currency | Future | Forex | TransactionEquity | TransactionOption | Product | TransactionMutualFund | TransactionCashEquivalent | CollectiveInvestment | TransactionFixedIncome
}

export interface TransactionMutualFund {
 assetType: 'EQUITY' | 'OPTION' | 'INDEX' | 'MUTUAL_FUND' | 'CASH_EQUIVALENT' | 'FIXED_INCOME' | 'CURRENCY' | 'COLLECTIVE_INVESTMENT';
 /** String representing CUSIP of instrument for which to fetch data. Note leading zeroes must be preserved. */
 cusip?: string;
 /** For ``FUNDAMENTAL`` projection, the symbol for which to get fundamentals. For other projections, a search term. See below for details. */
 symbol?: string;
 description?: string;
 instrumentId?: number;
 netChange?: number;
 fundFamilyName?: string;
 fundFamilySymbol?: string;
 fundGroup?: string;
 type?: 'NOT_APPLICABLE' | 'OPEN_END_NON_TAXABLE' | 'OPEN_END_TAXABLE' | 'NO_LOAD_NON_TAXABLE' | 'NO_LOAD_TAXABLE' | 'UNKNOWN';
 exchangeCutoffTime?: string;
 purchaseCutoffTime?: string;
 redemptionCutoffTime?: string;
}

export interface TransactionOption {
 assetType: 'EQUITY' | 'OPTION' | 'INDEX' | 'MUTUAL_FUND' | 'CASH_EQUIVALENT' | 'FIXED_INCOME' | 'CURRENCY' | 'COLLECTIVE_INVESTMENT';
 /** String representing CUSIP of instrument for which to fetch data. Note leading zeroes must be preserved. */
 cusip?: string;
 /** For ``FUNDAMENTAL`` projection, the symbol for which to get fundamentals. For other projections, a search term. See below for details. */
 symbol?: string;
 description?: string;
 instrumentId?: number;
 netChange?: number;
 expirationDate?: string;
 optionDeliverables?: any;
 optionPremiumMultiplier?: number;
 putCall?: 'PUT' | 'CALL' | 'UNKNOWN';
 strikePrice?: number;
 type?: 'VANILLA' | 'BINARY' | 'BARRIER' | 'UNKNOWN';
 underlyingSymbol?: string;
 underlyingCusip?: string;
 deliverable?: TransactionInstrument;
}

export interface Product {
 assetType: 'EQUITY' | 'OPTION' | 'INDEX' | 'MUTUAL_FUND' | 'CASH_EQUIVALENT' | 'FIXED_INCOME' | 'CURRENCY' | 'COLLECTIVE_INVESTMENT';
 /** String representing CUSIP of instrument for which to fetch data. Note leading zeroes must be preserved. */
 cusip?: string;
 /** For ``FUNDAMENTAL`` projection, the symbol for which to get fundamentals. For other projections, a search term. See below for details. */
 symbol?: string;
 description?: string;
 instrumentId?: number;
 netChange?: number;
 type?: 'TBD' | 'UNKNOWN';
}

export interface AccountCashEquivalent {
 assetType: 'EQUITY' | 'OPTION' | 'INDEX' | 'MUTUAL_FUND' | 'CASH_EQUIVALENT' | 'FIXED_INCOME' | 'CURRENCY' | 'COLLECTIVE_INVESTMENT';
 /** String representing CUSIP of instrument for which to fetch data. Note leading zeroes must be preserved. */
 cusip?: string;
 /** For ``FUNDAMENTAL`` projection, the symbol for which to get fundamentals. For other projections, a search term. See below for details. */
 symbol?: string;
 description?: string;
 instrumentId?: number;
 netChange?: number;
 type?: 'SWEEP_VEHICLE' | 'SAVINGS' | 'MONEY_MARKET_FUND' | 'UNKNOWN';
}

export interface AccountEquity {
 assetType: 'EQUITY' | 'OPTION' | 'INDEX' | 'MUTUAL_FUND' | 'CASH_EQUIVALENT' | 'FIXED_INCOME' | 'CURRENCY' | 'COLLECTIVE_INVESTMENT';
 /** String representing CUSIP of instrument for which to fetch data. Note leading zeroes must be preserved. */
 cusip?: string;
 /** For ``FUNDAMENTAL`` projection, the symbol for which to get fundamentals. For other projections, a search term. See below for details. */
 symbol?: string;
 description?: string;
 instrumentId?: number;
 netChange?: number;
}

export interface AccountFixedIncome {
 assetType: 'EQUITY' | 'OPTION' | 'INDEX' | 'MUTUAL_FUND' | 'CASH_EQUIVALENT' | 'FIXED_INCOME' | 'CURRENCY' | 'COLLECTIVE_INVESTMENT';
 /** String representing CUSIP of instrument for which to fetch data. Note leading zeroes must be preserved. */
 cusip?: string;
 /** For ``FUNDAMENTAL`` projection, the symbol for which to get fundamentals. For other projections, a search term. See below for details. */
 symbol?: string;
 description?: string;
 instrumentId?: number;
 netChange?: number;
 maturityDate?: string;
 factor?: number;
 variableRate?: number;
}

export interface AccountMutualFund {
 assetType: 'EQUITY' | 'OPTION' | 'INDEX' | 'MUTUAL_FUND' | 'CASH_EQUIVALENT' | 'FIXED_INCOME' | 'CURRENCY' | 'COLLECTIVE_INVESTMENT';
 /** String representing CUSIP of instrument for which to fetch data. Note leading zeroes must be preserved. */
 cusip?: string;
 /** For ``FUNDAMENTAL`` projection, the symbol for which to get fundamentals. For other projections, a search term. See below for details. */
 symbol?: string;
 description?: string;
 instrumentId?: number;
 netChange?: number;
}

export interface AccountOption {
 assetType: 'EQUITY' | 'OPTION' | 'INDEX' | 'MUTUAL_FUND' | 'CASH_EQUIVALENT' | 'FIXED_INCOME' | 'CURRENCY' | 'COLLECTIVE_INVESTMENT';
 /** String representing CUSIP of instrument for which to fetch data. Note leading zeroes must be preserved. */
 cusip?: string;
 /** For ``FUNDAMENTAL`` projection, the symbol for which to get fundamentals. For other projections, a search term. See below for details. */
 symbol?: string;
 description?: string;
 instrumentId?: number;
 netChange?: number;
 optionDeliverables?: any;
 putCall?: 'PUT' | 'CALL' | 'UNKNOWN';
 optionMultiplier?: number;
 type?: 'VANILLA' | 'BINARY' | 'BARRIER' | 'UNKNOWN';
 underlyingSymbol?: string;
}

export interface AccountAPIOptionDeliverable {
 /** For ``FUNDAMENTAL`` projection, the symbol for which to get fundamentals. For other projections, a search term. See below for details. */
 symbol?: string;
 deliverableUnits?: number;
 apiCurrencyType?: 'USD' | 'CAD' | 'EUR' | 'JPY';
 assetType?: 'EQUITY' | 'MUTUAL_FUND' | 'OPTION' | 'FUTURE' | 'FOREX' | 'INDEX' | 'CASH_EQUIVALENT' | 'FIXED_INCOME' | 'PRODUCT' | 'CURRENCY' | 'COLLECTIVE_INVESTMENT';
}

export interface TransactionAPIOptionDeliverable {
 rootSymbol?: string;
 strikePercent?: number;
 deliverableNumber?: number;
 deliverableUnits?: number;
 deliverable?: TransactionInstrument;
 assetType?: assetType;
}

export type apiOrderStatus = 'AWAITING_PARENT_ORDER' | 'AWAITING_CONDITION' | 'AWAITING_STOP_CONDITION' | 'AWAITING_MANUAL_REVIEW' | 'ACCEPTED' | 'AWAITING_UR_OUT' | 'PENDING_ACTIVATION' | 'QUEUED' | 'WORKING' | 'REJECTED' | 'PENDING_CANCEL' | 'CANCELED' | 'PENDING_REPLACE' | 'REPLACED' | 'FILLED' | 'EXPIRED' | 'NEW' | 'AWAITING_RELEASE_TIME' | 'PENDING_ACKNOWLEDGEMENT' | 'PENDING_RECALL' | 'UNKNOWN';

/** string Enum: [ TRADE, RECEIVE_AND_DELIVER, DIVIDEND_OR_INTEREST, ACH_RECEIPT, ACH_DISBURSEMENT, CASH_RECEIPT, CASH_DISBURSEMENT, ELECTRONIC_FUND, WIRE_OUT, WIRE_IN, JOURNAL, MEMORANDUM, MARGIN_CALL, MONEY_MARKET, SMA_ADJUSTMENT ] */
export type TransactionType = 'TRADE' | 'RECEIVE_AND_DELIVER' | 'DIVIDEND_OR_INTEREST' | 'ACH_RECEIPT' | 'ACH_DISBURSEMENT' | 'CASH_RECEIPT' | 'CASH_DISBURSEMENT' | 'ELECTRONIC_FUND' | 'WIRE_OUT' | 'WIRE_IN' | 'JOURNAL' | 'MEMORANDUM' | 'MARGIN_CALL' | 'MONEY_MARKET' | 'SMA_ADJUSTMENT';

export interface Transaction {
 activityId?: number;
 time?: string;
 user?: UserDetails;
 description?: string;
 accountNumber?: string;
 type?: TransactionType;
 /** Restrict query to orders with this status. See :class:`Order.Status` for options. */
 status?: 'VALID' | 'INVALID' | 'PENDING' | 'UNKNOWN';
 subAccount?: 'CASH' | 'MARGIN' | 'SHORT' | 'DIV' | 'INCOME' | 'UNKNOWN';
 tradeDate?: string;
 settlementDate?: string;
 positionId?: number;
 orderId?: number;
 netAmount?: number;
 activityType?: 'ACTIVITY_CORRECTION' | 'EXECUTION' | 'ORDER_ACTION' | 'TRANSFER' | 'UNKNOWN';
 transferItems?: TransferItem[];
}

export interface UserDetails {
 cdDomainId?: string;
 login?: string;
 type?: 'ADVISOR_USER' | 'BROKER_USER' | 'CLIENT_USER' | 'SYSTEM_USER' | 'UNKNOWN';
 userId?: number;
 systemUserName?: string;
 firstName?: string;
 lastName?: string;
 brokerRepCode?: string;
}

export interface TransferItem {
 instrument?: TransactionInstrument;
 amount?: number;
 cost?: number;
 price?: number;
 feeType?: 'COMMISSION' | 'SEC_FEE' | 'STR_FEE' | 'R_FEE' | 'CDSC_FEE' | 'OPT_REG_FEE' | 'ADDITIONAL_FEE' | 'MISCELLANEOUS_FEE' | 'FUTURES_EXCHANGE_FEE' | 'LOW_PROCEEDS_COMMISSION' | 'BASE_CHARGE' | 'GENERAL_CHARGE' | 'GST_FEE' | 'TAF_FEE' | 'INDEX_OPTION_FEE' | 'UNKNOWN';
 positionEffect?: 'OPENING' | 'CLOSING' | 'AUTOMATIC' | 'UNKNOWN';
}

export interface UserPreference {
 accounts?: UserPreferenceAccount[];
 streamerInfo?: StreamerInfo[];
 offers?: Offer[];
}

export interface UserPreferenceAccount {
 accountNumber?: string;
 primaryAccount?: boolean;
 type?: string;
 nickName?: string;
 accountColor?: string;
 displayAcctId?: string;
 autoPositionEffect?: boolean;
}

export interface StreamerInfo {
 streamerSocketUrl?: string;
 schwabClientCustomerId?: string;
 schwabClientCorrelId?: string;
 schwabClientChannel?: string;
 schwabClientFunctionId?: string;
}

export interface Offer {
 level2Permissions?: boolean;
 mktDataPermission?: string;
}
```
