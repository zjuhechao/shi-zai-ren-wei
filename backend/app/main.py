from __future__ import annotations

import json
import ipaddress
import io
import threading
import warnings
from functools import lru_cache

from fastapi import FastAPI, File, HTTPException, UploadFile, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.responses import Response
from urllib.parse import quote, urlsplit

from .agent import LowCarbonAgent
from .calculators import calculate_generic_scenario, calculate_pv_scenario
from .config import PROJECT_ROOT, get_settings
from .retrieval import LocalKnowledgeBase
from .knowledge_catalog import build_catalog, reviewed_ids
from .schemas import AgentQueryRequest, AgentQueryResponse, GenericScenarioRequest, PvScenarioRequest
from .plan_schemas import PlanRequest
from .safety import API_VERSION, MAX_IMAGE_BYTES, MAX_TOTAL_IMAGE_BYTES, MAX_IMAGE_PIXELS, redact_error
from .request_limits import RequestBodyLimitMiddleware


app = FastAPI(
    title="室在人为 低碳改造智能决策体",
    version=API_VERSION,
    description="多模态API、本地Chroma RAG和确定性Python计算工具后端。",
)
_ingest_lock = threading.Lock()
_knowledge_init_lock = threading.Lock()
_cloud_lock = threading.Lock()
_plan_lock = _cloud_lock
app.add_middleware(RequestBodyLimitMiddleware)


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    # JSON numbers such as 1e309 parse as infinity. Do not echo rejected values:
    # besides exposing input, nonfinite values cannot be encoded in a 422 response.
    detail = [{"type": item["type"],
               "loc": [redact_error(ValueError(part)) if isinstance(part, str) else part for part in item["loc"]],
               "msg": redact_error(ValueError(item["msg"]))}
              for item in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": detail})


def _public_error(exc: Exception) -> str:
    try:
        settings = get_settings()
        secrets = (settings.llm_api_key, settings.embedding_api_key)
    except Exception:
        secrets = ()
    return redact_error(exc, secrets)


@app.middleware("http")
async def reject_cross_site_writes(request: Request, call_next):
    # A reflected hostile Host can otherwise pass the same-origin check and rebind
    # an attacker's domain to loopback. This distribution is not a hosted service.
    try:
        host = urlsplit("http://" + request.headers.get("host", ""))
        hostname = host.hostname
        host.port  # Validate a supplied port as well as the hostname.
        loopback = not (host.username or host.password or host.path or host.query or host.fragment) and (
            hostname == "localhost" or bool(hostname and ipaddress.ip_address(hostname).is_loopback))
    except ValueError:
        loopback = False
    if not loopback:
        return JSONResponse(status_code=400, content={"detail": "此本地应用只接受 localhost 或回环地址的 Host"})
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if request.headers.get("sec-fetch-site") == "cross-site" or (origin and origin.rstrip("/") != str(request.base_url).rstrip("/")):
            return JSONResponse(status_code=403, content={"detail": "不接受跨站写入请求"})
    return await call_next(request)


@lru_cache(maxsize=1)
def _create_knowledge_base() -> LocalKnowledgeBase:
    return LocalKnowledgeBase(get_settings())


def get_knowledge_base() -> LocalKnowledgeBase:
    # lru_cache alone permits concurrent cache misses; Chroma's Rust startup is not reentrant.
    with _knowledge_init_lock:
        return _create_knowledge_base()


def get_agent(*, require_knowledge: bool = False) -> LowCarbonAgent:
    settings = get_settings()
    knowledge_base = None
    if require_knowledge:
        knowledge_base = get_knowledge_base()
        if knowledge_base.count() == 0:
            raise RuntimeError("本地知识库尚未建立，请配置向量服务并完成真实资料入库后再使用智能问答。")
    return LowCarbonAgent(settings, knowledge_base)


@app.get("/api/health")
def health() -> dict:
    settings = get_settings()
    rag_count = 0
    rag_error = None
    if settings.embeddings_configured:
        try:
            rag_count = get_knowledge_base().count()
        except Exception as exc:
            rag_error = _public_error(exc)
    return {
        "status": "ok",
        "version": app.version,
        "plan_pdf_available": True,
        "api_configured": settings.api_configured,
        "provider": settings.llm_provider,
        "model": settings.llm_model or None,
        "vision_model": settings.vision_model or None,
        "embeddings_configured": settings.embeddings_configured,
        "embedding_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model or None,
        "rag_ready": rag_count > 0,
        "rag_chunks": rag_count,
        "rag_error": rag_error,
        "manifest_found": settings.knowledge_manifest.exists(),
        "calculation_engine": "python",
    }


@app.get("/api/demo/case")
def demo_case() -> dict:
    case_path = PROJECT_ROOT / "data" / "cases" / "wangyue_case.json"
    if not case_path.exists():
        raise HTTPException(status_code=404, detail="望月公寓案例状态文件不存在")
    return json.loads(case_path.read_text(encoding="utf-8"))


@app.post("/api/calculate/generic")
def calculate_generic(payload: GenericScenarioRequest) -> dict:
    try:
        return calculate_generic_scenario(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/demo/assumptions")
def assumption_demo() -> dict:
    return json.loads((PROJECT_ROOT / "data" / "cases" / "assumption_demo.json").read_text(encoding="utf-8"))


@app.post("/api/calculate/sensitivity")
def calculate_sensitivity(payload: GenericScenarioRequest) -> dict:
    rows = []
    for label, investment_scale, savings_scale in (("保守假设", 1.2, 0.8), ("基准假设", 1.0, 1.0), ("乐观假设", 0.8, 1.2)):
        values = payload.model_dump()
        values["investment_cny"] *= investment_scale
        values["annual_energy_saving_kwh"] *= savings_scale
        try:
            result = calculate_generic_scenario(**values)
            rows.append({"label": label, "investment_scale": investment_scale, "savings_scale": savings_scale, "result": result})
        except ValueError as exc:
            rows.append({"label": label, "error": str(exc)})
    return {"data_nature": "assumption", "notice": "±20%为情景假设，不是预测准确度或置信区间，不代表望月公寓真实结果。", "scenarios": rows}


@app.post("/api/calculate/pv")
def calculate_pv(payload: PvScenarioRequest) -> dict:
    try:
        return calculate_pv_scenario(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/rag/ingest")
def ingest_rag() -> dict:
    if not _ingest_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="已有入库任务执行中，请等待完成")
    if not _cloud_lock.acquire(blocking=False):
        _ingest_lock.release()
        raise HTTPException(status_code=409, detail="已有智能任务执行中，请等待完成后入库")
    try:
        allowed = reviewed_ids(get_settings().knowledge_manifest)
        return get_knowledge_base().ingest_manifest(document_ids=allowed, skip_unchanged=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=_public_error(exc)) from exc
    finally:
        _cloud_lock.release()
        _ingest_lock.release()


@app.get("/api/knowledge/catalog")
def knowledge_catalog() -> dict:
    try:
        settings = get_settings()
        metadata = get_knowledge_base().collection.get(include=["metadatas"])["metadatas"] if settings.embeddings_configured else []
        return build_catalog(settings.knowledge_manifest, metadata)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=_public_error(exc)) from exc


@app.post("/api/agent/query", response_model=AgentQueryResponse)
def agent_query(payload: AgentQueryRequest) -> dict:
    if not payload.consent_cloud:
        raise HTTPException(status_code=422, detail="未确认云端资料处理，未执行智能问答")
    if not _cloud_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="已有智能任务执行中，请等待完成")
    try:
        return get_agent(require_knowledge=True).query(payload.question, payload.project_context, payload.region)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=_public_error(exc)) from exc
    finally:
        _cloud_lock.release()


