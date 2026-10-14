from __future__ import annotations

import contextlib
import getpass
import io
import tempfile
import unittest
import json
import importlib.util
import hashlib
from zipfile import ZipFile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch

from scripts import configure_secrets as wizard
from scripts import check_dependencies
from scripts import review_sources
from scripts import verify_customer_demo

ROOT = Path(__file__).resolve().parents[2]
builder_spec = importlib.util.spec_from_file_location("application_builder", ROOT / "tools" / "build_application.py")
application_builder = importlib.util.module_from_spec(builder_spec)
builder_spec.loader.exec_module(application_builder)

EXAMPLE = """# Local-only example
LLM_API_KEY=
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-flash
VISION_MODEL=deepseek-flash
LLM_PROVIDER=deepseek
EMBEDDING_API_KEY=
EMBEDDING_BASE_URL=
EMBEDDING_PROVIDER=dashscope
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIMENSIONS=1024
APP_HOST=127.0.0.1
APP_PORT=8000
"""
EMBED_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.backend = Path(self.temporary.name)
        (self.backend / ".env.example").write_text(EXAMPLE, encoding="utf-8")
        self.target = self.backend / ".env"
        # Deliberately fake test input; no real API secrets or API requests.
        self.fake_key = "sk-" + "TEST_ONLY_" * 3

    def run_configure(self, secrets=("", ""), ordinary=("", ""), stdin=True):
        output = io.StringIO()
        with patch.object(wizard, "BACKEND", self.backend), patch("sys.argv", ["configure_secrets.py"]), \
                patch("sys.stdin.isatty", return_value=stdin), \
                patch("getpass.getpass", side_effect=secrets), patch("builtins.input", side_effect=ordinary), \
                contextlib.redirect_stdout(output):
            wizard.configure()
        return output.getvalue()

    def test_official_embedding_urls_accepted(self):
        for url in (EMBED_URL, EMBED_URL + "/", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
                    "https://dashscope-us.aliyuncs.com/compatible-mode/v1",
                    "https://ws-example.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"):
            with self.subTest(url=url):
                self.assertEqual(wizard.validate_embedding_url(url), url.rstrip("/"))

    def test_wrong_embedding_url_rejected(self):
        for url in ("http://dashscope.aliyuncs.com/compatible-mode/v1", "dashscope.aliyuncs.com",
                    "https://dashscope.aliyuncs.com/api/v1", EMBED_URL + "/embeddings",
                    EMBED_URL + "?key=private", EMBED_URL + "#x", EMBED_URL + ";x",
                    "https://u:p@dashscope.aliyuncs.com/compatible-mode/v1",
                    "https://dashscope.aliyuncs.com.evil.example/compatible-mode/v1",
                    "https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
                    "https:///compatible-mode/v1", "https://dashscope.aliyuncs.com:8888/compatible-mode/v1",
                    "https://dashscope.aliyuncs.com/compatible-mode/v1 x"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                wizard.validate_embedding_url(url)

    def test_deepseek_base_url_accepts_official_forms(self):
        for url in ("https://api.deepseek.com", "https://api.deepseek.com/", "https://api.deepseek.com/v1"):
            self.assertEqual(wizard.validate_llm_url(url), url.rstrip("/"))

    def test_deepseek_base_url_rejects_wrong_provider_or_request_path(self):
        for url in ("http://api.deepseek.com", "https://example.com", "https://api.deepseek.com/chat/completions",
                    "https://api.deepseek.com/responses", "https://api.deepseek.com?key=x"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                wizard.validate_llm_url(url)

    def test_key_syntax_without_display(self):
        self.assertEqual(wizard.validate_key(self.fake_key), self.fake_key)
        for value in ("x", "sk-short", self.fake_key + "\n", self.fake_key + "'", self.fake_key + " "):
            with self.assertRaises(ValueError):
                wizard.validate_key(value)

    def test_env_update_removes_duplicate_active_values_and_preserves_comments(self):
        text = wizard.update_env_text("# KEEP\nLLM_API_KEY=old\nexport LLM_API_KEY=duplicate\nAPP_PORT=18063\n", {"LLM_API_KEY": self.fake_key})
        self.assertEqual(text.count("LLM_API_KEY="), 1)
        self.assertIn("# KEEP", text)
        self.assertIn("APP_PORT=18063", text)
        self.assertEqual(wizard.read_env_values(text)["LLM_API_KEY"], self.fake_key)

    def test_quoted_env_values_round_trip(self):
        value = "local's\\path"
        text = wizard.update_env_text("", {"CHROMA_PATH": value})
        self.assertEqual(wizard.read_env_values(text)["CHROMA_PATH"], value)

    def test_env_update_rejects_control_characters(self):
        with self.assertRaises(ValueError):
            wizard.update_env_text("", {"LLM_API_KEY": "bad\nAPP_HOST=0.0.0.0"})

    def test_first_configuration_needs_no_venv_or_dependencies(self):
        output = self.run_configure((self.fake_key, self.fake_key), (EMBED_URL, ""))
        self.assertTrue(self.target.is_file())
        values = wizard.read_env_values(self.target.read_text(encoding="utf-8"))
        self.assertEqual(values["LLM_API_KEY"], self.fake_key)
        self.assertEqual(values["EMBEDDING_BASE_URL"], EMBED_URL)
        self.assertNotIn(self.fake_key, output)
        self.assertIn("restart", output)
        self.assertIn("syntax only", output)
        self.assertIn("may incur charges", output)
        self.assertFalse((self.backend / ".venv").exists())

    def test_blank_input_preserves_existing_file_exactly(self):
        original = EXAMPLE.replace("LLM_API_KEY=", "LLM_API_KEY='" + self.fake_key + "'")
        self.target.write_bytes(original.encode("utf-8"))
        self.run_configure()
        self.assertEqual(self.target.read_bytes(), original.encode("utf-8"))

    def test_invalid_url_does_not_overwrite_previous_configuration(self):
        original = EXAMPLE.encode("utf-8")
        self.target.write_bytes(original)
        with self.assertRaises(ValueError):
            self.run_configure((self.fake_key, self.fake_key), ("https://dashscope.aliyuncs.com/api/v1", ""))
        self.assertEqual(self.target.read_bytes(), original)

    def test_missing_embedding_base_url_saves_incomplete_with_explicit_warning(self):
        output = self.run_configure(("", self.fake_key))
        self.assertTrue(self.target.exists())
        self.assertIn("INCOMPLETE", output)
        self.assertIn("before RAG can run", output)

    def test_invalid_later_field_does_not_save_earlier_key(self):
        with self.assertRaises(ValueError):
            self.run_configure((self.fake_key, self.fake_key), (EMBED_URL, "https://example.com"))
        self.assertFalse(self.target.exists())

    def test_cancelled_hidden_input_preserves_existing_configuration(self):
        original = EXAMPLE.encode("utf-8")
        self.target.write_bytes(original)
        with self.assertRaises(KeyboardInterrupt):
            self.run_configure((self.fake_key, KeyboardInterrupt()))
        self.assertEqual(self.target.read_bytes(), original)

    def test_noninteractive_input_is_rejected_before_prompt(self):
        with self.assertRaises(RuntimeError):
            self.run_configure(stdin=False)
        self.assertFalse(self.target.exists())

    def test_hidden_input_refuses_getpass_echo_fallback(self):
        with patch.object(wizard, "BACKEND", self.backend), patch("sys.argv", ["configure_secrets.py"]), \
                patch("sys.stdin.isatty", return_value=True), \
                patch("getpass.getpass", side_effect=getpass.GetPassWarning("insecure echo fallback")), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(getpass.GetPassWarning):
            wizard.configure()
        self.assertFalse(self.target.exists())

    def test_command_arguments_are_rejected(self):
        with patch("sys.argv", ["configure_secrets.py", "not-a-key"]), self.assertRaises(RuntimeError):
            wizard.configure()
        self.assertFalse(self.target.exists())

    def test_atomic_write_failure_preserves_file_and_cleans_temporary(self):
        original = EXAMPLE.encode("utf-8")
        self.target.write_bytes(original)
        with patch("os.replace", side_effect=OSError("simulated replace error")), self.assertRaises(OSError):
            wizard.write_env_atomic(self.target, "replacement")
        self.assertEqual(self.target.read_bytes(), original)
        self.assertEqual(list(self.backend.glob(".env.*.tmp")), [])

    def test_older_env_gets_missing_defaults_without_overwriting_custom_fields(self):
        self.target.write_text("APP_PORT=18063\nLLM_MODEL=custom-model\n", encoding="utf-8")
        self.run_configure(("", self.fake_key), (EMBED_URL, ""))
        values = wizard.read_env_values(self.target.read_text(encoding="utf-8"))
        self.assertEqual(values["APP_PORT"], "18063")
        self.assertEqual(values["LLM_MODEL"], "custom-model")
        self.assertEqual(values["LLM_BASE_URL"], "https://api.deepseek.com")

    def test_new_deepseek_key_cannot_reuse_previous_third_party_endpoint(self):
        self.target.write_text("LLM_PROVIDER=other\nLLM_BASE_URL=https://third-party.example/v1\nLLM_MODEL=old-model\nVISION_MODEL=old-vision\n", encoding="utf-8")
        self.run_configure((self.fake_key, ""))
        values = wizard.read_env_values(self.target.read_text(encoding="utf-8"))
        self.assertEqual(values["LLM_PROVIDER"], "deepseek")
        self.assertEqual(values["LLM_BASE_URL"], "https://api.deepseek.com")
        self.assertEqual(values["LLM_MODEL"], "deepseek-flash")
        self.assertEqual(values["VISION_MODEL"], "deepseek-flash")

    def test_new_alibaba_key_cannot_reuse_previous_third_party_endpoint(self):
        original = "EMBEDDING_BASE_URL=https://third-party.example/v1\n"
        self.target.write_text(original, encoding="utf-8")
        with self.assertRaises(ValueError):
            self.run_configure(("", self.fake_key))
        self.assertEqual(self.target.read_text(encoding="utf-8"), original)

    def test_env_quoted_values_accept_trailing_comments(self):
        text = 'LLM_BASE_URL="https://api.deepseek.com" # official endpoint\n'
        text += "EMBEDDING_BASE_URL='" + EMBED_URL + "' # same workspace\n"
        values = wizard.read_env_values(text)
        self.assertEqual(values["LLM_BASE_URL"], "https://api.deepseek.com")
        self.assertEqual(values["EMBEDDING_BASE_URL"], EMBED_URL)

    def test_env_double_quoted_escapes_round_trip_without_interpolation(self):
        values = wizard.read_env_values('CUSTOM_PATH="a\\\\b\\\"c" # comment\nMODEL="${ENV_MODEL}"\n')
        self.assertEqual(values["CUSTOM_PATH"], 'a\\b"c')
        self.assertEqual(values["MODEL"], "${ENV_MODEL}")

    def test_env_malformed_quoted_values_are_not_treated_as_configuration(self):
        values = wizard.read_env_values('LLM_BASE_URL="https://api.deepseek.com" accidental text\nLLM_MODEL="unterminated\n')
        self.assertNotIn("LLM_BASE_URL", values)
        self.assertNotIn("LLM_MODEL", values)

    def test_existing_commented_official_url_is_not_rejected(self):
        self.target.write_text('EMBEDDING_BASE_URL="' + EMBED_URL + '" # same workspace\n', encoding="utf-8")
        self.run_configure(("", self.fake_key))
        values = wizard.read_env_values(self.target.read_text(encoding="utf-8"))
        self.assertEqual(values["EMBEDDING_BASE_URL"], EMBED_URL)

    def test_atomic_flush_failure_preserves_previous_file(self):
        original = EXAMPLE.encode("utf-8")
        self.target.write_bytes(original)
        with patch("os.fsync", side_effect=OSError("simulated flush error")), self.assertRaises(OSError):
            wizard.write_env_atomic(self.target, "replacement")
        self.assertEqual(self.target.read_bytes(), original)
        self.assertEqual(list(self.backend.glob(".env.*.tmp")), [])

    def test_redirected_env_is_rejected_before_reading_or_prompting(self):
        with patch.object(wizard, "BACKEND", self.backend), patch("sys.argv", ["configure_secrets.py"]), \
                patch("sys.stdin.isatty", return_value=True), patch("pathlib.Path.is_symlink", return_value=True), \
                patch("getpass.getpass") as prompt, self.assertRaises(RuntimeError):
            wizard.configure()
        prompt.assert_not_called()


class DistributionSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.requirements = self.root / "requirements.txt"

    def application_fixture(self):
        source = self.root / "fixture_source"
        templates = self.root / "fixture_templates"
        source.mkdir()
        templates.mkdir()
        records = []
        for name in sorted(application_builder.ROOT_ALLOWLIST):
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            content = b"# TEST FIXTURE ONLY\n"
            if name == "backend/.env.example":
                content = b"LLM_API_KEY=\nEMBEDDING_API_KEY=\n"
            elif name.endswith(".py"):
                content = b"pass  # TEST FIXTURE ONLY\n"
            path.write_bytes(content)
            records.append({"path": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
        (source / "release_files.sha256.json").write_text(json.dumps({
            "release_version": application_builder.VERSION, "files": records}), encoding="utf-8")
        for name in application_builder.WRAPPERS:
            (templates / name).write_bytes(b"TEST FIXTURE ONLY\n")
        return source, templates

    def test_dependency_checker_matches_expected_pins_and_imports(self):
        self.requirements.write_text("# fixture only\nfixture-package==1.2.3\n", encoding="utf-8")
        with patch.object(check_dependencies, "version", return_value="1.2.3"), \
                patch.object(check_dependencies.importlib, "import_module") as imports:
            result = check_dependencies.inspect_dependencies(self.requirements)
        self.assertTrue(result["passed"])
        self.assertEqual(imports.call_count, len(check_dependencies.DIRECT_MODULES))

    def test_dependency_checker_detects_missing_package_despite_marker(self):
        self.requirements.write_text("fixture-package==1.2.3\n", encoding="utf-8")
        with patch.object(check_dependencies, "version", side_effect=check_dependencies.PackageNotFoundError), \
                patch.object(check_dependencies.importlib, "import_module") as imports:
            result = check_dependencies.inspect_dependencies(self.requirements)
        self.assertFalse(result["passed"])
        imports.assert_not_called()

    def test_dependency_checker_detects_wrong_package_version(self):
        self.requirements.write_text("fixture-package==1.2.3\n", encoding="utf-8")
        with patch.object(check_dependencies, "version", return_value="9.9.9"):
            self.assertFalse(check_dependencies.inspect_dependencies(self.requirements)["passed"])

    def test_dependency_checker_detects_import_failure_without_exception_contents(self):
        self.requirements.write_text("fixture-package==1.2.3\n", encoding="utf-8")
        with patch.object(check_dependencies, "version", return_value="1.2.3"), \
                patch.object(check_dependencies.importlib, "import_module", side_effect=ImportError("PRIVATE_TEST_DETAIL")):
            result = check_dependencies.inspect_dependencies(self.requirements)
        self.assertFalse(result["passed"])
        self.assertNotIn("PRIVATE_TEST_DETAIL", json.dumps(result))

    def test_dependency_checker_rejects_unpinned_and_empty_requirements(self):
        self.requirements.write_text("fixture-package>=1\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            check_dependencies.inspect_dependencies(self.requirements)
        self.requirements.write_text("# empty\n", encoding="utf-8")
        self.assertFalse(check_dependencies.inspect_dependencies(self.requirements)["passed"])

    def test_source_report_redacts_credentials_before_serialization(self):
        fake = "sk-" + "TEST_ONLY_" * 3
        text = review_sources.redacted_json([{"beginning": "API_KEY=" + fake, "ending": fake}])
        self.assertNotIn(fake, text)
        parsed = json.loads(text)
        self.assertIn("REDACTED", parsed[0]["beginning"])

    def test_source_report_redacts_complete_fake_private_key_block(self):
        fake_block = "-----BEGIN " + "TEST PRIVATE KEY-----\nNOT_A_REAL_KEY_TEST\n-----END " + "TEST PRIVATE KEY-----"
        text = review_sources.redacted_json({"excerpts": [fake_block]})
        self.assertNotIn("NOT_A_REAL_KEY_TEST", text)
        self.assertEqual(json.loads(text)["excerpts"], ["[PRIVATE KEY REDACTED]"])

    def test_source_report_redacts_truncated_fake_private_key_excerpt(self):
        fake_block = "-----BEGIN " + "TEST PRIVATE KEY-----\nNOT_A_REAL_KEY_TEST_PARTIAL"
        text = review_sources.redacted_json({"excerpts": [fake_block]})
        self.assertNotIn("NOT_A_REAL_KEY_TEST_PARTIAL", text)
        self.assertEqual(json.loads(text)["excerpts"], ["[PRIVATE KEY REDACTED]"])

    def test_source_report_redacts_nested_phone_and_identifier_fixture(self):
        phone = "1" + "38" + "0" * 8
        identifier = "110" + "101" + "19900101" + "001" + "X"
        text = review_sources.redacted_json({"nested": [{"value": phone + " " + identifier}], "count": 2})
        self.assertNotIn(phone, text)
        self.assertNotIn(identifier, text)
        self.assertEqual(json.loads(text)["count"], 2)

    def test_live_acceptance_requires_explicit_online_before_any_request(self):
        with patch("sys.argv", ["verify_customer_demo.py"]), \
                patch.object(verify_customer_demo, "request") as request, \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stopped:
            verify_customer_demo.main()
        self.assertEqual(stopped.exception.code, 2)
        request.assert_not_called()

    def test_live_acceptance_rejects_non_loopback_url_before_any_request(self):
        for url in ("https://127.0.0.1:8000", "http://example.com", "http://u:p@127.0.0.1",
                    "http://127.0.0.1/extra", "http://127.0.0.1:8000?token=fixture", "http://127.0.0.1:99999"):
            with self.subTest(url=url), patch("sys.argv", ["verify_customer_demo.py", "--online", "--base-url", url]), \
                    patch.object(verify_customer_demo, "request") as request, \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                verify_customer_demo.main()
            request.assert_not_called()

    def test_windows_archive_paths_reject_special_devices_and_ambiguous_paths(self):
        for name in ("../escape", "C:/escape", "x\\y", "x//y", "./x", "data/templates/CON.txt",
                     "data/templates/COM1", "trailing.", "trailing ", "", "x\x00y", "x?y",
                     "data/templates/.ENV", "data/templates/STORAGE/private.json", "data/templates/.VENV/file"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                application_builder.safe_relative(name)

    def test_windows_archive_paths_accept_actual_public_files(self):
        for name in ("backend/.env.example", "启动演示.ps1", "data/knowledge/policy.md"):
            self.assertEqual(application_builder.safe_relative(name).as_posix(), name)

    def test_application_build_is_reproducible_without_manifest_cycle(self):
        source, templates = self.application_fixture()
        first = self.root / "first.zip"
        second = self.root / "second.zip"
        result = application_builder.build_application(source, templates, first)
        application_builder.build_application(source, templates, second)
        self.assertTrue(result["passed"])
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertFalse((source / "backend" / ".env").exists())
        self.assertFalse((source / "storage").exists())

    def test_application_builder_accepts_blank_crlf_env_template_on_windows(self):
        source, templates = self.application_fixture()
        path = source / "backend/.env.example"
        content = b"LLM_API_KEY=\r\nEMBEDDING_API_KEY=\r\n"
        path.write_bytes(content)
        manifest_path = source / "release_files.sha256.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for record in manifest["files"]:
            if record["path"] == "backend/.env.example":
                record.update(bytes=len(content), sha256=hashlib.sha256(content).hexdigest())
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.assertTrue(application_builder.build_application(source, templates, self.root / "crlf.zip")["passed"])

    def test_application_builder_rejects_stale_file_hash(self):
        source, templates = self.application_fixture()
        (source / "app.js").write_text("changed fixture", encoding="utf-8")
        with self.assertRaises(ValueError):
            application_builder.build_application(source, templates, self.root / "blocked.zip")
        self.assertFalse((self.root / "blocked.zip").exists())

    def test_application_builder_rejects_redirected_wrapper(self):
        source, templates = self.application_fixture()
        original = Path.is_symlink
        with patch("pathlib.Path.is_symlink", lambda path: path.name == "start-app.bat" or original(path)), \
                self.assertRaises(ValueError):
            application_builder.build_application(source, templates, self.root / "blocked.zip")

    def test_application_audit_rejects_inconsistent_manifest_counts(self):
        source, templates = self.application_fixture()
        original = self.root / "first.zip"
        application_builder.build_application(source, templates, original)
        changed = self.root / "changed.zip"
        with ZipFile(original) as archive, ZipFile(changed, "w") as output:
            for entry in archive.infolist():
                content = archive.read(entry.filename)
                if entry.filename.endswith("/" + application_builder.MANIFEST_NAME):
                    manifest = json.loads(content)
                    manifest["zip_file_count"] += 1
                    content = json.dumps(manifest).encode("utf-8")
                output.writestr(entry, content)
        with self.assertRaises(ValueError):
            application_builder.audit_zip(changed)

    def test_application_audit_rejects_symbolic_link_zip_entries(self):
        source, templates = self.application_fixture()
        original = self.root / "first.zip"
        application_builder.build_application(source, templates, original)
        changed = self.root / "changed.zip"
        with ZipFile(original) as archive, ZipFile(changed, "w") as output:
            for entry in archive.infolist():
                content = archive.read(entry.filename)
                if entry.filename.endswith("/app.js"):
                    entry.external_attr = 0o120777 << 16
                output.writestr(entry, content)
        with self.assertRaises(ValueError):
            application_builder.audit_zip(changed)


if __name__ == "__main__":
    unittest.main()
