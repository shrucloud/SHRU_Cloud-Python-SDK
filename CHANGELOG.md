# Changelog

All notable changes to this project are documented here.

## [1.0.0]

Initial public release.

- `Client`: `account_info()`, `sync_services()`, `sync_catalog()`, `place_order()`, `check_status()`, plus the low-level `request()`.
- `ShruError`: one error type for every failed call, with `status`, `response` and `is_auth_error()`.
- The client finds the SHRU endpoint itself on first use: the domain + `/api/shru`, then the address exactly as given, then the address as given + `/api/shru`. `endpoint()` returns the one in use; orders are only ever sent there. Safe to share between threads.
- Plain HTTP is refused by default; redirects are never followed; TLS 1.2 or newer; every request has a time limit.
- `sign()` exported for anyone implementing the protocol elsewhere.
- Fully typed (`py.typed`, `TypedDict` replies).
- No dependencies: Python's standard library only.
