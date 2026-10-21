"""No-network regression coverage for the local prototype's bounded interfaces."""
import copy
import csv
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from app.agent import LowCarbonAgent
from app.main import app, _cloud_lock
from app.plan_schemas import PlanRequest
from app.plan_service import generate_plan
from app.retrieval import LocalKnowledgeBase
from app.safety import MAX_JSON_BODY_BYTES, parse_tool_json, redact_error
from app.schemas import AgentQueryRequest
from app.document_loader import chunk_text
from test_plan_report import payload, fake_agent
from test_calculators import GENERIC_INPUT, PV_INPUT


def indexed_fixture(folder):
    root = Path(folder)
    source = root / "source.txt"; source.write_text("仅供测试的资料。" * 200, encoding="utf-8")
    manifest = root / "manifest.csv"
    manifest.write_text("document_id,title,category,region,source_url,local_file,acquisition_date\nTEST,T,reference,全国,test:local,source.txt,2026-10-14\n", encoding="utf-8")
    chunks = chunk_text(source.read_text(encoding="utf-8"))
    metadata = {"document_id":"TEST","title":"T","category":"reference","region":"全国",
                "effective_from":"","effective_to":"","issuing_body":"","source_url":"test:local",
                "local_file":str(source.resolve()),"version":"未标注版本","acquisition_date":"2026-10-14",
                "checksum":hashlib.sha256(source.read_bytes()).hexdigest()}
    kb = LocalKnowledgeBase.__new__(LocalKnowledgeBase)
    kb.settings = SimpleNamespace(knowledge_manifest=manifest, embedding_model="TEST", embedding_batch_size=10)
    kb.collection = Mock(); kb.collection.count.return_value = len(chunks)
    kb.collection.get.return_value = {"ids":[str(i) for i in reversed(range(len(chunks)))],
        "metadatas":[{**metadata,"chunk_index":i} for i in reversed(range(len(chunks)))],
        "documents":list(reversed(chunks))}
    kb._embed = Mock(side_effect=lambda texts: [[1.,0.] for _ in texts])
    return kb, chunks


