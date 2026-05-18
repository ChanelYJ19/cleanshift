"""carbon_window context manager, decorator, and find_cleanest_window helper."""

import asyncio
import concurrent.futures
import functools
import multiprocessing
import os
import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .policies import Policy, find_best_start
from .providers.base import GridIntensityProvider, IntensityPoint
from .receipt import CarbonReceipt


def _run_async(coro: Any) -> Any:
    """Run *coro* regardless of whether we're inside a running event loop."""
    try:
        asyncio.get_running_loop()
        # Inside an async context — offload to a thread so we don't nest loops.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        return asyncio.run(coro)


def _halt_monitor_worker(
    target_pid: int,
    provider: GridIntensityProvider,
    threshold: float,
    poll_interval: float,
) -> None:
    """Child-process entry point for the halt_if_dirty monitor.

    Runs in a separate process so it continues executing when the parent is
    suspended via SIGSTOP.
    """
    paused = False
    while True:
        try:
            point: IntensityPoint = asyncio.run(provider.current())
            over = point.intensity_gco2_per_kwh > threshold
            if over and not paused:
                os.kill(target_pid, signal.SIGSTOP)
                paused = True
            elif not over and paused:
                os.kill(target_pid, signal.SIGCONT)
                paused = False
        except ProcessLookupError:
            break  # Target process is gone; nothing left to monitor.
        except Exception:
            pass  # Transient API errors must not crash the monitor.
        time.sleep(poll_interval)


