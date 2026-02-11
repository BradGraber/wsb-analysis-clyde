# Schwab Market Data API

**Version:** 1.0.0 (OAS3)
**Base URL:** `https://api.schwabapi.com/marketdata/v1`
**Auth:** `Authorization: Bearer {access_token}`

---

## Endpoints

| # | Method | Path | Description |
|---|--------|------|-------------|
| 1 | GET | /quotes | Get quotes by list of symbols |
| 2 | GET | /{symbol_id}/quotes | Get quote by single symbol |
| 3 | GET | /chains | Get option chain for an optionable symbol |
| 4 | GET | /expirationchain | Get option expiration chain |
| 5 | GET | /pricehistory | Get price history for a single symbol |
| 6 | GET | /movers/{symbol_id} | Get movers for a specific index |
| 7 | GET | /markets | Get market hours for multiple markets |
| 8 | GET | /markets/{market_id} | Get market hours for a single market |
| 9 | GET | /instruments | Get instruments by symbol/projection |
| 10 | GET | /instruments/{cusip_id} | Get instrument by CUSIP |

---

## Common Response Headers

| Header | Type | Description |
|--------|------|-------------|
| Schwab-Client-CorrelId | string (UUID) | Individual request identifier |
| Schwab-Resource-Version | string | API version |

## Common Error Responses

| Code | Description |
|------|-------------|
| 400 | Bad Request — missing header, invalid search combination, invalid fields |
| 401 | Unauthorized |
| 404 | Not Found (single-resource endpoints only) |
| 500 | Internal Server Error |

---

## 1. GET /quotes

Get quotes by list of symbols. Supports equities, options, indices, mutual funds, futures, and forex.

### Parameters

| Name | Type | In | Required | Description |
|------|------|-----|----------|-------------|
| symbols | string | query | No | Comma-separated list of symbols. Example: `AAPL,BAC,$DJI,$SPX,AMZN 230317C01360000,/ESH23,AUD/CAD` |
| fields | string | query | No | Comma-separated root nodes: `quote`, `fundamental`, `extended`, `reference`, `regular`. Default: `all` |
| indicative | boolean | query | No | Include indicative quotes for ETF symbols (e.g. `$ABC.IV`). Default: `false` |

### Response 200

