/* 前端离线计算口径回归：从 app.js 真实源码抽取 makeGenericScenario / makePvScenario，
   与 backend/app/calculators.py 的 Python 结果逐项对齐，防止前后端公式漂移。
   运行： node backend/tests/verify_frontend_calc.cjs                        */
"use strict";
const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "..", "..", "app.js"), "utf8");

// 只抽取两个纯计算函数体（它们只依赖 number/field/decimal，不触碰 DOM 之外的逻辑）。
function extract(name) {
  const head = src.indexOf(`function ${name}`);
  if (head < 0) throw new Error(`未找到 ${name}，app.js 结构已变`);
  const bodyStart = src.indexOf("{", head);
  let depth = 0;
  let i = bodyStart;
  for (; i < src.length; i++) {
    if (src[i] === "{") depth++;
    else if (src[i] === "}") { depth--; if (depth === 0) break; }
  }
  return src.slice(bodyStart + 1, i); // 函数体，不含外层花括号
}

const genericBody = extract("makeGenericScenario");
const pvBody = extract("makePvScenario");

// 提供被抽取函数体所需的最小运行时依赖（shim）。
const shim = `
"use strict";
function number(id) { return globalThis.__fields[id] === undefined || globalThis.__fields[id] === "" ? null : Number(globalThis.__fields[id]); }
function field(id) { const v = globalThis.__fields[id]; return v === undefined ? "" : String(v).trim(); }
function decimal(v, d) { if (v === null || v === undefined || (typeof v === "number" && !Number.isFinite(v))) return "不输出"; return Number(v).toFixed(d === undefined ? 2 : d); }
function makeGenericScenario(input, base) { ${genericBody} }
function makePvScenario(base) { ${pvBody} }
module.exports = { makeGenericScenario, makePvScenario };
`;

const tmp = path.join(__dirname, ".verify_frontend_calc.tmp.cjs");
fs.writeFileSync(tmp, shim, "utf8");
const { makeGenericScenario, makePvScenario } = require(tmp);
fs.unlinkSync(tmp);

let pass = 0, fail = 0;
const near = (a, b) => Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(a));
function eq(label, got, expect) {
  const ok = near(got, expect);
  ok ? pass++ : fail++;
  console.log((ok ? "  PASS " : "  FAIL ") + label + "  got=" + got + "  expect=" + expect);
}

// 与 backend/app/calculators.py 的数值基准一致（见 verify-engine.cjs 及 test_calculators.py）。
const base = { electricityPrice: 0.538, carbonFactor: 0.5, annualElectricity: 100000 };

console.log("[通用改造] makeGenericScenario 对照 calculators.calculate_generic_scenario");
globalThis.__fields = {};
const g = makeGenericScenario(
  { id: "t", name: "t", investment: 60000, subsidy: 0, annualSavingKwh: 12000,
    annualOm: 300, sourceName: "s", sourceUrl: "u", dataDate: "2026-10-12" }, base);
eq("annualBenefit", g.annualBenefit, 6456);
eq("netInvestment", g.netInvestment, 60000);
eq("annualNetBenefit", g.annualNetBenefit, 6156);
eq("annualCarbon", g.annualCarbon, 6000);
eq("payback", g.payback, 60000 / 6156);

console.log("[屋顶光伏] makePvScenario 对照 calculators.calculate_pv_scenario");
globalThis.__fields = {
  "pv-capacity": 30, "pv-yield": 1050, "pv-self-use": 0.8,
  "pv-feed-in-tariff": 0.4155, "pv-investment": 120000, "pv-subsidy": 0, "pv-om": 2000,
  "pv-source": "s", "pv-url": "u", "pv-date": "2026-10-12",
};
const gen = 30 * 1050, used = Math.min(gen * 0.8, 100000), exp = Math.max(0, gen - used);
const p = makePvScenario(base);
eq("generation", p.annualElectricitySaving, gen);
eq("annualBenefit", p.annualBenefit, used * 0.538 + exp * 0.4155);
eq("annualCarbon", p.annualCarbon, gen * 0.5);
eq("payback", p.payback, 120000 / (used * 0.538 + exp * 0.4155 - 2000));

console.log("[边界] 自用电量被建筑基线截断（gen > baseline）");
globalThis.__fields = {
  "pv-capacity": 100, "pv-yield": 2000, "pv-self-use": 1.0,
  "pv-feed-in-tariff": 0.4, "pv-investment": 1, "pv-subsidy": 0, "pv-om": 0,
  "pv-source": "s", "pv-url": "u", "pv-date": "2026-10-12",
};
const p2 = makePvScenario({ ...base, annualElectricity: 50000 });
// selfUsed 截断为 50000，electricityPrice 沿用 base 的 0.538：50000*0.538 + 150000*0.4
eq("截断后 annualBenefit", p2.annualBenefit, 50000 * 0.538 + 150000 * 0.4);

console.log("[口径] 年净收益 <= 0 时不输出回收期");
const g2 = makeGenericScenario(
  { id: "x", name: "x", investment: 1000, subsidy: 0, annualSavingKwh: 0,
    annualOm: 500, sourceName: "s", sourceUrl: "u", dataDate: "2026-10-12" }, { electricityPrice: 0.5, carbonFactor: 0.5 });
const okNull = g2.payback === null;
okNull ? pass++ : fail++;
console.log((okNull ? "  PASS " : "  FAIL ") + "payback 为 null -> " + g2.payback);

console.log("\n=== " + pass + " passed, " + fail + " failed ===");
process.exit(fail ? 1 : 0);
