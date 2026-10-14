import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from unittest.mock import Mock
from types import SimpleNamespace
from fastapi.testclient import TestClient
from app.main import app
from app.knowledge_catalog import build_catalog, reviewed_ids
from app.document_loader import extract_text


class CustomerDemoTests(unittest.TestCase):
    def test_malformed_tool_json_is_not_executed_and_can_retry(self):
        from app.agent import LowCarbonAgent
        agent = LowCarbonAgent.__new__(LowCarbonAgent)
        agent.settings = SimpleNamespace(llm_model="TEST")
        agent.knowledge_base = Mock()
        agent.knowledge_base.count.return_value = 1
        agent._reasoning = Mock(return_value=None)
        agent._execute_tool = Mock(return_value={"status":"ok","results":[]})
        agent.client = Mock()
        malformed = SimpleNamespace(type="function_call", name="search_knowledge", arguments='{"query":undefined}',call_id="bad")
        valid = SimpleNamespace(type="function_call", name="search_knowledge", arguments='{"query":"test","region":null,"category":null,"top_k":3}',call_id="good")
        agent.client.responses.create.side_effect = [SimpleNamespace(output=[malformed]), SimpleNamespace(output=[valid]), SimpleNamespace(output=[],output_text="未找到依据")]
        result = agent.query("test", {})
        self.assertEqual(agent._execute_tool.call_count, 1)
        self.assertEqual(result["tool_results"][0]["result"]["status"], "error")
        self.assertEqual(result["answer"], "未找到依据")

    def test_watermark_only_pdf_is_not_real_knowledge(self):
        import pymupdf
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "watermarks.pdf"
            with pymupdf.open() as pdf:
                for _ in range(20):
                    page = pdf.new_page()
                    page.insert_text((40, 40), "住房城乡建设部信息公开 浏览专用", fontname="china-s")
                pdf.save(path)
            with self.assertRaisesRegex(ValueError, "OCR"):
                extract_text(path)

    def test_ingest_endpoint_requires_review_before_cloud_access(self):
        with patch("app.main.reviewed_ids", side_effect=ValueError("资料已变更")), patch("app.main.get_knowledge_base") as kb:
            response = TestClient(app, base_url="http://127.0.0.1").post("/api/rag/ingest")
            self.assertEqual(response.status_code, 400)
            kb.assert_not_called()

    def test_ingest_endpoint_sends_only_reviewed_ids(self):
        with patch("app.main.reviewed_ids", return_value={"approved"}), patch("app.main.get_knowledge_base") as kb:
            kb.return_value.ingest_manifest.return_value = {"indexed_documents": 1}
            self.assertEqual(TestClient(app, base_url="http://127.0.0.1").post("/api/rag/ingest").status_code, 200)
            kb.return_value.ingest_manifest.assert_called_once_with(document_ids={"approved"}, skip_unchanged=True)

    def test_review_hash_prevents_silent_file_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data = root / "数据收集包"
            data.mkdir()
            source = data / "public.txt"
            source.write_text("public source", encoding="utf-8")
            manifest = data / "manifest.csv"
            manifest.write_text("document_id,local_file,source_url\nDOC1,public.txt,https://example.gov.cn\n", encoding="utf-8")
            review = root / "review.json"
            review.write_text(json.dumps({"documents":[{"document_id":"DOC1","checksum":hashlib.sha256(source.read_bytes()).hexdigest(),"source_url":"https://example.gov.cn"}]}), encoding="utf-8")
            with patch("app.knowledge_catalog.PROJECT_ROOT", root):
                self.assertEqual(reviewed_ids(manifest, review), {"DOC1"})
                source.write_text("changed", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "变更"):
                    reviewed_ids(manifest, review)

    def test_catalog_does_not_leak_local_paths_or_overcount_partial_index(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = root / "manifest.csv"
            manifest.write_text("document_id,category,region\nDOC1,policy,全国\n", encoding="utf-8")
            record = {"document_id":"DOC1","title":"Test","source_url":"https://example.gov.cn","local_file":"PRIVATE_PATH", "checksum":"abc","status":"parseable","chunks":3}
            with patch("app.knowledge_catalog.audit_manifest", return_value={"records":[record]}):
                result = build_catalog(manifest,[{"document_id":"DOC1","checksum":"abc"}], root / "absent.json")
            self.assertEqual(result["indexed_documents"], 0)
            self.assertNotIn("PRIVATE_PATH", json.dumps(result))

    def test_static_allowlist_never_exposes_credentials_and_storage(self):
        client = TestClient(app, base_url="http://127.0.0.1")
        for path in ("/backend/.env", "/.env", "/storage/chroma/chroma.sqlite3", "/data/knowledge/reviewed_documents.json"):
            self.assertEqual(client.get(path).status_code, 404)
        self.assertEqual(client.get("/client-ui.js").status_code, 200)


if __name__ == "__main__":
    unittest.main()
