import copy
import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pymupdf
from app.main import app
from app.plan_schemas import PlanRequest
from app.plan_service import calculate_plan, generate_plan, validate_narrative
from app.plan_pdf import render_plan_pdf


def payload():
    return {"base":{"dataNature":"assumption","projectName":"青禾测试案例","region":"浙江省 杭州市",
        "annualElectricity":100000,"electricityPrice":.538,"electricityPriceSource":"假设电价",
        "electricityPriceUrl":"assumption:test","carbonFactor":.5,"carbonSource":"假设因子",
        "carbonUrl":"assumption:test","baselineDate":"2026-10-12"},
        "generic_scenarios":[{"scenario_id":"lighting","scenario_name":"照明假设","investment_cny":60000,
        "subsidy_cny":0,"annual_energy_saving_kwh":12000,"electricity_price_cny_per_kwh":.538,
        "carbon_factor_kgco2e_per_kwh":.5,"annual_om_cny":300,"source_name":"人工假设",
        "source_url":"assumption:test","data_date":"2026-10-12"}],"comparison_investment":48000,"consent_cloud":True}


def narrative():
    return {"diagnosis":"这是测试用的定性草案，建筑设备数量与现场条件均需进一步核实，不能代替实地诊断或者专业设计。",
      "goals":["保持安全","保护照明品质","核验节能效果"],
      "measures":[{"title":"拟议照明措施","scope":"公共照明","action":"现场核实后开展样板验证。",
      "prerequisite":"完成电气安全核查","acceptance":"记录测试证据","evidence_ids":["R1"]} for _ in range(3)],
      "wider_building_strategy":"围护结构、空调及光伏尚缺少现场参数，本次只纳入待诊断方向，不把其可能收益计入照明测算结果中。",
      "procurement_notes":["核实范围","取得正式报价","保留采购记录"],
      "stages":[{"stage":"拟议阶段","actions":"完成资料核验","owner":"建议由项目负责人组织","gate":"取得核验记录"} for _ in range(4)],
      "risks":[{"risk":"输入未经核验","mitigation":"补齐可追溯记录","release_condition":"复核确认"} for _ in range(4)],
      "verification":[{"item":"用能核验","method":"比对相同边界和使用条件下的记录","record":"保留原始台账"} for _ in range(4)],
      "conclusion":"建议先补充现场条件和原始能耗记录，完成可比工程量与正式报价核验后，再决定是否进入工程实施阶段。"}


def fake_agent():
    source={"document_id":"TEST","chunk_index":0,"title":"测试引用","content":"仅为单元测试虚拟片段，非真实检索记录。",
      "source_url":"https://example.org","checksum":"test","validity_status":"unverified"}
    agent=Mock()
    agent.settings=SimpleNamespace(llm_model="test-model",embedding_model="test-embedding")
    agent.knowledge_base.count.return_value=1
    agent.knowledge_base.search.return_value=[source]
    agent._reasoning.return_value=None
    call=SimpleNamespace(type="function_call",name="record_retrofit_plan",arguments=json.dumps(narrative()))
    agent.client.responses.create.return_value=SimpleNamespace(output=[call],id="test-response")
    return agent


