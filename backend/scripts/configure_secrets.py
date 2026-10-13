"""Interactive local-only configuration. Never accepts secrets as command arguments."""
from __future__ import annotations

import getpass
import os
import re
import sys
import tempfile
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


def validate_embedding_url(value: str) -> str:
    parsed = urlparse(value)
    host = parsed.hostname or ""
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Embedding Base URL must be HTTPS without credentials, query or fragment.")
    if not (host == "dashscope.aliyuncs.com" or host.endswith(".maas.aliyuncs.com") or host in {"dashscope-intl.aliyuncs.com", "dashscope-us.aliyuncs.com"}):
        raise ValueError("This helper accepts official Alibaba endpoints only. Review other providers before configuring manually.")
    return value.rstrip("/")


def configure() -> None:
    if not sys.stdin.isatty():
        raise RuntimeError("Run this tool in your own interactive terminal. Keys must not be piped or sent as arguments.")
    target = BACKEND / ".env"
    original = (target if target.exists() else BACKEND / ".env.example").read_text(encoding="utf-8-sig")
    updates = {}
    print("Local configuration only. No API requests. Input is hidden. Blank keeps the existing value.")
    for name, prompt in (("LLM_API_KEY", "NEW DeepSeek API key: "), ("EMBEDDING_API_KEY", "Alibaba embedding API key: ")):
        value = getpass.getpass(prompt).strip()
        if value:
            if len(value) < 16 or any(char.isspace() for char in value):
                raise ValueError("Invalid key format. Nothing has been saved.")
            updates[name] = value
    base_url = input("Alibaba embedding Base URL (blank keeps existing): ").strip()
    if base_url:
        updates["EMBEDDING_BASE_URL"] = validate_embedding_url(base_url)
    if not updates:
        print("No changes.")
        return
    text = update_env_text(original, updates)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".env.", suffix=".tmp", dir=BACKEND)
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
    print("Saved to backend/.env. Values are not displayed. Restart the server, then run the online checks.")


if __name__ == "__main__":
    try:
        configure()
    except (Exception, KeyboardInterrupt) as exc:
        print(f"Configuration stopped: {type(exc).__name__}. Check the input and try again; no key will be printed.")
        raise SystemExit(1)
