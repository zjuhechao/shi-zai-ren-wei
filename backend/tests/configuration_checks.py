from __future__ import annotations

import contextlib
import getpass
import io
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch

from scripts import configure_secrets as wizard

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


if __name__ == "__main__":
    unittest.main()
