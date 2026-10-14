"""Local-prototype boundaries; these do not replace hosted-service authentication."""
from __future__ import annotations

import json
import math
import re
from typing import Any


API_VERSION = "0.6.2"
MAX_CONTEXT_BYTES = 32 * 1024
MAX_JSON_BODY_BYTES = 128 * 1024
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_IMAGE_BYTES = 32 * 1024 * 1024
MAX_IMAGE_BODY_BYTES = 51 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
MAX_TOOL_CALLS = 16
MAX_TOOL_CALLS_PER_ROUND = 4

# Detect likely credentials, not ordinary measurements or provenance identifiers.
_CREDENTIAL = re.compile(
    r"sk-[A-Za-z0-9_.\-/=+]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"
)


def reject_credentials(value: Any) -> None:
    serialized = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, allow_nan=False)
    if _CREDENTIAL.search(serialized):
        raise ValueError("输入疑似包含密钥或私钥，请删除后重试；未发送到云端")


def redact_error(exc: Exception, secrets: tuple[str, ...] = ()) -> str:
    # Pydantic's formatted exceptions include rejected input. Return messages only.
    try:
        from pydantic import ValidationError
        if isinstance(exc, ValidationError):
            message = "；".join(item["msg"] for item in exc.errors(include_input=False))
        else:
            message = str(exc)
    except Exception:
        message = "处理失败，请检查输入与配置"
    for secret in secrets:
        if secret:
            message = message.replace(secret, "[REDACTED]")
    message = _CREDENTIAL.sub("[REDACTED]", message)
    # Provider responses can contain authorization headers and URL credentials.
    message = re.sub(r"(?i)(?:bearer\s+)[^\s'\"<>]+", "Bearer [REDACTED]", message)
    message = re.sub(r"(https?://)[^/\s:@]+:[^/\s@]+@", r"\1[REDACTED]@", message)
    return message[:1200]


def validate_context(value: dict[str, Any]) -> dict[str, Any]:
    nodes = 0
    def visit(item: Any, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if depth > 8 or nodes > 4000:
            raise ValueError("项目上下文过于复杂，请减少嵌套与字段")
        if isinstance(item, dict):
            if len(item) > 128:
                raise ValueError("项目上下文字段过多")
            for key, child in item.items():
                if not isinstance(key, str) or len(key) > 120:
                    raise ValueError("项目上下文字段名无效或过长")
                visit(child, depth + 1)
        elif isinstance(item, list):
            if len(item) > 128:
                raise ValueError("项目上下文列表过长")
            for child in item:
                visit(child, depth + 1)
        elif isinstance(item, str):
            if len(item) > 4000:
                raise ValueError("项目上下文单个文本过长")
        elif isinstance(item, float) and not math.isfinite(item):
            raise ValueError("项目上下文必须使用有限数值")
        elif item is not None and not isinstance(item, (str, bool, int, float)):
            raise ValueError("项目上下文只接受JSON数据")
    visit(value, 0)
    if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_CONTEXT_BYTES:
        raise ValueError("项目上下文超过32KiB，请仅提供必要字段")
    reject_credentials(value)
    return value


def parse_tool_json(value: str, *, max_bytes: int = MAX_CONTEXT_BYTES) -> dict[str, Any]:
    if len(value.encode("utf-8")) > max_bytes:
        raise ValueError("工具参数过长，未执行")
    def nonfinite(_constant: str):
        raise ValueError("工具参数不允许NaN或Infinity")
    def unique_keys(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("工具参数含重复字段，未执行")
            result[key] = item
        return result
    result = json.loads(value, parse_constant=nonfinite, object_pairs_hook=unique_keys)
    if not isinstance(result, dict):
        raise ValueError("工具参数必须是JSON对象")
    reject_credentials(result)
    return result
