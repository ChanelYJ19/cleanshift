"""
Synthetic demo — no API key required.

Uses MockProvider (sinusoidal 24-hour curve) to demonstrate the full API:
  1. find_cleanest_window — pure scheduling query
  2. carbon_window context manager
  3. carbon_window decorator

max_delay_hours=0 is used throughout so the demo completes instantly.
In production you'd pass e.g. max_delay_hours=6 and the library would sleep
until the cleanest hour within that window.
"""

import time
from cleanshift import carbon_window, find_cleanest_window, MockProvider

provider = MockProvider(region="MOCK-DEMO")

# ------------------------------------------------------------------
# 1. Pure scheduling query
# ------------------------------------------------------------------
print("=" * 50)
print("find_cleanest_window (no execution)")
print("=" * 50)

best = find_cleanest_window(provider, duration_hours=2, max_delay_hours=8)
print(f"Best 2-hour window starts at: {best.isoformat()}")

# ------------------------------------------------------------------
# 2. Context manager
# ------------------------------------------------------------------
print()
print("=" * 50)
print("carbon_window context manager")
print("=" * 50)

with carbon_window(provider=provider, max_delay_hours=0) as window:
    time.sleep(0.1)  # stand-in for real work

print(window.receipt.model_dump_json(indent=2))

# ------------------------------------------------------------------
# 3. Decorator
# ------------------------------------------------------------------
print()
print("=" * 50)
print("carbon_window decorator")
print("=" * 50)


@carbon_window(provider=provider, max_delay_hours=0)
def fake_fine_tune() -> str:
    time.sleep(0.1)
    return "training complete"


result = fake_fine_tune()
print(f"Job returned: {result!r}")
print(fake_fine_tune.last_receipt.model_dump_json(indent=2))
