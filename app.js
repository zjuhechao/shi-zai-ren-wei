"use strict";

const $ = (id) => document.getElementById(id);
const state = {
  importedOptions: [],
  policies: [],
  report: null,
  backendReady: false,
  apiConfigured: false,
  embeddingsConfigured: false,
  ragReady: false,
  photoFiles: [],
  demoCase: null,
  dataNature: "user_supplied_unverified",
  assumptionNotice: "",
  assumptionDetails: [],
  revision: 0,
  agentBusy: false,
  ingestBusy: false,
  catalog: null,
  planBusy: false,
  planRevision: 0,
  healthBusy: false,
  catalogBusy: false,
  calculateBusy: false,
  visionBusy: false,
  photoRevision: 0,
  questionRevision: 0,
  optionsRevision: 0,
  policiesRevision: 0,
  manifestFound: false,
  visionModel: "",
  confirmationPending: false,
  scenarioBusy: false,
};

const FALLBACK_CASE = {
  project_name: "望月公寓",
  region: "浙江省 杭州市",
  safe_prefill: {
    project_name: "望月公寓",
    region: "浙江省 杭州市",
  },
  available_evidence: [
    { item: "政策、标准与价格资料", status: "已整理", detail: "知识清单40条，政策11条，电价57条，碳因子91条，改造参考报价30条。" },
    { item: "户型平面资料", status: "待核验来源", detail: "3份户型平面PDF有尺寸标注，但缺少原始图纸出处、图号和测绘/设计单位信息。" },
    { item: "建筑照片", status: "限内部核验", detail: "8张图片中部分含网站水印、楼栋或房间标识，来源与脱敏状态需重新确认。" },
  ],
  blocking_inputs: [
    { priority: "P0", field: "电力排放因子气体覆盖、单位与核算边界", why: "当前字段为kgCO2e/kWh，官方CO2因子保留为线索，不能未经核对直接改标或自动填入。" },
    { priority: "P0", field: "连续12个月用电量与电费", why: "缺失时不能计算年收益或回收期。" },
    { priority: "P0", field: "试点楼栋精确地址与区县", why: "用于核对区县政策和适用电价。" },
    { priority: "P0", field: "外墙、窗、屋顶可核验工程量", why: "决定项目投资，估算值不能直接采用。" },
    { priority: "P0", field: "节能审计或热工模拟结果", why: "不能用材料宣传比例代替项目节能量。" },
  ],
};

const field = (id) => $(id).value.trim();
const number = (id) => {
  const value = field(id);
  return value === "" ? null : Number(value);
};
const checked = (id) => $(id).checked;

