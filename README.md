# SHRU_Cloud-Python-SDK

[![Tests](https://github.com/shrucloud/SHRU_Cloud-Python-SDK/actions/workflows/test.yml/badge.svg)](https://github.com/shrucloud/SHRU_Cloud-Python-SDK/actions/workflows/test.yml)

Official Python client for the **SHRU Cloud** API (S-SERVER) - one dependency-free class that syncs a supplier's catalog, places orders and checks their status over the HMAC-signed SHRU protocol. Fully typed.

Part of the SHRU Cloud SDK family, with the same calls and the same safety rules in every language: [PHP](https://github.com/shrucloud/SHRU_Cloud-PHP-SDK) · [Node.js](https://github.com/shrucloud/SHRU_Cloud-Node-SDK) · **Python** · [.NET](https://github.com/shrucloud/SHRU_Cloud-DotNet-SDK).

**Contents:** [Requirements](#requirements) · [Install](#install) · [Quickstart](#quickstart) · [The base URL](#the-base-url) · [Getting your credentials](#getting-your-credentials) · [API reference](#api-reference) · [Error handling](#error-handling) · [Protocol reference](#protocol-reference) · [Security](#security)

## Requirements

- Python 3.9 or newer. **Recommended: Python 3.13 or newer.**
- No dependencies: Python's standard library only.

## Install

Straight from this repository:

```bash
pip install "shrucloud @ git+https://github.com/shrucloud/SHRU_Cloud-Python-SDK@v1.0.0"
```

## Quickstart

```python
from shrucloud import Client, ShruError

client = Client("https://reseller.example.com", "YOUR_KEY_ID", "YOUR_SECRET")

try:
    services = client.sync_services()
    order = client.place_order(services[0]["id"], "356789101234567")
    status = client.check_status(order["order_id"])
    print(status["status"], status["reply"])
except ShruError as error:
    print(error)
```

Runnable scripts are in [`examples/`](examples/): `sync_services.py`, `place_order.py`, `check_status.py`.

## The base URL

The first argument is the address the platform gave you, usually just its domain. Any of these work:

```
https://reseller.example.com/
https://reseller.example.com
reseller.example.com
https://reseller.example.com/api/shru
https://reseller.example.com/any/page/of/the/site
```

On first use the client finds the SHRU endpoint itself, trying in this order:

1. the domain + `/api/shru` (where every SHRU Cloud platform has it)
2. the address exactly as given
3. the address as given + `/api/shru`

It asks each one for `account_info`, a read-only call, and uses the first that answers as a SHRU endpoint, including a refusal in SHRU's own format (a wrong key, an IP not allowed), since that still proves the address is right. The endpoint found is kept for the client's lifetime; `client.endpoint()` returns it. Orders are only ever sent to that one endpoint, never retried at another address. Passing the full `https://reseller.example.com/api/shru` skips the check entirely. One client can be shared between threads.

## Getting your credentials

Every SHRU Cloud platform issues credentials from its own admin panel: Reseller API Keys -> your account -> **SHRU** tab -> Enable SHRU Access (on [SHRU_Cloud-Provider-Starter](https://github.com/shrucloud/SHRU_Cloud-Provider-Starter), that's Credentials -> New Credential):

| | |
|---|---|
| **Key ID** | Identifies your account, sent on every request. |
| **Secret** | Shown once, at creation/regeneration time only. Store it like a database password. |
| **Allowed IPs** | The platform rejects every request from an IP not on this list. Get the IP(s) your integration actually calls from added *before* your first request, or you'll get a 403. |

## API reference

```python
Client(
    base_url,
    key_id,
    secret,
    timeout_seconds=15,         # at least 1
    verify_tls=True,            # turn off only for a local test server
    allow_insecure_http=False,  # plain http:// only for a local test server
)
```

### `account_info()`

```python
{"success": True, "balance": float, "currency": str, "email": str}
```

A lightweight credentials/connectivity check - useful before doing anything else.

### `sync_services()` / `sync_catalog()`

The full catalog of services you're allowed to order, priced exactly as your account is billed (any tier pricing already applied server-side - never compute or cache pricing yourself). `sync_catalog()` returns `{"balance", "currency", "services"}` in one call. Each service:

```python
{
    "id": int,
    "name": str,
    "group": str,
    "type": "fixed" | "quantity",
    "price": float,
    "delivery": str,                       # eg. "Instant", "1-24h"
    "input_label": str | None,             # None when this service takes no primary input
    "input_required": bool,
    "quantity": {"min": int, "max": int} | None,  # only for type "quantity"
    "bulk": bool,                          # only ever True for type "fixed"
    "fields": [{"label", "key", "type": "input" | "textarea", "required"}],
}
```

Never assume `input_label` means "IMEI" - it's whatever this specific service actually asks for (SN, ECID, an account ID, ...). Each `fields[]` entry's `key` is exactly the name to use for it in `place_order()`'s `fields`, not necessarily the same string as its `label`.

### `place_order(service_id, input_value, quantity=1, fields=None)`

```python
{"success": True, "order_id": int, "status": str}
```

- `input_value` - the service's primary input (eg. an IMEI/serial). Pass `""` for a service whose `input_label` is `None`.
- `quantity` - only meaningful for a `type: "quantity"` service.
- `fields` - extra field values, keyed by each field's `key` from `sync_services()`.
- `bulk: True` means the service accepts several independent inputs - call `place_order()` once per value.

Re-submitting the exact same input, fields and quantity for a service you already have a still-queued order for returns that same order instead of creating (and billing) a duplicate - safe to retry after a network timeout without checking first. This applies to orders that carry an input or field values; an order with neither is always a new order. The exact same signed request sent twice within one second is refused with HTTP 409.

### `check_status(order_id)`

```python
{"success": True, "order_id": int, "status": str, "reply": str}
```

`status` is one of `queued`, `processing`, `completed`, `rejected`, `refunded`. `reply` is always plain text and is `""` until the order finishes.

### `request(action, params=None)`

Calls any action by name and returns the decoded reply (`success` included) - for an action a platform has added since this SDK's release, without waiting on a new version.

## Error handling

Every failed call - transport (network error, invalid JSON), auth (bad/expired signature, IP not allowlisted) or a normal API rejection (insufficient balance, service not found, ...) - raises a single `ShruError`:

```python
try:
    client.place_order(service_id, input_value)
except ShruError as error:
    str(error)              # the server's own "message", almost always safe to show a user directly
    error.status            # the HTTP status the server returned (0 = never reached the server)
    error.is_auth_error()   # True for 401/403 - bad Key ID/Secret, or your IP isn't allowlisted
    error.response          # the full decoded JSON body, when one exists
```

Wrong argument types (a non-integer service ID, ...) raise `TypeError` before anything is sent.

## Protocol reference

- **Endpoint** - `POST {domain}/api/shru`, JSON body, one `action` per request.
- **Headers** - `X-Key-Id`, `X-Timestamp` (Unix epoch seconds), `X-Signature`.
- **Actions** - `account_info`, `sync`, `submit_order`, `check_status`.
- **Response envelope** - always `{"success": true, ...}` or `{"success": false, "message": "..."}`.

**Signing algorithm** (also exported as `sign(secret, timestamp, body)`):

```
signable  = "POST\n/api/shru\n{timestamp}\n{raw JSON request body}"
signature = lowercase hex HMAC-SHA256(signable, your secret)
```

Servers reject a timestamp more than 5 minutes old; a rejected signature almost always means clock drift (NTP).

## Security

- Plain HTTP is refused by default - the constructor raises before any request is sent. Set `allow_insecure_http` only for a local test server, never in production.
- Redirects are never followed - a signed request has exactly one valid destination.
- TLS 1.2 or newer only. Every request has a time limit, and a reply larger than 10 MB is refused.
- Treat your Secret like a database password: never commit it, never log it, and regenerate it immediately if you suspect it leaked.

## License

MIT - see [LICENSE](LICENSE).
