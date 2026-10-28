"""The one error type the SHRU Cloud client raises for a failed call."""

from __future__ import annotations

from typing import Any, Dict, Optional

__all__ = ["ShruError"]


class ShruError(Exception):
    """A failed call: a connection problem (status 0), a reply that is not
    JSON, an authentication refusal (401/403) or a normal API rejection
    (insufficient balance, ...). str(error) is the server's own message
    whenever it sent one."""

    def __init__(self, message: str, status: int = 0, response: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        #: The HTTP status the server answered with, or 0 when it was never reached.
        self.status = status
        #: The full decoded JSON reply, when there is one.
        self.response = response

    def is_auth_error(self) -> bool:
        """True for 401/403: a wrong Key ID or Secret, or a caller IP not on the key's allowlist."""
        return self.status in (401, 403)
