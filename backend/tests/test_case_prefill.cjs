"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const root = path.resolve(__dirname, "../..");
const elements = new Map();
const element = id => {
  if (!elements.has(id)) elements.set(id, {value:"", checked:false, hidden:true,
    disabled:false, textContent:"", innerHTML:"", className:"", dataset:{},
    addEventListener(){}, scrollIntoView(){}, focus(){}, reset(){for(const item of elements.values()){item.value="";item.checked=false;}}, setAttribute(){}});
  return elements.get(id);
};
const context = vm.createContext({
  console, document:{getElementById:element, querySelectorAll:()=>[]},
  ClientUI:require(path.join(root,"client-ui.js")), URL, Blob,
  fetch:async()=>{throw new Error("Offline test; no network request is made");},
  window:{}, setTimeout, clearTimeout, AbortController,
});
vm.runInContext(fs.readFileSync(path.join(root,"app.js"),"utf8"),context);
vm.runInContext("confirmAction = async () => true", context);

(async()=>{
  await new Promise(resolve=>setImmediate(resolve));
  let assertions=0;
  for (const mode of ["case-json","offline-fallback"]) {
    context.caseData = mode === "case-json" ? JSON.parse(fs.readFileSync(path.join(root,"data/cases/wangyue_case.json"),"utf8")) : null;
    for (const id of ["carbon-factor","carbon-source","carbon-url","baseline-date"]) element(id).value="STALE INPUT";
    await vm.runInContext("state.demoCase=caseData; state.dataNature='user_supplied_unverified'; loadWangyueFields();",context);
    for (const id of ["carbon-factor","carbon-source","carbon-url","baseline-date"]) {
      assert.equal(element(id).value,"",`${mode}: ${id} must not reuse a CO2 value or attribution as CO2e`);
      assertions++;
    }
    assert.ok(element("case-note").textContent.includes("气体覆盖"),`${mode}: explain the pending unit boundary`);
    assertions++;
    assert.ok(vm.runInContext("validateBase()",context).some(error=>error.includes("电力排放因子")),`${mode}: missing factor must block calculation`);
    assertions++;
  }
  console.log(`Wangyue case prefill: ${assertions} assertions passed (online data and offline fallback; no cloud calls).`);
})().catch(error=>{console.error(error);process.exitCode=1;});
