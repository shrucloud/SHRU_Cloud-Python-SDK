"""The shapes the SHRU Cloud API answers with, for type checkers and editors."""

from typing import List, Literal, Optional, TypedDict

__all__ = ["AccountInfo", "Catalog", "OrderStatus", "PlacedOrder", "QuantityRange", "Service", "ServiceField"]

OrderStatusName = Literal["queued", "processing", "completed", "rejected", "refunded"]


class AccountInfo(TypedDict):
    success: bool
    balance: float
    currency: str
    email: str


class ServiceField(TypedDict):
    label: str
    #: The name to use for this field in place_order()'s ``fields``.
    key: str
    type: Literal["input", "textarea"]
    required: bool


class QuantityRange(TypedDict):
    min: int
    max: int


class Service(TypedDict):
    id: int
    name: str
    group: str
    type: Literal["fixed", "quantity"]
    price: float
    delivery: str
    #: None when the service takes no primary input.
    input_label: Optional[str]
    input_required: bool
    #: Only for type "quantity".
    quantity: Optional[QuantityRange]
    #: Only ever true for type "fixed": call place_order() once per value.
    bulk: bool
    fields: List[ServiceField]


class Catalog(TypedDict):
    balance: float
    currency: str
    services: List[Service]


class PlacedOrder(TypedDict):
    success: bool
    order_id: int
    status: OrderStatusName


class OrderStatus(TypedDict):
    success: bool
    order_id: int
    status: OrderStatusName
    #: Plain text; "" until the order finishes.
    reply: str
