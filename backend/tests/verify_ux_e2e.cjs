/* 客户体验层 E2E：验证 ux.js/ux.css 挂载且不破坏原有功能。 */
"use strict";
const puppeteer = require("puppeteer-core");
const path = require("path");

const EDGE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = "http://127.0.0.1:8001/";

let pass = 0, fail = 0;
function ok(label, cond) { cond ? pass++ : fail++; console.log((cond ? "  PASS " : "  FAIL ") + label); }

(async () => {
  const browser = await puppeteer.launch({ executablePath: EDGE, headless: true, args: ["--no-sandbox", "--disable-gpu"] });
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

  await page.goto(BASE, { waitUntil: "networkidle0", timeout: 30000 });

  // 0. 体验层元素已注入
  ok("进度仪表盘已注入", !!(await page.$("#ux-progress")));
  ok("底部悬浮栏已注入", !!(await page.$("#ux-dock")));

  // 1. 初始完成度应为 0/9（基线下拉显示基线必填）
  let count = await page.$eval("#ux-progress-count", (e) => e.textContent);
  ok("初始完成度显示为 0/9（实际 " + count + "）", count.includes("0 / 9"));

  // 2. 填写部分字段后完成度应更新（向导：region 在步骤1，其余在步骤2）
  await page.type("#region", "浙江省 杭州市");
  await new Promise((r) => setTimeout(r, 200));
  count = await page.$eval("#ux-progress-count", (e) => e.textContent);
  ok("步骤1 填 region 后完成度 1/9（实际 " + count + "）", count.includes("1 / 9"));
  // 切到步骤 2 填写用电字段
  await page.click(".wizard-step[data-step='2']");
  await page.type("#annual-electricity", "100000");
  await page.type("#electricity-price", "0.538");
  await new Promise((r) => setTimeout(r, 200));
  count = await page.$eval("#ux-progress-count", (e) => e.textContent);
  ok("步骤2 填 2 项后完成度 3/9（实际 " + count + "）", count.includes("3 / 9"));

  // 3. 失焦必填空字段触发字段级提示（electricity-price-source 在步骤2 已可见）
  await page.$eval("#electricity-price-source", (e) => { e.focus(); e.blur(); });
  await new Promise((r) => setTimeout(r, 150));
  const fieldMsg = await page.$eval("#electricity-price-source", (e) => {
    const m = e.parentElement?.querySelector(".ux-field-msg");
    return m ? m.textContent : "";
  });
  ok("必填字段失焦触发「必填项」提示", fieldMsg === "必填项");

  // 4. 载入假设情景后完成度应接近满、底部栏显示报告关键指标
  await page.click("#load-assumptions");
  // 等待确认对话框打开（headless 下 showModal 可能延迟）
  await page.waitForFunction(() => document.getElementById("action-confirm") && document.getElementById("action-confirm").open, { timeout: 8000 }).catch(() => {});
  const dialogOpen = await page.$("#action-confirm[open]");
  if (dialogOpen) {
    await page.click("#confirm-accept");
  } else {
    // 若无对话框，尝试直接点确认按钮
    await page.evaluate(() => { const b = document.getElementById("confirm-accept"); if (b && b.onclick) b.onclick(); });
  }
  await page.waitForFunction(() => !document.getElementById("data-nature-banner").hidden, { timeout: 10000 });
  await new Promise((r) => setTimeout(r, 400));
  count = await page.$eval("#ux-progress-count", (e) => e.textContent);
  ok("载入假设后完成度更新（实际 " + count + "）", !count.includes("0 /"));

  // 5. 点击生成报告后，底部悬浮栏显示方案数与回收期
  await page.click("#calculate");
  await page.waitForFunction(() => !document.getElementById("summary").hidden, { timeout: 15000 });
  await new Promise((r) => setTimeout(r, 400));
  const dockLabel = await page.$eval("#ux-dock-label", (e) => e.textContent);
  ok("生成报告后底部栏显示方案数与回收期（实际「" + dockLabel + "」）", dockLabel.includes("方案") && dockLabel.includes("回收期"));
  ok("悬浮「查看结果」按钮出现", !!(await page.$("#ux-jump-result")) && !(await page.$("#ux-jump-result").then((e) => e.evaluate((n) => n.hidden))));

  // 6. 滚动后悬浮栏可见
  await page.evaluate(() => window.scrollTo(0, 1200));
  await new Promise((r) => setTimeout(r, 500));
  const dockVisible = await page.$eval("#ux-dock", (e) => e.classList.contains("visible"));
  ok("向下滚动后悬浮栏可见", dockVisible);

  // 7. 无 JS 错误
  const realErrors = errors.filter((e) => !/favicon|net::ERR|Aborted/i.test(e));
  if (realErrors.length) console.log("  (JS 错误明细) " + realErrors.join(" | "));
  ok("全程无 JS 错误（" + realErrors.length + " 条）", realErrors.length === 0);

  await browser.close().catch(() => {});
  console.log("\n=== " + pass + " passed, " + fail + " failed ===");
  setTimeout(() => process.exit(fail ? 1 : 0), 200);
})().catch((e) => { console.error("E2E 失败：", e.message); process.exit(2); });
