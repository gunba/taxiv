"""
Convenience imports to ensure ORM models register with SQLAlchemy metadata.
"""

from . import legislation  # noqa: F401
from . import semantic  # noqa: F401

__all__ = ["legislation", "semantic"]