@app.post("/api/vision/analyze")
async def analyze_images(files: list[UploadFile] = File(...)) -> dict:
    if not 1 <= len(files) <= 5:
        raise HTTPException(status_code=422, detail="每次请上传1至5张现场照片")
    images = []
    total_bytes = 0
    allowed = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    for uploaded in files:
        if uploaded.content_type not in allowed:
            raise HTTPException(status_code=422, detail="只支持静态JPEG、PNG、WebP、GIF图片")
        data = await uploaded.read(MAX_IMAGE_BYTES + 1)
        await uploaded.close()
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=422, detail="单张图片超过10MiB")
        total_bytes += len(data)
        if total_bytes > MAX_TOTAL_IMAGE_BYTES:
            raise HTTPException(status_code=422, detail="照片合计超过32MiB，内联云端请求还需Base64编码，请缩图后重试")
        try:
            from PIL import Image
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as image:
                    detected = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp", "GIF": "image/gif"}.get(image.format)
                    if detected != uploaded.content_type:
                        raise ValueError("图片字节与声明格式不符")
                    if image.width * image.height > MAX_IMAGE_PIXELS:
                        raise ValueError("图片像素总数超过2500万，请缩小后上传")
                    if getattr(image, "is_animated", False):
                        raise ValueError("请上传静态现场照片，不支持动画图片")
                    image.verify()
        except Exception:
            raise HTTPException(status_code=422, detail="图片文件无效、格式不符、为动画或超过2500万像素，请更换静态照片") from None
        images.append((data, uploaded.content_type))
    if not _cloud_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="已有智能任务执行中，请等待完成")
    try:
        # 照片分析内含最长 90 秒的同步网络调用；若在事件循环内直接执行会阻塞
        # 全部请求（含 /api/health）。移入线程池，保持其他接口可响应。
        return await run_in_threadpool(get_agent().analyze_images, images)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=_public_error(exc)) from exc
    finally:
        _cloud_lock.release()


