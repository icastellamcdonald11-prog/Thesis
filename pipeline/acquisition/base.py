from __future__ import annotations

from abc import ABC, abstractmethod

from pipeline.models import RawItem


class AdapterError(Exception):
    """Raised when a source fetch fails. Callers catch this per-source and continue."""


class Adapter(ABC):
    @abstractmethod
    def fetch(self, source: dict, settings) -> list[RawItem]:
        """Fetch and return raw items for one source. Raise AdapterError on failure."""
