"""Local stdlib-only configuration; never accepts keys as command arguments."""
from __future__ import annotations

import getpass
import os
import re
import sys
import tempfile
import warnings
from pathlib import Path
from urllib.parse import urlparse

BACKEND = Path(__file__).resolve().parents[1]


def update_env_text(original: str, updates: dict[str, str]) -> str:
    lines = original.splitlines()
    for name, value in updates.items():
        if not re.fullmatch(r"[A-Z_]+", name) or any(char in value for char in "\r\n\x00"):
            raise ValueError("Invalid configuration value")
        replacement = name + "='" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
        matches = [index for index, line in enumerate(lines) if re.match(rf"^\s*(?:export\s+)?{re.escape(name)}\s*=", line)]
        if matches:
            lines[matches[0]] = replacement
            for index in reversed(matches[1:]):
                del lines[index]
        else:
            lines.append(replacement)
    return "\n".join(lines) + "\n"


def read_env_values(text: str) -> dict[str, str]:
    """Read our generated quoted values and simple example values without dotenv."""
    values = {}
    for line in text.splitlines():
        match = re.match(r"^\s*(?:export\s+)?([A-Z_]+)\s*=\s*(.*?)\s*$", line)
        if not match:
            continue
        name, value = match.groups()
        if value.startswith("'") and value.endswith("'"):
            value = re.sub(r"\\(['\\])", r"\1", value[1:-1])
        elif value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        values[name] = value
    return values


def validate_key(value: str) -> str:
    if not re.fullmatch(r"sk-[A-Za-z0-9._-]{12,}", value):
        raise ValueError("Invalid key format. No changes have been saved.")
    return value


def _parse_https_url(value: str):
    parsed = urlparse(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.params
            or any(char.isspace() for char in value) or any(char in value for char in "{}<>\\")):
        raise ValueError("Base URL must be a complete HTTPS address without credentials or placeholders.")
    if parsed.port not in (None, 443):
        raise ValueError("Base URL must use the standard HTTPS port.")
    return parsed


def validate_embedding_url(value: str) -> str:
    parsed = _parse_https_url(value)
    host = parsed.hostname or ""
    if not (host == "dashscope.aliyuncs.com" or host.endswith(".maas.aliyuncs.com")
            or host in {"dashscope-intl.aliyuncs.com", "dashscope-us.aliyuncs.com"}):
        raise ValueError("Use the Alibaba endpoint from the same workspace and region as the embedding key.")
    if parsed.path.rstrip("/") != "/compatible-mode/v1":
        raise ValueError("Embedding Base URL must end in /compatible-mode/v1, not /api/v1 or /embeddings.")
    return value.rstrip("/")


def validate_llm_url(value: str) -> str:
    parsed = _parse_https_url(value)
    if parsed.hostname != "api.deepseek.com" or parsed.path.rstrip("/") not in ("", "/v1"):
        raise ValueError("Use the official DeepSeek Base URL https://api.deepseek.com.")
    return value.rstrip("/")


def write_env_atomic(target: Path, text: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=".env.", suffix=".tmp", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        if os.name != "nt":
            temporary.chmod(0o600)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def configure() -> None:
    if len(sys.argv) > 1:
        raise RuntimeError("No command arguments are accepted. Enter keys only at the hidden prompts.")
    if not sys.stdin.isatty():
        raise RuntimeError("Run this tool in your own interactive terminal. Never pipe keys into it.")
    target = BACKEND / ".env"
    example = (BACKEND / ".env.example").read_text(encoding="utf-8-sig")
    original = target.read_text(encoding="utf-8-sig") if target.exists() else example
    existing = read_env_values(original)
    defaults = read_env_values(example)
    updates = {}
    print("Local configuration only; no API requests or paid calls are made.")
    print("Keys are hidden. Blank keeps existing values; it does not erase them.")
    print("DeepSeek key is for LLM_API_KEY; Alibaba key is for EMBEDDING_API_KEY. Do not swap them.")
    print("A NEW DeepSeek key selects the official DeepSeek provider/Base URL and deepseek-flash models.")
    # Refuse getpass's insecure echoing fallback, even on an unusual terminal.
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        for name, prompt in (("LLM_API_KEY", "NEW DeepSeek API key (hidden): "),
                             ("EMBEDDING_API_KEY", "Alibaba embedding API key (hidden): ")):
            value = getpass.getpass(prompt).strip()
            if value:
                updates[name] = validate_key(value)
                if name == "LLM_API_KEY":
                    # Never send a newly supplied DeepSeek key to an old third-party endpoint.
                    updates.update(LLM_PROVIDER="deepseek", LLM_BASE_URL="https://api.deepseek.com",
                                   LLM_MODEL="deepseek-flash", VISION_MODEL="deepseek-flash")
                else:
                    updates["EMBEDDING_PROVIDER"] = "dashscope"
    base_url = input("Alibaba Base URL /compatible-mode/v1 (blank keeps existing): ").strip()
    if base_url:
        updates["EMBEDDING_BASE_URL"] = validate_embedding_url(base_url)
    llm_url = input("DeepSeek Base URL (blank keeps existing or https://api.deepseek.com): ").strip()
    if llm_url:
        updates["LLM_BASE_URL"] = validate_llm_url(llm_url)
    if not updates:
        print("No changes. Local calculations and the fixed example PDF do not need keys.")
        return
    # Fill absent ordinary defaults in an older .env, without overwriting custom values.
    for name in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL", "VISION_MODEL", "LLM_REASONING_EFFORT",
                 "EMBEDDING_PROVIDER", "EMBEDDING_MODEL", "EMBEDDING_DIMENSIONS", "EMBEDDING_BATCH_SIZE",
                 "APP_HOST", "APP_PORT"):
        if not existing.get(name) and name not in updates and defaults.get(name):
            updates[name] = defaults[name]
    effective = existing | updates
    if effective.get("LLM_API_KEY") and ("LLM_API_KEY" in updates or "LLM_BASE_URL" in updates):
        validate_llm_url(effective.get("LLM_BASE_URL", ""))
    embedding_changed = "EMBEDDING_API_KEY" in updates or "EMBEDDING_BASE_URL" in updates
    if effective.get("EMBEDDING_API_KEY") and embedding_changed and effective.get("EMBEDDING_BASE_URL"):
        validate_embedding_url(effective["EMBEDDING_BASE_URL"])
    # All validation finishes before touching the existing file.
    write_env_atomic(target, update_env_text(original, updates))
    print("Saved to backend/.env. Values are not displayed; .env remains private and Git-ignored.")
    print("Stop and restart the server. Existing processes do not reload changed keys automatically.")
    print("This checks syntax only, not key validity, model access, region, balance, or cloud connectivity.")
    if effective.get("EMBEDDING_API_KEY") and not effective.get("EMBEDDING_BASE_URL"):
        print("Embedding configuration is INCOMPLETE: add the matching workspace HTTPS Base URL before RAG can run.")
    print("Online indexing and AI use your own accounts, upload selected document text, and may incur charges.")
    print("Existing process environment variables take precedence over backend/.env; remove conflicting variables if needed.")


if __name__ == "__main__":
    try:
        configure()
    except (Exception, KeyboardInterrupt) as exc:
        # Exception text might contain operator input: expose its class only.
        print(f"Configuration stopped: {type(exc).__name__}. Check the input and retry; no key will be printed.")
        print("Use an interactive terminal and do not supply keys as arguments. Keys must begin with sk-.")
        print("Alibaba Base URL: complete HTTPS address ending /compatible-mode/v1; DeepSeek: https://api.deepseek.com.")
        raise SystemExit(1)
