from datetime import datetime, timezone

import httpx

from .base import GridIntensityProvider, IntensityPoint

_BASE = "https://api.electricitymap.org/v3"


def _parse_iso(s: str) -> datetime:
    # datetime.fromisoformat() only accepts 'Z' in Python 3.11+
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


class ElectricityMapProvider(GridIntensityProvider):
    """ElectricityMap API v3 provider.

    Sign up at https://electricitymaps.com to obtain an API key.

    Args:
        api_key: ElectricityMap auth token.
        zone: Grid zone identifier (e.g. 'US-CAL-CISO').
    """

    def __init__(self, api_key: str, zone: str) -> None:
        self._api_key = api_key
        self._zone = zone

    @property
    def provider_name(self) -> str:
        return "electricitymap"

    @property
    def region(self) -> str:
        return self._zone

    def _headers(self) -> dict[str, str]:
        return {"auth-token": self._api_key}

    async def current(self) -> IntensityPoint:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_BASE}/carbon-intensity/latest",
                params={"zone": self._zone},
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()

        ts = _parse_iso(data["datetime"])
        return IntensityPoint(
            timestamp=ts,
            intensity_gco2_per_kwh=float(data["carbonIntensity"]),
        )

    async def forecast(self, from_dt: datetime, to_dt: datetime) -> list[IntensityPoint]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_BASE}/carbon-intensity/forecast",
                params={"zone": self._zone},
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()

        points: list[IntensityPoint] = []
        for entry in data.get("forecast", []):
            ts = _parse_iso(entry["datetime"])
            if from_dt <= ts <= to_dt:
                points.append(
                    IntensityPoint(
                        timestamp=ts,
                        intensity_gco2_per_kwh=float(entry["carbonIntensity"]),
                    )
                )
        return points
