from __future__ import annotations

import tempfile
import unittest
import csv
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

from fastapi.testclient import TestClient
from app.document_loader import extract_text
from app.main import app, _public_error
from app.retrieval import _region_matches, LocalKnowledgeBase
from scripts.configure_secrets import update_env_text, validate_embedding_url


class DeliveryV04Tests(unittest.TestCase):
    def test_assumption_fixture_cannot_claim_to_be_actual_evidence(self):
        data = TestClient(app).get("/api/demo/assumptions").json()
        self.assertEqual(data["data_nature"], "assumption")
        self.assertIn("不是望月公寓", data["notice"])
        self.assertTrue(data["fields"]["generic-url"].startswith("assumption:"))
        actual = TestClient(app).get("/api/demo/case").json()
        self.assertNotIn("annual_electricity_kwh", actual["safe_prefill"])

    def test_sensitivity_is_explicit_and_arithmetically_correct(self):
        response = TestClient(app).post("/api/calculate/sensitivity", json={
            "scenario_id": "test", "scenario_name": "assumption",
            "investment_cny": 60000, "subsidy_cny": 0, "annual_energy_saving_kwh": 12000,
            "electricity_price_cny_per_kwh": 0.538, "carbon_factor_kgco2e_per_kwh": 0.5,
            "annual_om_cny": 300, "source_name": "TEST ONLY", "source_url": "assumption:test", "data_date": "2026-10-12"})
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["data_nature"], "assumption")
        self.assertEqual(result["scenarios"][1]["result"]["annualNetBenefit"], 6156)
        self.assertGreater(result["scenarios"][0]["result"]["payback"], result["scenarios"][2]["result"]["payback"])

    def test_html_extraction_excludes_script_and_style(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "official.html"
            path.write_text("<script>DO_NOT_INCLUDE</script><style>NO_CSS</style><p>公开政策正文" + "测试文本" * 30 + "</p>", encoding="utf-8")
            text = extract_text(path)
            self.assertNotIn("DO_NOT_INCLUDE", text)
            self.assertNotIn("NO_CSS", text)
            self.assertIn("公开政策正文", text)

    def test_compound_regions_match_without_matching_unknown(self):
        self.assertTrue(_region_matches("全国/华东区域/浙江省等", "浙江省 杭州市"))
        self.assertTrue(_region_matches("浙江省/杭州市", "浙江省 杭州市"))
        self.assertFalse(_region_matches("北京市", "浙江省 杭州市"))
        self.assertFalse(_region_matches("", "浙江省 杭州市"))

    def test_region_formatting_notes_preserve_same_city(self):
        self.assertTrue(_region_matches('浙江省杭州市','浙江省 杭州市（场景设定）'))
        self.assertTrue(_region_matches('浙江省\u00a0杭州市','浙江省\u3000杭州市(假设案例)'))
        self.assertTrue(_region_matches('浙江省/杭州市','浙江省杭州市上城区'))

    def test_region_hierarchy_does_not_broaden_city_or_district_rules(self):
        self.assertTrue(_region_matches('浙江省','浙江省杭州市上城区'))
        self.assertTrue(_region_matches('浙江省杭州市','浙江省杭州市上城区'))
        self.assertFalse(_region_matches('浙江省杭州市','浙江省'))
        self.assertFalse(_region_matches('浙江省杭州市上城区','浙江省杭州市'))
        self.assertFalse(_region_matches('浙江省/杭州市','浙江省宁波市'))

    def test_region_cross_city_province_and_district_do_not_match(self):
        for document, project in [('浙江省杭州市','浙江省宁波市'),('浙江省温州市','浙江省杭州市'),
                                  ('浙江省杭州市','江苏省杭州市'),('浙江省杭州市上城区','浙江省杭州市余杭区'),
                                  ('北京市','浙江省杭州市'),('北京市海淀区','北京市朝阳区')]:
            with self.subTest(document=document,project=project):
                self.assertFalse(_region_matches(document,project))

    def test_region_bracketed_administrative_scope_and_unknown_labels(self):
        self.assertTrue(_region_matches('浙江省杭州市（上城区）','浙江省杭州市上城区'))
        self.assertFalse(_region_matches('浙江省杭州市（上城区）','浙江省杭州市余杭区'))
        for document, project in [('未知地区','未知地区'),('浙江省','杭州'),('杭州市','浙江省杭州市'),
                                  ('华东区域','浙江省杭州市'),('浙江省杭州市','未知')]:
            with self.subTest(document=document,project=project):
                self.assertFalse(_region_matches(document,project))
        self.assertTrue(_region_matches('全国','未知'))
        self.assertTrue(_region_matches('全国/华东区域/浙江省等','浙江省杭州市'))

    def test_region_municipality_and_full_names_without_guessing_aliases(self):
        self.assertTrue(_region_matches('北京市','北京市海淀区'))
        self.assertTrue(_region_matches('重庆市/江北区','重庆市江北区'))
        self.assertFalse(_region_matches('重庆市/江北区','重庆市渝北区'))
        self.assertTrue(_region_matches('台湾省','台湾省台北市'))
        self.assertTrue(_region_matches('浙江省（全省）','浙江省杭州市'))
        self.assertFalse(_region_matches('浙江省','浙/杭州'))
        self.assertFalse(_region_matches('台湾','台湾省台北市'))
        self.assertFalse(_region_matches('全省','浙江省杭州市'))
        self.assertFalse(_region_matches('浙江省/未知区县','浙江省杭州市上城区'))
        self.assertFalse(_region_matches('浙江省/上城区','浙江省杭州市上城区'))

    def test_region_filter_selects_local_document_before_embedding(self):
        kb=LocalKnowledgeBase.__new__(LocalKnowledgeBase);kb.collection=Mock()
        kb.collection.count.return_value=3
        metadata=[{'document_id':'hz','region':'浙江省杭州市','category':'policy'},
                  {'document_id':'nb','region':'浙江省宁波市','category':'policy'},
                  {'document_id':'unknown','region':'未知','category':'policy'}]
        kb.collection.get.return_value={'metadatas':metadata}
        kb._embed=Mock(return_value=[[1.,0.]])
        kb.collection.query.return_value={'documents':[['公开测试内容']], 'metadatas':[[metadata[0]]], 'distances':[[.1]]}
        result=kb.search('公共建筑改造',region='浙江省 杭州市（场景设定）',category='policy')
        self.assertEqual(kb.collection.query.call_args.kwargs['where'],{'document_id':{'$in':['hz']}})
        self.assertEqual(result[0]['document_id'],'hz')

    def test_secret_config_update_preserves_unrelated_settings(self):
        text = update_env_text("# comment\nAPP_PORT=8000\nLLM_API_KEY=\nLLM_API_KEY=old\n", {"LLM_API_KEY": "UNIT_TEST_NOT_A_SECRET"})
        self.assertEqual(text.count("LLM_API_KEY="), 1)
        self.assertIn("APP_PORT=8000", text)
        self.assertIn("# comment", text)

    def test_retrieval_filters_before_vector_search(self):
        kb = LocalKnowledgeBase.__new__(LocalKnowledgeBase)
        kb.collection = Mock()
        kb.collection.count.return_value = 40
        selected = {"document_id": "eligible", "category": "policy", "region": "浙江省/杭州市"}
        kb.collection.get.return_value = {"metadatas": [selected,
            {"document_id": "wrong-region", "category": "policy", "region": "北京市"},
            {"document_id": "expired", "category": "policy", "region": "全国", "effective_to": "2000-01-01"},
            {"document_id": "wrong-category", "category": "tariff", "region": "全国"}]}
        kb._embed = Mock(return_value=[[1.0, 0.0]])
        kb.collection.query.return_value = {"documents": [["测试条文"]], "metadatas": [[selected]], "distances": [[0.1]]}
        result = kb.search("测试", region="浙江省 杭州市", category="政策")
        self.assertEqual(kb.collection.query.call_args.kwargs["where"], {"document_id": {"$in": ["eligible"]}})
        self.assertEqual(kb.collection.query.call_args.kwargs["n_results"], 1)
        self.assertEqual(result[0]["document_id"], "eligible")

    def test_ingestion_uploads_only_explicitly_selected_documents(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "selected.txt").write_text("纯测试文本，不是工程证据。" * 30, encoding="utf-8")
            manifest = root / "manifest.csv"
            headers = ["document_id", "title", "category", "region", "source_url", "local_file", "acquisition_date"]
            with manifest.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(headers)
                writer.writerow(["selected", "TEST", "factor", "全国", "test:local", "selected.txt", "2026-10-12"])
                writer.writerow(["not-authorized", "TEST", "factor", "全国", "test:local", "absent.txt", "2026-10-12"])
            kb = LocalKnowledgeBase.__new__(LocalKnowledgeBase)
            kb.settings = SimpleNamespace(knowledge_manifest=manifest, embedding_batch_size=10, embedding_model="TEST")
            kb.collection = Mock()
            kb.collection.count.return_value = 1
            kb.collection.get.return_value = {"ids": []}
            kb._embed = Mock(side_effect=lambda texts: [[1.0, 0.0] for _ in texts])
            result = kb.ingest_manifest(document_ids={"selected"})
            self.assertEqual(result["indexed_documents"], 1)
            self.assertEqual(result["skipped"], [])
            metadata = kb.collection.upsert.call_args.kwargs["metadatas"]
            self.assertEqual({item["document_id"] for item in metadata}, {"selected"})
            kb._embed.reset_mock()
            with self.assertRaises(ValueError):
                kb.ingest_manifest(document_ids={"unknown"})
            kb._embed.assert_not_called()

    def test_secret_helper_rejects_non_official_and_non_https_urls(self):
        for url in ("http://example.com", "https://evil.example", "https://a.maas.aliyuncs.com/?token=123"):
            with self.assertRaises(ValueError):
                validate_embedding_url(url)
        self.assertEqual(validate_embedding_url("https://example.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"), "https://example.cn-beijing.maas.aliyuncs.com/compatible-mode/v1")

    def test_api_error_redacts_credentials(self):
        with patch("app.main.get_settings") as settings:
            settings.return_value.llm_api_key = "UNIT_TEST_SECRET"
            settings.return_value.embedding_api_key = ""
            self.assertNotIn("UNIT_TEST_SECRET", _public_error(RuntimeError("Invalid UNIT_TEST_SECRET")))

    def test_cross_site_writes_are_rejected(self):
        response = TestClient(app).post("/api/rag/ingest", headers={"Origin": "https://untrusted.example"})
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
