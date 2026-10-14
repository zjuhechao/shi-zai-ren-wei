from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from .safety import reject_credentials, validate_context


class GenericScenarioRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid", strict=True, str_max_length=500, str_strip_whitespace=True)

    scenario_id: str = Field(min_length=1, max_length=120)
    scenario_name: str = Field(min_length=1, max_length=120)
    investment_cny: float = Field(ge=0)
    subsidy_cny: float = Field(ge=0)
    annual_energy_saving_kwh: float = Field(ge=0)
    electricity_price_cny_per_kwh: float = Field(ge=0)
    carbon_factor_kgco2e_per_kwh: float = Field(ge=0)
    annual_om_cny: float = Field(ge=0)
    source_name: str
    source_url: str
    data_date: str
    notes: str = ""


class PvScenarioRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid", strict=True, str_max_length=500, str_strip_whitespace=True)

    capacity_kwp: float = Field(ge=0)
    annual_yield_kwh_per_kwp: float = Field(ge=0)
    self_use_ratio: float = Field(ge=0, le=1)
    annual_building_electricity_kwh: float = Field(ge=0)
    electricity_price_cny_per_kwh: float = Field(ge=0)
    feed_in_tariff_cny_per_kwh: float = Field(ge=0)
    carbon_factor_kgco2e_per_kwh: float = Field(ge=0)
    investment_cny: float = Field(ge=0)
    subsidy_cny: float = Field(ge=0)
    annual_om_cny: float = Field(ge=0)
    source_name: str
    source_url: str
    data_date: str


class AgentQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=2, max_length=4000)
    project_context: dict[str, Any] = Field(default_factory=dict)
    region: str | None = Field(default=None, max_length=120)
    consent_cloud: bool = Field(default=False, strict=True)

    @field_validator("question", "region")
    @classmethod
    def no_credentials(cls, value):
        if value is not None:
            reject_credentials(value)
        return value

    @field_validator("project_context")
    @classmethod
    def bounded_context(cls, value):
        return validate_context(value)


class AgentQueryResponse(BaseModel):
    answer: str
    citations: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