Map keyed by symbol. Each entry varies by `assetMainType`. See [Response Schemas](#response-schemas) for full field lists.

```json
{
  "AAPL": {
    "assetMainType": "EQUITY",
    "symbol": "AAPL",
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
      "closePrice": 177.57,
      "highPrice": 169,
      "lastPrice": 168.405,
      "lastSize": 200,
      "lowPrice": 167.09,
      "mark": 168.405,
      "markChange": -9.165,
      "markPercentChange": -5.161,
      "netChange": -9.165,
      "netPercentChange": -5.161,
      "openPrice": 167.37,
      "securityStatus": "Normal",
      "totalVolume": 22361159,
      "volatility": 0.0347
    },
    "regular": {
      "regularMarketLastPrice": 168.405,
      "regularMarketLastSize": 2,
      "regularMarketNetChange": -9.165,
      "regularMarketPercentChange": -5.161,
      "regularMarketTradeTime": 1644854683408
    },
    "fundamental": {
      "avg10DaysVolume": 1,
      "avg1YearVolume": 0,
      "divAmount": 1.1,
      "divYield": 1.1,
      "eps": 0,
      "peRatio": 1.1
    }
  }
}
```

---

## 2. GET /{symbol_id}/quotes

Get quote for a single symbol.

### Parameters

| Name | Type | In | Required | Description |
|------|------|-----|----------|-------------|
| symbol_id | string | path | **Yes** | Symbol of instrument. Example: `TSLA` |
| fields | string | query | No | Comma-separated root nodes: `quote`, `fundamental`, `extended`, `reference`, `regular`. Default: `all` |

### Response 200

Same schema as GET /quotes for a single symbol.

---

## 3. GET /chains

Get option chain for an optionable symbol, including information on options contracts associated with each expiration.

### Parameters

| Name | Type | In | Required | Description |
|------|------|-----|----------|-------------|
| symbol | string | query | **Yes** | Single symbol. Example: `AAPL` |
| contractType | string | query | No | `CALL`, `PUT`, `ALL` |
| strikeCount | integer | query | No | Number of strikes above/below ATM |
| includeUnderlyingQuote | boolean | query | No | Include underlying quote |
| strategy | string | query | No | Default: `SINGLE`. Values: `SINGLE`, `ANALYTICAL`, `COVERED`, `VERTICAL`, `CALENDAR`, `STRANGLE`, `STRADDLE`, `BUTTERFLY`, `CONDOR`, `DIAGONAL`, `COLLAR`, `ROLL`. `ANALYTICAL` enables volatility/underlyingPrice/interestRate/daysToExpiration params. |
| interval | number(double) | query | No | Strike interval for spread strategy chains |
| strike | number(double) | query | No | Strike price |
| range | string | query | No | Range: ITM, NTM, OTM, etc. |
| fromDate | string(date) | query | No | Format: `yyyy-MM-dd` |
| toDate | string(date) | query | No | Format: `yyyy-MM-dd` |
| volatility | number(double) | query | No | For ANALYTICAL strategy only |
| underlyingPrice | number(double) | query | No | For ANALYTICAL strategy only |
| interestRate | number(double) | query | No | For ANALYTICAL strategy only |
| daysToExpiration | integer(int32) | query | No | For ANALYTICAL strategy only |
| expMonth | string | query | No | `JAN`, `FEB`, `MAR`, `APR`, `MAY`, `JUN`, `JUL`, `AUG`, `SEP`, `OCT`, `NOV`, `DEC`, `ALL` |
| optionType | string | query | No | Option type filter |
| entitlement | string | query | No | Retail token entitlement: `PN` (NonPayingPro), `NP` (NonPro), `PP` (PayingPro) |

### Response 200

```json
{
  "symbol": "string",
  "status": "string",
  "underlying": {
    "ask": 0, "askSize": 0, "bid": 0, "bidSize": 0,
    "change": 0, "close": 0, "delayed": true,
    "description": "string", "exchangeName": "IND",
    "fiftyTwoWeekHigh": 0, "fiftyTwoWeekLow": 0,
    "highPrice": 0, "last": 0, "lowPrice": 0,
    "mark": 0, "markChange": 0, "markPercentChange": 0,
    "openPrice": 0, "percentChange": 0,
    "quoteTime": 0, "symbol": "string",
    "totalVolume": 0, "tradeTime": 0
  },
  "strategy": "SINGLE",
  "interval": 0,
  "isDelayed": true,
  "isIndex": true,
  "daysToExpiration": 0,
  "interestRate": 0,
  "underlyingPrice": 0,
  "volatility": 0,
  "callExpDateMap": {
    "<expDate>": {
      "<strike>": [OptionContract]
    }
  },
  "putExpDateMap": {
    "<expDate>": {
      "<strike>": [OptionContract]
    }
  }
}
```

#### OptionContract Schema

```json
{
  "putCall": "PUT|CALL",
  "symbol": "string",
  "description": "string",
  "exchangeName": "string",
  "bidPrice": 0,
  "askPrice": 0,
  "lastPrice": 0,
  "markPrice": 0,
  "bidSize": 0,
  "askSize": 0,
  "lastSize": 0,
  "highPrice": 0,
  "lowPrice": 0,
  "openPrice": 0,
  "closePrice": 0,
  "totalVolume": 0,
  "tradeDate": 0,
  "quoteTimeInLong": 0,
  "tradeTimeInLong": 0,
  "netChange": 0,
  "volatility": 0,
  "delta": 0,
  "gamma": 0,
  "theta": 0,
  "vega": 0,
  "rho": 0,
  "timeValue": 0,
  "openInterest": 0,
  "isInTheMoney": true,
  "theoreticalOptionValue": 0,
  "theoreticalVolatility": 0,
  "isMini": true,
  "isNonStandard": true,
  "optionDeliverablesList": [
    {
      "symbol": "string",
      "assetType": "string",
      "deliverableUnits": "string",
      "currencyType": "string"
    }
  ],
  "strikePrice": 0,
  "expirationDate": "string",
  "daysToExpiration": 0,
  "expirationType": "M",
  "lastTradingDay": 0,
  "multiplier": 0,
  "settlementType": "A",
  "deliverableNote": "string",
  "isIndexOption": true,
  "percentChange": 0,
  "markChange": 0,
  "markPercentChange": 0,
  "isPennyPilot": true,
  "intrinsicValue": 0,
  "optionRoot": "string"
}
```

---

## 4. GET /expirationchain

Get option expiration (series) information for an optionable symbol. Does not include individual options contracts.

### Parameters

| Name | Type | In | Required | Description |
|------|------|-----|----------|-------------|
| symbol | string | query | **Yes** | Single symbol. Example: `AAPL` |

### Response 200

```json
{
  "expirationList": [
    {
      "expirationDate": "2022-01-07",
      "daysToExpiration": 2,
      "expirationType": "W",
      "standard": true
    }
  ]
}
```

**expirationType values:** `W` (weekly), `S` (standard/monthly)

---

## 5. GET /pricehistory

Get historical OHLCV for a single symbol. Frequency available is dependent on periodType.

### Parameters

| Name | Type | In | Required | Description |
|------|------|-----|----------|-------------|
| symbol | string | query | **Yes** | Equity symbol. Example: `AAPL` |
| periodType | string | query | No | `day`, `month`, `year`, `ytd` |
| period | integer(int32) | query | No | Number of periods. See valid values below. |
| frequencyType | string | query | No | `minute`, `daily`, `weekly`, `monthly`. See valid values below. |
| frequency | integer(int32) | query | No | Frequency duration. See valid values below. Default: `1` |
| startDate | integer(int64) | query | No | Epoch milliseconds. If omitted: endDate - period (excluding weekends/holidays) |
| endDate | integer(int64) | query | No | Epoch milliseconds. If omitted: previous business day market close |
| needExtendedHoursData | boolean | query | No | Include extended hours data |
| needPreviousClose | boolean | query | No | Include previous close price/date |

#### Period/Frequency Valid Combinations

| periodType | Valid period values | Default period | Valid frequencyType | Default frequencyType |
|------------|-------------------|----------------|--------------------|-----------------------|
| day | 1, 2, 3, 4, 5, 10 | 10 | minute | minute |
| month | 1, 2, 3, 6 | 1 | daily, weekly | weekly |
| year | 1, 2, 3, 5, 10, 15, 20 | 1 | daily, weekly, monthly | monthly |
| ytd | 1 | 1 | daily, weekly | weekly |

| frequencyType | Valid frequency values |
|---------------|-----------------------|
| minute | 1, 5, 10, 15, 30 |
| daily | 1 |
| weekly | 1 |
| monthly | 1 |

### Response 200

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

> **Note:** `datetime` is in epoch milliseconds.

---

## 6. GET /movers/{symbol_id}

Get top 10 movers for a specific index.

### Parameters

| Name | Type | In | Required | Description |
|------|------|-----|----------|-------------|
| symbol_id | string | path | **Yes** | Index symbol: `$DJI`, `$COMPX`, `$SPX`, `NYSE`, `NASDAQ`, `OTCBB`, `INDEX_ALL`, `EQUITY_ALL`, `OPTION_ALL`, `OPTION_PUT`, `OPTION_CALL` |
| sort | string | query | No | `VOLUME`, `TRADES`, `PERCENT_CHANGE_UP`, `PERCENT_CHANGE_DOWN` |
| frequency | integer(int32) | query | No | Values: `0`, `1`, `5`, `10`, `30`, `60`. Default: `0` |

### Response 200

```json
{
  "screeners": [
    {
      "change": 10,
      "description": "Dow jones",
      "direction": "up",
      "last": 100,
      "symbol": "$DJI",
      "totalVolume": 100
    }
  ]
}
```

---

## 7. GET /markets

Get market hours for dates in the future across multiple markets.

### Parameters

| Name | Type | In | Required | Description |
|------|------|-----|----------|-------------|
| markets | array[string] | query | **Yes** | `equity`, `option`, `bond`, `future`, `forex` |
| date | string(date) | query | No | Format: `YYYY-MM-DD`. Range: today to 1 year out. Default: current day. |

### Response 200

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
          { "start": "2022-04-14T07:00:00-04:00", "end": "2022-04-14T09:30:00-04:00" }
        ],
        "regularMarket": [
          { "start": "2022-04-14T09:30:00-04:00", "end": "2022-04-14T16:00:00-04:00" }
        ],
        "postMarket": [
          { "start": "2022-04-14T16:00:00-04:00", "end": "2022-04-14T20:00:00-04:00" }
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
          { "start": "2022-04-14T09:30:00-04:00", "end": "2022-04-14T16:00:00-04:00" }
        ]
      }
    },
    "IND": {
      "date": "2022-04-14",
      "marketType": "OPTION",
      "product": "IND",
      "productName": "index option",
      "isOpen": true,
      "sessionHours": {
        "regularMarket": [
          { "start": "2022-04-14T09:30:00-04:00", "end": "2022-04-14T16:15:00-04:00" }
        ]
      }
    }
  }
}
```

---

## 8. GET /markets/{market_id}

Get market hours for a single market.

### Parameters

| Name | Type | In | Required | Description |
|------|------|-----|----------|-------------|
| market_id | string | path | **Yes** | `equity`, `option`, `bond`, `future`, `forex` |
| date | string(date) | query | No | Format: `YYYY-MM-DD`. Range: today to 1 year out. Default: current day. |

### Response 200

Same schema as GET /markets, scoped to the single requested market.

---

## 9. GET /instruments

Get instruments by symbols and projections. Use `fundamental` projection for detailed fundamental data.

### Parameters

| Name | Type | In | Required | Description |
|------|------|-----|----------|-------------|
| symbol | string | query | **Yes** | Symbol of a security |
| projection | string | query | **Yes** | `symbol-search`, `symbol-regex`, `desc-search`, `desc-regex`, `search`, `fundamental` |

### Response 200

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

---

## 10. GET /instruments/{cusip_id}

Get basic instrument details by CUSIP.

### Parameters

| Name | Type | In | Required | Description |
|------|------|-----|----------|-------------|
| cusip_id | string | path | **Yes** | CUSIP of a security |

### Response 200

```json
{
  "cusip": "037833100",
  "symbol": "AAPL",
  "description": "Apple Inc",
  "exchange": "NASDAQ",
  "assetType": "EQUITY"
}
```

---

## Response Schemas

### Quote Types by assetMainType

The GET /quotes and GET /{symbol_id}/quotes responses vary by asset type. Each includes a subset of: `reference`, `quote`, `regular`, `fundamental`, `extended`.

#### EQUITY

- **reference:** cusip, description, exchange, exchangeName, otcMarketTier
- **quote:** 52WeekHigh/Low, askPrice/Size/Time, askMICId, bidPrice/Size/Time, bidMICId, closePrice, highPrice, lastPrice/Size, lastMICId, lowPrice, mark, markChange, markPercentChange, netChange, netPercentChange, openPrice, quoteTime, securityStatus, totalVolume, tradeTime, volatility
- **regular:** regularMarketLastPrice, regularMarketLastSize, regularMarketNetChange, regularMarketPercentChange, regularMarketTradeTime
- **fundamental:** avg10DaysVolume, avg1YearVolume, declarationDate, divAmount, divExDate, divFreq, divPayAmount, divPayDate, divYield, eps, fundLeverageFactor, fundStrategy, nextDivExDate, nextDivPayDate, peRatio

#### OPTION

- **reference:** contractType (C/P), daysToExpiration, description, exchange, exchangeName, expirationDay/Month/Year, isPennyPilot, lastTradingDay, multiplier, settlementType, strikePrice, underlying, uvExpirationType
- **quote:** askPrice/Size, bidPrice/Size, closePrice, delta, gamma, theta, vega, rho, highPrice, impliedYield, lastPrice/Size, lowPrice, mark, markChange, markPercentChange, moneyIntrinsicValue, netChange, netPercentChange, openInterest, openPrice, quoteTime, securityStatus, theoreticalOptionValue, timeValue, totalVolume, tradeTime, underlyingPrice, volatility

#### INDEX

- **reference:** description, exchange, exchangeName
- **quote:** 52WeekHigh/Low, closePrice, highPrice, lastPrice, lowPrice, netChange, netPercentChange, openPrice, securityStatus, totalVolume, tradeTime

#### MUTUAL_FUND

- **reference:** cusip, description, exchange, exchangeName
- **quote:** 52WeekHigh/Low, closePrice, nAV, netChange, netPercentChange, securityStatus, totalVolume, tradeTime
- **fundamental:** avg10DaysVolume, avg1YearVolume, divAmount, divFreq, divPayAmount, divYield, eps, fundLeverageFactor, peRatio

#### FUTURE

- **reference:** description, exchange, exchangeName, futureActiveSymbol, futureExpirationDate, futureIsActive, futureIsTradable, futureMultiplier, futurePriceFormat, futureSettlementPrice, futureTradingHours, product
- **quote:** askPrice/Size, bidPrice/Size, closePrice, futurePercentChange, highPrice, lastPrice/Size, lowPrice, mark, netChange, openInterest, openPrice, quoteTime, securityStatus, settleTime, tick, tickAmount, totalVolume, tradeTime

#### FOREX

- **reference:** description, exchange, exchangeName, isTradable, marketMaker, product, tradingHours
- **quote:** 52WeekHigh/Low, askPrice/Size, bidPrice/Size, closePrice, highPrice, lastPrice/Size, lowPrice, mark, netChange, netPercentChange, openPrice, quoteTime, securityStatus, tick, tickAmount, totalVolume, tradeTime

### Enums

| Enum | Values |
|------|--------|
| AssetMainType | BOND, EQUITY, ETF, EXTENDED, FOREX, FUTURE, FUTURE_OPTION, FUNDAMENTAL, INDEX, INDICATOR, MUTUAL_FUND, OPTION, UNKNOWN |
| ContractType | CALL, PUT, ALL |
| SettlementType | A, P |
| ExpirationType | M, W, S |
| QuoteType | NBBO |
| DivFreq | 0, 1, 2, 4, 6, 12 |
| FundStrategy | A, P |
| ExerciseType | A (American), E (European) |