async function requestResource(path, options, consume, timeoutMs = 30000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await consume(await fetch(path, { ...options, signal: controller.signal }));
  } catch (error) {
    if (controller.signal.aborted) throw new Error("等待响应超时。云端任务可能仍在运行，请先核对服务记录后再重试，避免重复计费");
    if (error instanceof TypeError) throw new Error("无法连接本地服务，请确认后端正在运行，再点击重新检测");
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

async function apiRequest(path, options = {}, timeoutMs = 30000) {
  return requestResource(path, options, async response => {
    let body;
    try { body = await response.json(); } catch (_error) {
      throw new Error(`服务返回无法解析的响应（${response.status}），请检查后端日志`);
    }
    if (!response.ok) throw new Error(ClientUI.apiError(body.detail, response.status));
    return body;
  }, timeoutMs);
}

function setStatus(id, text, kind) {
  const element = $(id);
  element.textContent = text;
  element.className = `status-pill ${kind}`;
}

async function checkBackend() {
  if (state.healthBusy) return;
  state.healthBusy = true;
  $("check-backend").disabled = true;
  ["status-backend", "status-api", "status-embedding", "status-rag", "status-tool"].forEach((id) => setStatus(id, "检测中", "waiting"));
  try {
    const health = await apiRequest("/api/health", {}, 8000);
    state.backendReady = true;
    state.apiConfigured = Boolean(health.api_configured);
    state.embeddingsConfigured = Boolean(health.embeddings_configured);
    state.ragReady = Boolean(health.rag_ready) && Number(health.rag_chunks) > 0;
    state.manifestFound = Boolean(health.manifest_found);
    state.visionModel = health.vision_model || "";
    setStatus("status-backend", "已连接", "ok");
    setStatus("status-api", state.apiConfigured ? `${health.model} 已配置（待调用核验）` : "配置未齐", state.apiConfigured ? "ok" : "off");
    setStatus("status-embedding", state.embeddingsConfigured ? "已配置" : "未配置", state.embeddingsConfigured ? "ok" : "off");
    $("status-embedding-detail").textContent = health.embedding_model || "需单独的文本向量模型";
    setStatus("status-rag", state.ragReady ? "已建立" : (state.embeddingsConfigured ? "尚未入库" : "等待向量服务"), state.ragReady ? "ok" : "off");
    setStatus("status-tool", "Python 已启用", "ok");
    $("status-rag-detail").textContent = health.rag_chunks ? `${health.rag_chunks} 个文本块` : (health.manifest_found ? "知识清单已就位" : "未找到知识清单");
    $("ingest-rag").disabled = state.ingestBusy || !state.embeddingsConfigured || !health.manifest_found;
    $("analyze-photos").disabled = state.visionBusy || !state.apiConfigured || state.photoFiles.length === 0;
    $("ask-agent").disabled = state.agentBusy || !(state.apiConfigured && state.ragReady);
    if (state.apiConfigured && state.ragReady) {
      $("mode-note").textContent = "配置齐备且知识库非空；密钥是否有效、模型工具调用和召回质量仍需实际调用验收。数值由Python确定性工具计算。";
    } else if (state.apiConfigured && !state.embeddingsConfigured) {
      $("mode-note").textContent = "文本模型参数已配置，联通与照片能力仍须调用验收；语义RAG缺独立嵌入服务。DeepSeek密钥不能替代文本向量接口。";
    } else {
      $("mode-note").textContent = "Python计算后端已连接；未配置的API或RAG能力保持关闭。请按backend/.env.example填写新密钥。";
    }
  } catch (_error) {
    state.backendReady = false;
    state.apiConfigured = false;
    state.embeddingsConfigured = false;
    state.ragReady = false;
    state.manifestFound = false;
    state.visionModel = "";
    setStatus("status-backend", "未启动", "off");
    setStatus("status-api", "不可用", "off");
    setStatus("status-embedding", "不可用", "off");
    setStatus("status-rag", "不可用", "off");
    setStatus("status-tool", "浏览器校验模式", "off");
    $("status-embedding-detail").textContent = "";
    $("status-rag-detail").textContent = "";
    $("ingest-rag").disabled = true;
    $("analyze-photos").disabled = true;
    $("ask-agent").disabled = true;
    $("mode-note").textContent = "当前仅为离线浏览器校验模式：不会调用大模型、RAG 或 Python 工具。运行 backend/run.py 后再重新检测。";
  } finally {
    state.healthBusy = false;
    $("check-backend").disabled = false;
  }
  updateCapabilityHints();
  updatePlanButton();
}

function updateCapabilityHints() {
  const missing = [];
  if (!state.backendReady) missing.push("启动本地后端");
  else {
    if (!state.apiConfigured) missing.push("配置模型 API 密钥");
    if (!state.embeddingsConfigured) missing.push("配置百炼向量密钥、Base URL 与向量模型");
    if (!state.ragReady) missing.push("核对公开资料后真实入库");
  }
  $("agent-readiness").textContent = missing.length ? `智能咨询暂不可用：请${missing.join("、")}，然后重新检测。无密钥仍可运行本地确定性测算和下载固定示范 PDF。` : "智能咨询可调用；配置状态不等于密钥有效或检索结论可靠，每次答复仍须核对原文。";
  $("photo-readiness").textContent = !state.backendReady || !state.apiConfigured ? "照片分析需要已连接的后端和模型 API。选择照片仅生成本地预览，不会自动上传。" : `VISION_MODEL：${state.visionModel || "待配置"}。模型是否支持图像及接口联通仍需验收，不因配置文本 API 而视为识图已完成。照片仅在确认调用后发送云端，请核对授权、脱敏和费用。`;
}

function renderDemoCase(data) {
  state.demoCase = data;
  const p0 = (data.blocking_inputs || []).filter((item) => item.priority === "P0");
  $("case-overview").innerHTML = `
    <div class="case-metric"><span>原案例历史台账</span><strong>40 条索引（原机记录）</strong><small>当前可用资料以资料库状态为准</small></div>
    <div class="case-metric"><span>可计算方案</span><strong>0 项</strong><small>未补核心项目数据前不输出ROI</small></div>
    <div class="case-metric"><span>P0关键缺口</span><strong>${p0.length} 项</strong><small>账单、区县、工程量、节能量</small></div>`;
  $("case-evidence").innerHTML = (data.available_evidence || [])
    .map((item) => `<li><span class="evidence-status">${escapeHtml(item.status)}</span><strong>${escapeHtml(item.item)}</strong><small>${escapeHtml(item.detail)}</small></li>`)
    .join("");
  $("case-blockers").innerHTML = p0
    .map((item) => `<li><span class="evidence-status danger-status">${escapeHtml(item.priority)}</span><strong>${escapeHtml(item.field)}</strong><small>${escapeHtml(item.why)}</small></li>`)
    .join("");
  $("load-wangyue").disabled = false;
}

async function loadDemoCaseStatus() {
  try {
    renderDemoCase(await apiRequest("/api/demo/case"));
  } catch (_error) {
    renderDemoCase(FALLBACK_CASE);
  }
}

function confirmAction(message) {
  if (state.confirmationPending) return Promise.resolve(false);
  state.confirmationPending = true;
  const dialog = $("action-confirm");
  $("confirm-message").textContent = message;
  return new Promise((resolve) => {
    const finish = (accepted) => {
      dialog.close();
      $("confirm-accept").onclick = null;
      $("confirm-cancel").onclick = null;
      dialog.oncancel = null;
      state.confirmationPending = false;
      resolve(accepted);
    };
    $("confirm-accept").onclick = () => finish(true);
    $("confirm-cancel").onclick = () => finish(false);
    dialog.oncancel = (event) => { event.preventDefault(); finish(false); };
    dialog.showModal();
  });
}

async function loadWangyueFields() {
  const hasInputs = state.report || state.importedOptions.length || state.policies.length || state.photoFiles.length || [...document.querySelectorAll("#project-form input, #project-form textarea")].some(input => input.type === "checkbox" ? input.checked : input.value.trim()) || ["project-name", "annual-electricity", "carbon-factor", "generic-investment", "pv-capacity"].some(id => field(id));
  if (hasInputs && !await confirmAction("切换到望月公寓将清空当前全部输入、导入资料、图片和报告，避免将其他项目数值混入真实案例。继续吗？")) return;
  resetCase();
  const prefill = state.demoCase?.safe_prefill || FALLBACK_CASE.safe_prefill;
  $("project-name").value = prefill.project_name || "望月公寓";
  $("region").value = prefill.region || "浙江省 杭州市";
  $("carbon-factor").value = prefill.carbon_factor_kgco2e_per_kwh ?? "";
  $("carbon-source").value = prefill.carbon_source || "";
  $("carbon-url").value = prefill.carbon_source_url || "";
  $("baseline-date").value = prefill.carbon_data_date || "";
  $("case-note").textContent = "已加载项目名称和地区。官方CO2资料仅作线索；当前kgCO2e因子须确认气体覆盖、单位和核算边界后另行填写。电量、电费、用户类别、工程量、节能量和项目报价仍须补齐。";
  $("project-heading").scrollIntoView({ behavior: "smooth", block: "start" });
}

function invalidateReport() {
  state.revision += 1;
  state.report = null;
  ["summary", "result-table-wrap", "policy-matches", "report-nature", "sensitivity-results"].forEach((id) => { $(id).hidden = true; });
  ["summary", "result-table", "policy-matches", "report-nature", "sensitivity-results"].forEach((id) => { $(id).textContent = ""; });
  $("export-json").disabled = true;
  $("export-html").disabled = true;
  $("print-report").disabled = true;
  $("generate-plan").disabled = true;
  $("plan-status").textContent = state.planBusy ? "输入已改变，正在生成的旧版本不会自动下载。" : "先完成测算，再生成完整 PDF。";
  $("validation").textContent = "";
  if (!state.agentBusy) $("agent-result").hidden = true;
}

function resetCase() {
  $("project-form").reset();
  $("plan-objective").value = "";
  $("plan-comparison-investment").value = "";
  state.planRevision += 1;
  state.optionsRevision += 1;
  state.policiesRevision += 1;
  state.photoRevision += 1;
  state.questionRevision += 1;
  state.importedOptions = [];
  state.policies = [];
  state.photoFiles = [];
  state.dataNature = "user_supplied_unverified";
  state.assumptionNotice = "";
  state.assumptionDetails = [];
  $("data-nature-banner").hidden = true;
  $("import-status").textContent = "";
  $("photo-preview").textContent = "";
  $("agent-result").hidden = true;
  $("vision-result").hidden = true;
  $("analyze-photos").disabled = true;
  $("generic-fields").hidden = true;
  $("pv-fields").hidden = true;
  invalidateReport();
}

async function loadAssumptions() {
  if (state.scenarioBusy) return;
  if (!await confirmAction("将覆盖当前未保存输入，载入明确标注的假设情景。假设不会视为望月公寓真实数据。继续吗？")) return;
  const revision = state.revision;
  state.scenarioBusy = true;
  $("load-assumptions").disabled = true;
  $("start-demo").disabled = true;
  try {
    const scenario = await apiRequest("/api/demo/assumptions");
    if (revision !== state.revision) return;
    resetCase();
    state.dataNature = "assumption";
    state.assumptionNotice = scenario.notice;
    state.assumptionDetails = scenario.assumptions;
    Object.entries(scenario.fields).forEach(([id, value]) => { if ($(id)) $(id).value = value; });
    $("generic-enabled").checked = true;
    $("generic-fields").hidden = false;
    $("data-nature-banner").textContent = scenario.notice;
    $("data-nature-banner").hidden = false;
    $("project-heading").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    if (revision === state.revision) window.alert(`假设情景未载入：${error.message}。请先启动后端。`);
  } finally {
    state.scenarioBusy = false;
    $("load-assumptions").disabled = false;
    $("start-demo").disabled = false;
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function money(value) {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    maximumFractionDigits: 2,
  }).format(value);
}

function decimal(value, digits = 2) {
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: digits }).format(value);
}

function valueMissing(value) {
  return value === null || value === "" || (typeof value === "number" && !Number.isFinite(value));
}

function requireValue(errors, condition, label) {
  if (condition) errors.push(label);
}

