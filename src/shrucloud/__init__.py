"""Official Python client for the SHRU Cloud API (S-SERVER).

    from shrucloud import Client, ShruError

    client = Client("https://reseller.example.com", "YOUR_KEY_ID", "YOUR_SECRET")
    services = client.sync_services()
"""

from .client import VERSION, Client, sign
from .errors import ShruError
from .types import AccountInfo, Catalog, OrderStatus, PlacedOrder, Service, ServiceField

__version__ = VERSION

__all__ = [
    "AccountInfo",
    "Catalog",
    "Client",
    "OrderStatus",
    "PlacedOrder",
    "Service",
    "ServiceField",
    "ShruError",
    "VERSION",
    "__version__",
    "sign",
]
