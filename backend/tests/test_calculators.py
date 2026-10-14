from __future__ import annotations

import unittest
import json

from fastapi.testclient import TestClient

from app.calculators import calculate_generic_scenario, calculate_pv_scenario
from app.main import app


GENERIC_INPUT = {
    "scenario_id": "test-finite", "scenario_name": "Assumed test scenario",
    "investment_cny": 60000, "subsidy_cny": 0,
    "annual_energy_saving_kwh": 12000, "electricity_price_cny_per_kwh": 0.538,
    "carbon_factor_kgco2e_per_kwh": 0.5, "annual_om_cny": 300,
    "source_name": "TEST ASSUMPTIONS", "source_url": "assumption:finite-test",
    "data_date": "2026-10-13",
}
PV_INPUT = {
    "capacity_kwp": 10, "annual_yield_kwh_per_kwp": 1000,
    "self_use_ratio": 0.8, "annual_building_electricity_kwh": 100000,
    "electricity_price_cny_per_kwh": 0.538, "feed_in_tariff_cny_per_kwh": 0.3,
    "carbon_factor_kgco2e_per_kwh": 0.5, "investment_cny": 60000,
    "subsidy_cny": 0, "annual_om_cny": 300,
    "source_name": "TEST ASSUMPTIONS", "source_url": "assumption:finite-test",
    "data_date": "2026-10-13",
}


class CalculatorTests(unittest.TestCase):
    def test_direct_tools_reject_nonfinite_values(self) -> None:
        for function, fixture, field in (
            (calculate_generic_scenario, GENERIC_INPUT, "investment_cny"),
            (calculate_pv_scenario, PV_INPUT, "capacity_kwp"),
        ):
            for value in (float("inf"), float("-inf"), float("nan")):
                with self.subTest(function=function.__name__, value=value):
                    with self.assertRaises(ValueError):
                        function(**{**fixture, field: value})

    def test_direct_tools_reject_finite_input_overflow(self) -> None:
        with self.assertRaises(ValueError):
            calculate_generic_scenario(**{**GENERIC_INPUT, "annual_energy_saving_kwh": 1e308,
                                          "electricity_price_cny_per_kwh": 2})
        with self.assertRaises(ValueError):
            calculate_pv_scenario(**{**PV_INPUT, "capacity_kwp": 1e308,
                                     "annual_yield_kwh_per_kwp": 2})

    def test_api_rejects_overflowing_json_number_without_500(self) -> None:
        client = TestClient(app, base_url="http://127.0.0.1")
        for route, fixture, field in (("generic", GENERIC_INPUT, "investment_cny"),
                                      ("pv", PV_INPUT, "capacity_kwp")):
            body = json.dumps({**fixture, field: "OVERFLOW"}).replace('"OVERFLOW"', "1e309")
            with self.subTest(route=route):
                response = client.post("/api/calculate/" + route, content=body,
                                       headers={"Content-Type": "application/json"})
                self.assertEqual(response.status_code, 422)
                self.assertTrue(any(field in error["loc"] for error in response.json()["detail"]))
                self.assertTrue(all("input" not in error for error in response.json()["detail"]))

    def test_api_returns_bad_input_for_computation_overflow(self) -> None:
        client = TestClient(app, base_url="http://127.0.0.1")
        for route, payload in (
            ("generic", {**GENERIC_INPUT, "annual_energy_saving_kwh": 1e308, "electricity_price_cny_per_kwh": 2}),
            ("pv", {**PV_INPUT, "capacity_kwp": 1e308, "annual_yield_kwh_per_kwp": 2}),
        ):
            with self.subTest(route=route):
                response = client.post("/api/calculate/" + route, json=payload)
                self.assertEqual(response.status_code, 422)
                self.assertIn("数量级", response.json()["detail"])

    def test_generic_uses_only_supplied_values(self) -> None:
        result = calculate_generic_scenario(
            scenario_id="verified-1",
            scenario_name="verified scenario",
            investment_cny=1000,
            subsidy_cny=100,
            annual_energy_saving_kwh=200,
            electricity_price_cny_per_kwh=1,
            carbon_factor_kgco2e_per_kwh=0.5,
            annual_om_cny=20,
            source_name="source",
            source_url="archive/source.pdf",
            data_date="2026-01-01",
        )
        self.assertEqual(result["netInvestment"], 900)
        self.assertEqual(result["annualNetBenefit"], 180)
        self.assertEqual(result["annualCarbon"], 100)
        self.assertEqual(result["payback"], 5)

    def test_pv_caps_self_consumption_at_building_demand(self) -> None:
        result = calculate_pv_scenario(
            capacity_kwp=10,
            annual_yield_kwh_per_kwp=1000,
            self_use_ratio=1,
            annual_building_electricity_kwh=6000,
            electricity_price_cny_per_kwh=1,
            feed_in_tariff_cny_per_kwh=0.4,
            carbon_factor_kgco2e_per_kwh=0.5,
            investment_cny=10000,
            subsidy_cny=0,
            annual_om_cny=0,
            source_name="source",
            source_url="archive/source.pdf",
            data_date="2026-01-01",
        )
        self.assertEqual(result["annualBenefit"], 7600)
        self.assertEqual(result["annualCarbon"], 5000)

    def test_rejects_subsidy_greater_than_investment(self) -> None:
        with self.assertRaises(ValueError):
            calculate_generic_scenario(
                scenario_id="bad",
                scenario_name="bad",
                investment_cny=100,
                subsidy_cny=101,
                annual_energy_saving_kwh=1,
                electricity_price_cny_per_kwh=1,
                carbon_factor_kgco2e_per_kwh=1,
                annual_om_cny=0,
                source_name="source",
                source_url="source",
                data_date="2026-01-01",
            )


if __name__ == "__main__":
    unittest.main()
