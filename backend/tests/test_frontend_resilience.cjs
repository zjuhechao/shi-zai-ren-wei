"use strict";

// Deterministic browser-state regression tests. All network responses are mocked.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const root = path.resolve(__dirname, "../..");
const ui = require(path.join(root, "client-ui.js"));
const elements = new Map();
const downloads = [];
const element = id => {
  if (!elements.has(id)) elements.set(id, { value: "", checked: false, hidden: true,
    disabled: false, textContent: "", innerHTML: "", className: "", dataset: {}, listeners: {},
    addEventListener(name, callback) { this.listeners[name] = callback; },
    setAttribute(name, value) { this[name] = value; }, scrollIntoView() {}, focus() {}, append() {},
    reset() { for (const item of elements.values()) { item.value = ""; item.checked = false; } },
    close() {}, showModal() {}, click() { downloads.push(this); }, remove() {}
  });
  return elements.get(id);
};
const context = vm.createContext({ console, ClientUI: ui, URL, Blob, AbortController, FormData,
  document: { getElementById: element, querySelectorAll: () => [], createElement: tag => ({ ...element(`created-${tag}`) }), body: { append() {} } },
  window: { alert() {} }, setTimeout, clearTimeout,
  fetch: async () => { throw new Error("Mock-only test: external calls are forbidden"); }
});
vm.runInContext(fs.readFileSync(path.join(root, "app.js"), "utf8"), context);
const run = code => vm.runInContext(code, context);
const state = () => run("state");
const originalRequest = context.apiRequest;
let assertions = 0;
function ok(value, description) { assert.ok(value, description); assertions++; }
function equal(value, expected, description) { assert.equal(value, expected, description); assertions++; }
function throws(fn, pattern) { assert.throws(fn, pattern); assertions++; }
const tick = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };
const optionsHeader = "scenario_id,scenario_name,investment_cny,subsidy_cny,annual_energy_saving_kwh,annual_om_cny,source_name,source_url,data_date";
const optionsCsv = (id = "A", investment = "60000", date = "2026-10-14") => `${optionsHeader}\n${id},假设照明,${investment},0,12000,300,假设来源,demo://${id},${date}`;
const eventFile = (text, size = 100) => ({ target: { files: [{ size, text: () => typeof text === "string" ? Promise.resolve(text) : text }] } });
function fillBase() {
  run("resetCase()");
  const fields = { "project-name": "青禾测试假设", region: "浙江省 杭州市", "annual-electricity": "100000", "electricity-price": "0.538",
    "electricity-price-source": "测试假设", "electricity-price-url": "demo://price", "carbon-factor": "0.5", "carbon-source": "测试假设", "carbon-url": "demo://factor", "baseline-date": "2026-10-14",
    "generic-name": "照明假设", "generic-investment": "60000", "generic-subsidy": "0", "generic-saving": "12000", "generic-om": "300", "generic-source": "测试假设", "generic-url": "demo://lighting", "generic-date": "2026-10-14" };
  Object.entries(fields).forEach(([id, value]) => { element(id).value = value; });
  element("generic-enabled").checked = true;
  state().dataNature = "assumption";
  state().assumptionNotice = "测试用假设，不是真实项目";
  state().backendReady = true;
  state().apiConfigured = true;
  state().embeddingsConfigured = true;
  state().ragReady = true;
  state().manifestFound = true;
}

