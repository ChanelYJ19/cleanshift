"""
Batch inference with threshold policy.

Waits until grid intensity drops below 150 gCO₂/kWh (up to 12 hours),
then runs inference. Uses ElectricityMap; swap for WattTimeProvider if preferred.

Required environment variables:
  ELECTRICITY_MAP_API_KEY
  ELECTRICITY_MAP_ZONE  (default: US-CAL-CISO)
"""

import os
import time
from cleanshift import carbon_window, ElectricityMapProvider, Policy

provider = ElectricityMapProvider(
    api_key=os.environ["ELECTRICITY_MAP_API_KEY"],
    zone=os.environ.get("ELECTRICITY_MAP_ZONE", "US-CAL-CISO"),
)


@carbon_window(
    provider=provider,
    max_delay_hours=12,
    policy=Policy.THRESHOLD,
    max_intensity_gco2_per_kwh=150,
)
def batch_inference() -> None:
    print("Running batch inference ...")
    # Replace with your actual inference loop.
    time.sleep(2)
    print("Inference complete.")


batch_inference()
print("\nEmissions receipt:")
print(batch_inference.last_receipt.model_dump_json(indent=2))