function validateBase() {
  const errors = [];
  requireValue(errors, valueMissing(field("region")), "所在地区");
  requireValue(errors, valueMissing(number("annual-electricity")) || number("annual-electricity") < 0, "年用电量");
  requireValue(errors, valueMissing(number("electricity-price")) || number("electricity-price") < 0, "电价");
  requireValue(errors, valueMissing(field("electricity-price-source")), "电价来源名称");
  requireValue(errors, valueMissing(field("electricity-price-url")), "电价来源链接或文件编号");
  requireValue(errors, valueMissing(number("carbon-factor")) || number("carbon-factor") < 0, "电力排放因子");
  requireValue(errors, valueMissing(field("carbon-source")), "碳因子来源名称");
  requireValue(errors, valueMissing(field("carbon-url")), "碳因子来源链接或文件编号");
  requireValue(errors, !validDate(field("baseline-date")), "有效的数据基准日期（YYYY-MM-DD）");
  [["floor-area", "建筑面积"], ["roof-area", "屋顶可用面积"]].forEach(([id, label]) => { if (field(id) && (valueMissing(number(id)) || number(id) < 0)) errors.push(`${label}必须为有限的非负数`); });
  if (field("construction-year") && (!Number.isInteger(number("construction-year")) || number("construction-year") < 1800 || number("construction-year") > 2100)) errors.push("建筑年代必须为 1800–2100 的整数年份");
  return errors;
}

function validateGeneric() {
  const errors = [];
  if (!checked("generic-enabled")) return errors;
  const numeric = [
    ["generic-investment", "通用方案的改造总投资"],
    ["generic-subsidy", "通用方案的已确认补贴"],
    ["generic-saving", "通用方案的预计年节电量"],
    ["generic-om", "通用方案的年运维成本"],
  ];
  requireValue(errors, valueMissing(field("generic-name")), "通用方案名称");
  numeric.forEach(([id, label]) => requireValue(errors, valueMissing(number(id)) || number(id) < 0, label));
  [
    ["generic-source", "通用方案的数据来源名称"],
    ["generic-url", "通用方案的来源链接、文件编号或归档路径"],
    ["generic-date", "通用方案的数据日期"],
  ].forEach(([id, label]) => requireValue(errors, valueMissing(field(id)), label));
  if (field("generic-date") && !validDate(field("generic-date"))) errors.push("通用方案的数据日期必须为有效 YYYY-MM-DD 日期");
  if (!valueMissing(number("generic-investment")) && !valueMissing(number("generic-subsidy")) && number("generic-subsidy") > number("generic-investment")) {
    errors.push("通用方案的已确认补贴不能大于改造总投资，请核验口径");
  }
  return errors;
}

function validatePv() {
  const errors = [];
  if (!checked("pv-enabled")) return errors;
  const numeric = [
    ["pv-capacity", "光伏装机容量"],
    ["pv-yield", "光伏年发电量系数"],
    ["pv-self-use", "光伏自发自用比例"],
    ["pv-feed-in-tariff", "光伏余电上网电价"],
    ["pv-investment", "光伏改造总投资"],
    ["pv-subsidy", "光伏已确认补贴"],
    ["pv-om", "光伏年运维成本"],
  ];
  numeric.forEach(([id, label]) => requireValue(errors, valueMissing(number(id)) || number(id) < 0, label));
  if (!valueMissing(number("pv-self-use")) && number("pv-self-use") > 1) errors.push("光伏自发自用比例必须在 0 到 1 之间");
  [
    ["pv-source", "光伏数据来源名称"],
    ["pv-url", "光伏来源链接、文件编号或归档路径"],
    ["pv-date", "光伏数据日期"],
  ].forEach(([id, label]) => requireValue(errors, valueMissing(field(id)), label));
  if (field("pv-date") && !validDate(field("pv-date"))) errors.push("光伏的数据日期必须为有效 YYYY-MM-DD 日期");
  if (!valueMissing(number("pv-investment")) && !valueMissing(number("pv-subsidy")) && number("pv-subsidy") > number("pv-investment")) {
    errors.push("光伏方案的已确认补贴不能大于改造总投资，请核验口径");
  }
  return errors;
}

function makeGenericScenario(input, base) {
  const annualBenefit = input.annualSavingKwh * base.electricityPrice;
  const netInvestment = input.investment - input.subsidy;
  const annualNetBenefit = annualBenefit - input.annualOm;
  return {
    id: input.id,
    type: "通用改造",
    name: input.name,
    investment: input.investment,
    subsidy: input.subsidy,
    netInvestment,
    annualElectricitySaving: input.annualSavingKwh,
    annualBenefit,
    annualOm: input.annualOm,
    annualNetBenefit,
    annualCarbon: input.annualSavingKwh * base.carbonFactor,
    payback: annualNetBenefit > 0 ? netInvestment / annualNetBenefit : null,
    sourceName: input.sourceName,
    sourceUrl: input.sourceUrl,
    dataDate: input.dataDate,
    notes: input.notes || "",
    formula: "年节省额 = 年节电量 × 电价；年减碳量 = 年节电量 × 电力排放因子；静态回收期 = 净投资 ÷ 年净收益",
  };
}

function makePvScenario(base) {
  const capacity = number("pv-capacity");
  const annualYield = number("pv-yield");
  const selfUseRate = number("pv-self-use");
  const generation = capacity * annualYield;
  const selfUsed = Math.min(generation * selfUseRate, base.annualElectricity);
  const exported = Math.max(0, generation - selfUsed);
  const annualBenefit = selfUsed * base.electricityPrice + exported * number("pv-feed-in-tariff");
  const netInvestment = number("pv-investment") - number("pv-subsidy");
  const annualNetBenefit = annualBenefit - number("pv-om");
  return {
    id: "manual-pv",
    type: "屋顶光伏",
    name: "屋顶光伏",
    investment: number("pv-investment"),
    subsidy: number("pv-subsidy"),
    netInvestment,
    annualElectricitySaving: generation,
    annualBenefit,
    annualOm: number("pv-om"),
    annualNetBenefit,
    annualCarbon: generation * base.carbonFactor,
    payback: annualNetBenefit > 0 ? netInvestment / annualNetBenefit : null,
    sourceName: field("pv-source"),
    sourceUrl: field("pv-url"),
    dataDate: field("pv-date"),
    notes: `年发电量 ${decimal(generation)} kWh；按自发自用 ${decimal(selfUseRate * 100, 2)}% 估算，其中自用 ${decimal(selfUsed)} kWh、余电 ${decimal(exported)} kWh。减碳按全部发电量可替代同区域电网电量的前提计算。`,
    formula: "年发电量 = 装机容量 × 年发电量系数；年收益 = 自用电量 × 电价 + 余电量 × 上网电价；年减碳量 = 年发电量 × 电力排放因子",
  };
}

function buildBase() {
  return {
    dataNature: state.dataNature,
    assumptionNotice: state.assumptionNotice,
    projectName: field("project-name") || "未命名项目",
    region: field("region"),
    address: field("address"),
    constructionYear: number("construction-year"),
    floorArea: number("floor-area"),
    roofArea: number("roof-area"),
    annualElectricity: number("annual-electricity"),
    electricityPrice: number("electricity-price"),
    electricityPriceSource: field("electricity-price-source"),
    electricityPriceUrl: field("electricity-price-url"),
    carbonFactor: number("carbon-factor"),
    carbonSource: field("carbon-source"),
    carbonUrl: field("carbon-url"),
    baselineDate: field("baseline-date"),
  };
}

function manualGenericScenario(base) {
  return makeGenericScenario(
    {
      id: "manual-generic",
      name: field("generic-name"),
      investment: number("generic-investment"),
      subsidy: number("generic-subsidy"),
      annualSavingKwh: number("generic-saving"),
      annualOm: number("generic-om"),
      sourceName: field("generic-source"),
      sourceUrl: field("generic-url"),
      dataDate: field("generic-date"),
    },
    base,
  );
}

