from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="No customer records or photos are sent by this check.")
    parser.add_argument("--online", action="store_true", help="Explicitly permit two small billable API test calls")
    args = parser.parse_args()
    settings = get_settings()
    result = {"configuration_only": not args.online, "llm_configured": settings.api_configured, "embedding_configured": settings.embeddings_configured, "notice": "配置存在不等于连接成功；此检查不验证视觉或RAG答案质量。"}
    if args.online:
        from openai import OpenAI
        for kind, ready in (("llm", settings.api_configured), ("embedding", settings.embeddings_configured)):
            if not ready:
                result[kind] = {"status": "missing_configuration"}
                continue
            try:
                if kind == "llm":
                    client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url, timeout=45, max_retries=0)
                    extra = {"reasoning": {"effort": "none"}} if settings.llm_provider == "deepseek" else {}
                    response = client.responses.create(model=settings.llm_model, input="Reply with OK only. Connection test.", max_output_tokens=32, **extra)
                    result[kind] = {"status": "ok" if response.output_text.strip() else "empty_response"}
                else:
                    client = OpenAI(api_key=settings.embedding_api_key, base_url=settings.embedding_base_url, timeout=45, max_retries=0)
                    extra = {"dimensions": settings.embedding_dimensions} if settings.embedding_dimensions else {}
                    response = client.embeddings.create(model=settings.embedding_model, input=["公开政策资料检索测试"], encoding_format="float", **extra)
                    result[kind] = {"status": "ok", "dimensions": len(response.data[0].embedding)}
            except Exception as exc:
                result[kind] = {"status": "failed", "error_type": type(exc).__name__, "http_status": getattr(exc, "status_code", None)}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
