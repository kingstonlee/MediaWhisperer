"""Extract stage: turn sources into downloadable media items.

Importing this package registers every built-in extractor with the registry in
:mod:`mediawhisperer.extract.base`.
"""

from .base import Extractor, get_extractor, register
from . import podcast, youtube  # noqa: F401  (import for side-effect: registration)

__all__ = ["Extractor", "get_extractor", "register"]
