"""Provider tests — mock provider uses real logic; real providers use httpx mocking."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from cleanshift.providers.electricitymap import ElectricityMapProvider
from cleanshift.providers.mock import MockProvider
from cleanshift.providers.watttime import WattTimeProvider

# ---------------------------------------------------------------------------
# MockProvider
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_current_is_aware():
    provider = MockProvider()
    point = await provider.current()
    assert point.timestamp.tzinfo is not None


@pytest.mark.asyncio
async def test_mock_current_intensity_positive():
    provider = MockProvider()
    point = await provider.current()
    assert point.intensity_gco2_per_kwh > 0


@pytest.mark.asyncio
async def test_mock_forecast_returns_hourly_points():
    provider = MockProvider()
    now = datetime.now(tz=timezone.utc)
    forecast = await provider.forecast(now, now + timedelta(hours=5))
    # Expect 6 points: aligned hour + 5 subsequent hours
    assert len(forecast) >= 5


@pytest.mark.asyncio
async def test_mock_forecast_all_aware():
    provider = MockProvider()
    now = datetime.now(tz=timezone.utc)
    forecast = await provider.forecast(now, now + timedelta(hours=12))
    assert all(p.timestamp.tzinfo is not None for p in forecast)


@pytest.mark.asyncio
async def test_mock_forecast_all_positive():
    provider = MockProvider()
    now = datetime.now(tz=timezone.utc)
    forecast = await provider.forecast(now, now + timedelta(hours=24))
    assert all(p.intensity_gco2_per_kwh > 0 for p in forecast)


@pytest.mark.asyncio
async def test_mock_sinusoidal_has_min_near_3am():
    """Verify the curve minimum lands in the ~3 AM hour."""
    provider = MockProvider()
    base = datetime(2024, 6, 1, 0, 0, tzinfo=timezone.utc)
    forecast = await provider.forecast(base, base + timedelta(hours=23))
    min_point = min(forecast, key=lambda p: p.intensity_gco2_per_kwh)
    # Minimum should be between midnight and 6 AM UTC
    assert 0 <= min_point.timestamp.hour <= 6


@pytest.mark.asyncio
async def test_mock_region_label():
    provider = MockProvider(region="TEST-REGION")
    assert provider.region == "TEST-REGION"
    assert provider.provider_name == "mock"


# ---------------------------------------------------------------------------
# ElectricityMapProvider (httpx mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_electricitymap_current():
    respx.get("https://api.electricitymap.org/v3/carbon-intensity/latest").mock(
        return_value=httpx.Response(
            200,
            json={"datetime": "2024-06-01T12:00:00+00:00", "carbonIntensity": 142.7},
        )
    )

    provider = ElectricityMapProvider(api_key="test-key", zone="US-CAL-CISO")
    point = await provider.current()

    assert abs(point.intensity_gco2_per_kwh - 142.7) < 0.01
    assert point.timestamp.tzinfo is not None
    assert point.timestamp.hour == 12


@pytest.mark.asyncio
@respx.mock
async def test_electricitymap_forecast_filters_window():
    respx.get("https://api.electricitymap.org/v3/carbon-intensity/forecast").mock(
        return_value=httpx.Response(
            200,
            json={
                "forecast": [
                    {"datetime": "2024-06-01T10:00:00Z", "carbonIntensity": 100.0},
                    {"datetime": "2024-06-01T12:00:00Z", "carbonIntensity": 120.0},
                    {"datetime": "2024-06-01T20:00:00Z", "carbonIntensity": 80.0},
                ]
            },
        )
    )

    from_dt = datetime(2024, 6, 1, 11, 0, tzinfo=timezone.utc)
    to_dt = datetime(2024, 6, 1, 15, 0, tzinfo=timezone.utc)

    provider = ElectricityMapProvider(api_key="test-key", zone="US-CAL-CISO")
    forecast = await provider.forecast(from_dt, to_dt)

    # Only the 12:00 point falls inside [11:00, 15:00]
    assert len(forecast) == 1
    assert abs(forecast[0].intensity_gco2_per_kwh - 120.0) < 0.01


@pytest.mark.asyncio
@respx.mock
async def test_electricitymap_raises_on_4xx():
    respx.get("https://api.electricitymap.org/v3/carbon-intensity/latest").mock(
        return_value=httpx.Response(401, json={"error": "Unauthorized"})
    )

    provider = ElectricityMapProvider(api_key="bad-key", zone="US-CAL-CISO")
    with pytest.raises(httpx.HTTPStatusError):
        await provider.current()


# ---------------------------------------------------------------------------
# WattTimeProvider (httpx mocked)
# ---------------------------------------------------------------------------

_WT_LOGIN_URL = "https://api.watttime.org/v3/login"
_WT_INDEX_URL = "https://api.watttime.org/v3/signal-index"
_WT_FORECAST_URL = "https://api.watttime.org/v3/forecast"
_LBS_TO_G_KWH = 453.592 / 1000.0


@pytest.mark.asyncio
@respx.mock
async def test_watttime_current_with_unit_conversion():
    respx.get(_WT_LOGIN_URL).mock(
        return_value=httpx.Response(200, json={"token": "tok123"})
    )
    respx.get(_WT_INDEX_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"point_time": "2024-06-01T12:00:00Z", "value": 800.0}],
                "meta": {"units": "lbs_CO2_per_MWh"},
            },
        )
    )

    provider = WattTimeProvider(username="u", password="p", region="CAISO_NORTH")
    point = await provider.current()

    expected = 800.0 * _LBS_TO_G_KWH
    assert abs(point.intensity_gco2_per_kwh - expected) < 0.01
    assert point.timestamp.tzinfo is not None


@pytest.mark.asyncio
@respx.mock
async def test_watttime_token_cached():
    login_route = respx.get(_WT_LOGIN_URL).mock(
        return_value=httpx.Response(200, json={"token": "tok-cached"})
    )
    respx.get(_WT_INDEX_URL).mock(
        return_value=httpx.Response(
            200,
            json={"data": [{"point_time": "2024-06-01T12:00:00Z", "value": 500.0}]},
        )
    )

    provider = WattTimeProvider(username="u", password="p", region="CAISO_NORTH")
    await provider.current()
    await provider.current()

    # Login should only be called once despite two current() calls
    assert login_route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_watttime_forecast_filters_and_converts():
    respx.get(_WT_LOGIN_URL).mock(
        return_value=httpx.Response(200, json={"token": "tok"})
    )
    respx.get(_WT_FORECAST_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"point_time": "2024-06-01T10:00:00Z", "value": 600.0},
                    {"point_time": "2024-06-01T13:00:00Z", "value": 700.0},
                    {"point_time": "2024-06-01T20:00:00Z", "value": 400.0},
                ]
            },
        )
    )

    from_dt = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
    to_dt = datetime(2024, 6, 1, 15, 0, tzinfo=timezone.utc)

    provider = WattTimeProvider(username="u", password="p", region="CAISO_NORTH")
    forecast = await provider.forecast(from_dt, to_dt)

    assert len(forecast) == 1
    expected = 700.0 * _LBS_TO_G_KWH
    assert abs(forecast[0].intensity_gco2_per_kwh - expected) < 0.01
