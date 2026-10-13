from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency is installed in normal runtime
    load_dotenv = None


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    vision_model: str
    llm_reasoning_effort: str
    embedding_provider: str
    embedding_api_key: str
    embedding_base_url: str
    embedding_model: str
    embedding_dimensions: int | None
    embedding_batch_size: int
    chroma_path: Path
    knowledge_manifest: Path
    app_host: str
    app_port: int

    @property
    def api_configured(self) -> bool:
        return bool(self.llm_api_key and self.llm_base_url and self.llm_model)

    @property
    def embeddings_configured(self) -> bool:
        return bool(self.embedding_api_key and self.embedding_base_url and self.embedding_model)


def _optional_int(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else None


def get_settings() -> Settings:
    if load_dotenv is not None:
        load_dotenv(BACKEND_ROOT / ".env", override=False)

    # Backward-compatible aliases let an existing OpenAI configuration keep working.
    llm_api_key = (os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    llm_base_url = (os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.deepseek.com").strip()
    llm_model = (os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or "deepseek-flash").strip()
    embedding_api_key = (os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    embedding_base_url = (os.getenv("EMBEDDING_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "").strip()
    embedding_model = (os.getenv("EMBEDDING_MODEL") or os.getenv("OPENAI_EMBEDDING_MODEL") or "").strip()

    chroma_path = Path(os.getenv("CHROMA_PATH") or PROJECT_ROOT / "storage" / "chroma")
    manifest = Path(
        os.getenv("KNOWLEDGE_MANIFEST")
        or PROJECT_ROOT / "数据收集包" / "08_已整理结构化数据" / "knowledge_manifest.csv"
    )
    return Settings(
        llm_provider=os.getenv("LLM_PROVIDER", "deepseek").strip().lower(),
        llm_api_key=llm_api_key,
        llm_base_url=llm_base_url,
        llm_model=llm_model,
        vision_model=(os.getenv("VISION_MODEL") or llm_model).strip(),
        llm_reasoning_effort=os.getenv("LLM_REASONING_EFFORT", "none").strip().lower(),
        embedding_provider=os.getenv("EMBEDDING_PROVIDER", "openai_compatible").strip().lower(),
        embedding_api_key=embedding_api_key,
        embedding_base_url=embedding_base_url,
        embedding_model=embedding_model,
        embedding_dimensions=_optional_int("EMBEDDING_DIMENSIONS"),
        embedding_batch_size=max(1, min(64, int(os.getenv("EMBEDDING_BATCH_SIZE", "10")))),
        chroma_path=chroma_path,
        knowledge_manifest=manifest,
        app_host=os.getenv("APP_HOST", "127.0.0.1").strip(),
        app_port=int(os.getenv("APP_PORT", "8000")),
    )


def require_llm_settings(settings: Settings) -> None:
    missing = []
    if not settings.llm_api_key:
        missing.append("LLM_API_KEY")
    if not settings.llm_base_url:
        missing.append("LLM_BASE_URL")
    if not settings.llm_model:
        missing.append("LLM_MODEL")
    if missing:
        raise RuntimeError(f"缺少大模型配置：{', '.join(missing)}。请填写 backend/.env。")


def require_embedding_settings(settings: Settings) -> None:
    missing = []
    if not settings.embedding_api_key:
        missing.append("EMBEDDING_API_KEY")
    if not settings.embedding_base_url:
        missing.append("EMBEDDING_BASE_URL")
    if not settings.embedding_model:
        missing.append("EMBEDDING_MODEL")
    if missing:
        raise RuntimeError(
            f"缺少语义向量配置：{', '.join(missing)}。DeepSeek 不提供文本向量接口，"
            "请配置阿里云百炼/OpenAI兼容嵌入服务，或按说明改用本地中文向量模型。"
        )
