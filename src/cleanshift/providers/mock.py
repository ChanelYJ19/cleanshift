import math
from datetime import datetime, timedelta, timezone

from .base import GridIntensityProvider, IntensityPoint


class MockProvider(GridIntensityProvider):
    """Synthetic 24-hour sinusoidal intensity curve — no API key required.

    The curve peaks around 3 PM UTC and troughs around 3 AM UTC, which is a
    reasonable approximation of solar-heavy grids. Useful for tests and demos.

    Args:
        region: Label used in receipts.
        base_intensity: Midpoint of the sine curve in gCO₂/kWh.
        amplitude: Half-range of the curve in gCO₂/kWh.
    """

    def __init__(
        self,
        region: str = "MOCK",
        base_intensity: float = 300.0,
        amplitude: float = 150.0,
    ) -> None:
        self._region = region
        self.base_intensity = base_intensity
        self.amplitude = amplitude

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def region(self) -> str:
        return self._region

    def _intensity_at(self, dt: datetime) -> float:
        hour = dt.hour + dt.minute / 60.0
        # sin(-π/2) = -1 when hour=3 → minimum; sin(π/2) = 1 when hour=15 → maximum
        angle = 2 * math.pi * (hour - 9) / 24
        return self.base_intensity + self.amplitude * math.sin(angle)

    async def current(self) -> IntensityPoint:
        now = datetime.now(tz=timezone.utc)
        return IntensityPoint(
            timestamp=now,
            intensity_gco2_per_kwh=self._intensity_at(now),
        )

    async def forecast(self, from_dt: datetime, to_dt: datetime) -> list[IntensityPoint]:
        """Return one point per hour between from_dt and to_dt inclusive."""
        points: list[IntensityPoint] = []
        # Align to the start of the current hour
        current = from_dt.replace(minute=0, second=0, microsecond=0)
        while current <= to_dt:
            points.append(
                IntensityPoint(
                    timestamp=current,
                    intensity_gco2_per_kwh=self._intensity_at(current),
                )
            )
            current += timedelta(hours=1)
        return points
