"""Validated inputs and qualitative model output for the plan report."""
from __future__ import annotations

from datetime import date
from typing import Annotated, Literal
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .schemas import GenericScenarioRequest, PvScenarioRequest
from .safety import reject_credentials


class BoundedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_max_length=1800, str_strip_whitespace=True)

    @field_validator("*", mode="before")
    @classmethod
    def trim_text(cls, value):
        def trim(item):
            return re.sub(r"^[\s\u200b\ufeff]+|[\s\u200b\ufeff]+$", "", item) if isinstance(item, str) else item
        return [trim(item) for item in value] if isinstance(value, list) else trim(value)


class PlanBase(BoundedModel):
    dataNature: Literal["assumption", "user_supplied_unverified"]
    assumptionNotice: str = ""
    projectName: str = Field(min_length=1, max_length=120)
    region: str = Field(min_length=1, max_length=120)
    address: str = ""
    constructionYear: int | None = None
    floorArea: float | None = Field(default=None, ge=0)
    roofArea: float | None = Field(default=None, ge=0)
    annualElectricity: float = Field(gt=0)
    electricityPrice: float = Field(ge=0)
    electricityPriceSource: str = Field(min_length=1)
    electricityPriceUrl: str = Field(min_length=1)
    carbonFactor: float = Field(ge=0)
    carbonSource: str = Field(min_length=1)
    carbonUrl: str = Field(min_length=1)
    baselineDate: date


class PlanGeneric(GenericScenarioRequest):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_max_length=500)


class PlanPv(PvScenarioRequest):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_max_length=500)


class PlanRequest(BoundedModel):
    base: PlanBase
    generic_scenarios: list[PlanGeneric] = Field(default_factory=list, max_length=8)
    pv_scenario: PlanPv | None = None
    objective: str = Field(default="在不降低安全与使用品质的前提下，开展低碳改造前期方案比选。", max_length=1500)
    comparison_investment: float | None = Field(default=None, ge=0)
    consent_cloud: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def check_plan_inputs(self):
        reject_credentials(self.model_dump(mode="json"))
        if not self.generic_scenarios and not self.pv_scenario:
            raise ValueError("完整方案至少需要一项已录入的可计算方案")
        ids = [item.scenario_id for item in self.generic_scenarios]
        if len(ids) != len(set(ids)):
            raise ValueError("方案编号不能重复，请分别编号后再生成报告")
        for item in self.generic_scenarios:
            if item.electricity_price_cny_per_kwh != self.base.electricityPrice or item.carbon_factor_kgco2e_per_kwh != self.base.carbonFactor:
                raise ValueError("方案的电价和碳因子必须与项目基线一致")
            if item.annual_energy_saving_kwh > self.base.annualElectricity:
                raise ValueError("单项年节电量不能超过输入的建筑年用电量，请核对边界")
        if self.pv_scenario:
            p = self.pv_scenario
            if (p.electricity_price_cny_per_kwh != self.base.electricityPrice or
                    p.carbon_factor_kgco2e_per_kwh != self.base.carbonFactor or
                    p.annual_building_electricity_kwh != self.base.annualElectricity):
                raise ValueError("光伏输入必须与项目用电基线一致")
        if self.comparison_investment is not None:
            if len(self.generic_scenarios) != 1 or self.pv_scenario:
                raise ValueError("投资调整比较只适用于单项通用方案")
            if self.comparison_investment < self.generic_scenarios[0].subsidy_cny:
                raise ValueError("比较投资不能低于已确认补贴")
        return self


class Measure(BoundedModel):
    title: str = Field(min_length=1, max_length=70)
    scope: str = Field(min_length=1, max_length=220)
    action: str = Field(min_length=1, max_length=450)
    prerequisite: str = Field(min_length=1, max_length=280)
    acceptance: str = Field(min_length=1, max_length=280)
    evidence_ids: list[str] = Field(max_length=4)


class Stage(BoundedModel):
    stage: str = Field(min_length=1, max_length=60)
    actions: str = Field(min_length=1, max_length=320)
    owner: str = Field(min_length=1, max_length=100)
    gate: str = Field(min_length=1, max_length=220)


class Risk(BoundedModel):
    risk: str = Field(min_length=1, max_length=140)
    mitigation: str = Field(min_length=1, max_length=320)
    release_condition: str = Field(min_length=1, max_length=220)


class Verification(BoundedModel):
    item: str = Field(min_length=1, max_length=90)
    method: str = Field(min_length=1, max_length=350)
    record: str = Field(min_length=1, max_length=250)


class PlanNarrative(BoundedModel):
    diagnosis: str = Field(min_length=40, max_length=700)
    goals: list[Annotated[str, Field(min_length=1)]] = Field(min_length=3, max_length=5)
    measures: list[Measure] = Field(min_length=3, max_length=5)
    wider_building_strategy: str = Field(min_length=40, max_length=650)
    procurement_notes: list[Annotated[str, Field(min_length=1)]] = Field(min_length=3, max_length=5)
    stages: list[Stage] = Field(min_length=4, max_length=5)
    risks: list[Risk] = Field(min_length=4, max_length=5)
    verification: list[Verification] = Field(min_length=4, max_length=5)
    conclusion: str = Field(min_length=40, max_length=600)
