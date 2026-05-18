"""Policy unit tests — all async, no network calls."""

from datetime import datetime, timedelta, timezone

import pytest

from cleanshift.policies import Policy, JobSkipped, find_best_start
from cleanshift.providers.mock import MockProvider


@pytest.mark.asyncio
async def test_min_carbon_picks_lowest_in_window():
    provider = MockProvider()
    now = datetime.now(tz=timezone.utc)
    forecast = await provider.forecast(now, now + timedelta(hours=24))

    best_time = await find_best_start(provider, max_delay_hours=24, policy=Policy.MIN_CARBON)

    expected = min(forecast, key=lambda p: p.intensity_gco2_per_kwh).timestamp
    assert abs((best_time - expected).total_seconds()) < 1


@pytest.mark.asyncio
async def test_min_carbon_within_delay_window():
    provider = MockProvider()
    now = datetime.now(tz=timezone.utc)

    best_time = await find_best_start(provider, max_delay_hours=6, policy=Policy.MIN_CARBON)

    assert best_time <= now + timedelta(hours=6, seconds=1)


@pytest.mark.asyncio
async def test_threshold_returns_now_when_already_clean():
    provider = MockProvider(base_intensity=50.0, amplitude=5.0)  # always ~50 gCO₂/kWh

    now = datetime.now(tz=timezone.utc)
    best_time = await find_best_start(
        provider,
        max_delay_hours=24,
        policy=Policy.THRESHOLD,
        max_intensity_gco2_per_kwh=200.0,
    )

    assert (best_time - now).total_seconds() < 60


@pytest.mark.asyncio
async def test_threshold_finds_future_slot_when_dirty():
    provider = MockProvider(base_intensity=400.0, amplitude=50.0)  # always ~400 gCO₂/kWh

    # Threshold is lower than anything in the forecast, so falls back to min
    best_time = await find_best_start(
        provider,
        max_delay_hours=24,
        policy=Policy.THRESHOLD,
        max_intensity_gco2_per_kwh=100.0,
    )

    now = datetime.now(tz=timezone.utc)
    # Should still be within the delay window even when no slot meets threshold
    assert best_time <= now + timedelta(hours=24, seconds=1)


@pytest.mark.asyncio
async def test_threshold_requires_threshold_arg():
    provider = MockProvider()
    with pytest.raises(ValueError, match="max_intensity_gco2_per_kwh"):
        await find_best_start(provider, max_delay_hours=6, policy=Policy.THRESHOLD)


@pytest.mark.asyncio
async def test_now_or_never_runs_when_clean():
    provider = MockProvider(base_intensity=50.0, amplitude=5.0)

    now = datetime.now(tz=timezone.utc)
    best_time = await find_best_start(
        provider,
        max_delay_hours=0,
        policy=Policy.NOW_OR_NEVER,
        max_intensity_gco2_per_kwh=200.0,
    )

    assert (best_time - now).total_seconds() < 60


@pytest.mark.asyncio
async def test_now_or_never_raises_when_dirty():
    provider = MockProvider(base_intensity=500.0, amplitude=10.0)

    with pytest.raises(JobSkipped):
        await find_best_start(
            provider,
            max_delay_hours=24,
            policy=Policy.NOW_OR_NEVER,
            max_intensity_gco2_per_kwh=100.0,
        )


@pytest.mark.asyncio
async def test_now_or_never_requires_threshold_arg():
    provider = MockProvider()
    with pytest.raises(ValueError, match="max_intensity_gco2_per_kwh"):
        await find_best_start(provider, max_delay_hours=6, policy=Policy.NOW_OR_NEVER)


@pytest.mark.asyncio
async def test_halt_if_dirty_starts_immediately():
    provider = MockProvider()
    now = datetime.now(tz=timezone.utc)

    best_time = await find_best_start(provider, max_delay_hours=24, policy=Policy.HALT_IF_DIRTY)

    assert (best_time - now).total_seconds() < 60
