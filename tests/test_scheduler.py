"""Scheduler tests — MockProvider only, no network calls."""

import time

import pytest

from cleanshift import JobSkipped, Policy, carbon_window, find_cleanest_window
from cleanshift.providers.mock import MockProvider


def test_context_manager_executes_body(mock_provider):
    executed = []
    with carbon_window(provider=mock_provider, max_delay_hours=0) as window:
        executed.append(True)
    assert executed == [True]


def test_receipt_is_set_after_exit(mock_provider):
    with carbon_window(provider=mock_provider, max_delay_hours=0) as window:
        pass
    assert window.receipt is not None


def test_receipt_fields_are_sane(mock_provider):
    with carbon_window(provider=mock_provider, max_delay_hours=0) as window:
        time.sleep(0.05)

    r = window.receipt
    assert r.region == "MOCK"
    assert r.provider == "mock"
    assert r.scheduled_at.tzinfo is not None
    assert r.ran_at.tzinfo is not None
    assert r.delay_seconds >= 0
    assert r.duration_seconds >= 0
    assert r.avg_intensity_gco2_per_kwh > 0
    assert r.counterfactual_avg_intensity > 0


def test_receipt_savings_pct_type(mock_provider):
    with carbon_window(provider=mock_provider, max_delay_hours=0) as window:
        pass
    assert isinstance(window.receipt.estimated_savings_pct, float)


def test_decorator_returns_function_result(mock_provider):
    @carbon_window(provider=mock_provider, max_delay_hours=0)
    def job():
        return 42

    result = job()
    assert result == 42


def test_decorator_sets_last_receipt(mock_provider):
    @carbon_window(provider=mock_provider, max_delay_hours=0)
    def job():
        pass

    assert job.last_receipt is None  # before first call
    job()
    assert job.last_receipt is not None
    assert job.last_receipt.provider == "mock"


def test_decorator_last_receipt_updates_each_call(mock_provider):
    @carbon_window(provider=mock_provider, max_delay_hours=0)
    def job():
        pass

    job()
    first = job.last_receipt.ran_at
    time.sleep(0.05)
    job()
    second = job.last_receipt.ran_at
    assert second >= first


def test_now_or_never_raises_job_skipped(high_intensity_provider):
    with pytest.raises(JobSkipped):
        with carbon_window(
            provider=high_intensity_provider,
            max_delay_hours=0,
            policy=Policy.NOW_OR_NEVER,
            max_intensity_gco2_per_kwh=100.0,
        ):
            pass  # should never reach here


def test_now_or_never_runs_when_clean(low_intensity_provider):
    ran = []
    with carbon_window(
        provider=low_intensity_provider,
        max_delay_hours=0,
        policy=Policy.NOW_OR_NEVER,
        max_intensity_gco2_per_kwh=200.0,
    ):
        ran.append(True)
    assert ran == [True]


def test_find_cleanest_window_returns_aware_datetime(mock_provider):
    best = find_cleanest_window(mock_provider, duration_hours=2, max_delay_hours=8)
    assert best.tzinfo is not None


def test_find_cleanest_window_within_delay(mock_provider):
    from datetime import datetime, timedelta, timezone

    now = datetime.now(tz=timezone.utc)
    best = find_cleanest_window(mock_provider, duration_hours=1, max_delay_hours=6)
    assert best <= now + timedelta(hours=6, minutes=1)


def test_exception_in_body_propagates(mock_provider):
    with pytest.raises(RuntimeError, match="boom"):
        with carbon_window(provider=mock_provider, max_delay_hours=0):
            raise RuntimeError("boom")


def test_receipt_is_still_set_after_body_exception(mock_provider):
    try:
        with carbon_window(provider=mock_provider, max_delay_hours=0) as window:
            raise ValueError("oops")
    except ValueError:
        pass
    assert window.receipt is not None
