/* 客户体验增强层：完成度进度、滚动定位、字段级校验、操作反馈、离开提醒。
   纯展示与交互增强，不参与任何计算，不写入浏览器本地存储，不改变后端口径。
   通过 DOM 事件与 MutationObserver 挂钩 app.js，独立可开关。 */
"use strict";
(function () {
  const $ = (id) => document.getElementById(id);

  // 必填字段（与 app.js 的 validateBase/validateGeneric/validatePv 保持一致）
  const REQUIRED_BASE = [
    "region", "annual-electricity", "electricity-price", "electricity-price-source",
    "electricity-price-url", "carbon-factor", "carbon-source", "carbon-url", "baseline-date",
  ];
  const REQUIRED_GENERIC = [
    "generic-name", "generic-investment", "generic-subsidy", "generic-saving",
    "generic-om", "generic-source", "generic-url", "generic-date",
  ];
  const REQUIRED_PV = [
    "pv-capacity", "pv-yield", "pv-self-use", "pv-feed-in-tariff",
    "pv-investment", "pv-subsidy", "pv-om", "pv-source", "pv-url", "pv-date",
  ];

  function value(id) {
    const el = $(id);
    if (!el) return "";
    return el.type === "checkbox" ? el.checked : el.value.trim();
  }
  const filled = (id) => value(id) !== "";

  function requiredNow() {
    const list = [...REQUIRED_BASE];
    if ($("generic-enabled") && $("generic-enabled").checked) list.push(...REQUIRED_GENERIC);
    if ($("pv-enabled") && $("pv-enabled").checked) list.push(...REQUIRED_PV);
    return list;
  }

  /* ── 1. 顶部进度仪表盘 ─────────────────────────────────────────── */
  function buildProgressBar() {
    const form = $("project-form");
    if (!form || $("ux-progress")) return;
    const bar = document.createElement("div");
    bar.id = "ux-progress";
    bar.className = "ux-progress";
    bar.setAttribute("role", "status");
    bar.setAttribute("aria-live", "polite");
    bar.innerHTML = `
      <div class="ux-progress-head">
        <span class="ux-progress-title">项目录入完成度</span>
        <span class="ux-progress-count" id="ux-progress-count">—</span>
      </div>
      <div class="ux-progress-track"><div class="ux-progress-fill" id="ux-progress-fill"></div></div>
      <div class="ux-progress-note" id="ux-progress-note">基线信息共 9 项必填；通用与光伏方案按需勾选。</div>`;
    form.parentNode.insertBefore(bar, form);
  }

  function updateProgress() {
    const fill = $("ux-progress-fill");
    if (!fill) return;
    const list = requiredNow();
    const done = list.filter(filled).length;
    const pct = list.length ? Math.round((done / list.length) * 100) : 0;
    fill.style.width = pct + "%";
    fill.classList.toggle("complete", pct === 100);
    const count = $("ux-progress-count");
    count.textContent = `${done} / ${list.length}`;
    const missing = list.filter((id) => !filled(id));
    const note = $("ux-progress-note");
    if (!missing.length) {
      note.textContent = "必填项已齐备，可进入方案录入或直接生成报告。";
      note.classList.add("ok");
    } else {
      note.textContent = `还需填写 ${missing.length} 项：${missing.slice(0, 3).map(uxFieldLabel).join("、")}${missing.length > 3 ? " 等" : ""}。`;
      note.classList.remove("ok");
    }
  }

  function uxFieldLabel(id) {
    const el = $(id);
    if (!el) return id;
    const parent = el.closest("label");
    if (parent) {
      const span = parent.querySelector(".required");
      const text = parent.textContent.replace(/必填/g, "").trim();
      if (text) return text.slice(0, 14);
    }
    return id;
  }

  /* ── 2. 底部悬浮操作栏 ─────────────────────────────────────────── */
  function buildDock() {
    if ($("ux-dock")) return;
    const dock = document.createElement("div");
    dock.id = "ux-dock";
    dock.className = "ux-dock";
    dock.innerHTML = `
      <div class="ux-dock-progress">
        <span class="ux-dock-label" id="ux-dock-label">正在检查录入状态…</span>
      </div>
      <div class="ux-dock-actions">
        <button type="button" id="ux-jump-result" class="ux-dock-btn" hidden>查看结果 ↓</button>
        <button type="button" id="ux-back-top" class="ux-dock-btn">返回顶部 ↑</button>
      </div>`;
    document.body.appendChild(dock);
    $("ux-jump-result").addEventListener("click", () => {
      const target = $("result-heading") || $("project-heading");
      target?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    $("ux-back-top").addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));
  }

  function updateDock() {
    const label = $("ux-dock-label");
    if (!label) return;
    const list = requiredNow();
    const done = list.filter(filled).length;
    // 报告状态直接从已渲染的 DOM 读取，不依赖 app.js 的模块级 state（const 不挂 window）。
    const summaryEl = $("summary");
    const tableRows = [...document.querySelectorAll("#result-table tr")];
    const hasReport = summaryEl && !summaryEl.hidden && tableRows.length > 0;
    if (hasReport) {
      const firstPayback = document.querySelector("#result-table tr td:nth-child(5)");
      const paybackText = firstPayback ? firstPayback.textContent.trim().split("\n")[0] : "—";
      label.textContent = `已生成 ${tableRows.length} 项方案 · 首项回收期约 ${paybackText}`;
      $("ux-jump-result").hidden = false;
    } else {
      label.textContent = done === list.length ? "必填项已齐备，可生成报告" : `录入完成度 ${done} / ${list.length}`;
      $("ux-jump-result").hidden = true;
    }
  }

  /* ── 3. 滚动定位（scroll-spy）与返回顶部显隐 ─────────────────────── */
  const NAV_IDS = ["knowledge-heading", "case-heading", "technology-heading", "project-heading", "agent-heading", "result-heading", "plan-heading"];
  function buildScrollSpy() {
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
      if (!visible.length) return;
      const id = visible[0].target.id;
      document.querySelectorAll(".page-nav a").forEach((a) => {
        a.classList.toggle("active", a.getAttribute("href") === "#" + id);
      });
    }, { rootMargin: "-96px 0px -55% 0px", threshold: 0 });
    NAV_IDS.forEach((id) => { const el = $(id); if (el) observer.observe(el); });

    const dock = () => { const d = $("ux-dock"); if (d) d.classList.toggle("visible", window.scrollY > 600); };
    window.addEventListener("scroll", dock, { passive: true });
    dock();
  }

  /* ── 4. 字段级校验（失焦即提示，不必等提交） ──────────────────────── */
  function ensureFieldMessage(input) {
    let msg = input.parentElement?.querySelector(".ux-field-msg");
    if (!msg) {
      msg = document.createElement("span");
      msg.className = "ux-field-msg";
      input.insertAdjacentElement("afterend", msg);
    }
    return msg;
  }
  function bindFieldValidation() {
    const all = [...REQUIRED_BASE, ...REQUIRED_GENERIC, ...REQUIRED_PV];
    all.forEach((id) => {
      const el = $(id);
      if (!el) return;
      const apply = () => {
        const required = requiredNow().includes(id);
        const empty = value(id) === "";
        el.classList.toggle("ux-invalid", required && empty);
        const msg = ensureFieldMessage(el);
        if (required && empty && el === document.activeElement) return; // 聚焦中不打断输入
        if (required && empty) msg.textContent = "必填项";
        else msg.textContent = "";
      };
      el.addEventListener("blur", apply);
      el.addEventListener("input", () => {
        el.classList.remove("ux-invalid");
        ensureFieldMessage(el).textContent = "";
      });
    });
  }

  /* ── 5. 操作反馈（toast） ───────────────────────────────────────── */
  let toastTimer = null;
  function toast(text, kind) {
    let el = $("ux-toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "ux-toast";
      el.className = "ux-toast";
      el.setAttribute("role", "status");
      document.body.appendChild(el);
    }
    el.textContent = text;
    el.className = "ux-toast " + (kind || "");
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), 2600);
  }
  function bindToasts() {
    document.addEventListener("click", (event) => {
      const btn = event.target.closest("button");
      if (!btn) return;
      const id = btn.id;
      if (id === "export-json") toast("已导出 JSON 初步测算报告");
      else if (id === "export-html") toast("已下载可阅读的 HTML 报告");
      else if (id === "print-report") toast("已打开打印预览");
      else if (id === "load-assumptions") toast("正在载入假设情景（数据均为演示假设）", "warn");
    }, true);
    // 观察「假设情景已载入」横幅出现，作为成功提示
    const banner = $("data-nature-banner");
    if (banner) {
      new MutationObserver((mutations) => {
        if (mutations.some((m) => m.type === "attributes" && m.attributeName === "hidden" && banner.hidden === false)) {
          toast("假设情景已载入，可下拉到结果区生成报告", "warn");
        }
      }).observe(banner, { attributes: true });
    }
  }

  /* ── 6. 离开提醒（不写存储，仅提示未导出内容） ─────────────────────── */
  function bindBeforeUnload() {
    window.addEventListener("beforeunload", (event) => {
      const hasInput = [...document.querySelectorAll("#project-form input, #project-form textarea")].some((el) => (el.type === "checkbox" ? el.checked : el.value.trim() !== ""));
      const summaryEl = $("summary");
      const hasReport = summaryEl && !summaryEl.hidden;
      if (hasInput || hasReport) {
        event.preventDefault();
        event.returnValue = "当前有未导出的录入内容或报告，离开后将丢失。确定离开吗？";
        return event.returnValue;
      }
    });
  }

  /* ── 6. 基线多步向导 ───────────────────────────────────────────── */
  function bindWizard() {
    const wizard = $("base-wizard");
    if (!wizard) return;
    const steps = [...wizard.querySelectorAll(".wizard-step")];
    const panels = [...wizard.querySelectorAll(".wizard-panel")];
    const prev = $("wizard-prev");
    const next = $("wizard-next");
    let current = 1;
    const TOTAL = steps.length;

    function go(step) {
      current = Math.max(1, Math.min(TOTAL, step));
      steps.forEach((s) => {
        const isActive = Number(s.dataset.step) === current;
        s.classList.toggle("active", isActive);
        s.setAttribute("aria-selected", String(isActive));
      });
      panels.forEach((p) => {
        const isActive = Number(p.dataset.step) === current;
        p.classList.toggle("active", isActive);
        p.hidden = !isActive;
      });
      prev.disabled = current === 1;
      next.textContent = current === TOTAL ? "完成录入" : "下一步";
    }

    steps.forEach((s) => s.addEventListener("click", () => go(Number(s.dataset.step))));
    if (next) next.addEventListener("click", () => go(current + 1));
    if (prev) prev.addEventListener("click", () => go(current - 1));
    go(1);
  }

  /* ── 7. 报告生成后刷新图表 ─────────────────────────────────────── */
  function bindCharts() {
    const summary = $("summary");
    if (!summary) return;
    new MutationObserver(() => {
      if (!summary.hidden && window.__charts) window.__charts.renderAll();
    }).observe(summary, { attributes: true });
  }

  /* ── 启动 ──────────────────────────────────────────────────────── */
  function init() {
    buildProgressBar();
    buildDock();
    buildScrollSpy();
    bindFieldValidation();
    bindToasts();
    bindBeforeUnload();
    bindWizard();
    bindCharts();
    document.addEventListener("input", () => { updateProgress(); updateDock(); });
    document.addEventListener("change", () => { updateProgress(); updateDock(); });
    // app.js 通过 element.value= 程序化赋值（如载入假设情景）不触发 input/change，
    // 用低频轮询兜底刷新，保证进度与悬浮栏始终反映真实表单状态。
    setInterval(() => { updateProgress(); updateDock(); }, 500);
    // 报告生成后（summary 从隐藏变显示）刷新 dock 关键指标
    const summary = $("summary");
    if (summary) {
      new MutationObserver(() => { if (!summary.hidden) updateDock(); }).observe(summary, { attributes: true });
    }
    updateProgress();
    updateDock();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
