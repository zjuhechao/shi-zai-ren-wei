"""Paginated customer deliverable; calculations are never delegated to the model."""
from __future__ import annotations

import io
import os
from pathlib import Path
from html import escape
from urllib.parse import urlsplit
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, CondPageBreak, KeepTogether, Flowable

TEAL=colors.HexColor('#123f43')
MUTED=colors.HexColor('#51666b')
PALE=colors.HexColor('#edf5f2')
LINE=colors.HexColor('#cfddd8')
WIDTH=A4[0]-36*mm


def register_fonts():
    if 'PlanCN' in pdfmetrics.getRegisteredFontNames():
        return
    candidates=[os.getenv('REPORT_FONT_PATH',''),r'C:\Windows\Fonts\msyh.ttc',
                '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc']
    path=next((p for p in candidates if p and Path(p).is_file()),None)
    if not path:
        raise RuntimeError('PDF需要中文TrueType字体；请设置REPORT_FONT_PATH指向合法可用的TTF/TTC字体文件')
    pdfmetrics.registerFont(TTFont('PlanCN',path))
    bold=r'C:\Windows\Fonts\msyhbd.ttc'
    pdfmetrics.registerFont(TTFont('PlanCNB',bold if Path(bold).is_file() else path))
    pdfmetrics.registerFontFamily('PlanCN',normal='PlanCN',bold='PlanCNB',italic='PlanCN',boldItalic='PlanCNB')


def amount(value):
    return '不输出' if value is None else f'{value:,.2f}'


class Cashflow(Flowable):
    def __init__(self,scenarios):
        super().__init__()
        self.scenarios=scenarios[:4]
        self.width=WIDTH
        self.height=204
    def draw(self):
        c=self.canv
        left,bottom,w,h=58,40,self.width-82,124
        vals=[-s['netInvestment']+s['annualNetBenefit']*y for s in self.scenarios for y in range(16)]
        lo,hi=min(vals+[0]),max(vals+[0])
        span=max(hi-lo,1)
        lo-=span*.08;hi+=span*.08
        xx=lambda y:left+w*y/15
        yy=lambda v:bottom+h*(v-lo)/(hi-lo)
        c.setFont('PlanCN',8)
        for i in range(5):
            value=lo+(hi-lo)*i/4
            c.setStrokeColor(LINE);c.setLineWidth(.5);c.line(left,yy(value),left+w,yy(value))
            c.setFillColor(MUTED);c.drawRightString(left-6,yy(value)-3,f'{value/10000:.1f}')
        c.setStrokeColor(MUTED);c.setDash(3,3);c.line(left,yy(0),left+w,yy(0));c.setDash()
        for year in [0,5,10,15]:
            c.setFillColor(MUTED);c.drawCentredString(xx(year),bottom-15,str(year))
        c.drawString(left,bottom+h+15,'累计净现金流 / 万元（不折现）')
        c.drawString(left+w+12,bottom-15,'年')
        palette=[TEAL,colors.HexColor('#ba723a'),colors.HexColor('#557aaa'),colors.HexColor('#857098')]
        for index,s in enumerate(self.scenarios):
            color=palette[index]
            c.setStrokeColor(color);c.setLineWidth(2)
            p=c.beginPath();p.moveTo(xx(0),yy(-s['netInvestment']))
            for y in range(1,16):p.lineTo(xx(y),yy(-s['netInvestment']+s['annualNetBenefit']*y))
            c.drawPath(p)
            x=left+index*102
            c.line(x,8,x+16,8);c.setFillColor(color);c.drawString(x+22,5,s['plan_id'])


