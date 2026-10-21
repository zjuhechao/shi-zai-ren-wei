# 室在人为 v0.6.2 源码运行说明

软件 API 版本为 v0.6.2，资料与应用分发修订为 r4（2026-10-14）。项目使用 FastAPI、DeepSeek Responses API 工具调用、百炼兼容文本向量接口、本地 Chroma 与 Python 确定性测算，输出完整前期改造与分析方案 PDF。新版本加强请求和工具校验、向量响应检查、网页超时与过时结果保护，以及下载配置诊断；原技术路线不变。青禾固定方案保留原生成与复核历史，没有重新调用模型。

校赛前最终核查（2026-10-21）修复了三项遗留问题（PDF 有效性标签映射、照片分析事件循环阻塞、前端口径对齐测试），并为网页增加客户体验增强：录入完成度进度条、基线三步向导、结果区纯前端 SVG 图表（净投资条形图与现金流曲线）与 Hero 区视觉装饰。这些改动不改变计算口径、不引入本地存储。

当前公开源码地址为 [zjuhechao/shi-zai-ren-wei](https://github.com/zjuhechao/shi-zai-ren-wei)，按团队要求提供校赛公开链接。公开仓库可直接下载，不需要邀请；下文的私有仓库权限提示只适用于今后改为私有的情况。仓库未另行授予开源许可证，公开可见不等于授权任意复用；团队代码权属和第三方资料使用边界仍须确认。仓库是否完成上传以页面实际文件和提交为准。

源码不含已配置密钥、私人照片、账单、签章、原机向量库或视频。解压后默认没有 API Key，向量片段从零开始。无需密钥仍能打开网页、校验输入、进行 Python 测算，并下载已生成的青禾社区假设方案。新输入的完整智能方案必须在真实 API 和 RAG 就绪后生成，不会回退为伪造智能答案。

## 获取应用或完整源码

普通使用者可[下载 Windows 本地应用包](https://github.com/zjuhechao/shi-zai-ren-wei/raw/refs/heads/main/downloads/app-windows-v0.6.2.zip)，完整解压后查看“开始使用.html”，运行 `start-app.bat`。这是源码型本地应用，仍需 Windows x64 Python 3.12 和首次联网安装依赖，不是免安装 EXE，也不是托管公网后端。包内有前后端、配置向导、三份公开样本、固定示范 PDF 和逐文件指纹；不含 Python 运行时、团队 Key、原向量库、开发测试或 Docker。

开发者使用 **Code → Download ZIP** 或 `git clone https://github.com/zjuhechao/shi-zai-ren-wei.git` 获取完整仓库。完整仓库另含测试、Docker备用配置及应用打包脚本；`downloads` 中的应用 ZIP 是公开分发资产，不是私人交付包。构建方式见 [应用分发说明](downloads/README.md)。普通下载者不需要安装 Git、Node 或 GPU。

## 从 GitHub 下载后的最短入门

第一次使用请看 [下载后运行与配置教程](docs/下载后运行与配置.md)。当前公开仓库可直接下载；若仓库今后改为私有，则需要先接受持有人的邀请。下载者不需要安装 Git，也不需要获得团队的密钥。

1. 下载上述应用 ZIP，或在仓库选择 **Code → Download ZIP**，完整解压；不要直接双击 `index.html`。
2. 准备 Windows x64 的 Python 3.12；应用包双击 `start-app.bat`，完整源码双击 `启动演示.bat`。等待首次依赖安装，按窗口显示的地址打开网页。
3. 无密钥先点“载入假设情景演示”，完成 Python 测算，并下载青禾示范方案 PDF。
4. 要生成自己的新方案，再用 `configure-keys.bat` 配置**自己账号**的 DeepSeek 和百炼；按教程显式测试联通、审核并入库三份公开样本，然后彻底停止并重新启动服务。

Python 3.12.14 是本次实际验收的运行时，不存在该版的传统官方 Windows 安装包；不要寻找来路不明的同名安装器。教程提供 Python Install Manager 与 Astral uv 的可选安装路径，并说明版本和验收范围。

## 首次运行：Windows / Python 3.12

推荐 Windows x64、Python 3.12。本版实际验收环境为 Python 3.12.14；Windows 3.12 使用 `backend/requirements-lock.windows-py312.txt` 锁定直接及传递依赖。其他系统或 Python 版本使用 11 项直接依赖的 `backend/requirements.txt`，其中 Pillow 用于检查图片真实格式和尺寸，原完整锁文件已包含它。其他环境需额外验收；Node.js 仅用于前端测试，日常网页运行不需要 Node。

双击 `启动演示.bat`，或在项目根目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\启动演示.ps1
```

启动器自动探测可用 Python；若已有 Python 但自动探测失败，明确提供完整路径，例如：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\启动演示.ps1 -PythonPath "C:\你的Python目录\python.exe" -Port 18061
```

默认包索引是官方 `https://pypi.org/simple`。本机官方源连接失败，浙江大学镜像实际安装成功；必要时可单次指定，不改变全局 pip 设置：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\启动演示.ps1 -IndexUrl https://mirrors.zju.edu.cn/pypi/web/simple -Port 18061
```

脚本首次创建 `.venv` 和空白 `backend/.env`，根据依赖文件指纹和导入/依赖检查决定是否安装或修复。已有同类服务占用端口时，只显示该服务的网址和版本，不会停止它；使用 `-Port 18061` 可以运行独立副本。若其他程序占用端口则明确报错。命令行窗口显示实际网页地址，关闭该窗口停止本副本；批处理正常退出后也保留提示。

也可手动运行（有 Python Launcher 时）：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-lock.windows-py312.txt
.\.venv\Scripts\python.exe -m pip check
$env:APP_PORT = "18061"
.\.venv\Scripts\python.exe backend\run.py
```

此手动方式不写启动器指纹，因此随后首次使用启动器会再核对依赖。锁文件是本机完整安装版本记录，并非所有平台通用的锁。

## 三份公开知识样本与真实 RAG

本副本仅附 `DOC-FAC-0001`、`DOC-POL-0002`、`DOC-POL-0004` 三份政府公开归档。出处、版本、获取日期与 SHA-256 位于 `数据收集包/08_已整理结构化数据/knowledge_manifest.csv`，审核字节指纹位于 `data/knowledge/reviewed_documents.json`。原机曾有 22 份入库资料、482 个片段，属于历史记录，不能当作此副本已经入库。

三份样本用于复现同一检索路线，不是普通住宅改造的充分依据：公共机构政策不可直接套用于住宅；历史排放因子不可自动当作项目最新适用值；政策对象、地域、版本和有效性仍需复核。地域筛选按明确全国、同省、同市和同区县层级处理，消除输入中的空白与场景说明，不猜测省份简称或不明确地址。

运行 `configure-keys.bat`，在本地隐藏输入新的 DeepSeek Key、百炼文本向量 Key 和对应业务空间的 HTTPS Base URL。配置只保存在被 Git 忽略的 `backend/.env`。聊天里公开过的旧密钥应由账号持有人撤销并替换。配置齐全不等于服务已联通，模型权限、余额、地域、接口兼容性须实际检查。

先进行离线文档预检，不发送正文、不调用 API：

```powershell
.\.venv\Scripts\python.exe backend\scripts\ingest_knowledge.py --audit-only
```

确认有权向服务发送这三份公开文件后，显式选择已审核文档入库（产生平台调用费用）：

```powershell
.\.venv\Scripts\python.exe backend\scripts\ingest_knowledge.py --document-id DOC-FAC-0001 --document-id DOC-POL-0002 --document-id DOC-POL-0004 --reviewed
```

审核指纹不匹配、文件不可解析或配置缺失会阻断。入库数量以真实返回值为准；没有库时不会伪造检索结果。更换向量模型、维度或接口地址后须重建匹配索引。不要让多个进程同时写同一个嵌入式 Chroma 目录。

完整智能方案以百炼生成查询向量、Chroma 检索证据、DeepSeek 组织定性正文；正文限制数字，定量结果由 Python 重算后插入。片段编号与相关性标记仅用于查证，不表示对应条款已经适用。生成前须确认云端处理，项目输入与检索片段会发送模型平台。照片处理另行授权，本轮未新增照片或付费 API 效果验收。

## 报告、真实案例与安全边界

`assets/reports/qinghe_plan_demo.pdf` 是青禾社区**假设案例**的内容复核 r2 固定成品，仅通过 `/api/demo/plan.pdf` 提供下载；改变网页输入不会改动此文件。无需旧交付目录即可运行。新生成报告的输入快照、检索及计算审计留在私有 `storage/reports`，该目录、`.git` 与 `.env` 不公开为静态网页。

投资为前期假设投入，不能把它视为正式报价或总包预算；节能收益及回收期随已确认口径计算，未纳入项会明确提示。真实望月公寓的账单、工程量、报价、节能依据、核算边界与授权仍未补齐，不输出伪造真实收益。案例历史台账不代表原件随此源码提供。

望月公开因子线索为 2023 年浙江省 `0.4974 kgCO2/kWh`，气体覆盖是 CO2，不自动填入程序的 CO2e 测算字段。气体覆盖、单位和核算边界确认前因子保持为空；青禾的 `0.5 kgCO2e/kWh` 明确是测试假设。来源、日期和必填文本包括 Unicode 空白均校验；可选备注允许为空，非有限数值会拒绝。结论必须经项目真实证据和人工审查，不替代施工图或正式工程审查。

## 离线验收与测试

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe backend\scripts\check_readiness.py --json
Push-Location backend
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
Pop-Location
node backend\tests\test_client_ui.cjs
node backend\tests\test_case_prefill.cjs
```

2026-10-13，本源码自身的独立 `.venv` 实际完成 Windows/Python 3.12.14 的 95 包锁定依赖安装，逐项版本差异为零，`pip check` 无冲突。53 项后端单元测试、前端 14 项与真实案例预填 12 项断言、18 项离线准备检查、20 项 HTTP 检查及 3 项启动器检查均通过。配置提示文字的最后一次修改后，又在同一独立环境复验 53 项后端测试。对应事实与边界见 [源码复现验收](docs/源码复现验收_v0.6.1.md)，详细原始记录另附提交包运行与验收目录。`requirements.snapshot.windows-py312.txt` 同步为实际安装的 95 包版本快照；安装入口仍以完整锁文件为准。

验收服务位于 `http://127.0.0.1:18061`，返回 v0.6.1、3 份公开样本、0 个已索引向量且无密钥。本轮没有新增云端调用；这些检查不代表模型准确率、云端联通率或另一台电脑部署成功率。

Windows 默认使用系统微软雅黑。Linux 可通过 `REPORT_FONT_PATH` 指向可用且合法的中文 TTF/TTC，并重新检查 PDF 排版。Docker 配置使用 Python 3.12、11 项直接依赖、文泉驿字体与固定报告资产；公开资料只读挂载到 `/app/数据收集包`，Chroma 独立持久化。本机未安装 Docker，当前只审查配置，不声称完成 Linux 构建或远程验收。公网使用还需要鉴权、HTTPS、配额、费用与数据保护专项实现；本版 Host 保护只允许回环访问，不直接作为公开网站使用。

## 下载配置的专题检查

配置专题检查只使用假测试输入，验证地址校验、隐藏输入、取消不覆盖、原子保存和正确服务绑定；不读取团队密钥或调用云端。历史 v0.6.1 的 21 项检查保留原日期；v0.6.2 增加配置解析和保存保护，与本版核心业务/前端测试分别记录。测试数量不代表模型准确率或异机部署成功率。

```powershell
.\.venv\Scripts\python.exe -S backend\tests\configuration_checks.py -v
```

本地配置向导只需Python标准库，因此首次配置不需要已安装全部项目依赖。填完密钥与地址仍需彻底重启服务，并按教程明确选择在线检查和知识入库；没有密钥或索引不能生成新的智能方案。

## v0.6.2 本轮完善

84 项后端、127 个前端断言、46 项配置／分发检查及 31 项独立无 Key 实际 HTTP 检查通过，范围分别记录，不相加为模型准确率。浏览器实测输入变更、重新计算、未配置提示及固定 PDF 下载；窄屏上传控件溢出已修复。详见 [本轮完善与验收](docs/完善与验收_v0.6.2.md) 和 [更新记录](CHANGELOG.md)。本轮复用既有 95 包运行时，没有新增付费 API 调用或自动重建私有库。

## v0.6.2 交互和处理边界

网页为状态检测、计算、咨询、照片、入库及完整 PDF 设置不同超时；按钮处理中阻止重复请求，项目、问题、照片或 CSV 改变后不展示旧操作的迟到结果。超时只结束浏览器等待，云端任务可能仍继续并产生费用，不会自动重试。未保存输入留在当前浏览器页面；导出的 JSON/HTML 含项目资料，应保留私有。

CSV 导入最多每文件 2 MiB / 500 条，要求规范表头、引号、有效日期、有限非负数和唯一方案 ID。后端在云端前检查输入边界及疑似凭据，验证模型工具参数和向量返回值。照片检查格式/字节不构成识别效果验收，模型引用校验也不能替代专业审查。新完整方案仍必须具备本人 API、真实 Chroma 资料和严格布尔云端处理同意。SDK 不做隐式传输重试；方案结构生成最多两次（首次加一次纠错）。

入库只有在原文、实际块正文和元数据均一致时才跳过；解析、切分或元数据变化可能重新向量化并计费。升级不会自动重建原私有库。Windows 入口拒绝非回环监听；容器内部通配监听须显式开启，宿主仍仅发布回环端口，Docker 尚未实际构建验收。

`check_readiness.py` 的离线检查只报告代码与本机依赖准备情况，不能把总体 PASS 当作云端 API 或新智能 PDF 已验收。客户演示诊断默认离线；确实同意发送假设输入并承担调用费用时，才显式执行 `backend/scripts/verify_customer_demo.py --online`。

## r4 分发核验范围

`application_manifest.sha256.json` 位于应用包内，记录必要运行文件和包装入口的字节指纹，不对自身取指纹；源码清单 `release_files.sha256.json` 另记录完整仓库。应用构建仅选择白名单文件，不递归复制 `downloads`，不读取 `.env`、`.venv` 或 `storage`。本次分发检查与前述 10 月 13 日基础验收分开记录，不把本机解压运行当作另一台电脑安装、模型准确率或新的付费 API 联调。

## Git 与归档

公开仓库已作为团队指定提交入口，发布状态以实际远端文件和核验记录为准。提交前确认 `.env`、`.venv`、`storage`、私人项目资料及付费服务密钥没有入 Git。克隆的 `.git` 保留历史；Code 下载和源码快照 ZIP 只含 Git 跟踪文件，没有 `.git`、运行环境或真实配置。当前完整仓库 ZIP 内含 `downloads` 的无密钥应用 ZIP；应用 ZIP 自身不嵌套压缩包。完整校赛材料含身份信息，只交组织方，不上传仓库。

`release_files.sha256.json` 列出当前 Git 跟踪文件的字节指纹，故意不哈希自身。最终 HEAD 和 ZIP 指纹由提交包外部核验记录保存，避免循环依赖。下述 bundle 属于历史恢复备份，组织方核心提交不要求该文件；没有 bundle 的下载者直接从 GitHub 克隆即可查看完整公开历史。

在随包 bundle 所在目录运行以下命令，可恢复源码与当前发布历史到一个不存在的新文件夹。关闭自动换行转换是为了与发布指纹进行同字节核对：

```powershell
git -c core.autocrlf=false clone ".\室在人为_v0.6.2_当前发布历史.bundle" ".\恢复源码"
```

旧版主工程 README、旧交付 PDF、旧技术说明与架构图已移出当前源码工作树，另存为历史追溯资料；当前说明和架构位于 `docs/技术说明_v0.6.2.pdf` 与 `docs/技术架构_v0.6.2.svg`，本页是此版运行依据。旧资料仍可通过历史追溯目录或 Git 历史恢复，不应混入当前运行资产或冒充当前验收。