function genericApiPayload(input, base) {
  return {
    scenario_id: input.id,
    scenario_name: input.name,
    investment_cny: input.investment,
    subsidy_cny: input.subsidy,
    annual_energy_saving_kwh: input.annualSavingKwh,
    electricity_price_cny_per_kwh: base.electricityPrice,
    carbon_factor_kgco2e_per_kwh: base.carbonFactor,
    annual_om_cny: input.annualOm,
    source_name: input.sourceName,
    source_url: input.sourceUrl,
    data_date: input.dataDate,
    notes: input.notes || "",
  };
}

function manualGenericInput() {
  return {
    id: "manual-generic",
    name: field("generic-name"),
    investment: number("generic-investment"),
    subsidy: number("generic-subsidy"),
    annualSavingKwh: number("generic-saving"),
    annualOm: number("generic-om"),
    sourceName: field("generic-source"),
    sourceUrl: field("generic-url"),
    dataDate: field("generic-date"),
    notes: "",
  };
}

function pvApiPayload(base) {
  return {
    capacity_kwp: number("pv-capacity"),
    annual_yield_kwh_per_kwp: number("pv-yield"),
    self_use_ratio: number("pv-self-use"),
    annual_building_electricity_kwh: base.annualElectricity,
    electricity_price_cny_per_kwh: base.electricityPrice,
    feed_in_tariff_cny_per_kwh: number("pv-feed-in-tariff"),
    carbon_factor_kgco2e_per_kwh: base.carbonFactor,
    investment_cny: number("pv-investment"),
    subsidy_cny: number("pv-subsidy"),
    annual_om_cny: number("pv-om"),
    source_name: field("pv-source"),
    source_url: field("pv-url"),
    data_date: field("pv-date"),
  };
}

function setValidation(errors, message) {
  const area = $("validation");
  if (errors.length) {
    area.innerHTML = `<div class="error"><strong>尚不能生成数值报告。请补充或更正：</strong><ul>${errors
      .map((item) => `<li>${escapeHtml(item)}</li>`)
      .join("")}</ul></div>`;
    return;
  }
  area.innerHTML = `<div class="ok"><strong>数据校验通过。</strong>${escapeHtml(message)}</div>`;
}

function renderResults(report) {
  $("report-nature").textContent = report.dataNature === "assumption" ? report.disclaimer : "用户录入数据尚需核验，计算通过不等于数据真实或工程可行。";
  $("report-nature").hidden = false;
  if (report.sensitivity) {
    $("sensitivity-results").innerHTML = `<h3>假设敏感性分析</h3><p>${escapeHtml(report.sensitivity.notice)}</p><ul>${report.sensitivity.scenarios.map((item) => `<li>${escapeHtml(item.label)}：${item.error ? escapeHtml(item.error) : `年净收益 ${money(item.result.annualNetBenefit)}，静态回收期 ${item.result.payback === null ? "不输出" : `${decimal(item.result.payback)} 年`}`}</li>`).join("")}</ul>`;
    $("sensitivity-results").hidden = false;
  } else if (report.sensitivityError) {
    $("sensitivity-results").textContent = report.sensitivityError;
    $("sensitivity-results").hidden = false;
  }
  const totals = report.scenarios.reduce(
    (current, scenario) => ({
      investment: current.investment + scenario.netInvestment,
      annualNetBenefit: current.annualNetBenefit + scenario.annualNetBenefit,
      carbon: current.carbon + scenario.annualCarbon,
    }),
    { investment: 0, annualNetBenefit: 0, carbon: 0 },
  );
  const summary = $("summary");
  summary.innerHTML = `
    <div class="metric"><span>已纳入测算的方案</span><strong>${report.scenarios.length} 项</strong></div>
    <div class="metric"><span>方案净投资合计（不代表可同时实施）</span><strong>${money(totals.investment)}</strong></div>
    <div class="metric"><span>年度净收益与年减碳量合计（不代表组合方案）</span><strong>${money(totals.annualNetBenefit)} · ${decimal(totals.carbon)} kgCO₂e</strong></div>`;
  summary.hidden = false;

  $("result-table").innerHTML = report.scenarios
    .map(
      (scenario) => `
      <tr>
        <td><strong>${escapeHtml(scenario.name)}</strong><br /><small>${escapeHtml(scenario.type)}</small></td>
        <td>${money(scenario.netInvestment)}<br /><small>总投资 ${money(scenario.investment)}；补贴 ${money(scenario.subsidy)}</small></td>
        <td>${money(scenario.annualNetBenefit)}<br /><small>节省或发电收益 ${money(scenario.annualBenefit)}；运维 ${money(scenario.annualOm)}</small></td>
        <td>${decimal(scenario.annualCarbon)} kgCO₂e</td>
        <td>${scenario.payback === null ? "不输出" : `${decimal(scenario.payback)} 年`}<br /><small>${scenario.payback === null ? "年度净收益不大于零" : "静态口径"}</small></td>
        <td><small>${escapeHtml(scenario.formula)}<br />来源：${escapeHtml(scenario.sourceName)}（${escapeHtml(scenario.dataDate)}）</small></td>
      </tr>`,
    )
    .join("");
  $("result-table-wrap").hidden = false;
  $("export-json").disabled = false;
  $("print-report").disabled = false;
  renderPolicyMatches(report.base.region);
}

function renderPolicyMatches(region) {
  const candidate = state.policies.filter((policy) => policy.region && region.includes(policy.region));
  const area = $("policy-matches");
  if (!candidate.length) {
    area.hidden = true;
    return;
  }
  area.innerHTML = `<h3>同地区候选政策资料（需人工核验）</h3><p>以下记录仅按地区文本匹配，不代表本项目符合申领条件，也不会自动计入补贴。</p><ul>${candidate
    .map(
      (policy) => `<li><strong>${escapeHtml(policy.policy_name)}</strong>：${escapeHtml(policy.conditions || "请查阅原文条件")}；来源：${escapeHtml(policy.source_url || "未填写")}</li>`,
    )
    .join("")}</ul>`;
  area.hidden = false;
}