class SafetyV062Tests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict("os.environ", {}, clear=True)
        self.dotenv = patch("app.config.load_dotenv", None)
        self.env.start(); self.dotenv.start()
        self.addCleanup(self.env.stop); self.addCleanup(self.dotenv.stop)
        self.client = TestClient(app, base_url="http://127.0.0.1")

    def test_only_loopback_hosts_and_same_origin_writes(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        for host in ("evil.example", "testserver", "0.0.0.0", "192.168.1.10", "user@127.0.0.1", "127.0.0.1:not-a-port"):
            with self.subTest(host=host):
                self.assertEqual(self.client.get("/api/health", headers={"host": host}).status_code, 400)
        for host in ("localhost:8000", "127.0.0.2:8000", "[::1]:8000"):
            self.assertEqual(self.client.get("/api/health", headers={"host": host}).status_code, 200)
        self.assertEqual(self.client.post("/api/rag/ingest", headers={"origin": "http://evil.example", "host": "evil.example"}).status_code, 400)
        self.assertEqual(self.client.post("/api/rag/ingest", headers={"origin": "https://untrusted.example"}).status_code, 403)

    def test_oversized_json_rejected_before_endpoint_or_cloud(self):
        with patch("app.main.get_agent") as agent:
            response = self.client.post("/api/agent/query", content=b" " * (MAX_JSON_BODY_BYTES + 1), headers={"content-type": "application/json"})
            self.assertEqual(response.status_code, 413)
            agent.assert_not_called()

    def test_chunked_body_without_length_is_bounded(self):
        from app.request_limits import RequestBodyLimitMiddleware
        import asyncio
        async def run():
            downstream, send = Mock(), []
            parts = iter([{"type": "http.request", "body": b"x" * MAX_JSON_BODY_BYTES, "more_body": True},
                          {"type": "http.request", "body": b"x", "more_body": False}])
            async def receive(): return next(parts)
            async def capture(message): send.append(message)
            await RequestBodyLimitMiddleware(downstream)({"type": "http", "method": "POST", "path": "/api/agent/query", "headers": []}, receive, capture)
            downstream.assert_not_called()
            self.assertEqual(send[0]["status"], 413)
        asyncio.run(run())

    def test_nested_nonfinite_context_has_private_safe_422(self):
        response = self.client.post("/api/agent/query", content='{"question":"test","project_context":{"n":1e309}}', headers={"content-type": "application/json"})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("Infinity", response.text)
        self.assertNotIn('"input"', response.text)

    def test_context_depth_and_total_text_bounds(self):
        context = {"x": "end"}
        for _ in range(10): context = {"x": context}
        for invalid in (context, {"x": list(range(129))}, {f"k{i}": "文" * 1000 for i in range(15)}):
            with self.subTest(context_type=type(invalid).__name__), self.assertRaises(ValidationError):
                AgentQueryRequest(question="test", project_context=invalid)

    def test_secret_input_is_rejected_before_any_cloud_operation(self):
        secret = "sk-" + "x" * 32
        with patch("app.main.get_agent") as agent:
            for data in ({"question": secret, "project_context": {}}, {"question": "test", "project_context": {"sourceUrl": secret}}):
                response = self.client.post("/api/agent/query", json=data)
                self.assertEqual(response.status_code, 422)
                self.assertNotIn(secret, response.text)
            agent.assert_not_called()
        data = payload(); data["generic_scenarios"][0]["source_url"] = secret
        with self.assertRaises(ValidationError): PlanRequest.model_validate(data)

    def test_validation_location_does_not_echo_secret_field_name(self):
        secret = "sk-" + "x" * 32
        response = self.client.post("/api/agent/query", json={"question": "test", secret: True})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(secret, response.text)

    def test_duplicate_scenario_ids_are_rejected(self):
        data = payload(); data["comparison_investment"] = None
        data["generic_scenarios"].append(copy.deepcopy(data["generic_scenarios"][0]))
        with self.assertRaisesRegex(ValidationError, "编号不能重复"): PlanRequest.model_validate(data)

    def test_public_numeric_and_plan_consent_require_real_json_types(self):
        for path, fixture, field in (("generic", GENERIC_INPUT, "investment_cny"), ("pv", PV_INPUT, "capacity_kwp")):
            for value in (True, "60000"):
                response = self.client.post("/api/calculate/" + path, json={**fixture, field:value})
                self.assertEqual(response.status_code,422)
            self.assertEqual(self.client.post("/api/calculate/" + path,json=fixture).status_code,200)
        with patch("app.main.get_agent") as agent:
            for value in ("yes", "true", 1):
                request = payload(); request["consent_cloud"] = value
                self.assertEqual(self.client.post("/api/reports/plan",json=request).status_code,422)
            agent.assert_not_called()

    def test_tool_json_rejects_nonfinite_and_duplicate_keys(self):
        for raw in ('{"n":NaN}', '{"n":Infinity}', '{"n":1,"n":2}', '[]'):
            with self.subTest(raw=raw), self.assertRaises(ValueError): parse_tool_json(raw)

    def test_runtime_tool_schema_rejects_bool_and_unknown_fields(self):
        agent = LowCarbonAgent.__new__(LowCarbonAgent); agent.knowledge_base = Mock()
        valid = {"query": "test", "region": None, "category": None, "top_k": 3}
        for invalid in ({**valid, "top_k": True}, {**valid, "extra": "bad"}, {**valid, "category": "unknown"}):
            with self.assertRaises(ValidationError): agent._execute_tool("search_knowledge", invalid)
        agent.knowledge_base.search.assert_not_called()

    def test_excess_tool_calls_stop_before_execution(self):
        agent = LowCarbonAgent.__new__(LowCarbonAgent); agent.settings = SimpleNamespace(llm_model="TEST")
        agent.knowledge_base = Mock(); agent.knowledge_base.count.return_value = 1
        agent._reasoning = Mock(return_value=None); agent._execute_tool = Mock(); agent.client = Mock()
        calls = [SimpleNamespace(type="function_call", name="search_knowledge", arguments='{}', call_id=str(i)) for i in range(5)]
        agent.client.responses.create.return_value = SimpleNamespace(output=calls)
        with self.assertRaisesRegex(RuntimeError, "超过预算"): agent.query("test", {})
        agent._execute_tool.assert_not_called()

    def test_intelligent_operations_share_nonblocking_concurrency_gate(self):
        _cloud_lock.acquire()
        try:
            with patch("app.main.get_agent") as agent:
                self.assertEqual(self.client.post("/api/agent/query", json={"question": "test", "consent_cloud": True}).status_code, 409)
                self.assertEqual(self.client.post("/api/reports/plan", json=payload()).status_code, 409)
                self.assertEqual(self.client.post("/api/rag/ingest").status_code, 409)
                agent.assert_not_called()
        finally: _cloud_lock.release()

    def test_image_signature_and_static_geometry_validated_before_cloud(self):
        with patch("app.main.get_agent") as agent:
            self.assertEqual(self.client.post("/api/vision/analyze", files={"files": ("private.png", b"not an image", "image/png")}).status_code, 422)
            image = io.BytesIO(); Image.new("RGB", (4, 4)).save(image, "PNG")
            self.assertEqual(self.client.post("/api/vision/analyze", files={"files": ("x.jpg", image.getvalue(), "image/jpeg")}).status_code, 422)
            agent.assert_not_called()
            agent.return_value.analyze_images.return_value = {"requires_human_confirmation": True}
            result = self.client.post("/api/vision/analyze", files={"files": ("x.png", image.getvalue(), "image/png")})
            self.assertEqual(result.status_code, 200)
            agent.return_value.analyze_images.assert_called_once()

    def test_vision_analysis_runs_in_threadpool_not_event_loop(self):
        # 照片分析含最长 90 秒同步网络调用；必须移入线程池，否则阻塞全部请求。
        import threading
        captured: list[str] = []

        def fake_analyze(images):
            captured.append(threading.current_thread().name)
            return {"requires_human_confirmation": True}

        with patch("app.main.get_agent") as agent:
            agent.return_value.analyze_images = fake_analyze
            image = io.BytesIO(); Image.new("RGB", (4, 4)).save(image, "PNG")
            result = self.client.post("/api/vision/analyze", files={"files": ("x.png", image.getvalue(), "image/png")})
            self.assertEqual(result.status_code, 200)
            self.assertTrue(captured)
            self.assertNotIn("MainThread", captured[0], "照片分析仍在主线程同步执行")

    def test_query_requires_explicit_cloud_consent_before_initialization(self):
        with patch("app.main.get_agent") as agent:
            for flag in (None, False):
                request = {"question": "test"}
                if flag is not None: request["consent_cloud"] = flag
                self.assertEqual(self.client.post("/api/agent/query", json=request).status_code, 422)
            agent.assert_not_called()

    def test_photo_total_limit_stops_before_cloud(self):
        image = io.BytesIO(); Image.new("RGB", (4, 4)).save(image, "PNG")
        data = image.getvalue()
        with patch("app.main.MAX_TOTAL_IMAGE_BYTES", len(data)), patch("app.main.get_agent") as agent:
            response = self.client.post("/api/vision/analyze", files=[("files", ("a.png", data, "image/png")), ("files", ("b.png", data, "image/png"))])
            self.assertEqual(response.status_code, 422)
            self.assertIn("32MiB", response.text)
            agent.assert_not_called()

    def test_query_tool_cannot_override_explicit_region(self):
        agent = LowCarbonAgent.__new__(LowCarbonAgent); agent.settings = SimpleNamespace(llm_model="TEST")
        agent.knowledge_base = Mock(); agent.knowledge_base.count.return_value = 1
        agent._reasoning = Mock(return_value=None); agent._execute_tool = Mock(return_value={"status":"ok","results":[]}); agent.client = Mock()
        call = SimpleNamespace(type="function_call", name="search_knowledge", arguments=json.dumps({"query":"test","region":None,"category":None,"top_k":3}), call_id="test")
        agent.client.responses.create.side_effect = [SimpleNamespace(output=[call]), SimpleNamespace(output=[],output_text="未找到依据")]
        agent.query("test", {}, "浙江省杭州市")
        self.assertEqual(agent._execute_tool.call_args.args[1]["region"], "浙江省杭州市")

    def test_vision_model_observation_requires_full_typed_fields(self):
        agent = LowCarbonAgent.__new__(LowCarbonAgent); agent.settings = SimpleNamespace(vision_model="TEST")
        agent._reasoning = Mock(return_value=None); agent.client = Mock()
        agent.client.responses.create.return_value = SimpleNamespace(output=[SimpleNamespace(type="function_call", name="record_building_observation", arguments='{"facade_material":"test"}')])
        with self.assertRaises(ValidationError): agent.analyze_images([(b"test", "image/png")])

    def test_errors_hide_pydantic_input_and_provider_authorization(self):
        secret = "sk-" + "x" * 32
        try: AgentQueryRequest(question="x", project_context={"private": "DO_NOT_ECHO"})
        except ValidationError as exc:
            self.assertNotIn("DO_NOT_ECHO", redact_error(exc))
        self.assertNotIn(secret, redact_error(RuntimeError("Bearer " + secret)))
        self.assertNotIn("sensitivepassword", redact_error(RuntimeError("https://name:sensitivepassword@example.org")))

    def test_embedding_response_indices_dimensions_and_values_are_checked(self):
        kb = LocalKnowledgeBase.__new__(LocalKnowledgeBase)
        kb.settings = SimpleNamespace(embedding_model="TEST", embedding_dimensions=2)
        kb.embedding_client = Mock()
        for entries in ([SimpleNamespace(index=0, embedding=[1., 0.])],
                        [SimpleNamespace(index=0, embedding=[1., 0.]), SimpleNamespace(index=0, embedding=[0., 1.])],
                        [SimpleNamespace(index=0, embedding=[float("nan"), 0.]), SimpleNamespace(index=1, embedding=[0., 1.])],
                        [SimpleNamespace(index=0, embedding=[1.]), SimpleNamespace(index=1, embedding=[0., 1.])]):
            kb.embedding_client.embeddings.create.return_value = SimpleNamespace(data=entries)
            with self.assertRaises(ValueError): kb._embed(["one", "two"])
        kb.embedding_client.embeddings.create.return_value = SimpleNamespace(data=[SimpleNamespace(index=1, embedding=[0., 1.]), SimpleNamespace(index=0, embedding=[1., 0.])])
        self.assertEqual(kb._embed(["one", "two"]), [[1., 0.], [0., 1.]])

    def test_embedding_failure_does_not_partially_mutate_document(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / "source.txt").write_text("仅为单元测试。" * 400, encoding="utf-8")
            manifest = root / "manifest.csv"
            with manifest.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle); writer.writerow(["document_id", "title", "category", "region", "source_url", "local_file", "acquisition_date"])
                writer.writerow(["TEST", "TEST", "reference", "全国", "test:local", "source.txt", "2026-10-14"])
            kb = LocalKnowledgeBase.__new__(LocalKnowledgeBase)
            kb.settings = SimpleNamespace(knowledge_manifest=manifest, embedding_batch_size=1, embedding_model="TEST")
            kb.collection = Mock(); kb._embed = Mock(side_effect=[[[1., 0.]], RuntimeError("simulated provider failure")])
            with self.assertRaisesRegex(RuntimeError, "simulated"): kb.ingest_manifest(document_ids={"TEST"})
            kb.collection.upsert.assert_not_called(); kb.collection.delete.assert_not_called()

    def test_unchanged_compares_indexed_documents_by_chunk_index(self):
        with tempfile.TemporaryDirectory() as folder:
            kb, _ = indexed_fixture(folder)
            result = kb.ingest_manifest(document_ids={"TEST"},skip_unchanged=True)
            self.assertEqual(result["unchanged_documents"],1)
            kb._embed.assert_not_called(); kb.collection.upsert.assert_not_called()

    def test_changed_splitter_content_reembeds_even_when_count_and_checksum_match(self):
        with tempfile.TemporaryDirectory() as folder:
            kb, _ = indexed_fixture(folder)
            kb.collection.get.return_value["documents"][0] += "旧分块差异"
            result = kb.ingest_manifest(document_ids={"TEST"},skip_unchanged=True)
            self.assertEqual(result["indexed_documents"],1)
            self.assertEqual(result["unchanged_documents"],0)
            kb._embed.assert_called(); kb.collection.upsert.assert_called_once()

    def test_llm_and_embedding_sdk_disable_implicit_transport_retries(self):
        settings = SimpleNamespace(llm_api_key="UNIT_TEST_NOT_A_SECRET",llm_base_url="https://unit-test.invalid",
                                   embedding_api_key="UNIT_TEST_NOT_A_SECRET",embedding_base_url="https://unit-test.invalid",
                                   embedding_model="TEST",embedding_dimensions=2,embedding_provider="TEST")
        sdk = Mock()
        # Constructor argument coverage only. Importing TLS libraries inside an
        # intentionally empty Windows environment can require absent system paths.
        with patch("app.agent.require_llm_settings"), patch("app.retrieval.require_embedding_settings"), \
                patch.dict("sys.modules", {"openai":SimpleNamespace(OpenAI=sdk), "chromadb":SimpleNamespace(PersistentClient=Mock())}), \
                tempfile.TemporaryDirectory() as folder:
            LowCarbonAgent(settings)
            settings.chroma_path = Path(folder)/"chroma"
            LocalKnowledgeBase(settings)
            self.assertEqual(sdk.call_count,2)
            self.assertTrue(all(call.kwargs["max_retries"] == 0 for call in sdk.call_args_list))

    def test_startup_binding_is_loopback_unless_explicit_linux_container(self):
        from run import validate_bind_host
        for platform in ("win32", "linux", "darwin"):
            for host in ("localhost", "127.0.0.1", "127.0.0.2", "::1"):
                validate_bind_host(host,platform=platform)
            for host in ("evil.example", "192.168.1.10", "0.0.0.0", "::"):
                with self.assertRaises(ValueError): validate_bind_host(host,platform=platform)
        for platform in ("win32", "darwin"):
            with self.assertRaises(ValueError): validate_bind_host("0.0.0.0",platform=platform,allow_container_bind="true")
        validate_bind_host("0.0.0.0",platform="linux",allow_container_bind="true")
        for flag in ("TRUE", "1", "false", ""):
            with self.assertRaises(ValueError): validate_bind_host("0.0.0.0",platform="linux",allow_container_bind=flag)

    def test_absolute_path_is_canonicalized(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); path = root / "inside" / ".." / "outside.txt"
            self.assertEqual(LocalKnowledgeBase._resolve_source(root / "manifest.csv", str(path)), (root / "outside.txt").resolve())

    def test_chunk_overlap_never_exceeds_declared_length(self):
        text = "X" * 1000 + "\n\n" + "Y" * 1200 + "\n\n" + "Z" * 1500
        chunks = chunk_text(text)
        self.assertTrue(chunks)
        self.assertTrue(all(len(item) <= 1200 for item in chunks))
        self.assertIn("Y" * 1200, chunks)

    def test_invalid_chunk_settings_are_rejected(self):
        for kwargs in ({"chunk_size":0}, {"overlap":1200}, {"overlap":-1}, {"chunk_size":True}):
            with self.assertRaises(ValueError): chunk_text("test", **kwargs)

    def test_duplicate_document_ids_stop_before_embedding(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest = Path(folder) / "manifest.csv"
            manifest.write_text("document_id,title,category,region,source_url,local_file,acquisition_date\nTEST,T,reference,全国,test:local,test.txt,2026-10-14\nTEST,T,reference,全国,test:local,test.txt,2026-10-14\n", encoding="utf-8")
            kb = LocalKnowledgeBase.__new__(LocalKnowledgeBase); kb.settings = SimpleNamespace(knowledge_manifest=manifest)
            kb._embed = Mock()
            with self.assertRaisesRegex(ValueError,"重复document_id"): kb.ingest_manifest(document_ids={"TEST"})
            kb._embed.assert_not_called()

    def test_knowledge_secret_is_skipped_before_embedding(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / "source.txt").write_text("sk-" + "x" * 32, encoding="utf-8")
            manifest = root / "manifest.csv"
            manifest.write_text("document_id,title,category,region,source_url,local_file,acquisition_date\nTEST,T,reference,全国,test:local,source.txt,2026-10-14\n", encoding="utf-8")
            kb = LocalKnowledgeBase.__new__(LocalKnowledgeBase)
            kb.settings = SimpleNamespace(knowledge_manifest=manifest, embedding_model="TEST")
            kb.collection = Mock(); kb.collection.count.return_value = 0; kb._embed = Mock()
            result = kb.ingest_manifest(document_ids={"TEST"})
            self.assertEqual(result["indexed_documents"], 0)
            self.assertEqual(len(result["skipped"]), 1)
            kb._embed.assert_not_called(); kb.collection.upsert.assert_not_called()

    def test_retrieved_secret_is_not_sent_to_drafting_model(self):
        agent = fake_agent(); agent.knowledge_base.search.return_value[0]["content"] = "sk-" + "x" * 32
        with self.assertRaisesRegex(ValueError, "密钥"): generate_plan(PlanRequest.model_validate(payload()), agent)
        agent.client.responses.create.assert_not_called()


if __name__ == "__main__": unittest.main()
