"""The SHRU Cloud API client."""

from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import platform
import ssl
import threading
import time
from typing import Any, Dict, List, Mapping, Optional, Tuple
from urllib.parse import urlsplit

from .errors import ShruError
from .types import AccountInfo, Catalog, OrderStatus, PlacedOrder, Service

__all__ = ["Client", "sign", "VERSION"]

VERSION = "1.0.0"
API_PATH = "/api/shru"
MAX_RESPONSE_BYTES = 10 * 1024 * 1024


def sign(secret: str, timestamp: str, body: str) -> str:
    """The signature the server checks: lowercase hex HMAC-SHA256 of
    "POST\\n/api/shru\\n{timestamp}\\n{raw JSON body}" with your Secret."""
    signable = "POST\n" + API_PATH + "\n" + timestamp + "\n" + body
    return hmac.new(secret.encode("utf-8"), signable.encode("utf-8"), hashlib.sha256).hexdigest()


class _Address:
    """A parsed base URL: its origin (scheme://host[:port]), path and query."""

    def __init__(self, base_url: str) -> None:
        text = str(base_url).strip()
        if "://" not in text:
            text = "https://" + text.lstrip("/")
        try:
            parts = urlsplit(text)
            port = parts.port
        except ValueError:
            raise ValueError('Could not determine a valid host from base URL: "%s"' % base_url) from None
        scheme = parts.scheme.lower()
        if scheme not in ("http", "https"):
            raise ValueError('Unsupported URL scheme "%s" in base URL: "%s"' % (scheme, base_url))
        if not parts.hostname:
            raise ValueError('Could not determine a valid host from base URL: "%s"' % base_url)
        host = parts.hostname
        if ":" in host:
            host = "[" + host + "]"
        default_port = 443 if scheme == "https" else 80
        self.scheme = scheme
        self.origin = scheme + "://" + host + ("" if port in (None, default_port) else ":%d" % port)
        self.path = parts.path
        self.query = parts.query

    def candidates(self) -> List[str]:
        """Where the SHRU endpoint may be, in the order endpoint() tries them,
        without duplicates: the domain + /api/shru, the address exactly as
        given, and the address as given + /api/shru."""
        path = self.path.rstrip("/")
        if path == API_PATH and not self.query:
            return [self.origin + API_PATH]
        if path == "" and not self.query:
            as_given = self.origin + "/"
        else:
            as_given = self.origin + (self.path or "/") + ("?" + self.query if self.query else "")
        found: List[str] = []
        for url in (self.origin + API_PATH, as_given, self.origin + path + API_PATH):
            if url not in found:
                found.append(url)
        return found