async function calculate(event) {
  event.preventDefault();
  if (state.calculateBusy) return;
  invalidateReport();
  const revision = state.revision;
  const errors = [...validateBase(), ...validateGeneric(), ...validatePv()];
  if (checked("generic-enabled") && number("generic-saving") > number("annual-electricity")) errors.push("单项通用方案节电量不能大于建筑年用电量，请核对基线与节能范围");
  if (state.importedOptions.some(option => option.annualSavingKwh > number("annual-electricity"))) errors.push("导入的单项通用方案节电量不能大于建筑年用电量");
  const hasManual = checked("generic-enabled") || checked("pv-enabled");
  if (!hasManual && state.importedOptions.length === 0) errors.push("至少录入一项通用方案、光伏方案，或导入一项可复核方案 CSV");
  if (errors.length) {
    state.report = null;
    $("summary").hidden = true;
    $("result-table-wrap").hidden = true;
    $("policy-matches").hidden = true;
    $("export-json").disabled = true;
    $("print-report").disabled = true;
    setValidation(errors, "");
    return;
  }
  const base = buildBase();
  const usingBackend = state.backendReady;
  const genericInput = checked("generic-enabled") ? manualGenericInput() : null;
  const pvInput = checked("pv-enabled") ? pvApiPayload(base) : null;
  const imported = state.importedOptions.slice();
  const policies = state.policies.slice();
  const scenarios = [];
  state.calculateBusy = true;
  $("calculate").disabled = true;
  $("calculate").textContent = "正在校验与测算…";
  $("validation").setAttribute("aria-busy", "true");
  try {
    if (usingBackend) {
      const requests = [];
      if (genericInput) {
        requests.push(apiRequest("/api/calculate/generic", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(genericApiPayload(genericInput, base)),
        }));
      }
      if (pvInput) {
        requests.push(apiRequest("/api/calculate/pv", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(pvInput),
        }));
      }
      imported.forEach((record) => {
        requests.push(apiRequest("/api/calculate/generic", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(genericApiPayload(record, base)),
        }));
      });
      scenarios.push(...(await Promise.all(requests)));
    } else {
      if (genericInput) scenarios.push(makeGenericScenario(genericInput, base));
      if (pvInput) scenarios.push(makePvScenario(base));
      imported.forEach((record) => scenarios.push(makeGenericScenario(record, base)));
      scenarios.forEach((scenario) => { scenario.calculationEngine = "Browser offline validation"; });
    }
    if (state.revision !== revision) return;
    if (scenarios.some(scenario => ["netInvestment", "annualBenefit", "annualNetBenefit", "annualCarbon"].some(key => !Number.isFinite(scenario[key])) || scenario.payback !== null && !Number.isFinite(scenario.payback))) throw new Error("计算结果超出有限数值范围，请核对输入量级");
    const report = {
      createdAt: new Date().toISOString(),
      executionMode: usingBackend ? "Python deterministic tool" : "Browser offline validation",
      softwareVersion: "0.6.2",
      dataNature: base.dataNature,
      assumptions: base.dataNature === "assumption" ? ClientUI.currentAssumptions(base, scenarios) : [],
      base,
      scenarios,
      policies,
      disclaimer: (base.dataNature === "assumption" ? base.assumptionNotice + " " : "") + "所有数值均为初步测算；需由具备相应资质和权限的人员结合现场条件、适用政策和正式设计资料复核。",
    };
    report.scenarios.forEach((scenario) => { scenario.dataNature = base.dataNature; });
    if (usingBackend && genericInput) {
      try {
        report.sensitivity = await apiRequest("/api/calculate/sensitivity", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(genericApiPayload(genericInput, base)) });
      } catch (_error) { report.sensitivityError = "敏感性分析未完成，未使用替代结果。"; }
    }
    if (state.revision !== revision) return;
    state.report = report;
    $("export-html").disabled = false;
    setValidation([], `已使用 ${scenarios.length} 项可复核方案生成结果；计算模式：${state.report.executionMode}。`);
    renderResults(state.report);
    updatePlanButton();
  } catch (error) {
    if (state.revision === revision) setValidation([`计算未完成：${error.message}`], "");
  } finally {
    state.calculateBusy = false;
    $("calculate").disabled = false;
    $("calculate").textContent = "校验并生成初步方案报告";
    $("validation").setAttribute("aria-busy", "false");
  }
}

function updatePlanButton() {
  $("generate-plan").disabled = state.planBusy || !state.report || !state.backendReady || !state.apiConfigured || !state.ragReady;
  if (state.report && !state.planBusy) $("plan-status").textContent = $("generate-plan").disabled ? "完整方案需要后端、模型和知识库均就绪。" : "测算已就绪，可补充目标并生成完整方案 PDF。";
}

async function generateFullPlan() {
  if (!state.report || state.planBusy || !state.backendReady || !state.apiConfigured || !state.ragReady) { updatePlanButton(); return; }
  const revision = state.revision;
  const planRevision = state.planRevision;
  const base = buildBase();
  const comparison = number("plan-comparison-investment");
  if (comparison !== null && (!Number.isFinite(comparison) || comparison < 0)) { $("plan-status").textContent = "比较投资必须为有限的非负数；留空则不增加情景。"; return; }
  const generic = [];
  if (checked("generic-enabled")) generic.push(genericApiPayload(manualGenericInput(), base));
  state.importedOptions.forEach(record => generic.push(genericApiPayload(record, base)));
  if (generic.length > 8) { $("plan-status").textContent = "完整 PDF 最多纳入 8 项通用方案，请先减少方案再确认云端调用。现有本地测算仍保留。"; return; }
  if (new Set(generic.map(record => record.scenario_id)).size !== generic.length) { $("plan-status").textContent = "方案 ID 重复：请避免导入记录使用手动方案的 manual-generic 编号，再生成完整 PDF。"; return; }
  const request = {base, generic_scenarios: generic, pv_scenario: checked("pv-enabled") ? pvApiPayload(base) : null,
    objective: field("plan-objective") || "在保障安全与使用品质的前提下，形成改造措施、投资分析、实施安排与效果验证方案。",
    comparison_investment: comparison, consent_cloud: true};
  const payload = JSON.stringify(request);
  if (!await confirmAction("将当前项目基线、方案输入、目标及检索片段发送给已配置的百炼和 DeepSeek 服务，生成完整方案 PDF，可能产生 API 费用。不发送照片或密钥文件。请确认这些输入已获授权。继续吗？")) return;
  if (revision !== state.revision || planRevision !== state.planRevision) { $("plan-status").textContent = "授权确认期间输入或目标已改变，未向云端发送本次请求。请按最新内容重新测算并确认。"; return; }
  if (!state.report || state.planBusy || !state.backendReady || !state.apiConfigured || !state.ragReady) { updatePlanButton(); return; }
  state.planBusy = true;
  $("generate-plan").disabled = true;
  $("generate-plan").textContent = "正在生成完整 PDF…";
  $("plan-status").textContent = "正在重新计算、检索资料并编写方案；请保持本页打开，预计需要几分钟。";
  try {
    const { response, blob } = await requestResource("/api/reports/plan", {method:"POST",headers:{"Content-Type":"application/json"},body:payload}, async response => {
      if (!response.ok) {
        let message = `请求失败（${response.status}）`;
        try { const error = await response.json(); message = ClientUI.apiError(error.detail, response.status); } catch (_) {}
        throw new Error(message);
      }
      if (!response.headers.get("content-type")?.includes("application/pdf")) throw new Error("服务器未返回 PDF，未保存伪装报告。");
      const blob = await response.blob();
      if (!blob.size || await blob.slice(0, 5).text() !== "%PDF-") throw new Error("返回内容不是有效 PDF 文件，未保存伪装报告");
      return { response, blob };
    }, 360000);
    if (revision !== state.revision || planRevision !== state.planRevision) {
      $("plan-status").textContent = "生成期间输入或目标发生变化，旧 PDF 已丢弃；请按最新内容重新生成。";
      return;
    }
    const link = document.createElement("a");
    const url = URL.createObjectURL(blob);
    link.href = url;
    link.download = `${base.dataNature === "assumption" ? "假设情景_" : "待核验_"}${ClientUI.filename(base.projectName)}_改造方案与分析报告.pdf`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    $("plan-status").textContent = `完整方案 PDF 已生成并下载。本次检索 ${response.headers.get("X-Source-Count") || "若干"} 个片段；报告编号 ${response.headers.get("X-Report-Id") || "见PDF"}。请核验工程条件后使用。`;
  } catch (error) {
    if (revision === state.revision && planRevision === state.planRevision) $("plan-status").textContent = `完整方案未生成：${error.message}。现有测算结果仍保留；不会提供替代的伪完成报告。`;
  } finally {
    state.planBusy = false;
    $("generate-plan").textContent = "生成并下载完整方案 PDF →";
    $("generate-plan").disabled = !state.report || !state.backendReady || !state.apiConfigured || !state.ragReady;
  }
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let quoted = false;
  let closedQuoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const next = text[index + 1];
    if (char === '"' && quoted && next === '"') {
      cell += '"';
      index += 1;
    } else if (char === '"') {
      if (quoted) { quoted = false; closedQuoted = true; }
      else {
        if (cell.trim() || closedQuoted) throw new Error("CSV 引号位置不规范，请重新导出 CSV");
        quoted = true;
        cell = "";
      }
    } else if (char === "," && !quoted) {
      row.push(cell.trim());
      cell = "";
      closedQuoted = false;
    } else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && next === "\n") index += 1;
      row.push(cell.trim());
      if (row.some((item) => item !== "")) rows.push(row);
      row = [];
      cell = "";
      closedQuoted = false;
    } else {
      if (closedQuoted && !/\s/.test(char)) throw new Error("CSV 引号后出现多余字符，请重新导出 CSV");
      cell += char;
    }
  }
  if (quoted) throw new Error("CSV 引号未闭合，请以 UTF-8 编码重新导出规范 CSV");
  row.push(cell.trim());
  if (row.some((item) => item !== "")) rows.push(row);
  if (rows.length < 2) throw new Error("CSV 至少应包含表头和一条数据记录");
  const headers = rows[0].map((header) => header.replace(/^\uFEFF/, ""));
  if (headers.some(header => !header) || new Set(headers).size !== headers.length) throw new Error("CSV 表头不得为空或重复");
  if (rows.length > 501) throw new Error("单次导入最多 500 条记录，请拆分文件");
  const irregular = rows.slice(1).findIndex(values => values.length !== headers.length);
  if (irregular !== -1) throw new Error(`CSV 第 ${irregular + 2} 行列数与表头不一致，请核对带逗号字段的引号`);
  return rows.slice(1).map((values) => Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""])));
}

function validDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(value + "T00:00:00Z");
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

function csvText(file) {
  if (file.size > 2 * 1024 * 1024) return Promise.reject(new Error("CSV 文件应小于 2 MB，请拆分后导入"));
  return file.text();
}

function loadOptions(event) {
  const file = event.target.files[0];
  if (!file) return;
  const revision = ++state.optionsRevision;
  state.importedOptions = [];
  invalidateReport();
  return csvText(file)
    .then(parseCsv)
    .then((rows) => {
      const required = [
        "scenario_id",
        "scenario_name",
        "investment_cny",
        "subsidy_cny",
        "annual_energy_saving_kwh",
        "annual_om_cny",
        "source_name",
        "source_url",
        "data_date",
      ];
      const missingHeaders = required.filter((header) => !(header in rows[0]));
      if (missingHeaders.length) throw new Error(`方案 CSV 缺少字段：${missingHeaders.join("、")}`);
      const errors = [];
      const ids = new Set();
      const parsed = rows.map((row, index) => {
        const numericKeys = ["investment_cny", "subsidy_cny", "annual_energy_saving_kwh", "annual_om_cny"];
        const missing = required.filter((key) => row[key] === "" || row[key] === undefined);
        const badNumber = numericKeys.filter((key) => !/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(row[key]) || !Number.isFinite(Number(row[key])) || Number(row[key]) < 0);
        if (!validDate(row.data_date)) badNumber.push("data_date 必须为有效 YYYY-MM-DD 日期");
        if (ids.has(row.scenario_id)) badNumber.push("scenario_id 重复");
        ids.add(row.scenario_id);
        if (Number(row.subsidy_cny) > Number(row.investment_cny)) badNumber.push("subsidy_cny 不得大于 investment_cny");
        if (missing.length || badNumber.length) errors.push(`第 ${index + 2} 行：${[...missing, ...badNumber].join("、")}`);
        return {
          id: row.scenario_id,
          name: row.scenario_name,
          investment: Number(row.investment_cny),
          subsidy: Number(row.subsidy_cny),
          annualSavingKwh: Number(row.annual_energy_saving_kwh),
          annualOm: Number(row.annual_om_cny),
          sourceName: row.source_name,
          sourceUrl: row.source_url,
          dataDate: row.data_date,
          notes: row.notes || "",
        };
      });
      if (errors.length) throw new Error(`存在无法测算的记录：${errors.join("；")}`);
      if (revision !== state.optionsRevision) return;
      state.importedOptions = parsed;
      invalidateReport();
      $("import-status").textContent = `已导入 ${parsed.length} 项可复核方案。提交报告时将与手动方案一并列出。`;
    })
    .catch((error) => {
      if (revision !== state.optionsRevision) return;
      state.importedOptions = [];
      $("import-status").textContent = `方案 CSV 未导入：${error.message}`;
    });
}

function loadPolicies(event) {
  const file = event.target.files[0];
  if (!file) return;
  const revision = ++state.policiesRevision;
  state.policies = [];
  invalidateReport();
  return csvText(file)
    .then(parseCsv)
    .then((rows) => {
      const required = ["policy_id", "region", "policy_name", "conditions", "source_url", "data_date"];
      const missingHeaders = required.filter((header) => !(header in rows[0]));
      if (missingHeaders.length) throw new Error(`政策 CSV 缺少字段：${missingHeaders.join("、")}`);
      const bad = rows.filter((row) => required.some((header) => row[header] === "" || row[header] === undefined));
      if (bad.length) throw new Error("政策 CSV 存在必填字段为空的记录");
      if (rows.some(row => !validDate(row.data_date))) throw new Error("政策 data_date 必须为有效 YYYY-MM-DD 日期");
      if (new Set(rows.map(row => row.policy_id)).size !== rows.length) throw new Error("政策 policy_id 不得重复");
      if (revision !== state.policiesRevision) return;
      state.policies = rows;
      invalidateReport();
      const prefix = $("import-status").textContent ? `${$("import-status").textContent} ` : "";
      $("import-status").textContent = `${prefix}已导入 ${rows.length} 条政策资料；生成报告后按地区提示候选项。`;
    })
    .catch((error) => {
      if (revision !== state.policiesRevision) return;
      state.policies = [];
      $("import-status").textContent = `政策 CSV 未导入：${error.message}`;
    });
}

function previewPhotos(event) {
  const area = $("photo-preview");
  area.innerHTML = "";
  state.photoRevision += 1;
  $("vision-result").hidden = true;
  state.photoFiles = [];
  const files = [...event.target.files];
  if (files.length > 5 || files.some(file => !["image/jpeg", "image/png", "image/webp", "image/gif"].includes(file.type) || file.size > 10 * 1024 * 1024 || file.size === 0) || files.reduce((total, file) => total + file.size, 0) > 32 * 1024 * 1024) {
    $("photo-readiness").textContent = "照片未接受：请选择 1–5 张静态 JPG/PNG/WebP/GIF，每张大于 0 且不超过 10 MiB，合计不超过 32 MiB。请先缩图；文件只在本地校验，未上传。";
    $("analyze-photos").disabled = true;
    return;
  }
  state.photoFiles = files;
  updateCapabilityHints();
  $("analyze-photos").disabled = state.visionBusy || !state.apiConfigured || state.photoFiles.length === 0;
  state.photoFiles.forEach((file) => {
    const url = URL.createObjectURL(file);
    const figure = document.createElement("figure");
    const image = document.createElement("img");
    const caption = document.createElement("figcaption");
    image.src = url;
    image.alt = `现场照片预览：${file.name}`;
    image.onload = image.onerror = () => URL.revokeObjectURL(url);
    caption.textContent = file.name;
    figure.append(image, caption);
    area.append(figure);
  });
}

function renderJsonList(value) {
  if (!Array.isArray(value) || value.length === 0) return "无";
  return value.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
}

