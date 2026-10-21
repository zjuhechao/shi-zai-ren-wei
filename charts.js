/* 纯前端 SVG 图表：方案净投资对比条形图 + 15 年累计现金流曲线。
   只读取 app.js 的 state.report 已算好的数值，自身不做任何计算、不伪造数据。
   依赖 app.js 先执行；通过全局 window.__charts 暴露，供 app.js/ux.js 调用。 */
"use strict";
(function () {
  const $ = (id) => document.getElementById(id);
  const NS = "http://www.w3.org/2000/svg";
  const PALETTE = ["#007a78", "#b8733a", "#557aaa", "#857098", "#2fa17f", "#9a5f00"];

  function el(name, attrs, parent) {
    const node = document.createElementNS(NS, name);
    for (const k in attrs) node.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(node);
    return node;
  }

  function textNode(parent, x, y, str, cls, anchor) {
    const t = el("text", { x, y, class: cls, "text-anchor": anchor || "middle" }, parent);
    t.textContent = str;
    return t;
  }

  function money(value) {
    return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(value);
  }

  // 取报告方案数据；无报告时返回空
  function scenarios() {
    // app.js 的 state 是模块级 const（不挂 window），renderResults 时已把 report 暴露到 window.__report
    const report = (window.__report) || (window.state && window.state.report);
    if (report && Array.isArray(report.scenarios)) return report.scenarios;
    return [];
  }

  /* ── 方案净投资对比条形图 ─────────────────────────────────────── */
  function renderInvestment(host) {
    host.innerHTML = "";
    const sc = scenarios();
    if (!sc.length) return;
    const W = 640, LH = 28, L = 210, R = 70, T = 16, B = 34;
    const H = T + sc.length * LH + B;
    const maxVal = Math.max(...sc.map((s) => s.netInvestment), 1);
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "方案净投资对比条形图", class: "svg-chart" }, host);

    // 网格线（3 等分）
    for (let i = 0; i <= 3; i++) {
      const x = L + ((W - L - R) * i) / 3;
      const gridVal = (maxVal * i) / 3;
      el("line", { x1: x, y1: T, x2: x, y2: T + sc.length * LH, class: "grid-line" }, svg);
      textNode(svg, x, H - 8, money(gridVal), "axis-text");
    }

    sc.forEach((s, i) => {
      const y = T + i * LH;
      const barW = ((W - L - R) * s.netInvestment) / maxVal;
      textNode(svg, L - 10, y + LH / 2 + 4, s.name || s.id, "bar-label", "end");
      el("rect", { x: L, y: y + 5, width: Math.max(barW, 2), height: LH - 10, rx: 4, fill: PALETTE[i % PALETTE.length], class: "bar-rect" }, svg);
      textNode(svg, L + Math.max(barW, 2) + 8, y + LH / 2 + 4, money(s.netInvestment), "bar-value", "start");
    });
  }

  /* ── 15 年累计现金流曲线 ─────────────────────────────────────── */
  function renderCashflow(host) {
    host.innerHTML = "";
    const sc = scenarios();
    if (!sc.length) return;
    const W = 640, H = 300, L = 58, R = 18, T = 20, B = 34;
    const years = 15;
    // 每个方案的现金流序列：y=0..15，值 = -netInvestment + annualNetBenefit*y
    const series = sc.map((s) => {
      const vals = [];
      for (let y = 0; y <= years; y++) vals.push(-s.netInvestment + s.annualNetBenefit * y);
      return { name: s.name || s.id, vals, color: PALETTE[sc.indexOf(s) % PALETTE.length] };
    });
    let lo = 0, hi = 0;
    series.forEach((sr) => sr.vals.forEach((v) => { if (v < lo) lo = v; if (v > hi) hi = v; }));
    const span = Math.max(hi - lo, 1);
    lo -= span * 0.08; hi += span * 0.08;
    const x = (y) => L + ((W - L - R) * y) / years;
    const yv = (v) => T + ((H - T - B) * (hi - v)) / (hi - lo);

    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "15 年累计现金流曲线", class: "svg-chart" }, host);

    // 水平网格 + Y 轴刻度
    for (let i = 0; i <= 4; i++) {
      const v = hi - ((hi - lo) * i) / 4;
      const yy = yv(v);
      el("line", { x1: L, y1: yy, x2: W - R, y2: yy, class: "grid-line" }, svg);
      textNode(svg, L - 8, yy + 4, (v / 10000).toFixed(0), "axis-text", "end");
    }
    // 零基线
    if (lo < 0 && hi > 0) {
      el("line", { x1: L, y1: yv(0), x2: W - R, y2: yv(0), class: "zero-line" }, svg);
    }
    // X 轴年份
    [0, 5, 10, 15].forEach((y) => textNode(svg, x(y), H - 10, String(y), "axis-text"));

    // 曲线
    series.forEach((sr) => {
      const d = sr.vals.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${yv(v).toFixed(1)}`).join(" ");
      el("path", { d, fill: "none", stroke: sr.color, "stroke-width": 2, "stroke-linecap": "round", "stroke-linejoin": "round", class: "cashflow-line" }, svg);
    });

    // 图例
    const legend = el("g", { class: "chart-legend" }, svg);
    series.forEach((sr, i) => {
      const ly = T + i * 18;
      el("line", { x1: W - R - 40, y1: ly + 6, x2: W - R - 26, y2: ly + 6, stroke: sr.color, "stroke-width": 3 }, legend);
      textNode(legend, W - R - 22, ly + 10, sr.name, "legend-text", "start");
    });
  }

  function renderAll() {
    const box = $("charts");
    const sc = scenarios();
    if (!box) return;
    if (!sc.length) { box.hidden = true; return; }
    box.hidden = false;
    renderInvestment($("chart-investment"));
    renderCashflow($("chart-cashflow"));
  }

  window.__charts = { renderAll };

  // 报告渲染完成后（summary 显示）自动刷新图表
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      const summary = $("summary");
      if (summary) new MutationObserver(() => { if (!summary.hidden) renderAll(); }).observe(summary, { attributes: true });
    });
  } else {
    const summary = $("summary");
    if (summary) new MutationObserver(() => { if (!summary.hidden) renderAll(); }).observe(summary, { attributes: true });
  }
})();
