"""Small live acceptance test: only public questions and explicitly hypothetical numbers."""
import json
import argparse
import os
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlparse

BASE = "http://127.0.0.1:" + os.getenv("APP_PORT", "8000")

def request(path, payload=None):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(BASE + path, data=data, headers={"Content-Type":"application/json"})
    with urlopen(req, timeout=300) as response:
        return json.load(response)

def main():
    global BASE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=BASE, help="Locally reachable app URL, e.g. http://127.0.0.1:18000")
    parser.add_argument("--online", action="store_true", help="Explicitly permit billable AI calls using the locally configured accounts")
    args = parser.parse_args()
    if not args.online:
        parser.error("This live test calls cloud AI and may incur charges. Re-run with --online only after authorizing those calls. No requests were made.")
    parsed = urlparse(args.base_url)
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}):
        parser.error("--base-url must be a local loopback HTTP address with no credentials or extra request path")
    try:
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError("Invalid port")
    except ValueError:
        parser.error("Invalid local port")
    BASE = args.base_url.rstrip("/")
    catalog = request("/api/knowledge/catalog")
    print(json.dumps({k:catalog[k] for k in ("total","indexed_documents","indexed_chunks","blocked_documents")}, ensure_ascii=False), flush=True)
    checks = [
        {"name":"python_tool_assumption", "question":"以下完全是假设情景，非真实项目。请先检索相关口径资料，再调用calculate_generic_scenario工具计算，不要只解释公式。scenario_id=DEMO-CHECK，scenario_name=假设照明改造，investment_cny=60000，subsidy_cny=0，annual_energy_saving_kwh=12000，electricity_price_cny_per_kwh=0.538，carbon_factor_kgco2e_per_kwh=0.5，annual_om_cny=300，source_name=联调假设（非实测），source_url=assumption:acceptance-test，data_date=2026-10-12，notes=所有数值仅验证计算流程。给出年净收益与静态回收期，明确标注假设。", "context":{"dataNature":"assumption"}},
        {"name":"missing_real_data", "question":"没有提供望月公寓的电费账单、工程量、项目报价和节能审计。能否直接给出它真实的年收益和回收期？请列出阻断项，不允许用公开工程报价或经验值填补。", "context":{}},
    ]
    results = []
    output = Path(__file__).resolve().parents[2] / "storage" / "customer_demo_acceptance.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    for check in checks:
        try:
            result = request("/api/agent/query", {"question":check["question"],"project_context":check["context"],"region":"浙江省 杭州市","consent_cloud":True})
        except HTTPError as exc:
            result = {"answer":"", "tool_results":[], "error":exc.read().decode("utf-8")}
        calls = result.get("tool_results", [])
        if check["name"] == "python_tool_assumption":
            calculations = [t["result"] for t in calls if t["tool"] == "calculate_generic_scenario"]
            passed = bool(calculations and calculations[-1].get("annualNetBenefit") == 6156 and "假设" in result["answer"])
        else:
            passed = not any(t["tool"].startswith("calculate_") for t in calls) and any(w in result["answer"] for w in ("不能", "无法", "不可以"))
        results.append({"name":check["name"],"passed":passed,**result})
        output.write_text(json.dumps({"catalog":catalog,"checks":results}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"name":check["name"],"passed":passed,"tools":[t["tool"] for t in calls],"answer":result["answer"]},ensure_ascii=False), flush=True)
    output.write_text(json.dumps({"catalog":catalog,"checks":results}, ensure_ascii=False, indent=2), encoding="utf-8")
    if not all(r["passed"] for r in results):
        raise SystemExit("Acceptance checks require manual investigation")

if __name__ == "__main__":
    main()
