"""Driver registry."""

from .base import Driver
from .mock import MockDriver

__all__ = ["Driver", "MockDriver"]


def make_driver(kind, **kwargs):
    """Factory: 'mock' -> MockDriver, 'embedded' -> EmbeddedDriver."""
    if kind == "mock":
        return MockDriver()
    if kind == "embedded":
        from .embedded import EmbeddedDriver
        return EmbeddedDriver(**kwargs)
    raise ValueError(f"unknown driver kind: {kind}")
