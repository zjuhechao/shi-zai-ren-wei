# 智能体后端 v0.6.1 运行说明

后端由三条相互独立的链路组成：

1. DeepSeek `deepseek-flash` 负责多模态识别和智能体工具编排；
2. 阿里云百炼 `text-embedding-v4` 或其他 OpenAI 兼容嵌入服务负责文本向量化，本地 Chroma 存储和检索；
3. Python 确定性函数负责投资、节省额、减碳量和静态回收期。

这种拆分避免用大模型直接生成工程数值，也避免把没有向量模型的关键词匹配冒充语义RAG。

## 安装与启动

在项目根目录打开 PowerShell：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-lock.windows-py312.txt
.\.venv\Scripts\python.exe -m pip check
# backend/.env 不存在时才复制，不覆盖已配置密钥。
if (-not (Test-Path -LiteralPath backend\.env)) { Copy-Item backend\.env.example backend\.env }
```

编辑 `backend\.env`：

Windows Python 3.12 使用本版完整依赖锁；其他平台使用 `backend/requirements.txt` 的 10 项直接依赖，尚未做跨平台验收。首次安装默认官方 PyPI；本机浙江大学镜像实测可安装，可显式增加 `--index-url https://mirrors.zju.edu.cn/pypi/web/simple`，不改变全局配置。也可使用根目录启动器及其 `-PythonPath`、`-IndexUrl`、`-Port` 参数。Node 仅用于测试。

- `LLM_API_KEY`：新建的 DeepSeek API Key；
- `LLM_BASE_URL=https://api.deepseek.com`；
- `LLM_MODEL=deepseek-flash`，`VISION_MODEL=deepseek-flash`；
- `EMBEDDING_API_KEY`：阿里云百炼或其他嵌入服务的密钥；
- `EMBEDDING_BASE_URL`：账号业务空间对应的 OpenAI 兼容地址；
- `EMBEDDING_MODEL=text-embedding-v4`，推荐维度1024。

密钥不得写入 HTML、JavaScript、文档、截图或 Git。聊天中暴露过的密钥必须先在平台后台作废并重新生成。

## 建立RAG并运行

`数据收集包/08_已整理结构化数据/knowledge_manifest.csv` 已登记政策、标准、价格和因子原文。配置嵌入服务后执行：

```powershell
.\.venv\Scripts\python.exe backend\scripts\check_readiness.py --json
.\.venv\Scripts\python.exe backend\scripts\ingest_knowledge.py --audit-only
.\.venv\Scripts\python.exe backend\scripts\ingest_knowledge.py --reviewed --document-id DOC-FAC-0001 --document-id DOC-POL-0002 --document-id DOC-POL-0004
.\.venv\Scripts\python.exe backend\run.py
```

打开 `http://127.0.0.1:8000`。页面应分别显示智能体API、文本向量服务、本地Chroma和Python计算状态。

前两个检查完全离线，不发送正文或调用模型。第三行只入库审核名单内明确选定的三个公开样本，会产生向量API费用。必须先核对相同来源与文件SHA256。原机与干净源码的文档数、向量数分别记录，不自动沿用。

完整方案入口 `POST /api/reports/plan` 根据当前输入实际检索、调用模型并生成PDF；`GET /api/demo/plan.pdf` 下载 `assets/reports/qinghe_plan_demo.pdf` 固定青禾假设样例（内容复核 r2，与修改后的输入无关）。新生成草案需复核。生成记录位于不对静态网页公开的 `storage/reports`。完整方案缺少真实 RAG、API 或云端同意会阻断，不回退为伪造模型结果。定性正文限制数字，数值由 Python 重算插入；引用片段的相关性不能视为适用性确认。

## 验证

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
Pop-Location
node backend\tests\test_client_ui.cjs
node backend\tests\test_case_prefill.cjs
```

没有 API 密钥也可测试 Python 计算、前端数据校验和固定报告下载；涉及模型的操作明确提示未配置。单元测试通过不代表模型质量、云端联通或照片效果验收。必填 Unicode 空白、非有限值、地区层级和真实案例碳因子不自动混用均有回归测试。

望月公开 `0.4974 kgCO2/kWh` 仅为 CO2 线索，不自动填入 CO2e 字段；真实项目气体覆盖、单位、边界及其他原始证据未齐时不能计算真实收益。

PDF需要ReportLab和中文TrueType字体。本机使用系统字体；Docker备选已配置文泉驿字体与固定版本依赖，但尚未实际构建验证。非Docker Linux运行时可设置 `REPORT_FONT_PATH`，指向有权使用的TTF/TTC文件。完整部署步骤见 `deploy/部署与验收说明.txt`。

## 数据安全

- 图片会上传到配置的云端模型，必须先取得授权并完成脱敏；
- 不上传身份证、人脸、车牌、住户门牌、电话号码或精确住址；
- 后端默认只监听 `127.0.0.1`；公网部署前需增加登录、权限、HTTPS、日志脱敏和文件安全检查；
- 政策、标准和价格检索只提供候选依据，适用性与补贴资格由人工复核。
