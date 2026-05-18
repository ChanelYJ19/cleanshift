from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class IntensityPoint:
    """A single grid carbon intensity reading."""

    timestamp: datetime  # always UTC-aware
    intensity_gco2_per_kwh: float


class GridIntensityProvider(ABC):
    """Abstract base for grid intensity data sources."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Short identifier used in receipts (e.g. 'electricitymap')."""
        ...

    @property
    @abstractmethod
    def region(self) -> str:
        """Grid region or zone identifier."""
        ...

    @abstractmethod
    async def current(self) -> IntensityPoint:
        """Return the current (or most recent) carbon intensity."""
        ...

    @abstractmethod
    async def forecast(self, from_dt: datetime, to_dt: datetime) -> list[IntensityPoint]:
        """Return hourly intensity forecasts between from_dt and to_dt (both UTC-aware)."""
        ...