@app.get("/api/demo/plan.pdf")
def demo_plan_pdf() -> FileResponse:
    path = PROJECT_ROOT / "assets" / "reports" / "qinghe_plan_demo.pdf"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="示范报告未随此源码副本提供，请使用完整方案生成入口")
    return FileResponse(path, media_type="application/pdf", filename="青禾社区_改造方案与分析报告.pdf",
                        headers={"Cache-Control": "no-store"})


@app.post("/api/reports/plan")
def full_plan_report(payload: PlanRequest) -> Response:
    if not payload.consent_cloud:
        raise HTTPException(status_code=422, detail="未确认云端资料处理，未生成报告")
    if not _plan_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="正在生成另一份完整方案，请稍后重试")
    try:
        from .plan_service import generate_plan
        from .plan_pdf import render_plan_pdf, register_fonts
        register_fonts()  # Fail before paid calls if PDF prerequisites are missing.
        plan = generate_plan(payload, get_agent(require_knowledge=True))
        pdf = render_plan_pdf(plan)
        audit_dir = PROJECT_ROOT / "storage" / "reports"
        audit_dir.mkdir(parents=True, exist_ok=True)
        (audit_dir / (plan["report_id"] + ".json")).write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        name = ("假设情景_" if payload.base.dataNature == "assumption" else "待核验_") + payload.base.projectName + "_改造方案与分析报告.pdf"
        return Response(pdf, media_type="application/pdf", headers={
            "Content-Disposition": "attachment; filename=retrofit-plan.pdf; filename*=UTF-8''" + quote(name),
            "Cache-Control": "no-store", "X-Report-Id": plan["report_id"],
            "X-Source-Count": str(len(plan["sources"])),
        })
    except Exception as exc:
        raise HTTPException(status_code=400, detail=_public_error(exc)) from exc
    finally:
        _plan_lock.release()


# 仅白名单提供前端文件，避免把 backend/.env、知识文件或原始数据作为静态文件暴露。
@app.get("/", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
def frontend_index() -> FileResponse:
    return FileResponse(PROJECT_ROOT / "index.html", media_type="text/html; charset=utf-8")


@app.get("/app.js", include_in_schema=False)
def frontend_script() -> FileResponse:
    return FileResponse(PROJECT_ROOT / "app.js", media_type="application/javascript; charset=utf-8")


@app.get("/styles.css", include_in_schema=False)
def frontend_styles() -> FileResponse:
    return FileResponse(PROJECT_ROOT / "styles.css", media_type="text/css; charset=utf-8")


@app.get("/ux.css", include_in_schema=False)
def frontend_ux_styles() -> FileResponse:
    return FileResponse(PROJECT_ROOT / "ux.css", media_type="text/css; charset=utf-8")


@app.get("/ux.js", include_in_schema=False)
def frontend_ux_script() -> FileResponse:
    return FileResponse(PROJECT_ROOT / "ux.js", media_type="application/javascript; charset=utf-8")


@app.get("/charts.js", include_in_schema=False)
def frontend_charts_script() -> FileResponse:
    return FileResponse(PROJECT_ROOT / "charts.js", media_type="application/javascript; charset=utf-8")


@app.get("/client-ui.js", include_in_schema=False)
def frontend_client_ui() -> FileResponse:
    return FileResponse(PROJECT_ROOT / "client-ui.js", media_type="application/javascript; charset=utf-8")


@app.get("/docs/数据与材料收集清单.md", include_in_schema=False)
def frontend_collection_note() -> FileResponse:
    return FileResponse(PROJECT_ROOT / "docs" / "数据与材料收集清单.md", media_type="text/markdown; charset=utf-8")