(async () => {
  await tick();
  run("confirmAction = async () => true");
  for (const [value, expected] of [["甲/乙:项目?", "甲_乙_项目_"], ["CON", "_CON"], ["nul.txt", "_nul.txt"], ["项目.  ", "项目"], ["\u0000报告", "_报告"], ["", "未命名项目"]]) equal(ui.filename(value), expected, "safe download filename");
  equal(Array.from(ui.filename("甲".repeat(120))).length, 80, "bounded Unicode filename");
  equal(ui.apiError([{ loc: ["body", "investment"], msg: "must be nonnegative" }], 422), "investment：must be nonnegative", "readable validation details");
  equal(ui.apiError("余额不足", 502), "余额不足", "string API errors preserved");
  ok(ui.apiError({}, 500).includes("500"), "fallback API status");
  for (const [csv, pattern] of [["a,a\n1,2", /重复/], ["a,\n1,2", /为空/], ["a,b\n1", /列数/], ['a,b\n"open,1', /未闭合/], ['a,b\n"closed"extra,1', /多余字符/], ['a,b\nwrong"quote",1', /位置/]]) throws(() => context.parseCsv(csv), pattern);
  equal(context.parseCsv('\uFEFFa,b\r\n"comma,with \"\"quote\"\"",2')[0].a, 'comma,with "quote"', "BOM, CRLF, comma and escaped quote");
  equal(context.validDate("2024-02-29"), true, "valid leap date");
  equal(context.validDate("2026-02-29"), false, "invalid leap date");
  equal(context.validDate("2026-10-32"), false, "invalid day");
  equal(context.valueMissing(Infinity), true, "infinite numeric values rejected");
  equal(context.valueMissing(0), false, "zero remains a valid numeric input");

  await context.loadOptions(eventFile(optionsCsv()));
  equal(state().importedOptions.length, 1, "valid CSV imported");
  await context.loadOptions(eventFile(optionsCsv("A", "Infinity")));
  equal(state().importedOptions.length, 0, "infinite CSV rejected without retaining previous data");
  ok(element("import-status").textContent.includes("未导入"), "invalid import visibly reported");
  await context.loadOptions(eventFile(optionsCsv("A", "0x10")));
  equal(state().importedOptions.length, 0, "hexadecimal values rejected");
  await context.loadOptions(eventFile(optionsCsv("A", "60000", "2026-02-29")));
  equal(state().importedOptions.length, 0, "invalid date rejected");
  await context.loadOptions(eventFile(optionsCsv() + "\nA,重复,1,0,1,0,来源,demo://x,2026-10-14"));
  equal(state().importedOptions.length, 0, "duplicate scenario IDs rejected");
  await context.loadOptions(eventFile(optionsCsv(), 3 * 1024 * 1024));
  ok(element("import-status").textContent.includes("2 MB"), "CSV byte limit");
  throws(() => context.parseCsv("a\n" + Array(501).fill("x").join("\n")), /500/);
  const oldCsv = deferred();
  const pendingOldCsv = context.loadOptions(eventFile(oldCsv.promise));
  await context.loadOptions(eventFile(optionsCsv("NEW")));
  oldCsv.resolve(optionsCsv("OLD"));
  await pendingOldCsv;
  equal(state().importedOptions[0].id, "NEW", "old file response cannot overwrite newer CSV");
  const resetCsv = deferred();
  const pendingResetCsv = context.loadOptions(eventFile(resetCsv.promise));
  run("resetCase()");
  resetCsv.resolve(optionsCsv("STALE"));
  await pendingResetCsv;
  equal(state().importedOptions.length, 0, "cleared project cannot be repopulated by pending CSV");
  const policyCsv = deferred();
  const pendingPolicy = context.loadPolicies(eventFile(policyCsv.promise));
  run("resetCase()");
  policyCsv.resolve("policy_id,region,policy_name,conditions,source_url,data_date\nP1,浙江,测试政策,需核对,demo://policy,2026-10-14");
  await pendingPolicy;
  equal(state().policies.length, 0, "pending policy CSV cannot repopulate cleared project");

  const assumptions = deferred(); let scenarioCalls = 0;
  context.apiRequest = async () => { scenarioCalls++; return assumptions.promise; };
  const pendingAssumptions = context.loadAssumptions(); await tick();
  await context.loadAssumptions();
  equal(scenarioCalls, 1, "scenario loading reentry blocked");
  run("resetCase()");
  element("project-name").value = "NEW PROJECT";
  assumptions.resolve({ notice: "OLD ASSUMPTIONS", assumptions: [], fields: { "project-name": "OLD PROJECT" } });
  await pendingAssumptions;
  equal(element("project-name").value, "NEW PROJECT", "pending assumptions cannot overwrite a changed project");
  equal(state().scenarioBusy, false, "scenario busy state recovers");
  equal(element("load-assumptions").disabled, false, "scenario load button recovers");

  fillBase();
  await context.loadWangyueFields();
  equal(element("annual-electricity").value, "", "real-case switch clears other project energy");
  equal(element("generic-investment").value, "", "real-case switch clears other project investment");
  equal(state().dataNature, "user_supplied_unverified", "real-case switch clears assumption mode");
  state().apiConfigured = false;
  state().embeddingsConfigured = false;
  state().ragReady = false;
  context.updateCapabilityHints();
  ok(element("agent-readiness").textContent.includes("无密钥仍可"), "no-key message preserves available local capabilities");
  ok(element("photo-readiness").textContent.includes("不会自动上传"), "photo preview has privacy boundary");

  fillBase();
  const calculation = deferred(); let calculationCalls = 0;
  context.apiRequest = async endpoint => { if (endpoint.includes("generic")) { calculationCalls++; return calculation.promise; } return { notice: "假设", scenarios: [] }; };
  const firstCalculation = context.calculate({ preventDefault() {} });
  await context.calculate({ preventDefault() {} });
  equal(calculationCalls, 1, "calculate reentry blocked");
  ok(element("calculate").disabled, "calculate button shows pending state");
  element("generic-investment").value = "48000";
  context.invalidateReport();
  calculation.resolve(context.makeGenericScenario({ id: "A", name: "假设", investment: 60000, subsidy: 0, annualSavingKwh: 12000, annualOm: 300, sourceName: "假设", sourceUrl: "demo://x", dataDate: "2026-10-14" }, context.buildBase()));
  await firstCalculation;
  equal(state().report, null, "stale calculation cannot become an exportable report");
  equal(element("calculate").disabled, false, "calculation button recovers after stale response");
  fillBase(); state().backendReady = false;
  await context.calculate({ preventDefault() {} });
  equal(state().report.softwareVersion, "0.6.2", "JSON report version");
  equal(state().report.dataNature, "assumption", "JSON data nature retained");
  equal(state().report.scenarios[0].sourceUrl, "demo://lighting", "JSON source retained");
  equal(state().report.executionMode, "Browser offline validation", "offline result honestly labels its engine");
  equal(state().report.scenarios[0].annualNetBenefit, 6156, "fixed assumed formula remains unchanged");
  context.renderResults({ ...state().report, sensitivityError: "敏感性分析未完成，未使用替代结果。" });
  equal(element("sensitivity-results").hidden, false, "sensitivity failure is visible instead of silently missing");
  fillBase(); element("generic-saving").value = "200000";
  await context.calculate({ preventDefault() {} });
  equal(state().report, null, "single-option energy savings cannot exceed baseline");
  ok(element("validation").innerHTML.includes("年用电量"), "energy boundary has readable validation");

  fillBase(); element("agent-question").value = "测试问题一";
  const answer = deferred(); let agentCalls = 0;
  let agentPayload;
  context.apiRequest = async (_endpoint, options) => { agentCalls++; agentPayload = JSON.parse(options.body); return answer.promise; };
  const pendingAnswer = context.askAgent();
  await context.askAgent();
  equal(agentCalls, 1, "agent reentry blocked");
  equal(agentPayload.consent_cloud, true, "cloud query sends explicit consent only after confirmation");
  element("agent-question").value = "测试问题二";
  answer.resolve({ answer: "OLD ANSWER", citations: [], tool_results: [] });
  await pendingAnswer;
  ok(!element("agent-result").innerHTML.includes("OLD ANSWER"), "changed question suppresses old answer");
  ok(element("agent-result").textContent.includes("已变更"), "stale answer explains recovery");
  equal(state().agentBusy, false, "agent busy state recovers");
  fillBase(); element("agent-question").value = "取消授权测试";
  run("confirmAction = async () => false");
  let canceledCalls = 0;
  context.apiRequest = async () => { canceledCalls++; return {}; };
  await context.askAgent();
  equal(canceledCalls, 0, "canceling cloud consent never calls the agent API");
  equal(state().agentBusy, false, "canceling consent restores busy state");
  run("confirmAction = async () => true");
  fillBase();
  const photo = new Blob(["image"], { type: "image/png" });
  state().photoFiles = [photo];
  const photoResult = deferred(); let photoCalls = 0;
  context.apiRequest = async () => { photoCalls++; return photoResult.promise; };
  const pendingPhoto = context.analyzePhotos(); await tick();
  await context.analyzePhotos();
  equal(photoCalls, 1, "photo reentry blocked");
  state().photoRevision++;
  element("vision-result").innerHTML = "NEW PHOTO STATE";
  photoResult.resolve({ facade_material: "OLD FACADE" });
  await pendingPhoto;
  equal(element("vision-result").innerHTML, "NEW PHOTO STATE", "changed photos suppress old observation");
  equal(state().visionBusy, false, "vision busy state recovers");
  context.previewPhotos({ target: { files: [{ type: "image/png", size: 0, name: "empty.png" }] } });
  equal(state().photoFiles.length, 0, "empty photo rejected locally");
  context.previewPhotos({ target: { files: Array.from({ length: 6 }, () => ({ type: "image/png", size: 10 })) } });
  equal(state().photoFiles.length, 0, "extra photos rejected instead of silently dropped");
  context.previewPhotos({ target: { files: Array.from({ length: 4 }, () => ({ type: "image/png", size: 9 * 1024 * 1024 })) } });
  equal(state().photoFiles.length, 0, "aggregate photo bytes cannot exceed conservative 32 MiB limit");
  ok(element("photo-readiness").textContent.includes("32 MiB"), "oversized photo batch explains resizing");

  fillBase(); state().backendReady = false; await context.calculate({ preventDefault() {} }); state().backendReady = true;
  context.fetch = async () => ({ ok: true, headers: new Headers({ "content-type": "application/pdf" }), blob: async () => new Blob(["<html>wrong</html>"]) });
  context.Headers = Headers;
  const beforeDownload = downloads.length;
  await context.generateFullPlan();
  equal(downloads.length, beforeDownload, "PDF MIME alone cannot disguise a non-PDF download");
  ok(element("plan-status").textContent.includes("不是有效 PDF"), "bad PDF response shown as failure");
  const pdf = deferred();
  context.fetch = async () => ({ ok: true, headers: new Headers({ "content-type": "application/pdf" }), blob: async () => pdf.promise });
  const pendingPdf = context.generateFullPlan(); await tick();
  state().planRevision++;
  pdf.resolve(new Blob(["%PDF-1.4\nmock"]));
  await pendingPdf;
  equal(downloads.length, beforeDownload, "changed objective suppresses stale PDF");
  ok(element("plan-status").textContent.includes("旧 PDF 已丢弃"), "stale PDF recovery notice");
  equal(state().planBusy, false, "PDF busy state recovers");

  fillBase(); state().backendReady = false; await context.calculate({ preventDefault() {} }); state().backendReady = true;
  const changedInputConsent = deferred(); let preflightCalls = 0;
  context.confirmAction = () => changedInputConsent.promise;
  context.fetch = async () => { preflightCalls++; throw new Error("should not send stale authorized data"); };
  const pendingChangedInputPlan = context.generateFullPlan();
  element("generic-investment").value = "48000";
  context.invalidateReport();
  changedInputConsent.resolve(true);
  await pendingChangedInputPlan;
  equal(preflightCalls, 0, "input change while consent is pending prevents cloud submission");
  ok(element("plan-status").textContent.includes("授权确认期间"), "pending-consent input race has recovery guidance");
  equal(state().planBusy, false, "rejected pending-consent request does not leave PDF busy");

  fillBase(); state().backendReady = false; await context.calculate({ preventDefault() {} }); state().backendReady = true;
  const changedObjectiveConsent = deferred();
  context.confirmAction = () => changedObjectiveConsent.promise;
  const pendingChangedObjectivePlan = context.generateFullPlan();
  state().planRevision++;
  element("plan-objective").value = "授权期间新增目标";
  changedObjectiveConsent.resolve(true);
  await pendingChangedObjectivePlan;
  equal(preflightCalls, 0, "objective change while consent is pending prevents cloud submission");
  ok(element("plan-status").textContent.includes("未向云端发送"), "objective race is not presented as generated output");

  fillBase(); state().backendReady = false; await context.calculate({ preventDefault() {} }); state().backendReady = true;
  let excessConfirmations = 0;
  context.confirmAction = async () => { excessConfirmations++; return true; };
  state().importedOptions = Array.from({ length: 8 }, (_, index) => ({ ...context.manualGenericInput(), id: `CSV-${index}` }));
  await context.generateFullPlan();
  equal(excessConfirmations, 0, "over-eight generic options are rejected before paid consent");
  ok(element("plan-status").textContent.includes("8 项"), "PDF generic-option limit is visible");
  state().importedOptions = [{ ...context.manualGenericInput(), id: "manual-generic" }];
  await context.generateFullPlan();
  equal(excessConfirmations, 0, "manual/imported duplicate ID is rejected before paid consent");
  ok(element("plan-status").textContent.includes("ID 重复"), "manual/imported duplicate ID has clear recovery");
  run("confirmAction = async () => true");

  context.apiRequest = originalRequest;
  let timeoutCalls = 0;
  context.fetch = (_path, options) => { timeoutCalls++; return new Promise((_resolve, reject) => options.signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")))); };
  await assert.rejects(() => context.apiRequest("/mock-timeout", {}, 5), /云端任务可能仍在运行/); assertions++;
  equal(timeoutCalls, 1, "timeout never automatically retries a cloud operation");
  context.fetch = async () => ({ ok: false, status: 422, json: async () => ({ detail: [{ loc: ["body", "field"], msg: "invalid" }] }) });
  await assert.rejects(() => context.apiRequest("/mock-validation"), /field：invalid/); assertions++;
  context.fetch = async () => ({ ok: true, status: 200, json: async () => { throw new Error("not JSON"); } });
  await assert.rejects(() => context.apiRequest("/mock-invalid-json"), /无法解析/); assertions++;
  const health = deferred(); let healthCalls = 0;
  context.apiRequest = async () => { healthCalls++; return health.promise; };
  const pendingHealth = context.checkBackend();
  await context.checkBackend();
  equal(healthCalls, 1, "health refresh reentry blocked");
  health.resolve({ api_configured: false, embeddings_configured: false, rag_ready: false, manifest_found: true, model: "test" });
  await pendingHealth;
  equal(state().backendReady, true, "no-key health still means local backend connected");
  equal(element("ask-agent").disabled, true, "no-key agent remains disabled");
  equal(element("check-backend").disabled, false, "health refresh button recovers");
  context.apiRequest = async () => ({ api_configured: true, embeddings_configured: true, rag_ready: true, rag_chunks: 0, manifest_found: true, model: "test", vision_model: "test-vision" });
  await context.checkBackend();
  equal(state().ragReady, false, "ready flag alone cannot claim a nonempty RAG");
  ok(element("photo-readiness").textContent.includes("是否支持图像"), "vision configuration does not claim successful image analysis");
  const catalog = deferred(); let catalogCalls = 0;
  context.apiRequest = async () => { catalogCalls++; return catalog.promise; };
  const pendingCatalog = context.loadKnowledgeCatalog();
  await context.loadKnowledgeCatalog();
  equal(catalogCalls, 1, "catalog refresh reentry blocked");
  catalog.reject(new Error("local service unavailable"));
  await pendingCatalog;
  equal(state().catalog, null, "failed refresh discards previous catalog state");
  equal(element("hero-docs").textContent, "—", "failed catalog does not display stale counts");

  const app = fs.readFileSync(path.join(root, "app.js"), "utf8");
  ok(!/localStorage|sessionStorage/.test(app), "no browser persistence of project data");
  const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
  ok(html.includes('class="skip-link"') && html.includes('id="project-heading" tabindex="-1"'), "keyboard skip destination");
  ok(html.includes('role="region" aria-label="方案比选结果'), "keyboard-scrollable result table");
  const css = fs.readFileSync(path.join(root, "styles.css"), "utf8");
  ok(/input\[type="file"\][^{]*\{[^}]*width:\s*100%[^}]*min-width:\s*0/.test(css), "file inputs can shrink to a narrow viewport");
  ok(/\.photo-block > \*[^\{]*\{[^}]*min-width:\s*0/.test(css), "photo/import grid children do not impose intrinsic width");
  ok(!/(?:body|html)\s*\{[^}]*overflow(?:-x)?:\s*hidden/.test(css), "narrow layout does not hide page overflow to mask defects");
  console.log(`Frontend resilience: ${assertions} assertions passed (mock responses only; no cloud calls).`);
})().catch(error => { console.error(error); process.exitCode = 1; });