class CarbonWindow:
    """Carbon-aware execution context that can be used as a context manager or decorator.

    Do not instantiate directly — use :func:`carbon_window` instead.
    """

    def __init__(
        self,
        provider: GridIntensityProvider,
        max_delay_hours: float,
        policy: Policy,
        max_intensity_gco2_per_kwh: float | None,
        poll_interval_seconds: float,
    ) -> None:
        self.provider = provider
        self.max_delay_hours = max_delay_hours
        self.policy = policy
        self.max_intensity_gco2_per_kwh = max_intensity_gco2_per_kwh
        self.poll_interval_seconds = poll_interval_seconds
        self.receipt: CarbonReceipt | None = None

        self._scheduled_at: datetime | None = None
        self._counterfactual_intensity: float | None = None
        self._ran_at: datetime | None = None
        self._ran_at_intensity: float | None = None
        self._start_monotonic: float | None = None
        self._monitor_process: multiprocessing.Process | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "CarbonWindow":
        self._scheduled_at = datetime.now(tz=timezone.utc)

        async def _prepare() -> tuple[float, datetime]:
            current = await self.provider.current()
            best = await find_best_start(
                self.provider,
                self.max_delay_hours,
                self.policy,
                self.max_intensity_gco2_per_kwh,
                _current_hint=current,
            )
            return current.intensity_gco2_per_kwh, best

        self._counterfactual_intensity, best_time = _run_async(_prepare())

        delay = (best_time - datetime.now(tz=timezone.utc)).total_seconds()
        if delay > 1.0:
            time.sleep(delay)

        self._ran_at = datetime.now(tz=timezone.utc)
        self._ran_at_intensity = _run_async(self.provider.current()).intensity_gco2_per_kwh
        self._start_monotonic = time.monotonic()

        if self.policy is Policy.HALT_IF_DIRTY:
            if sys.platform == "win32":
                raise NotImplementedError(
                    "halt_if_dirty is not supported on Windows "
                    "(SIGSTOP/SIGCONT are unavailable)"
                )
            if self.max_intensity_gco2_per_kwh is None:
                raise ValueError("halt_if_dirty policy requires max_intensity_gco2_per_kwh")
            self._start_halt_monitor()

        return self

    def __exit__(
        self,
        exc_type: type | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool:
        if self._monitor_process is not None:
            self._monitor_process.terminate()
            self._monitor_process.join(timeout=5)
            self._monitor_process = None

        duration = time.monotonic() - self._start_monotonic  # type: ignore[operator]
        end_intensity = _run_async(self.provider.current()).intensity_gco2_per_kwh
        avg_intensity = (self._ran_at_intensity + end_intensity) / 2.0  # type: ignore[operator]

        self.receipt = CarbonReceipt(
            scheduled_at=self._scheduled_at,  # type: ignore[arg-type]
            ran_at=self._ran_at,  # type: ignore[arg-type]
            delay_seconds=int((self._ran_at - self._scheduled_at).total_seconds()),  # type: ignore[operator]
            duration_seconds=int(duration),
            avg_intensity_gco2_per_kwh=avg_intensity,
            counterfactual_avg_intensity=self._counterfactual_intensity,  # type: ignore[arg-type]
            region=self.provider.region,
            provider=self.provider.provider_name,
        )
        return False  # never suppress exceptions

    def _start_halt_monitor(self) -> None:
        ctx = multiprocessing.get_context("spawn")
        proc = ctx.Process(
            target=_halt_monitor_worker,
            args=(
                os.getpid(),
                self.provider,
                self.max_intensity_gco2_per_kwh,
                self.poll_interval_seconds,
            ),
            daemon=True,
        )
        proc.start()
        self._monitor_process = proc

    # ------------------------------------------------------------------
    # Decorator
    # ------------------------------------------------------------------

    def __call__(self, func: Callable) -> Callable:
        """Wrap *func* so each call runs inside a fresh CarbonWindow."""
        provider = self.provider
        max_delay_hours = self.max_delay_hours
        policy = self.policy
        max_intensity_gco2_per_kwh = self.max_intensity_gco2_per_kwh
        poll_interval_seconds = self.poll_interval_seconds

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            instance = CarbonWindow(
                provider=provider,
                max_delay_hours=max_delay_hours,
                policy=policy,
                max_intensity_gco2_per_kwh=max_intensity_gco2_per_kwh,
                poll_interval_seconds=poll_interval_seconds,
            )
            with instance:
                result = func(*args, **kwargs)
            wrapper.last_receipt = instance.receipt
            return result

        wrapper.last_receipt = None  # type: ignore[attr-defined]
        return wrapper


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def carbon_window(
    provider: GridIntensityProvider,
    max_delay_hours: float = 6.0,
    policy: str | Policy = Policy.MIN_CARBON,
    max_intensity_gco2_per_kwh: float | None = None,
    poll_interval_seconds: float = 300.0,
) -> CarbonWindow:
    """Create a carbon-aware execution window.

    Can be used as a context manager or a decorator.

    Args:
        provider: Grid intensity data source.
        max_delay_hours: How long the job is allowed to wait for a clean window.
        policy: One of ``'min_carbon'``, ``'threshold'``, ``'now_or_never'``,
            or ``'halt_if_dirty'``.
        max_intensity_gco2_per_kwh: Intensity ceiling for ``threshold``,
            ``now_or_never``, and ``halt_if_dirty`` policies.
        poll_interval_seconds: How often ``halt_if_dirty`` rechecks intensity
            (default 5 minutes).

    Returns:
        A :class:`CarbonWindow` instance. After the ``with`` block exits,
        ``window.receipt`` contains the emissions record. When used as a
        decorator, each call stores its receipt in ``func.last_receipt``.

    Example::

        with carbon_window(provider=provider, max_delay_hours=6) as window:
            run_job()
        print(window.receipt)

        @carbon_window(provider=provider, max_delay_hours=12)
        def nightly_job():
            ...
    """
    return CarbonWindow(
        provider=provider,
        max_delay_hours=max_delay_hours,
        policy=Policy(policy) if isinstance(policy, str) else policy,
        max_intensity_gco2_per_kwh=max_intensity_gco2_per_kwh,
        poll_interval_seconds=poll_interval_seconds,
    )


def find_cleanest_window(
    provider: GridIntensityProvider,
    duration_hours: float,
    max_delay_hours: float,
) -> datetime:
    """Find the start time of the lowest-average-intensity window.

    Scans all candidate start times within *max_delay_hours* from now and
    returns the one whose *duration_hours*-long window has the lowest average
    carbon intensity.

    Args:
        provider: Grid intensity data source.
        duration_hours: Expected job duration used for window averaging.
        max_delay_hours: Search horizon from now.

    Returns:
        A timezone-aware UTC datetime.
    """

    async def _find() -> datetime:
        now = datetime.now(tz=timezone.utc)
        deadline = now + timedelta(hours=max_delay_hours)
        forecast = await provider.forecast(now, deadline)

        if not forecast:
            return now

        duration_delta = timedelta(hours=duration_hours)
        best_start = now
        best_avg = float("inf")

        for point in forecast:
            window_end = point.timestamp + duration_delta
            window_points = [
                p for p in forecast if point.timestamp <= p.timestamp <= window_end
            ]
            if window_points:
                avg = sum(p.intensity_gco2_per_kwh for p in window_points) / len(window_points)
                if avg < best_avg:
                    best_avg = avg
                    best_start = point.timestamp

        return best_start

    return _run_async(_find())
