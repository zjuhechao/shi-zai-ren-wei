/* 三项 UI 增强 E2E：hero 装饰 + 多步向导 + 图表渲染。 */
"use strict";
const puppeteer = require("puppeteer-core");
const path = require("path");
const fs = require("fs");

const EDGE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8001/";
const OUT = path.join(__dirname, "..", "..", "..", "03_说明与记录");

let pass = 0, fail = 0;
function ok(label, cond) { cond ? pass++ : fail++; console.log((cond ? "  PASS " : "  FAIL ") + label); }

(async () => {
  const browser = await puppeteer.launch({ executablePath: EDGE, headless: true, args: ["--no-sandbox", "--disable-gpu"] });
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.setViewport({ width: 1280, height: 900 });
  await page.goto(BASE, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForSelector("#base-wizard", { timeout: 10000 });
  await new Promise((r) => setTimeout(r, 800));

  // 1. hero 装饰元素存在
  ok("hero 渐变光晕已注入", !!(await page.$(".hero-glow")));
  ok("hero 光球装饰已注入", !!(await page.$(".hero-orb-a")));
  ok("hero 网格线已注入", !!(await page.$(".hero-grid-lines")));
  ok("hero 碳排趋势 SVG 已注入", !!(await page.$(".hero-spark svg")));

  // 2. 多步向导：3 步、默认第 1 步激活
  const stepCount = await page.$$eval(".wizard-step", (els) => els.length);
  ok("向导共 3 步（实际 " + stepCount + "）", stepCount === 3);
  const activeStep = await page.$eval(".wizard-step.active", (e) => e.dataset.step);
  ok("默认激活第 1 步（实际 " + activeStep + "）", activeStep === "1");
  const step1Visible = await page.$eval(".wizard-panel[data-step='1']", (e) => !e.hidden);
  ok("第 1 步面板可见", step1Visible);

  // 3. 点「下一步」切到第 2 步
  await page.click("#wizard-next");
  await new Promise((r) => setTimeout(r, 200));
  const activeStep2 = await page.$eval(".wizard-step.active", (e) => e.dataset.step);
  ok("点击下一步切到第 2 步（实际 " + activeStep2 + "）", activeStep2 === "2");
  const step2Visible = await page.$eval(".wizard-panel[data-step='2']", (e) => !e.hidden);
  ok("第 2 步面板可见", step2Visible);

  // 4. 直接点步骤 3 跳转
  await page.click(".wizard-step[data-step='3']");
  await new Promise((r) => setTimeout(r, 200));
  const activeStep3 = await page.$eval(".wizard-step.active", (e) => e.dataset.step);
  ok("点击步骤 3 跳转（实际 " + activeStep3 + "）", activeStep3 === "3");
  const nextText = await page.$eval("#wizard-next", (e) => e.textContent);
  ok("第 3 步按钮文案为「完成录入」（实际「" + nextText + "」）", nextText.includes("完成"));

  // 5. 载入假设 → 生成报告 → 图表渲染
  await page.click("#load-assumptions");
  await page.waitForFunction(() => document.getElementById("action-confirm") && document.getElementById("action-confirm").open, { timeout: 8000 }).catch(() => {});
  const dialogOpen = await page.$("#action-confirm[open]");
  if (dialogOpen) await page.click("#confirm-accept");
  else await page.evaluate(() => { const b = document.getElementById("confirm-accept"); if (b && b.onclick) b.onclick(); });
  await page.waitForFunction(() => !document.getElementById("data-nature-banner").hidden, { timeout: 10000 });
  await page.click("#calculate");
  await page.waitForFunction(() => !document.getElementById("summary").hidden, { timeout: 15000 });
  await new Promise((r) => setTimeout(r, 500));
  const chartsVisible = await page.$eval("#charts", (e) => !e.hidden);
  ok("图表容器可见", chartsVisible);
  const invSvg = await page.$eval("#chart-investment", (e) => e.querySelectorAll("svg").length);
  const cfSvg = await page.$eval("#chart-cashflow", (e) => e.querySelectorAll("svg").length);
  ok("净投资条形图已渲染（svg=" + invSvg + "）", invSvg > 0);
  ok("现金流曲线已渲染（svg=" + cfSvg + "）", cfSvg > 0);
  const barCount = await page.$eval("#chart-investment", (e) => e.querySelectorAll(".bar-rect").length);
  ok("条形图含方案柱（bar=" + barCount + "）", barCount >= 1);

  // 6. 截图
  await page.evaluate(() => window.scrollTo(0, 0));
  await new Promise((r) => setTimeout(r, 500));
  await page.screenshot({ path: path.join(OUT, "ui_enhance_hero.png") });
  await page.evaluate(() => document.getElementById("result-heading").scrollIntoView());
  await new Promise((r) => setTimeout(r, 500));
  await page.screenshot({ path: path.join(OUT, "ui_enhance_charts.png") });

  // 7. 无 JS 错误
  const realErrors = errors.filter((e) => !/favicon|net::ERR|Aborted/i.test(e));
  if (realErrors.length) console.log("  (错误明细) " + realErrors.join(" | "));
  ok("全程无 JS 错误（" + realErrors.length + " 条）", realErrors.length === 0);

  await browser.close().catch(() => {});
  console.log("\n=== " + pass + " passed, " + fail + " failed ===");
  setTimeout(() => process.exit(fail ? 1 : 0), 200);
})().catch((e) => { console.error("E2E 失败:", e.message); process.exit(2); });
