from pydantic import AwareDatetime, BaseModel, computed_field


class CarbonReceipt(BaseModel):
    """Emissions record for a single job execution.

    All intensity values are in gCO₂/kWh. ``estimated_savings_pct`` is positive
    when the job ran in a cleaner window than it would have at scheduling time.
    """

    scheduled_at: AwareDatetime
    ran_at: AwareDatetime
    delay_seconds: int
    duration_seconds: int
    avg_intensity_gco2_per_kwh: float
    counterfactual_avg_intensity: float
    region: str
    provider: str

    @computed_field  # type: ignore[misc]
    @property
    def estimated_savings_pct(self) -> float:
        """Percentage reduction vs. running immediately at scheduling time."""
        if self.counterfactual_avg_intensity == 0.0:
            return 0.0
        return (
            (self.counterfactual_avg_intensity - self.avg_intensity_gco2_per_kwh)
            / self.counterfactual_avg_intensity
            * 100.0
        )
