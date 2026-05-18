"""
Delay a fine-tuning job to the cleanest grid window.

Required environment variables:
  ELECTRICITY_MAP_API_KEY   — your ElectricityMap auth token
  ELECTRICITY_MAP_ZONE      — grid zone (default: US-CAL-CISO)

The job will sleep until the lowest-carbon hour within the next 6 hours,
then run and print a savings receipt.
"""

import os
import time
from cleanshift import carbon_window, ElectricityMapProvider

provider = ElectricityMapProvider(
    api_key=os.environ["ELECTRICITY_MAP_API_KEY"],
    zone=os.environ.get("ELECTRICITY_MAP_ZONE", "US-CAL-CISO"),
)

print(f"Scheduling fine-tune for region {provider.region} ...")
print("Waiting for a clean window (up to 6 hours) ...")

with carbon_window(provider=provider, max_delay_hours=6) as window:
    print(f"Started at {window._ran_at.isoformat()}")
    # Replace the sleep below with your actual fine-tuning call.
    time.sleep(2)

print("\nDone. Emissions receipt:")
print(window.receipt.model_dump_json(indent=2))
