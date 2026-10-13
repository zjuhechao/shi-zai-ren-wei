from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GenericScenarioRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    scenario_id: str
    scenario_name: str
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
    model_config = ConfigDict(allow_inf_nan=False)

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
    question: str = Field(min_length=2, max_length=4000)
    project_context: dict[str, Any] = Field(default_factory=dict)
    region: str | None = None


class AgentQueryResponse(BaseModel):
    answer: str
    citations: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
