from datetime import datetime, timedelta, timezone
from enum import Enum

from .providers.base import GridIntensityProvider, IntensityPoint


class Policy(str, Enum):
    MIN_CARBON = "min_carbon"
    THRESHOLD = "threshold"
    NOW_OR_NEVER = "now_or_never"
    HALT_IF_DIRTY = "halt_if_dirty"


class JobSkipped(Exception):
    """Raised by the ``now_or_never`` policy when current intensity is above threshold."""


async def find_best_start(
    provider: GridIntensityProvider,
    max_delay_hours: float,
    policy: Policy = Policy.MIN_CARBON,
    max_intensity_gco2_per_kwh: float | None = None,
    _current_hint: IntensityPoint | None = None,
) -> datetime:
    """Return the recommended start time according to *policy*.

    Args:
        provider: Grid intensity data source.
        max_delay_hours: Maximum allowable delay from now.
        policy: Scheduling policy.
        max_intensity_gco2_per_kwh: Threshold used by ``threshold`` and
            ``now_or_never`` policies.
        _current_hint: Pre-fetched current reading to avoid a redundant API
            call (internal use by the scheduler).

    Returns:
        A timezone-aware UTC datetime no more than ``max_delay_hours`` from now.

    Raises:
        JobSkipped: If policy is ``now_or_never`` and current intensity exceeds
            ``max_intensity_gco2_per_kwh``.
        ValueError: If a required threshold is missing.
    """
    now = datetime.now(tz=timezone.utc)
    deadline = now + timedelta(hours=max_delay_hours)

    if policy is Policy.MIN_CARBON:
        forecast = await provider.forecast(now, deadline)
        if not forecast:
            return now
        return min(forecast, key=lambda p: p.intensity_gco2_per_kwh).timestamp

    if policy is Policy.THRESHOLD:
        if max_intensity_gco2_per_kwh is None:
            raise ValueError("threshold policy requires max_intensity_gco2_per_kwh")
        current = _current_hint or await provider.current()
        if current.intensity_gco2_per_kwh <= max_intensity_gco2_per_kwh:
            return now
        forecast = await provider.forecast(now, deadline)
        for point in sorted(forecast, key=lambda p: p.timestamp):
            if point.intensity_gco2_per_kwh <= max_intensity_gco2_per_kwh:
                return point.timestamp
        # No clean window found — pick the least-bad slot
        if forecast:
            return min(forecast, key=lambda p: p.intensity_gco2_per_kwh).timestamp
        return now

    if policy is Policy.NOW_OR_NEVER:
        if max_intensity_gco2_per_kwh is None:
            raise ValueError("now_or_never policy requires max_intensity_gco2_per_kwh")
        current = _current_hint or await provider.current()
        if current.intensity_gco2_per_kwh <= max_intensity_gco2_per_kwh:
            return now
        raise JobSkipped(
            f"Current intensity {current.intensity_gco2_per_kwh:.1f} gCO₂/kWh "
            f"exceeds threshold {max_intensity_gco2_per_kwh:.1f}"
        )

    if policy is Policy.HALT_IF_DIRTY:
        # Execution starts immediately; mid-run pausing is handled by the scheduler.
        return now

    raise ValueError(f"Unknown policy: {policy}")
