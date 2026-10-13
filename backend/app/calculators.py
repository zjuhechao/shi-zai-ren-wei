from __future__ import annotations

from typing import Any
from math import isfinite


def _non_negative(name: str, value: float) -> float:
    value = float(value)
    if not isfinite(value):
        raise ValueError(f"{name}必须是有限数值")
    if value < 0:
        raise ValueError(f"{name}不能为负数")
    return value


def _finite_result(result: dict[str, Any]) -> dict[str, Any]:
    if any(isinstance(value, float) and not isfinite(value) for value in result.values()):
        raise ValueError("输入数值超出可计算范围，请检查单位与数量级")
    return result


def calculate_generic_scenario(
    *,
    scenario_id: str,
    scenario_name: str,
    investment_cny: float,
    subsidy_cny: float,
    annual_energy_saving_kwh: float,
    electricity_price_cny_per_kwh: float,
    carbon_factor_kgco2e_per_kwh: float,
    annual_om_cny: float,
    source_name: str,
    source_url: str,
    data_date: str,
    notes: str = "",
) -> dict[str, Any]:
    investment = _non_negative("改造总投资", investment_cny)
    subsidy = _non_negative("已确认补贴", subsidy_cny)
    if subsidy > investment:
        raise ValueError("已确认补贴不能大于改造总投资")
    saving = _non_negative("预计年节电量", annual_energy_saving_kwh)
    price = _non_negative("电价", electricity_price_cny_per_kwh)
    factor = _non_negative("电力排放因子", carbon_factor_kgco2e_per_kwh)
    annual_om = _non_negative("年运维成本", annual_om_cny)
    if not all([scenario_id.strip(), scenario_name.strip(), source_name.strip(), source_url.strip(), data_date.strip()]):
        raise ValueError("方案编号、名称、来源、来源地址和数据日期均不能为空")

    annual_benefit = saving * price
    net_investment = investment - subsidy
    annual_net_benefit = annual_benefit - annual_om
    return _finite_result({
        "id": scenario_id,
        "type": "通用改造",
        "name": scenario_name,
        "investment": investment,
        "subsidy": subsidy,
        "netInvestment": net_investment,
        "annualElectricitySaving": saving,
        "annualBenefit": annual_benefit,
        "annualOm": annual_om,
        "annualNetBenefit": annual_net_benefit,
        "annualCarbon": saving * factor,
        "payback": net_investment / annual_net_benefit if annual_net_benefit > 0 else None,
        "sourceName": source_name,
        "sourceUrl": source_url,
        "dataDate": data_date,
        "notes": notes,
        "formula": "年节省额 = 年节电量 × 电价；年减碳量 = 年节电量 × 电力排放因子；静态回收期 = 净投资 ÷ 年净收益",
        "calculationEngine": "Python deterministic tool",
    })


def calculate_pv_scenario(
    *,
    capacity_kwp: float,
    annual_yield_kwh_per_kwp: float,
    self_use_ratio: float,
    annual_building_electricity_kwh: float,
    electricity_price_cny_per_kwh: float,
    feed_in_tariff_cny_per_kwh: float,
    carbon_factor_kgco2e_per_kwh: float,
    investment_cny: float,
    subsidy_cny: float,
    annual_om_cny: float,
    source_name: str,
    source_url: str,
    data_date: str,
) -> dict[str, Any]:
    capacity = _non_negative("装机容量", capacity_kwp)
    annual_yield = _non_negative("年发电量系数", annual_yield_kwh_per_kwp)
    ratio = float(self_use_ratio)
    if not 0 <= ratio <= 1:
        raise ValueError("自发自用比例必须在0到1之间")
    baseline = _non_negative("建筑年用电量", annual_building_electricity_kwh)
    price = _non_negative("电价", electricity_price_cny_per_kwh)
    feed_in = _non_negative("余电上网电价", feed_in_tariff_cny_per_kwh)
    factor = _non_negative("电力排放因子", carbon_factor_kgco2e_per_kwh)
    investment = _non_negative("改造总投资", investment_cny)
    subsidy = _non_negative("已确认补贴", subsidy_cny)
    annual_om = _non_negative("年运维成本", annual_om_cny)
    if subsidy > investment:
        raise ValueError("已确认补贴不能大于改造总投资")
    if not all([source_name.strip(), source_url.strip(), data_date.strip()]):
        raise ValueError("光伏方案来源、来源地址和数据日期均不能为空")

    generation = capacity * annual_yield
    self_used = min(generation * ratio, baseline)
    exported = max(0.0, generation - self_used)
    annual_benefit = self_used * price + exported * feed_in
    net_investment = investment - subsidy
    annual_net_benefit = annual_benefit - annual_om
    return _finite_result({
        "id": "pv-tool-result",
        "type": "屋顶光伏",
        "name": "屋顶光伏",
        "investment": investment,
        "subsidy": subsidy,
        "netInvestment": net_investment,
        "annualElectricitySaving": generation,
        "annualBenefit": annual_benefit,
        "annualOm": annual_om,
        "annualNetBenefit": annual_net_benefit,
        "annualCarbon": generation * factor,
        "payback": net_investment / annual_net_benefit if annual_net_benefit > 0 else None,
        "sourceName": source_name,
        "sourceUrl": source_url,
        "dataDate": data_date,
        "notes": (
            f"年发电量 {generation:.2f} kWh；自用 {self_used:.2f} kWh；余电 {exported:.2f} kWh。"
            "减碳量按全部发电量替代同区域电网电量的前提计算，需由项目人员确认该边界。"
        ),
        "formula": "年发电量 = 装机容量 × 年发电量系数；年收益 = 自用电量 × 电价 + 余电量 × 上网电价；年减碳量 = 年发电量 × 电力排放因子",
        "calculationEngine": "Python deterministic tool",
    })