async function analyzePhotos() {
  const area = $("vision-result");
  if (state.visionBusy || !state.backendReady || !state.apiConfigured || state.photoFiles.length === 0) return;
  const revision = state.photoRevision;
  if (!await confirmAction("将所选照片发送云端多模态模型，可能产生费用。请确认已获授权并去除身份、房号等敏感信息。继续吗？")) return;
  if (revision !== state.photoRevision || !state.photoFiles.length) return;
  state.visionBusy = true;
  $("analyze-photos").disabled = true;
  area.setAttribute("aria-busy", "true");
  area.hidden = false;
  area.className = "agent-output";
  area.textContent = "正在调用多模态 API，仅提取照片中可见信息……";
  const body = new FormData();
  state.photoFiles.forEach((file) => body.append("files", file));
  try {
    const result = await apiRequest("/api/vision/analyze", { method: "POST", body }, 180000);
    if (revision !== state.photoRevision) return;
    area.innerHTML = `<h3>待人工确认的照片观察</h3>
      <p><strong>外墙：</strong>${escapeHtml(result.facade_material ?? "无法确认")}</p>
      <p><strong>门窗：</strong>${escapeHtml(result.window_type ?? "无法确认")}</p>
      <p><strong>外遮阳：</strong>${escapeHtml(result.external_shading ?? "无法确认")}</p>
      <p><strong>屋顶形式：</strong>${escapeHtml(result.roof_form ?? "无法确认")}</p>
      <p><strong>可见问题：</strong></p><ul>${renderJsonList(result.visible_issues)}</ul>
      <p><strong>不确定字段：</strong></p><ul>${renderJsonList(result.uncertain_fields)}</ul>
      <p><strong>建议人工核查：</strong></p><ul>${renderJsonList(result.recommended_manual_checks)}</ul>
      <p class="hint">此结果不会自动写入工程参数；面积、传热系数、窗墙比、承载力和价格仍须由真实资料提供。</p>`;
  } catch (error) {
    if (revision !== state.photoRevision) return;
    area.className = "agent-output error-output";
    area.textContent = `多模态分析未完成：${error.message}`;
  } finally {
    state.visionBusy = false;
    $("analyze-photos").disabled = !state.apiConfigured || !state.backendReady || !state.photoFiles.length;
    area.setAttribute("aria-busy", "false");
  }
}

async function ingestRag() {
  if (state.ingestBusy) return;
  if (!await confirmAction("只同步已核对名单中指纹一致的公开资料。原文、解析/分块和元数据均一致的已入库文档跳过，新增或变化内容会发送百炼生成向量，可能产生费用。继续吗？")) return;
  const button = $("ingest-rag");
  state.ingestBusy = true;
  button.disabled = true;
  $("mode-note").textContent = "正在核对上传名单、文件指纹并同步资料，请勿关闭页面或重复操作……";
  try {
    const result = await apiRequest("/api/rag/ingest", { method: "POST" }, 360000);
    await checkBackend();
    await loadKnowledgeCatalog();
    $("mode-note").textContent = `同步完成：新增或更新 ${result.indexed_documents ?? 0} 份，未变化 ${result.unchanged_documents ?? 0} 份，跳过 ${result.skipped?.length ?? 0} 条。`;
  } catch (error) {
    $("mode-note").textContent = `RAG 入库未完成：${error.message}`;
  } finally {
    state.ingestBusy = false;
    button.disabled = !state.embeddingsConfigured || !state.backendReady || !state.manifestFound;
  }
}

async function askAgent() {
  if (state.agentBusy) return;
  const question = field("agent-question");
  const area = $("agent-result");
  area.hidden = false;
  area.className = "agent-output";
  if (question.length < 2) {
    area.className = "agent-output error-output";
    area.textContent = "请先填写需要核查的问题。";
    return;
  }
  if (!state.backendReady || !state.apiConfigured || !state.ragReady) { updateCapabilityHints(); area.textContent = $("agent-readiness").textContent; return; }
  const questionRevision = state.questionRevision;
  const revision = state.revision;
  const button = $("ask-agent");
  state.agentBusy = true;
  button.disabled = true;
  button.textContent = "正在检索与核查…";
  area.setAttribute("aria-busy", "true");
  try {
    if (!await confirmAction("将问题、当前项目基线及检索片段发送至配置的百炼向量和模型云端服务，可能产生 API 费用。请确认内容不含密钥、个人身份或未授权资料。继续吗？")) { area.textContent = "已取消咨询，未向云端发送问题或项目资料。"; return; }
    if (revision !== state.revision || questionRevision !== state.questionRevision || question !== field("agent-question")) { area.textContent = "授权确认期间输入或问题已改变，请按最新内容重新提问。"; return; }
    area.innerHTML = '<div class="loading-line"><span class="loading-dot"></span>正在检索资料并组织答复，请稍候。不会以预写答案代替 API 响应。</div>';
    const result = await apiRequest("/api/agent/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, project_context: buildBase(), region: field("region") || null, consent_cloud: true }),
    }, 180000);
    if (revision !== state.revision || questionRevision !== state.questionRevision || question !== field("agent-question")) { area.textContent = "项目输入或问题已变更，本次旧回答未展示。请按最新内容重新提问。"; return; }
    const tools = result.tool_results || [];
    area.innerHTML = `<div class="answer-header"><span class="answer-label">AI 决策助手</span><small>${tools.length} 次实际工具调用 · 请人工复核</small></div><div class="answer-body">${ClientUI.markdown(result.answer)}</div><h3 class="sources-heading">检索来源 · 点击核查原文</h3>${ClientUI.citations(result.citations || [])}<details class="tool-trace"><summary>查看实际检索 / 计算记录</summary>${tools.map(t=>`<h4>${escapeHtml(t.tool)}</h4><pre>${escapeHtml(JSON.stringify({arguments:t.arguments,result:t.result},null,2))}</pre>`).join("")}</details>`;
  } catch (error) {
    area.className = "agent-output error-output";
    area.textContent = revision === state.revision && questionRevision === state.questionRevision ? `本次咨询未完成：${error.message}。请确认服务余额与网络后重试；未展示替代答案。` : "项目输入或问题已变更，请重新提问。";
  } finally {
    state.agentBusy = false;
    button.disabled = !(state.apiConfigured && state.ragReady);
    button.textContent = "检索资料并回答 →";
    area.setAttribute("aria-busy", "false");
  }
}

async function loadKnowledgeCatalog() {
  if (state.catalogBusy) return;
  state.catalogBusy = true;
  try {
    state.catalog = await apiRequest("/api/knowledge/catalog", {}, 8000);
    const c = state.catalog;
    $("hero-docs").textContent = c.indexed_documents;
    $("hero-chunks").textContent = c.indexed_chunks;
    $("hero-readiness").textContent = `${c.total} 条资料记录 · ${c.blocked_documents} 条需处理或核对`;
    $("library-metrics").innerHTML = [[c.total,"清单记录"],[c.indexed_documents,"已真实入库"],[c.indexed_chunks,"可检索文本块"],[c.blocked_documents,"需处理 / 待核对"]].map(([n,label])=>`<div><strong>${n}</strong><span>${label}</span></div>`).join("");
    $("knowledge-notice").textContent = c.notice + " 私人照片、账单、签章和密钥未批量上传。";
    renderKnowledgeCatalog();
  } catch (error) {
    state.catalog = null;
    $("hero-docs").textContent = "—";
    $("hero-chunks").textContent = "—";
    $("knowledge-list").textContent = "资料状态读取失败；未继续展示上次的入库状态。";
    $("knowledge-count").textContent = "当前状态未知，请重新检测。";
    $("library-metrics").textContent = `资料状态读取失败：${error.message}`;
    $("hero-readiness").textContent = "资料状态暂不可用，请检查本地服务。";
  } finally {
    state.catalogBusy = false;
  }
}

