/* Small, escaped Markdown renderer. Never accepts model-provided HTML. */
(function (root) {
  "use strict";
  const escape = value => String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
  function safeUrl(value) {
    try { const url = new URL(value); return ["https:", "http:"].includes(url.protocol) && !url.username && !url.password ? url.href : ""; } catch { return ""; }
  }
  function inline(value) {
    return escape(value).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  }
  function markdown(value) {
    const lines = String(value ?? "").replace(/\r\n/g, "\n").split("\n");
    const parts = []; let list = null; let code = null;
    const closeList = () => { if (list) { parts.push(`</${list}>`); list = null; } };
    const cells = line => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(v => v.trim());
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      if (line.startsWith("```")) { closeList(); if (code !== null) { parts.push(`<pre><code>${escape(code.join("\n"))}</code></pre>`); code = null; } else code = []; continue; }
      if (code !== null) { code.push(lines[i]); continue; }
      if (!line) { closeList(); continue; }
      if (line.includes("|") && lines[i+1] && cells(lines[i+1]).every(c => /^:?-{3,}:?$/.test(c))) {
        closeList(); const headers = cells(line); i++;
        let table = `<div class="answer-table"><table><thead><tr>${headers.map(c=>`<th>${inline(c)}</th>`).join("")}</tr></thead><tbody>`;
        while (lines[i+1]?.includes("|")) { i++; table += `<tr>${cells(lines[i]).map(c=>`<td>${inline(c)}</td>`).join("")}</tr>`; }
        parts.push(table + "</tbody></table></div>"); continue;
      }
      const heading = line.match(/^(#{1,6})\s+(.+)$/);
      if (heading) { closeList(); const n = Math.min(heading[1].length + 2, 6); parts.push(`<h${n}>${inline(heading[2])}</h${n}>`); continue; }
      const bullet = line.match(/^(?:[-*+]\s+|\d+[.)、]\s+)(.+)$/);
      if (bullet) { const type = /^\d/.test(line) ? "ol" : "ul"; if (list !== type) { closeList(); parts.push(`<${type}>`); list = type; } parts.push(`<li>${inline(bullet[1])}</li>`); continue; }
      closeList(); parts.push(/^---+$/.test(line) ? "<hr>" : `<p>${inline(line)}</p>`);
    }
    closeList(); if (code !== null) parts.push(`<pre><code>${escape(code.join("\n"))}</code></pre>`);
    return parts.join("\n");
  }
  function citations(records) {
    const groups = new Map();
    records.forEach(r => { const key = `${r.document_id || r.source_url}:${r.version || ""}`; const group = groups.get(key) || {...r, chunks: new Set()}; group.chunks.add(r.chunk_index); groups.set(key, group); });
    if (!groups.size) return '<p class="hint">未返回知识来源，不能作为政策或标准依据。</p>';
    return `<div class="source-cards">${[...groups.values()].map((r,i) => {
      const url = safeUrl(r.source_url);
      return `<article class="source-card"><span class="source-number">${String(i+1).padStart(2,"0")}</span><div><strong>${escape(r.title || "未命名资料")}</strong><p>${escape(r.version || "版本待核")} · ${r.chunks.size} 个检索片段</p><small>${escape(r.document_id)} · ${r.validity_status === "within_recorded_interval" ? "在清单日期区间内，适用性待核" : "有效期待核验"}</small>${url ? `<a href="${escape(url)}" target="_blank" rel="noreferrer noopener">查看来源 ↗</a>` : ""}</div></article>`;
    }).join("")}</div>`;
  }
  function reportHtml(report) {
    const n = value => new Intl.NumberFormat('zh-CN',{maximumFractionDigits:4}).format(value);
    const b = report.base;
    const rows = report.scenarios.map(s=>`<tr><td>${escape(s.name)}</td><td>¥${n(s.netInvestment)}</td><td>¥${n(s.annualNetBenefit)}</td><td>${n(s.annualCarbon)} kgCO₂e</td><td>${s.payback === null ? '不输出' : n(s.payback)+' 年'}</td></tr>`).join('');
    const sources = report.scenarios.map(s=>`<li><strong>${escape(s.name)}</strong><p>${escape(s.formula)}</p><p>${escape(s.sourceName)} · ${escape(s.dataDate)}<br>${escape(s.sourceUrl)}</p><p>${escape(s.notes)}</p></li>`).join('');
    return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escape(b.projectName)} · 初步方案报告</title><style>body{font:15px/1.8 'Microsoft YaHei',sans-serif;color:#213e42;background:#f0f5f3;margin:0;padding:32px}main{max-width:960px;margin:auto;background:white;padding:40px;border-radius:16px}header{border-bottom:3px solid #267465;padding-bottom:20px}h1{font-size:26px;line-height:1.5}h2{font-size:18px;margin-top:28px}p{margin:.6em 0}.tag{color:#287462;font-size:12px;letter-spacing:.12em}.note{background:#fff5da;border-left:4px solid #d49a29;padding:16px;margin:24px 0}.baseline{display:grid;grid-template-columns:1fr 1fr;gap:10px;background:#eff7f3;padding:18px}.table{overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:600px;font-size:13px}th,td{border-bottom:1px solid #dbe6e1;padding:12px;text-align:left}th{background:#eaf3ee}li{margin-bottom:15px}small,footer{color:#607673}footer{border-top:1px solid #dbe6e1;padding-top:20px;margin-top:28px;font-size:12px}p,li{overflow-wrap:anywhere}@media(max-width:600px){body{padding:10px}main{padding:20px}.baseline{grid-template-columns:1fr}}@media print{@page{size:A4 landscape;margin:14mm}body{padding:0;background:white}main{padding:0;max-width:none}h2{break-after:avoid}tr,li,.note{break-inside:avoid}thead{display:table-header-group}table{min-width:0}}</style></head><body><main><header><span class="tag">室在人为 / LOW CARBON DECISION REPORT</span><h1>${report.dataNature==='assumption'?'假设情景 · ':''}${escape(b.projectName)}<br>低碳改造初步方案报告</h1><small>生成时间 ${escape(report.createdAt)} · ${escape(report.executionMode)}</small></header><div class="note">${escape(report.disclaimer)}</div><h2>01 项目基线</h2><div class="baseline"><div>地区：${escape(b.region)}</div><div>年用电量：${n(b.annualElectricity)} kWh</div><div>电价：${n(b.electricityPrice)} 元/kWh</div><div>排放因子：${escape(b.carbonFactor)} kgCO₂e/kWh</div></div><h2>02 方案比选</h2><div class="table"><table><thead><tr><th>方案</th><th>净投资</th><th>年净收益</th><th>年减碳量</th><th>静态回收期</th></tr></thead><tbody>${rows}</tbody></table></div><h2>03 公式与资料来源</h2><ul>${sources}<li>电价：${escape(b.electricityPriceSource)}<p>${escape(b.electricityPriceUrl)}</p></li><li>排放因子：${escape(b.carbonSource)}<p>${escape(b.carbonUrl)}</p></li></ul>${report.sensitivity ? `<h2>04 敏感性分析</h2><p>${escape(report.sensitivity.notice)}</p><ul>${report.sensitivity.scenarios.map(s=>`<li>${escape(s.label)}：${s.result ? `净投资 ¥${n(s.result.netInvestment)}；年净收益 ¥${n(s.result.annualNetBenefit)}；静态回收期 ${s.result.payback === null ? '不输出' : n(s.result.payback)+' 年'}` : escape(s.error)}</li>`).join('')}</ul>`:''}<footer>本报告仅用于前期筛查；不构成收益承诺、采购报价、结构安全结论或补贴资格证明。所有工程、政策及现场条件须人工复核。</footer></main></body></html>`;
  }
  function currentAssumptions(base, scenarios) {
    return [
      `年用电量 ${base.annualElectricity} kWh、电价 ${base.electricityPrice} 元/kWh、碳因子 ${base.carbonFactor} kgCO2e/kWh 均为当前演示输入，不代表真实项目。`,
      ...scenarios.map(s => `${s.name}：当前投资 ${s.investment} 元、补贴 ${s.subsidy} 元、年运维 ${s.annualOm} 元、年节电或发电量 ${s.annualElectricitySaving} kWh，均为假设，不具报价或审计效力。`),
      "敏感性上下浮动范围为情景假设，不是预测置信区间。"
    ];
  }
  const api = { escape, safeUrl, markdown, citations, reportHtml, currentAssumptions };
  if (typeof module !== "undefined") module.exports = api;
  root.ClientUI = api;
})(typeof window === "undefined" ? globalThis : window);