class PlanReportTests(unittest.TestCase):
    def test_blank_required_plan_text_rejected(self):
        required_fields={'measures':['title','scope','action','prerequisite','acceptance'],
                         'stages':['stage','actions','owner','gate'],
                         'risks':['risk','mitigation','release_condition'],
                         'verification':['item','method','record']}
        for blank in [' \t\n ', '\u00a0\u3000', '\u200b \ufeff \u200b']:
            for group, fields in required_fields.items():
                for field in fields:
                    data=narrative();data[group][0][field]=blank
                    with self.subTest(group=group,field=field,blank=repr(blank)):
                        with self.assertRaises(ValidationError):validate_narrative(data,{'R1'})
            for group in ['goals','procurement_notes']:
                data=narrative();data[group][0]=blank
                with self.subTest(group=group,blank=repr(blank)):
                    with self.assertRaises(ValidationError):validate_narrative(data,{'R1'})

    def test_blank_project_provenance_rejected_before_cloud(self):
        for field in ['projectName','region','electricityPriceSource','electricityPriceUrl','carbonSource','carbonUrl']:
            data=payload();data['base'][field]=' \u00a0\u3000\u200b\ufeff '
            with self.subTest(field=field), patch('app.main.get_agent') as agent:
                self.assertEqual(TestClient(app).post('/api/reports/plan',json=data).status_code,422)
                agent.assert_not_called()

    def test_optional_plan_text_may_be_empty(self):
        data=payload();data['base'].update(assumptionNotice='',address='\u200b\ufeff');data['objective']=''
        parsed=PlanRequest.model_validate(data)
        self.assertEqual(parsed.base.address,'')
        self.assertEqual(parsed.base.assumptionNotice,'')
        self.assertEqual(parsed.objective,'')
        draft=narrative()
        for measure in draft['measures']:measure['evidence_ids']=[]
        self.assertEqual(validate_narrative(draft,{'R1'}).measures[0].evidence_ids,[])

    def test_calculations_recompute_input_and_comparison(self):
        result=calculate_plan(PlanRequest.model_validate(payload()))
        self.assertEqual(result['scenarios'][0]['annualNetBenefit'],6156)
        self.assertAlmostEqual(result['scenarios'][1]['payback'],48000/6156)
        self.assertEqual(result['cashflows'][10]['values'][0],1560)

    def test_nonfinite_or_missing_or_inconsistent_input_rejected(self):
        for mutation in [lambda p:p['base'].update(annualElectricity=float('nan')),
                         lambda p:p.update(generic_scenarios=[]),
                         lambda p:p['generic_scenarios'][0].update(electricity_price_cny_per_kwh=1)]:
            data=payload();mutation(data)
            with self.assertRaises(ValidationError):PlanRequest.model_validate(data)

    def test_saving_cannot_exceed_baseline(self):
        data=payload();data['generic_scenarios'][0]['annual_energy_saving_kwh']=100001
        with self.assertRaises(ValidationError):PlanRequest.model_validate(data)

    def test_model_number_and_unknown_reference_rejected(self):
        data=narrative();data['conclusion']+='保证收益100000元。'
        with self.assertRaises(ValueError):validate_narrative(data,{'R1'})
        data=narrative();data['measures'][0]['evidence_ids']=['R99']
        with self.assertRaises(ValueError):validate_narrative(data,{'R1'})

    def test_no_cloud_without_consent(self):
        data=payload();data['consent_cloud']=False
        with patch('app.main.get_agent') as agent:
            self.assertEqual(TestClient(app).post('/api/reports/plan',json=data).status_code,422)
            agent.assert_not_called()

    def test_empty_retrieval_never_uses_fake_report(self):
        agent=fake_agent();agent.knowledge_base.search.return_value=[]
        with self.assertRaisesRegex(RuntimeError,'未检索'):generate_plan(PlanRequest.model_validate(payload()),agent)
        agent.client.responses.create.assert_not_called()

    def test_secret_pattern_not_sent(self):
        data=payload();data['objective']='sk-'+'a'*32
        agent=fake_agent()
        with self.assertRaisesRegex(ValueError,'密钥'):generate_plan(PlanRequest.model_validate(data),agent)
        agent.knowledge_base.search.assert_not_called()

    def test_real_pipeline_calls_and_pdf_sections(self):
        agent=fake_agent()
        plan=generate_plan(PlanRequest.model_validate(payload()),agent)
        self.assertEqual(agent.knowledge_base.search.call_count,2)
        self.assertEqual(agent.client.responses.create.call_count,1)
        self.assertEqual(len(plan['sources']),1)
        with pymupdf.open(stream=render_plan_pdf(plan),filetype='pdf') as doc:
            text=''.join(page.get_text() for page in doc)
            self.assertGreaterEqual(len(doc),11)
            for term in ['技术改造措施包','投资分析','现金流','验收','风险','假设情景','6,156.00','7.80']:
                self.assertIn(term,text)

    def test_private_audit_not_public(self):
        self.assertEqual(TestClient(app).get('/storage/reports/123.json').status_code,404)

    def test_invalid_model_output_stops_after_two_attempts(self):
        agent=fake_agent();agent.client.responses.create.return_value=SimpleNamespace(output=[],id='test')
        with self.assertRaisesRegex(RuntimeError,'两次'):generate_plan(PlanRequest.model_validate(payload()),agent)
        self.assertEqual(agent.client.responses.create.call_count,2)

    def test_pdf_endpoint_returns_pdf_and_private_audit(self):
        with tempfile.TemporaryDirectory() as folder, patch('app.main.PROJECT_ROOT',Path(folder)), patch('app.main.get_agent',return_value=fake_agent()):
            response=TestClient(app).post('/api/reports/plan',json=payload())
            self.assertEqual(response.status_code,200)
            self.assertTrue(response.content.startswith(b'%PDF-'))
            self.assertIn('application/pdf',response.headers['content-type'])
            self.assertEqual(response.headers['cache-control'],'no-store')
            record=Path(folder)/'storage/reports'/f"{response.headers['x-report-id']}.json"
            self.assertTrue(record.is_file())
            self.assertEqual(TestClient(app).get('/storage/reports/'+record.name).status_code,404)

    def test_generation_failure_releases_lock_and_redacts_error(self):
        with patch('app.main.get_agent',return_value=fake_agent()), patch('app.plan_service.generate_plan',side_effect=RuntimeError('sk-'+'x'*32)):
            client=TestClient(app)
            for _ in range(2):
                response=client.post('/api/reports/plan',json=payload())
                self.assertEqual(response.status_code,400)
                self.assertNotIn('sk-'+'x'*32,response.text)


if __name__=='__main__':unittest.main()
