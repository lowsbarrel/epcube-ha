"""Endpoint groups, one per area of the API."""

from .account import AccountEndpoints, PublicEndpoints
from .base import EndpointGroup
from .data import DataEndpoints
from .device import DeviceEndpoints
from .extras import (
    MessageEndpoints,
    SmartBreakerEndpoints,
    SupportEndpoints,
    VppEndpoints,
)

__all__ = [
    "AccountEndpoints",
    "DataEndpoints",
    "DeviceEndpoints",
    "EndpointGroup",
    "MessageEndpoints",
    "PublicEndpoints",
    "SmartBreakerEndpoints",
    "SupportEndpoints",
    "VppEndpoints",
]