function renderKnowledgeCatalog() {
  if (!state.catalog) return;
  const query = $("knowledge-search").value.trim().toLowerCase();
  const status = $("knowledge-filter").value;
  const records = state.catalog.records.filter(r => (!query || `${r.title} ${r.region} ${r.document_id}`.toLowerCase().includes(query)) && (status === "all" || status === r.status || status === "blocked" && r.status === "review"));
  const labels = {indexed:"已入库", pending:"等待入库", blocked:"需处理", review:"待核对"};
  $("knowledge-count").textContent = `显示 ${records.length} / ${state.catalog.total} 条资料`;
  $("knowledge-list").innerHTML = records.length ? records.map(r => {
    const url = ClientUI.safeUrl(r.source_url);
    return `<article class="knowledge-item"><div><span class="status-pill ${r.status === "indexed" ? "ok" : "off"}">${labels[r.status] || "待核对"}</span><small>${escapeHtml(r.document_id)} · ${escapeHtml(r.region)}</small></div><h3>${escapeHtml(r.title)}</h3><p>${escapeHtml(r.reason)}</p>${r.source_note ? `<p class="hint">${escapeHtml(r.source_note)}</p>` : ""}<div class="knowledge-bottom"><span>${r.indexed_chunks} 个已入库片段 · 适用性待核验</span>${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">查看来源 ↗</a>` : ""}</div></article>`;
  }).join("") : '<p class="hint">没有匹配的资料，换个关键词试试。</p>';
}

function exportJson() {
  if (!state.report) return;
  const blob = new Blob([JSON.stringify(state.report, null, 2)], { type: "application/json;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${state.report.dataNature === "assumption" ? "假设情景_" : "待核验_"}${ClientUI.filename(state.report.base.projectName)}_初步测算报告.json`;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 10000);
}

function exportReadableReport() {
  if (!state.report) return;
  const blob = new Blob([ClientUI.reportHtml(state.report)], {type:"text/html;charset=utf-8"});
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${state.report.dataNature === "assumption" ? "假设情景_" : "待核验_"}${ClientUI.filename(state.report.base.projectName)}_初步方案报告.html`;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 10000);
}

function printReport() {
  if (!state.report) return;
  const report = state.report;
  const rows = report.scenarios
    .map(
      (scenario) => `<tr><td>${escapeHtml(scenario.name)}</td><td>${money(scenario.netInvestment)}</td><td>${money(scenario.annualNetBenefit)}</td><td>${decimal(scenario.annualCarbon)} kgCO₂e</td><td>${scenario.payback === null ? "不输出" : `${decimal(scenario.payback)} 年`}</td><td>${escapeHtml(scenario.formula)}<br>方案来源：${escapeHtml(scenario.sourceName)}；${escapeHtml(scenario.sourceUrl)}；${escapeHtml(scenario.dataDate)}<br>${escapeHtml(scenario.notes)}</td></tr>`)
    .join("");
  const popup = window.open("", "_blank");
  if (!popup) {
    window.alert("浏览器阻止了报告窗口，请允许弹出窗口后重试。");
    return;
  }
  popup.document.write(`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>${escapeHtml(report.base.projectName)} 初步测算报告</title><style>body{font-family:'Microsoft YaHei',sans-serif;color:#1b313c;max-width:900px;margin:40px auto;line-height:1.65}h1{font-size:24px}h2{font-size:17px;margin-top:28px}table{width:100%;border-collapse:collapse;font-size:12px}th,td{border:1px solid #bfcbd0;padding:8px;vertical-align:top;text-align:left}th{background:#eaf3f2}.note{padding:12px;background:#f8f2e5}.sources{font-size:13px}</style></head><body><h1>${escapeHtml(report.base.projectName)} 低碳改造初步测算报告</h1><p>生成时间：${escapeHtml(new Date(report.createdAt).toLocaleString("zh-CN"))}；计算模式：${escapeHtml(report.executionMode)}</p><div class="note">${escapeHtml(report.disclaimer)}</div><h2>项目基线</h2><p>地区：${escapeHtml(report.base.region)}；年用电量：${decimal(report.base.annualElectricity)} kWh；电价：${decimal(report.base.electricityPrice, 4)} 元/kWh；电力排放因子：${decimal(report.base.carbonFactor, 6)} kgCO₂e/kWh。</p><h2>方案比选</h2><table><thead><tr><th>方案</th><th>净投资</th><th>年净收益</th><th>年减碳量</th><th>静态回收期</th><th>计算与来源</th></tr></thead><tbody>${rows}</tbody></table><h2>基线数据来源</h2><ul class="sources"><li>电价：${escapeHtml(report.base.electricityPriceSource)}；${escapeHtml(report.base.electricityPriceUrl)}；基准日期 ${escapeHtml(report.base.baselineDate)}</li><li>碳因子：${escapeHtml(report.base.carbonSource)}；${escapeHtml(report.base.carbonUrl)}；基准日期 ${escapeHtml(report.base.baselineDate)}</li></ul><p>政策、工程适用性、补贴资格与现场条件须由项目团队另行核验。</p></body></html>`);
  popup.document.close();
  popup.focus();
  popup.print();
}

function setupToggle(toggleId, contentId) {
  $(toggleId).addEventListener("change", () => {
    $(contentId).hidden = !checked(toggleId);
  });
}

$("project-form").addEventListener("submit", calculate);
$("options-csv").addEventListener("change", loadOptions);
$("policies-csv").addEventListener("change", loadPolicies);
$("photos").addEventListener("change", previewPhotos);
$("analyze-photos").addEventListener("click", analyzePhotos);
$("check-backend").addEventListener("click", () => { checkBackend(); loadKnowledgeCatalog(); });
$("ingest-rag").addEventListener("click", ingestRag);
$("ask-agent").addEventListener("click", askAgent);
$("export-json").addEventListener("click", exportJson);
$("export-html").addEventListener("click", exportReadableReport);
$("print-report").addEventListener("click", printReport);
$("generate-plan").addEventListener("click", generateFullPlan);
$("plan-options").addEventListener("input", () => { state.planRevision += 1; if (state.planBusy) $("plan-status").textContent = "目标或比较输入已改变，旧版本生成后不会自动下载。"; });
$("load-wangyue").addEventListener("click", loadWangyueFields);
$("load-assumptions").addEventListener("click", loadAssumptions);
$("clear-case").addEventListener("click", async () => { if (await confirmAction("清空当前未保存的输入、图片及报告？")) resetCase(); });
$("project-form").addEventListener("input", event => { if (event.target.id !== "agent-question") invalidateReport(); });
$("agent-question").addEventListener("input", () => { state.questionRevision += 1; if (!state.agentBusy) $("agent-result").hidden = true; });
$("start-demo").addEventListener("click", loadAssumptions);
$("knowledge-search").addEventListener("input", renderKnowledgeCatalog);
$("knowledge-filter").addEventListener("change", renderKnowledgeCatalog);
document.querySelectorAll("[data-question]").forEach(button => button.addEventListener("click", () => { state.questionRevision += 1; $("agent-question").value = button.dataset.question; if (!state.agentBusy) $("agent-result").hidden = true; $("agent-question").focus(); }));
setupToggle("generic-enabled", "generic-fields");
setupToggle("pv-enabled", "pv-fields");
checkBackend();
loadDemoCaseStatus();
loadKnowledgeCatalog();
