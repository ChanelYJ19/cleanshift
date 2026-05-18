from datetime import datetime, timezone

import httpx

from .base import GridIntensityProvider, IntensityPoint

_BASE = "https://api.watttime.org/v3"


def _parse_iso(s: str) -> datetime:
    # datetime.fromisoformat() only accepts 'Z' in Python 3.11+
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
# WattTime reports CO₂ MOER in lbs CO₂/MWh; convert to gCO₂/kWh
_LBS_MWH_TO_G_KWH = 453.592 / 1000.0


class WattTimeProvider(GridIntensityProvider):
    """WattTime API v3 provider.

    Sign up at https://watttime.org to obtain credentials.

    Args:
        username: WattTime account username.
        password: WattTime account password.
        region: WattTime grid region (e.g. 'CAISO_NORTH').
    """

    def __init__(self, username: str, password: str, region: str) -> None:
        self._username = username
        self._password = password
        self._region = region
        self._token: str | None = None

    @property
    def provider_name(self) -> str:
        return "watttime"

    @property
    def region(self) -> str:
        return self._region

    async def _auth_headers(self) -> dict[str, str]:
        if self._token is None:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{_BASE}/login",
                    auth=(self._username, self._password),
                )
                resp.raise_for_status()
                self._token = resp.json()["token"]
        return {"Authorization": f"Bearer {self._token}"}

    async def current(self) -> IntensityPoint:
        headers = await self._auth_headers()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_BASE}/signal-index",
                params={"region": self._region, "signal_type": "co2_moer"},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        entry = data["data"][0]
        ts = _parse_iso(entry["point_time"])
        return IntensityPoint(
            timestamp=ts,
            intensity_gco2_per_kwh=float(entry["value"]) * _LBS_MWH_TO_G_KWH,
        )

    async def forecast(self, from_dt: datetime, to_dt: datetime) -> list[IntensityPoint]:
        headers = await self._auth_headers()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_BASE}/forecast",
                params={
                    "region": self._region,
                    "signal_type": "co2_moer",
                    "start": from_dt.isoformat(),
                    "end": to_dt.isoformat(),
                },
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        points: list[IntensityPoint] = []
        for entry in data.get("data", []):
            ts = _parse_iso(entry["point_time"])
            if from_dt <= ts <= to_dt:
                points.append(
                    IntensityPoint(
                        timestamp=ts,
                        intensity_gco2_per_kwh=float(entry["value"]) * _LBS_MWH_TO_G_KWH,
                    )
                )
        return points
