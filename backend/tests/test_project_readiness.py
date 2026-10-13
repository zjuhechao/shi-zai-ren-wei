from __future__ import annotations

import csv
import json
import unittest
from datetime import date
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import PROJECT_ROOT, get_settings
from app.main import app
from app.retrieval import LocalKnowledgeBase, _validity


class ProjectReadinessTests(unittest.TestCase):
    def test_validity_does_not_treat_missing_dates_as_current(self) -> None:
        today = date(2026, 10, 12)
        self.assertEqual(_validity({}, today), "unverified")
        self.assertEqual(_validity({"effective_to": "2025-12-31"}, today), "outside_recorded_interval")
        self.assertEqual(_validity({"effective_from": "2027-01-01"}, today), "outside_recorded_interval")
        self.assertEqual(_validity({"effective_from": "2026-01-01", "effective_to": "2026-12-31"}, today), "within_recorded_interval")
        self.assertEqual(_validity({"effective_to": "长期"}, today), "unverified")

    def test_default_route_is_deepseek_with_independent_embeddings(self) -> None:
        with patch.dict("os.environ", {}, clear=True), patch("app.config.load_dotenv", None):
            settings = get_settings()
        self.assertEqual(settings.llm_provider, "deepseek")
        self.assertEqual(settings.llm_base_url, "https://api.deepseek.com")
        self.assertEqual(settings.llm_model, "deepseek-flash")
        self.assertEqual(settings.embedding_model, "")
        self.assertFalse(settings.api_configured)
        self.assertFalse(settings.embeddings_configured)
        env_example = (PROJECT_ROOT / "backend" / ".env.example").read_text(encoding="utf-8")
        self.assertIn("EMBEDDING_MODEL=text-embedding-v4", env_example)

    def test_agent_endpoint_stops_when_knowledge_is_unavailable(self) -> None:
        with patch("app.main.get_knowledge_base", side_effect=RuntimeError("RAG not configured")):
            response = TestClient(app).post("/api/agent/query", json={"question": "test", "project_context": {}})
        self.assertEqual(response.status_code, 400)
        self.assertIn("RAG not configured", response.json()["detail"])

    def test_manifest_files_resolve_from_the_merged_data_pack(self) -> None:
        settings = get_settings()
        with settings.knowledge_manifest.open("r", encoding="utf-8-sig", newline="") as handle:
            manifest = list(csv.DictReader(handle))
        first_local = next(item["local_file"] for item in manifest if item.get("local_file"))
        resolved = LocalKnowledgeBase._resolve_source(settings.knowledge_manifest, first_local)
        self.assertTrue(resolved.exists())

    def test_demo_case_does_not_invent_blocking_values(self) -> None:
        case = json.loads((PROJECT_ROOT / "data" / "cases" / "wangyue_case.json").read_text(encoding="utf-8"))
        safe = case["safe_prefill"]
        self.assertNotIn("annual_electricity_kwh", safe)
        self.assertNotIn("electricity_price_cny_per_kwh", safe)
        self.assertNotIn("investment_cny", safe)
        self.assertNotIn("annual_energy_saving_kwh", safe)
        self.assertGreaterEqual(len(case["blocking_inputs"]), 5)

    def test_public_routes_and_deterministic_calculator(self) -> None:
        client = TestClient(app)
        health = client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertTrue(health.json()["manifest_found"])

        demo_case = client.get("/api/demo/case")
        self.assertEqual(demo_case.status_code, 200)
        self.assertEqual(demo_case.json()["case_id"], "wangyue-2026-10-12")

        result = client.post(
            "/api/calculate/generic",
            json={
                "scenario_id": "unit-test",
                "scenario_name": "unit test",
                "investment_cny": 20000,
                "subsidy_cny": 0,
                "annual_energy_saving_kwh": 12000,
                "electricity_price_cny_per_kwh": 0.538,
                "carbon_factor_kgco2e_per_kwh": 0.4974,
                "annual_om_cny": 0,
                "source_name": "test",
                "source_url": "local:test",
                "data_date": "2026-10-12",
            },
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["annualBenefit"], 6456)
        self.assertEqual(result.json()["annualCarbon"], 5968.8)


if __name__ == "__main__":
    unittest.main()