class Client:
    """Official Python client for the SHRU Cloud API.

    >>> client = Client("https://reseller.example.com", "YOUR_KEY_ID", "YOUR_SECRET")
    >>> services = client.sync_services()

    :param base_url: The address the platform gave you, usually just its domain
        ("https://reseller.example.com", even "reseller.example.com"), the full
        endpoint (".../api/shru") or any page of the site.
    :param key_id: Your Key ID.
    :param secret: Your Secret. Store it like a database password.
    :param timeout_seconds: Time limit for connecting and for each read (at least 1).
    :param verify_tls: Checks the server's TLS certificate. Turn off only for a local test server.
    :param allow_insecure_http: Allows plain http:// - only for a local test server, never in production.
    """

    def __init__(
        self,
        base_url: str,
        key_id: str,
        secret: str,
        timeout_seconds: float = 15,
        verify_tls: bool = True,
        allow_insecure_http: bool = False,
    ) -> None:
        if not base_url or not key_id or not secret:
            raise ValueError("base_url, key_id and secret are all required.")
        if not isinstance(timeout_seconds, (int, float)) or timeout_seconds < 1:
            raise ValueError("timeout_seconds must be at least 1.")
        address = _Address(base_url)
        if address.scheme != "https" and not allow_insecure_http:
            raise ValueError(
                'Refusing to connect to "%s" over plain HTTP - your Key ID, order details and every reply '
                "would travel unencrypted. Set allow_insecure_http only for a local test server, never in "
                "production." % address.origin
            )
        self._key_id = str(key_id)
        self._secret = str(secret)
        self._timeout = float(timeout_seconds)
        self._candidates = address.candidates()
        self._endpoint: Optional[str] = None
        self._lock = threading.Lock()
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        if not verify_tls:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        self._tls = context
        self._user_agent = "SHRU_Cloud-Python-SDK/%s (Python %s)" % (VERSION, platform.python_version())

    def endpoint(self) -> str:
        """The SHRU endpoint this client talks to. Found on first use by asking
        each candidate for account_info (read-only) until one answers as a SHRU
        Cloud endpoint - a success, or a refusal in SHRU's own format, which
        still proves the address. Kept for the client's lifetime once found.
        Orders are only ever sent to this one endpoint."""
        if self._endpoint is not None:
            return self._endpoint
        if len(self._candidates) == 1:
            self._endpoint = self._candidates[0]
            return self._endpoint
        with self._lock:
            if self._endpoint is not None:
                return self._endpoint
            body = json.dumps({"action": "account_info"}, separators=(",", ":"))
            for url in self._candidates:
                ok, _error, _status, decoded = self._send(url, body)
                if ok and decoded is not None and isinstance(decoded.get("success"), bool):
                    self._endpoint = url
                    return url
        # Nothing answered: use the most likely address for this call, and
        # look again next time instead of keeping a guess.
        return self._candidates[0]

    def account_info(self) -> AccountInfo:
        """Your balance, currency and email: a light credentials check."""
        return self.request("account_info")  # type: ignore[return-value]

    def sync_services(self) -> List[Service]:
        """The services you may order, priced as your account is billed."""
        return self.sync_catalog()["services"]

    def sync_catalog(self) -> Catalog:
        """The same services plus your current balance, in one call."""
        reply = self.request("sync")
        services = reply.get("services")
        return {
            "balance": float(reply.get("balance") or 0),
            "currency": str(reply.get("currency") or "USD"),
            "services": services if isinstance(services, list) else [],
        }

    def place_order(
        self,
        service_id: int,
        input_value: str,
        quantity: int = 1,
        fields: Optional[Mapping[str, str]] = None,
    ) -> PlacedOrder:
        """Places an order. Sending the exact same input, fields and quantity
        again while that order is still queued returns the same order instead
        of a second charge, so a call that timed out is safe to retry.

        :param service_id: An ``id`` from sync_services().
        :param input_value: The service's primary input ("" when it takes none).
        :param quantity: Only used by a "quantity" service.
        :param fields: Extra field values, keyed by each field's ``key``.
        """
        if isinstance(service_id, bool) or not isinstance(service_id, int) or service_id < 1:
            raise TypeError("service_id must be a positive whole number.")
        if not isinstance(input_value, str):
            raise TypeError('input_value must be a string (use "" when the service takes none).')
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
            raise TypeError("quantity must be a positive whole number.")
        if fields is not None and not isinstance(fields, Mapping):
            raise TypeError("fields must be a mapping of field key to value.")
        return self.request(  # type: ignore[return-value]
            "submit_order",
            {"service_id": service_id, "input": input_value, "quantity": quantity, "fields": dict(fields or {})},
        )

    def check_status(self, order_id: int) -> OrderStatus:
        """Status and (once finished) result of an order placed with this key.
        status is one of: queued, processing, completed, rejected, refunded."""
        if isinstance(order_id, bool) or not isinstance(order_id, int) or order_id < 1:
            raise TypeError("order_id must be a positive whole number.")
        return self.request("check_status", {"order_id": order_id})  # type: ignore[return-value]

    def request(self, action: str, params: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        """Calls any action by name and returns the decoded reply ("success"
        included) - for an action a platform added after this SDK's release."""
        payload: Dict[str, Any] = {"action": action}
        payload.update(params or {})
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        ok, error, status, decoded = self._send(self.endpoint(), body)
        if not ok:
            raise ShruError("Connection to SHRU Cloud failed: " + error, 0, None)
        if decoded is None:
            raise ShruError("SHRU Cloud returned a non-JSON response (HTTP %d)" % status, status, None)
        if not decoded.get("success"):
            message = decoded.get("message")
            raise ShruError(
                message if isinstance(message, str) and message else "SHRU Cloud rejected the request",
                status,
                decoded,
            )
        return decoded

    def _send(self, url: str, body: str) -> Tuple[bool, str, int, Optional[Dict[str, Any]]]:
        """One signed POST. Never raises: answers (ok, error, status, decoded)
        for request() and endpoint() to judge. Redirects are never followed -
        a signed request has exactly one valid destination."""
        target = urlsplit(url)
        timestamp = str(int(time.time()))
        data = body.encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": self._user_agent,
            "X-Key-Id": self._key_id,
            "X-Timestamp": timestamp,
            "X-Signature": sign(self._secret, timestamp, body),
        }
        path = (target.path or "/") + ("?" + target.query if target.query else "")
        host = target.hostname or ""
        if target.scheme == "https":
            conn: http.client.HTTPConnection = http.client.HTTPSConnection(
                host, target.port, timeout=self._timeout, context=self._tls
            )
        else:
            conn = http.client.HTTPConnection(host, target.port, timeout=self._timeout)
        try:
            conn.request("POST", path, body=data, headers=headers)
            response = conn.getresponse()
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                return False, "the reply is larger than 10 MB", 0, None
            status = response.status
        except (OSError, http.client.HTTPException) as e:
            return False, str(e) or e.__class__.__name__, 0, None
        finally:
            conn.close()
        parsed: Any
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except ValueError:
            parsed = None
        decoded: Optional[Dict[str, Any]] = parsed if isinstance(parsed, dict) else None
        return True, "", status, decoded
