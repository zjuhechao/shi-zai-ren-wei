/* UI 改进视觉回归：截图 + 关键断言（无 JS 错误、按钮变体、焦点环、响应式）。 */
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
  await page.waitForSelector("#ux-progress", { timeout: 10000 });
  await new Promise((r) => setTimeout(r, 800));

  // 1. 桌面截图
  await page.screenshot({ path: path.join(OUT, "ui_review_desktop.png"), fullPage: true });

  // 2. danger 按钮已应用
  const clearBtnClass = await page.$eval("#clear-case", (e) => e.className);
  ok("清空按钮已用 danger 变体（实际 class=" + clearBtnClass + "）", clearBtnClass.includes("danger-button"));

  // 3. 焦点环颜色统一（应含 0, 122, 120 → 墨绿）
  const focusColor = await page.evaluate(() => {
    const el = document.getElementById("region");
    el.focus();
    return getComputedStyle(el).outlineColor;
  });
  ok("输入框焦点环为墨绿系（实际 " + focusColor + "）", focusColor.includes("0, 122, 120") || focusColor.includes("0,122,120"));

  // 4. 结果表斑马纹已生效（先载入假设生成报告；单方案只有1行，验证 CSS 规则存在即可）
  await page.click("#load-assumptions");
  await page.waitForFunction(() => document.getElementById("action-confirm") && document.getElementById("action-confirm").open, { timeout: 8000 }).catch(() => {});
  const dialogOpen = await page.$("#action-confirm[open]");
  if (dialogOpen) {
    await page.click("#confirm-accept");
  } else {
    await page.evaluate(() => { const b = document.getElementById("confirm-accept"); if (b && b.onclick) b.onclick(); });
  }
  await page.waitForFunction(() => !document.getElementById("data-nature-banner").hidden, { timeout: 10000 });
  await new Promise((r) => setTimeout(r, 400));
  await page.click("#calculate");
  await page.waitForFunction(() => !document.getElementById("summary").hidden, { timeout: 15000 });
  await page.evaluate(() => document.getElementById("result-heading").scrollIntoView());
  await new Promise((r) => setTimeout(r, 400));
  const zebra = await page.evaluate(() => {
    const trs = document.querySelectorAll("#result-table tbody tr");
    if (trs.length < 2) return "单方案仅1行，无需斑马纹";
    return getComputedStyle(trs[1]).backgroundColor;
  });
  const cssHasZebra = fs.readFileSync(path.join(__dirname, "..", "..", "styles.css"), "utf8").includes("#result-table tbody tr:nth-child(even)");
  ok("结果表斑马纹 CSS 已定义（运行时：" + zebra + "）", cssHasZebra);

  // 5. 结果区截图
  await page.screenshot({ path: path.join(OUT, "ui_review_result.png") });

  // 6. 移动端响应式截图 + 无横向滚动（新页面实例避免会话状态干扰）
  const mpage = await browser.newPage();
  mpage.on("pageerror", (e) => errors.push(String(e)));
  mpage.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await mpage.setViewport({ width: 390, height: 844 });
  await mpage.goto(BASE, { waitUntil: "domcontentloaded", timeout: 30000 });
  await mpage.waitForSelector("#ux-progress", { timeout: 10000 });
  await new Promise((r) => setTimeout(r, 800));
  const noHScroll = await mpage.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
  ok("移动端 390px 无横向滚动", noHScroll);
  await mpage.screenshot({ path: path.join(OUT, "ui_review_mobile.png") });
  await mpage.close().catch(() => {});

  // 7. 无 JS 错误
  const realErrors = errors.filter((e) => !/favicon|net::ERR|Aborted/i.test(e));
  if (realErrors.length) console.log("  (错误明细) " + realErrors.join(" | "));
  ok("全程无 JS 错误（" + realErrors.length + " 条）", realErrors.length === 0);

  await browser.close().catch(() => {});
  console.log("\n=== " + pass + " passed, " + fail + " failed ===");
  setTimeout(() => process.exit(fail ? 1 : 0), 200);
})().catch((e) => { console.error("视觉回归失败:", e.message); process.exit(2); });