def render_plan_pdf(plan:dict)->bytes:
    register_fonts()
    base=plan['request']['base'];calc=plan['calculations'];n=plan['narrative']
    assumed=base['dataNature']=='assumption'
    nature='假设情景演示' if assumed else '用户录入资料待核验'
    styles={
        'body':ParagraphStyle('body',fontName='PlanCN',fontSize=10,leading=16,spaceAfter=8,wordWrap='CJK',textColor=colors.HexColor('#223539')),
        'small':ParagraphStyle('small',fontName='PlanCN',fontSize=8,leading=12,spaceAfter=5,wordWrap='CJK',textColor=MUTED),
        'title':ParagraphStyle('title',fontName='PlanCNB',fontSize=28,leading=39,spaceAfter=20,textColor=TEAL,wordWrap='CJK'),
        'h1':ParagraphStyle('h1',fontName='PlanCNB',fontSize=19,leading=27,spaceAfter=16,keepWithNext=True,textColor=TEAL),
        'h2':ParagraphStyle('h2',fontName='PlanCNB',fontSize=12,leading=18,spaceBefore=12,spaceAfter=8,keepWithNext=True,textColor=TEAL),
        'cell':ParagraphStyle('cell',fontName='PlanCN',fontSize=9,leading=14,wordWrap='CJK'),
    }
    def p(text,style='body'):
        return Paragraph(escape(str(text)).replace('\n','<br/>'),styles[style])
    story=[]
    def para(text):story.append(p(text))
    def heading(text):story.append(p(text,'h2'))
    def chapter(text):
        story.extend([PageBreak() if text.startswith('01 ') else CondPageBreak(290),Spacer(1,18),p(text,'h1')])
    def table(headers,rows,widths=None):
        data=[[p(x,'cell') for x in headers]]+[[p(x,'cell') for x in row] for row in rows]
        t=Table(data,colWidths=widths or [WIDTH/len(headers)]*len(headers),repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),PALE),('VALIGN',(0,0),(-1,-1),'TOP'),
                              ('GRID',(0,0),(-1,-1),.45,LINE),('LEFTPADDING',(0,0),(-1,-1),8),
                              ('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),8),
                              ('BOTTOMPADDING',(0,0),(-1,-1),8),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#fafcfb')])]))
        if len(rows)<=4:
            group=[t]
            if story and isinstance(story[-1],Paragraph) and getattr(story[-1].style,'keepWithNext',False):
                group.insert(0,story.pop())
            story.append(KeepTogether(group))
        else:
            story.append(t)
        story.append(Spacer(1,10))
    def bullets(items):
        for i,text in enumerate(items,1):para(f'{i}. {text}')
    first=calc['scenarios'][0]
    story.extend([Spacer(1,28),p('室在人为  /  客户方案交付','small'),Spacer(1,20),
                  p('低碳改造方案\n与分析报告','title'),p(base['projectName'],'h1'),p(nature+' · 前期策划与方案比选','h2')])
    para(f"地区：{base['region']}  |  数据基准日：{base['baselineDate']}")
    para(f"报告版本：v{plan['version']}  |  生成日期：{plan['created_at'][:10]}")
    para(f"报告编号：{plan['report_id'][:12]}")
    story.append(Spacer(1,14))
    table(['当前方案净投资 / 元','年净节省 / 元','静态回收期 / 年'],[[amount(first['netInvestment']),amount(first['annualNetBenefit']),amount(first['payback'])]])
    heading('交付结论')
    para(n['conclusion'])
    heading('使用边界')
    para('本报告给出完整的前期改造建议、分析框架、测算和实施条件，不是可直接施工的设计文件。'+
         ('本案例及用户为假设情景；全部输入数值均为假设，不代表望月公寓或任何真实项目的实测收益。' if assumed else
          '输入由用户提供，系统未核验账单、工程量、报价、设计及授权的真实性。'))
    para('设备选型、工程量、施工图、消防与电气安全、投资审批及最终节能量，须由有资质的责任主体结合现场确认。检索到文件不代表该文件对本项目必然适用。')

    chapter('01  项目现状与方案目标')
    para('本报告以当前录入的可计算方案为主线。没有输入的建筑条件列为待核实事项，不以模型推测替代现场诊断。')
    table(['基线项目','本次输入','证据状态'],[
        ['项目',base['projectName'],nature],['位置 / 备注',base['address'] or '未提供',nature],
        ['建筑年代 / 面积',f"{base['constructionYear'] or '未提供'} / {base['floorArea'] if base['floorArea'] is not None else '未提供'}",'未实测核验'],
        ['年用电量',f"{amount(base['annualElectricity'])} kWh",nature],
        ['执行电价',f"{base['electricityPrice']} 元/kWh",base['electricityPriceSource']],
        ['电力排放因子',f"{base['carbonFactor']} kgCO2e/kWh",base['carbonSource']],
        ['照片 / 图纸 / 设备台账','本报告未接收已确认的现场观察、签章图纸及设备台账','待提供'],
    ],[100,170,WIDTH-270])
    heading('用户目标')
    para(plan['request']['objective'])
    heading('本次方案目标')
    bullets(n['goals'])
    heading('初步诊断')
    para(n['diagnosis'])

    chapter('02  整体改造路径与边界')
    para(n['wider_building_strategy'])
    table(['系统','本次处理方式','进入量化设计前的条件'],[
        ['已录入改造方案','详见后续措施包及确定性测算。所有措施包费用均暂包含在输入总投资中，不另行叠加。','核对勘察、设备数量、分项报价与节能量依据。'],
        ['围护结构 / 门窗','仅列为待诊断方向，不输出传热系数、改造厚度和节能率。','图纸、构造、面积、窗墙比、当地气候及热工计算。'],
        ['空调 / 通风 / 热水','未输入时不进入本次金额与节能量合计。','设备清单、工况、运行时间、分项能耗及负荷计算。'],
        ['屋顶光伏','仅在用户录入光伏方案时量化；不能由屋顶照片推算容量。','屋顶权属、承载复核、资源条件、用电曲线及接入条件。'],
        ['运行管理与计量','可作为拟议配套工作，不能与硬件改造重复计算节能量。','计量边界、责任人、运维制度和可追溯记录。'],
    ],[90,WIDTH*.44,WIDTH-90-WIDTH*.44])
    heading('推荐推进顺序')
    para('先核实建筑现状和能源基线，再开展候选措施设计与样板验证，取得正式工程量和报价后完成投资决策。施工验收与持续能耗核验是两个不同环节。当前不直接推荐整体项目开工。')
    para('只改变投资数额的比较情景不是第二种技术设计；它用于检验报价变化对经济性的影响，不能代表更低价格已经取得，也不能据此改变工程质量或安全条件。')

    chapter('03  技术改造措施包')
    para('下列为模型基于项目输入与检索片段形成的设计建议，均须专业复核。未列直接引用的内容属于拟议做法，不是已核验的标准条文。')
    for i,m in enumerate(n['measures'],1):
        heading(f"措施 {i}  {m['title']}")
        table(['事项','方案内容'],[['适用范围',m['scope']],['建议做法',m['action']],['实施前提',m['prerequisite']],
              ['验收建议',m['acceptance']],['检索支持',', '.join(m['evidence_ids']) if m['evidence_ids'] else '无直接条文依据；作为设计建议，须另行核实。']],[78,WIDTH-78])

    chapter('04  方案比选与投资分析')
    para('下表逐项比较，不将互斥、重叠或尚未验证的方案直接相加。“维持现状”只表示不实施本项目时新增改造投资与新增节省额均为零，原有能源支出仍存在。')
    rows=[['S0 维持现状','0.00','0.00','不适用','未评价现状是否合规']]
    rows += [[s['plan_id']+' '+s['name'],amount(s['netInvestment']),amount(s['annualNetBenefit']),amount(s['payback']),
              '仅投资变化；非新技术方案' if s['comparison_only'] else nature] for s in calc['scenarios']]
    table(['方案','净投资 / 元','年净节省 / 元','回收期 / 年','性质'],rows,[140,82,88,72,WIDTH-382])
    table(['分析项目','解释'],[
        ['经济判断边界','静态回收期只反映输入条件下的简单回收时间；未计折现、融资、设备衰减、更新替换、残值与税费。'],
        ['投资构成','总投资为输入值；设备、安装、调试、设计、监测及不可预见费的分项报价尚未获得，不人为拆分金额。'],
        ['折现指标','未提供折现率与经确认的设备寿命，因此不输出NPV、IRR或全生命周期盈利结论。'],
        ['补贴资格','仅按用户输入的补贴金额计算，不因检索到政策而自动认定资格或补足补贴。'],
        ['选择建议','先验证效果和安全，再获取可比口径报价；任何降价情景均须维持相同工程范围和品质条件。'],
    ],[90,WIDTH-90])

    chapter('05  节能、减碳与计算依据')
    for s in calc['scenarios']:
        heading(s['plan_id']+'  '+s['name'])
        table(['量化指标','结果','来源 / 口径'],[
            ['投资 / 补贴',f"{amount(s['investment'])} / {amount(s['subsidy'])} 元",s['sourceName']],
            ['年节电或发电量',amount(s['annualElectricitySaving'])+' kWh','用户输入节电量，或由光伏容量与资源系数计算'],
            ['年毛节省或发电收益',amount(s['annualBenefit'])+' 元','Python确定性公式'],
            ['年运维 / 年净节省',amount(s['annualOm'])+' / '+amount(s['annualNetBenefit'])+' 元','净节省=毛节省-运维'],
            ['情景减碳量',amount(s['annualCarbon'])+' kgCO2e/年','因子口径待核验；不代表经核证减排量'],
        ],[120,150,WIDTH-270])
        para(s['formula'])
        if s['type']=='通用改造':
            share=s['annualElectricitySaving']/base['annualElectricity']*100
            para(f"节电量占输入建筑年用电量的 {share:.2f}%。这只是两个输入量的比值，不是经实测验证的灯具或建筑节能率；年节电量并非本系统热工模型预测值。")
        if s['notes']:para(s['notes'])
    heading('计算边界')
    para('实际节能量须通过基线与改造后用能的可比条件核验。营业或使用时间、入住率、气候、照明服务品质等变化可能改变结果。照明品质与安全要求不应因追求节电而降低。')
    para('kgCO2与kgCO2e并非可不加说明地互换。本报告按输入的kgCO2e/kWh进行算术演示；正式核算应确认因子年份、地域、覆盖气体与边界后重新计算。')

    chapter('06  现金流与敏感性分析')
    para('以下采用15年演示观察窗口，假设年净节省不变，不折现、不计替换成本。该窗口不代表设备寿命或保修年限，也不是正式财务可研结论。图中最多展示前四个情景。')
    story.append(Cashflow(calc['scenarios']))
    table(['时点']+[s['plan_id']+'累计净现金流 / 元' for s in calc['scenarios'][:4]],[
        [f"第{r['year']}年"]+[amount(v) for v in r['values'][:4]] for r in calc['cashflows'] if r['year'] in [0,5,10,15]])
    if calc['sensitivity']:
        story.append(CondPageBreak(210))
        heading('首项通用方案敏感性')
        para('保守：投资增加20%、节电量减少20%；乐观：投资减少20%、节电量增加20%。电价、补贴和运维保持输入值。它们是情景测试，不是置信区间，也不是独立工程方案。')
        table(['情景','年净节省 / 元','静态回收期 / 年'],[[r['label'],r.get('error') or amount(r['result']['annualNetBenefit']),
               '不输出' if r.get('error') else amount(r['result']['payback'])] for r in calc['sensitivity']])
    else:para('未录入通用改造方案，本版未输出通用方案敏感性；不使用其他项目的结果替代。')
    para('实际现金流通常按结算时点发生；曲线中的直线连接仅用于展示趋势，不能理解为每天均匀兑现收益。')

    chapter('07  工程量、采购与实施安排')
    para('本节是拟议工作安排，未指定供应商、型号或已获批准的工期。正式工程量与价格应通过现场清点、深化设计和采购流程形成。')
    para('开工门槛：取得业主或其他权利人的有效授权、投资决策、必要的设计审查和安全作业条件确认。物业或运维方认可不能代替法定批准。安全问题必须闭环后方可交付使用。')
    table(['工作包','待明确的工程量 / 采购资料','当前状态'],[
        ['主设备与附属材料','部位、规格、数量、样品和兼容性证明；结合实际方案补齐。','未提供，不计虚构分项价'],
        ['控制与计量','回路、点位、接口、计量边界和调试清单。','待设计与现场确认'],
        ['安装及恢复','拆除、安装、运输、作业条件及成品保护范围。','待勘察后报价'],
        ['设计与验收','设计成果、审查要求、测试项目、档案移交清单。','待责任主体确认'],
    ],[95,WIDTH-205,110])
    bullets(n['procurement_notes'])
    heading('阶段门槛与建议责任角色')
    for stage in n['stages']:
        heading(stage['stage'])
        para('工作：'+stage['actions'])
        para('建议责任角色：'+stage['owner'].rstrip('。')+'。进入下一阶段的条件：'+stage['gate'])

    chapter('08  验收与运行效果验证方案')
    para('施工功能验收通过不等于节能收益已经兑现。需分别保存施工质量、安全、服务品质与用能效果的证据，形成可复核的数据链。')
    para('照明项目的验收底线：由专业人员按确认的设计、测点布置与适用标准，采用经检定或校准的仪器检测照度等指标；目视和住户感受仅作补充。电气、消防及应急功能另按责任专业完成检测，不以节能结果替代。')
    para('效果验证口径：使用真实基线期与报告期的计量数据，记录运行时间、使用状态等调整项及测量不确定性。本报告的假设节电量与简单现金流不得作为竣工实测结论；正式验证应形成独立记录并签署。')
    for item in n['verification']:
        heading(item['item'])
        para('建议方法：'+item['method'])
        para('保留记录：'+item['record'])
    heading('建议建立的数据结构')
    table(['数据表','关键字段'],[
        ['设备与点位台账 CSV/XLSX','位置、设备编号、规格、数量、回路、原状照片编号、新设备资料编号、确认人'],
        ['能耗与运行记录 CSV','时点、计量边界、电量、运行时长、使用状态、异常事件、采集设备、校准信息'],
        ['验收和问题闭环 PDF/XLSX','测试项目、依据版本、结果、问题描述、整改措施、复核记录、责任方签署'],
        ['费用与报价档案 PDF/XLSX','工程范围、分项数量与单价、含税口径、报价有效期、合同与结算对应关系'],
    ],[132,WIDTH-132])

    chapter('09  风险控制与数据补齐')
    for item in n['risks']:
        heading(item['risk'])
        para('应对措施：'+item['mitigation'])
        para('解除条件：'+item['release_condition'])
    heading('开展真实项目的必要资料')
    table(['资料','获取方与格式','用途'],[
        ['连续能耗账单与计量边界','物业/业主/供电服务导出；账单PDF/JPG与月度CSV，建议覆盖连续12个月','建立可比基线，确认电价与用户类别'],
        ['图纸、设备台账与授权照片','业主/物业/测绘或设计单位；PDF、XLSX及已脱敏JPG','确定工程量、现场约束和合法使用权限'],
        ['正式报价与节能量依据','供应商/造价/审计/设计单位；签署PDF及计算XLSX','替换假设投资及节电量，重新比较'],
        ['适用政策、标准和审查结论','主管部门、设计及项目责任主体；原文与适用性核对表','核验适用地域、时间、工程类别和审查责任'],
    ],[104,WIDTH-204,100])

    chapter('10  检索依据与生成记录')
    para('以下条目来自本次实际Chroma检索。相似度、入库或引用都不等于法律效力、工程适用性和事实准确性已核实。日期状态仅反映已登记的日期区间；不相关片段不应作为技术参数依据。')
    cited={rid for m in n['measures'] for rid in m['evidence_ids']}
    for source in plan['sources']:
        block_start=len(story)
        heading(source['reference_id']+'  '+str(source['title']))
        para(f"文档编号：{source['document_id']}；版本：{source.get('version') or '未标注'}；地区：{source.get('region') or '未标注'}")
        status={'unverified':'有效性待核实','active_by_dates':'仅登记日期区间有效','expired':'登记日期已到期','not_yet_effective':'登记尚未生效'}.get(source.get('validity_status'),str(source.get('validity_status') or '未登记'))
        para(f"登记生效：{source.get('effective_from') or '缺失'}；登记失效：{source.get('effective_to') or '缺失'}；核对状态：{status}；{'模型候选引用，适用性待复核' if source['reference_id'] in cited else '检索命中，仅列为核查线索'}")
        url=str(source.get('source_url') or '')
        if urlsplit(url).scheme in {'http','https'}:
            story.append(Paragraph('来源：<link href="'+escape(url,quote=True)+'" color="#087b77">'+escape(url)+'</link>',styles['small']))
        else:story.append(p('来源：'+url,'small'))
        story.append(p('片段定位：'+str(source.get('chunk_index'))+'；文件SHA256：'+str(source.get('checksum')),'small'))
        story.append(p('片段提示：'+str(source['content'])[:100]+'……（请回到原文核查上下文）','small'))
        block=story[block_start:]
        story[block_start:]=[KeepTogether(block)]
    heading('确定性输入来源')
    para('电价：'+base['electricityPriceSource']+'；'+base['electricityPriceUrl'])
    para('碳因子：'+base['carbonSource']+'；'+base['carbonUrl'])
    for s in calc['scenarios']:para(s['plan_id']+'：'+s['sourceName']+'；'+s['sourceUrl']+'；'+s['dataDate'])
    heading('技术留痕')
    pipe=plan['pipeline']
    table(['项目','记录'],[['模型',pipe['llm_model']],['向量',pipe['embedding_model']],['知识库 / 计算','Chroma / Python deterministic tool'],
          ['实际检索','；'.join(r['query']+f"（{r['hits']}个片段）" for r in plan['retrieval_runs'])],
          ['生成时间',plan['created_at']],['完整报告编号',plan['report_id']],['输入指纹 SHA256',plan['input_sha256']]], [106,WIDTH-106])
    para('模型只撰写定性草案；数值表格与曲线由后端重新计算。本文档经过结构和数字字段检查，但不代表全部模型语义已由专家审核。正式实施前必须完成专业设计与资料核验。')
    if plan.get('editorial_review'):
        heading('文本复核修订记录（非工程审查）')
        bullets(plan['editorial_review']['changes'])
        para('保留原始模型调用和检索记录；本次文字与引用范围修订未改变任何输入或测算结果，不代表有资质的工程人员已经审核。')
    output=io.BytesIO()
    def page_frame(c,doc):
        c.saveState();c.setStrokeColor(LINE);c.line(18*mm,A4[1]-15*mm,A4[0]-18*mm,A4[1]-15*mm)
        c.setFont('PlanCN',8);c.setFillColor(MUTED);c.drawString(18*mm,A4[1]-12*mm,'室在人为  |  低碳改造方案与分析报告')
        c.drawRightString(A4[0]-18*mm,A4[1]-12*mm,nature)
        c.drawString(18*mm,11*mm,'前期方案 / 未经工程审查，不直接用于施工')
        c.drawRightString(A4[0]-18*mm,11*mm,f'{doc.page}')
        c.restoreState()
    doc=SimpleDocTemplate(output,pagesize=A4,rightMargin=18*mm,leftMargin=18*mm,topMargin=22*mm,bottomMargin=20*mm,
                          title=base['projectName']+' 低碳改造方案与分析报告',author='室在人为',allowSplitting=1)
    doc.build(story,onFirstPage=page_frame,onLaterPages=page_frame)
    return output.getvalue()
