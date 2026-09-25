# Command Gauge

A Home Assistant custom integration for [CommandCode](https://commandcode.ai/).

It provides the same practical gauge workflow as `ha-go-gauge`, but uses CommandCode's cloud API as its data source.

## Features

- Separate config entries for multiple CommandCode accounts
- Monthly, purchased, free, and remaining credits
- 5-hour and weekly rolling usage windows
- Reset timestamps, time remaining, remaining percentage, pace, forecast, and burn rate
- Aggregate cost, request, and token counts
- Subscription status and plan
- Dynamic model catalog exposed as one sensor with JSON attributes
- Connectivity, subscription, credit-threshold, and limit-exceeded binary sensors
- Configurable polling, thresholds, and live settings
- Manual refresh button
- Diagnostics redact the API key to an 8-character SHA-256 fingerprint

## Installation

1. Add this repository to HACS as a custom integration repository.
2. Search for **Command Gauge** in HACS and install it.
3. Restart Home Assistant.
4. Add the integration under **Settings → Devices & Services → Add Integration → Command Gauge**.
5. Enter an account label and a CommandCode API key.

> The CommandCode usage endpoints used by this integration are currently alpha/undocumented. The base URL can be overridden in the config flow. The integration treats missing and malformed data as unavailable instead of publishing it as zero.

## Data endpoints

The client currently uses these CommandCode paths:

- `GET /alpha/whoami`
- `GET /alpha/billing/credits`
- `GET /alpha/billing/subscriptions`
- `GET /alpha/usage/summary`
- `GET /provider/v1/models`

The API key is sent as a Bearer token. It is never written to logs, entity attributes, diagnostics, or repository files.

## Development

```bash
python3 -m pytest
ruff check .
```

The first implementation is intentionally defensive around the alpha API schema. A future release can add stricter schema validation once CommandCode publishes a stable contract.
