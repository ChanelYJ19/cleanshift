# cleanshift

Delay batch ML/AI jobs to the cleanest grid window.

`cleanshift` wraps your long-running job — fine-tuning, batch inference, embedding generation — and schedules it during the lowest-carbon hour within a time window you specify. After execution it prints a **savings receipt** showing estimated CO₂ avoided vs. running immediately.

## Install

```bash
pip install cleanshift
```

## Quick start — no API key needed

```python
import time
from cleanshift import carbon_window, MockProvider

provider = MockProvider()

with carbon_window(provider=provider, max_delay_hours=6) as window:
    time.sleep(1)  # your job here

print(window.receipt.model_dump_json(indent=2))
```

`MockProvider` generates a synthetic sinusoidal intensity curve (peak at 3 PM UTC, trough at 3 AM UTC) so you can develop and test without signing up for anything.

## Real API example

```python
import os, time
from cleanshift import carbon_window, ElectricityMapProvider

provider = ElectricityMapProvider(
    api_key=os.environ["ELECTRICITY_MAP_API_KEY"],
    zone="US-CAL-CISO",
)

with carbon_window(provider=provider, max_delay_hours=6) as window:
    run_fine_tuning()

print(window.receipt.model_dump_json(indent=2))
```

## Decorator form

```python
from cleanshift import carbon_window, ElectricityMapProvider, Policy

@carbon_window(
    provider=provider,
    max_delay_hours=12,
    policy=Policy.THRESHOLD,
    max_intensity_gco2_per_kwh=150,
)
def nightly_finetune():
    ...

nightly_finetune()
print(nightly_finetune.last_receipt.model_dump_json(indent=2))
```

## Pure scheduling query

```python
from cleanshift import find_cleanest_window, MockProvider

best = find_cleanest_window(
    MockProvider(),
    duration_hours=2,
    max_delay_hours=24,
)
print(f"Recommended start: {best.isoformat()}")
```

## Policies

| Policy | Behaviour |
|--------|-----------|
| `min_carbon` *(default)* | Sleep until the lowest-intensity hour in the allowable window |
| `threshold` | Run as soon as intensity drops below `max_intensity_gco2_per_kwh`; falls back to the cleanest available slot if the threshold is never met |
| `now_or_never` | Run immediately if intensity is clean; raise `JobSkipped` otherwise |
| `halt_if_dirty` | Start immediately; **pause** execution if intensity spikes above `max_intensity_gco2_per_kwh` mid-run; resume automatically when it drops back *(Unix only)* |

### `halt_if_dirty` notes

`halt_if_dirty` requires `max_intensity_gco2_per_kwh` and uses `SIGSTOP`/`SIGCONT` to pause the process, so it is **not supported on Windows**. The intensity is re-checked every `poll_interval_seconds` (default 5 minutes).

## Receipt schema

```python
class CarbonReceipt(BaseModel):
    scheduled_at: AwareDatetime        # when carbon_window was entered
    ran_at: AwareDatetime              # when execution actually started
    delay_seconds: int
    duration_seconds: int
    avg_intensity_gco2_per_kwh: float  # mean of readings at start + end of run
    counterfactual_avg_intensity: float  # intensity at scheduling time
    estimated_savings_pct: float       # computed field (positive = savings)
    region: str
    provider: str
```

`avg_intensity_gco2_per_kwh` is the arithmetic mean of readings taken at the start and end of the run — a point estimate, not a true integral. If your job is long enough that accuracy matters, prefer a provider with dense historical data.

## Providers

| Class | Source | Sign-up |
|-------|--------|---------|
| `MockProvider` | Synthetic curve | None |
| `ElectricityMapProvider` | [electricitymaps.com](https://electricitymaps.com) | Free tier available |
| `WattTimeProvider` | [watttime.org](https://watttime.org) | Free tier available |

### Adding a provider

Implement `GridIntensityProvider`:

```python
from cleanshift.providers.base import GridIntensityProvider, IntensityPoint

class MyProvider(GridIntensityProvider):
    @property
    def provider_name(self) -> str: return "myprovider"

    @property
    def region(self) -> str: return "MY-REGION"

    async def current(self) -> IntensityPoint: ...

    async def forecast(self, from_dt, to_dt) -> list[IntensityPoint]: ...
```

## CLI

```bash
# Dry-run with mock data (no API key)
cleanshift schedule --duration 2h --max-delay 24h --region US-CAL-CISO --dry-run

# With ElectricityMap
cleanshift schedule --duration 2h --max-delay 24h \
    --provider electricitymap --api-key $KEY --zone US-CAL-CISO --dry-run
```

## Development

```bash
pip install -e ".[dev]"
pytest
python examples/synthetic_demo.py
```

## License

MIT
