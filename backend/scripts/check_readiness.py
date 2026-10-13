"""Offline package and no-key smoke checks. Never loads .env or calls cloud APIs."""
from __future__ import annotations

import argparse
import json
import os
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

PACKAGES = (
    "fastapi", "uvicorn", "openai", "chromadb", "python-multipart",
    "python-dotenv", "pymupdf", "python-docx", "reportlab", "httpx",
)


def collect_checks() -> dict:
    checks = []

    def record(name: str, ok: bool, detail: str, required: bool = True) -> None:
        checks.append({"check": name, "status": "pass" if ok else "fail" if required else "pending",
                       "detail": detail, "required": required})

    record("python", sys.version_info >= (3, 11), f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    dependencies = {}
    for package in PACKAGES:
        try:
            dependencies[package] = version(package)
        except PackageNotFoundError:
            dependencies[package] = None
    record("dependencies", all(dependencies.values()),
           "All runtime packages installed" if all(dependencies.values()) else "Missing: " + ", ".join(p for p, v in dependencies.items() if v is None))
    for relative in ("index.html", "app.js", "client-ui.js", "styles.css", "backend/.env.example",
                     "data/cases/wangyue_case.json", "data/cases/assumption_demo.json",
                     "docs/数据与材料收集清单.md"):
        record("asset:" + relative, (ROOT / relative).is_file(), relative)
    demo = ROOT / "04_完整方案交付_v0.6" / "青禾社区_改造方案与分析报告.pdf"
    demo_pdf = demo.is_file() and demo.read_bytes().startswith(b"%PDF-")
    record("demo_pdf", demo_pdf, "Fixed Qinghe assumed-case PDF included; not the result of changed inputs")
    manifest = ROOT / "数据收集包" / "08_已整理结构化数据" / "knowledge_manifest.csv"
    record("knowledge_manifest", manifest.is_file(), "Local knowledge manifest; cloud indexing is a separate step", required=False)

    if all(dependencies.values()):
        try:
            from app.plan_pdf import register_fonts
            register_fonts()
            record("pdf_font", True, "Chinese TrueType font registered successfully")
        except Exception as exc:
            record("pdf_font", False, type(exc).__name__ + ": install an available Chinese TTF/TTC font or set REPORT_FONT_PATH")
        try:
            # Empty keys override the operator's environment without reading backend/.env.
            environment = {"LLM_API_KEY": "", "OPENAI_API_KEY": "", "EMBEDDING_API_KEY": "",
                           "APP_HOST": "127.0.0.1", "APP_PORT": "8000"}
            with patch.dict(os.environ, environment), patch("app.config.load_dotenv", None):
                from fastapi.testclient import TestClient
                from app.main import app
                client = TestClient(app)
                health = client.get("/api/health")
                status = health.json()
                record("no_key_health", health.status_code == 200 and not status["api_configured"] and not status["embeddings_configured"],
                       "No API keys and no live vector index are used by this check")
                record("no_key_frontend", client.get("/").status_code == 200, "Frontend opens without API keys")
                sample = client.get("/api/demo/plan.pdf")
                record("no_key_demo_download", sample.status_code == 200 and sample.content.startswith(b"%PDF-"),
                       "Sample PDF downloads without cloud calls")
                calculation = client.post("/api/calculate/generic", json={
                    "scenario_id": "OFFLINE-CHECK", "scenario_name": "Offline test assumptions",
                    "investment_cny": 60000, "subsidy_cny": 0,
                    "annual_energy_saving_kwh": 12000, "electricity_price_cny_per_kwh": 0.538,
                    "carbon_factor_kgco2e_per_kwh": 0.5, "annual_om_cny": 300,
                    "source_name": "TEST ASSUMPTIONS ONLY", "source_url": "assumption:offline-check",
                    "data_date": "2026-10-13",
                })
                valid_calculation = calculation.status_code == 200 and calculation.json().get("annualNetBenefit") == 6156
                record("no_key_python_calculation", valid_calculation, "Assumed annual net benefit calculated by Python: 6156 CNY")
                record("private_paths", client.get("/backend/.env").status_code == 404 and
                       client.get("/storage/reports/private.json").status_code == 404,
                       "Frontend routes do not expose credentials or report audit storage")
        except Exception as exc:
            # Avoid printing configuration values if an optional prerequisite fails.
            record("offline_smoke", False, type(exc).__name__)
    passed = all(check["status"] == "pass" for check in checks if check["required"])
    return {"mode": "offline_no_keys_no_api_calls", "passed": passed,
            "python": sys.version.split()[0], "dependencies": dependencies, "checks": checks,
            "notice": "This verifies package prerequisites and no-key demo behavior only; it does not verify cloud connectivity, RAG quality, photos, or target-host deployment."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print a machine-readable readiness result")
    args = parser.parse_args()
    result = collect_checks()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for check in result["checks"]:
            print(f"[{check['status'].upper()}] {check['check']}: {check['detail']}")
        print(result["notice"])
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
