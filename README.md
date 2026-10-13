# 室在人为 v0.6 源码复现说明

这是 2026-10-13 校赛非视频提交用的完整源码副本。提交包中的完整源码文件夹是本地 Git 仓库，初始提交由 `Codex local release <codex-local-release@localhost>` 创建；尚未推送至远程平台，也没有公开访问网址。单独提供的源码 ZIP 仅含已跟踪文件，不含隐藏 `.git` 和 Git bundle，须使用另外附带的 bundle 恢复版本历史。主工程的 README 另存为 `docs/主工程README_v0.6.md` 供版本追溯，以本页描述的干净副本范围为准。

本副本包括前端、FastAPI 后端、DeepSeek Responses API 工具调用、百炼兼容文本向量接口、本地 Chroma、Python 确定性测算、完整方案 PDF 生成、测试、启动与部署配置。与主工程保持同一实现，不携带任何已配置密钥、已有向量库、私人照片、能耗账单、签章或视频。

## 干净副本与原机记录

原机 22 份资料、482 个向量片段及云端联调是此前的实测记录；本副本从 0 个向量片段开始，只附 3 份政府公开归档供重建示例。两者不能混称。本副本已附青禾社区假设报告，可通过网页直接下载；该固定 PDF 是此前完整知识库生成的成品展示，与用户修改后的输入无关。本包的最小知识示例用于跑通同一条真实检索链路，不声称可逐字重现历史模型回答。

三份公开归档分别为 `DOC-FAC-0001`（2022 年电力二氧化碳排放因子公告）、`DOC-POL-0002`（杭州市公共机构既有建筑改造通知）、`DOC-POL-0004`（浙江省设备更新举措）。来源 URL、版本、获取日期和 SHA-256 保留在 `数据收集包/08_已整理结构化数据/knowledge_manifest.csv`，字节指纹对应 `data/knowledge/reviewed_documents.json`。政策的适用对象、有效状态仍需核对；公共机构规定不能直接套用于普通住宅，归档因子也不能自动充当用户项目最新适用因子。

`data/cases/wangyue_case.json` 保留原工程的真实案例核验状态，其中资料台账、照片和户型数量是原工程历史记录，不代表这些原件随源码提供。页面知识目录显示本副本实际三份样本；案例状态中的未核验值不能自动转为可计算输入。

## Windows 快速运行

推荐 Python 3.12。Node.js 只用于前端单元验证，日常网页运行不需要 Node。

在本目录打开 PowerShell：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe backend\run.py
```

打开 `http://127.0.0.1:8000/`，即可进行本地校验、通用改造和光伏测算、假设情景演示及固定青禾 PDF 下载。没有密钥时，界面会如实显示智能体和语义向量服务未配置。

`启动演示.bat` 会代为创建环境、安装依赖和首次建立空白 `backend/.env`。依赖直连版本位于 `backend/requirements.txt`；`backend/requirements.snapshot.windows-py312.txt` 是原机完整安装版本快照，用于排查差异，不代表这些版本已在所有系统上安装验证。

首次安装依赖需要可访问的包索引。本次在空白环境重装遇到镜像读取超时，官方源重试中止，未完成安装；验收因此使用原机已经安装的依赖。新电脑应先完成安装，再执行 `python -m pip check` 和下方验收命令，不以当前日志替代新环境实测。

## 配置真实 API 和重建 RAG

运行 `configure-keys.bat`，在自己的终端内输入新建的 DeepSeek Key、百炼文本向量 Key 和业务空间对应的 HTTPS Base URL。输入不会显示，密钥只保存在被 Git 忽略的 `backend/.env`。模型和向量维度以 `.env.example` 为参考；服务权限、余额、地域及模型可用性由账号持有人核对。

先做不调用 API 的文档预检：

```powershell
.\.venv\Scripts\python.exe backend\scripts\ingest_knowledge.py --audit-only
```

确认有权发送这三份公开归档后，再执行实际向量入库（会产生平台调用费用）：

```powershell
.\.venv\Scripts\python.exe backend\scripts\ingest_knowledge.py --document-id DOC-FAC-0001 --document-id DOC-POL-0002 --document-id DOC-POL-0004 --reviewed
```

命令只发送显式选中的文件，且必须与审核指纹一致。也可在网页通过云端处理确认后入库。成功后查看返回的真实入库数量，并进行资料内、资料外和地区不匹配问题测试；不预填准确率或把单元测试当作模型效果验收。

重启后可使用智能体和“生成完整方案 PDF”。正文检索通过百炼生成查询向量并在 Chroma 中匹配，相关片段与项目输入发送 DeepSeek 组织方案，投资与收益由 Python 重新计算。云端不可用或来源缺失时，入口返回具体错误。完整报告仍需人工审查和项目真实证据。

## 测试与字体

```powershell
.\.venv\Scripts\python.exe backend\scripts\check_readiness.py --json
Push-Location backend
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
Pop-Location
node backend\tests\test_client_ui.cjs
```

本次干净副本运行验收保存在上一级提交包的 `06_运行与验收/源码复现验收.json`。验证使用同一台 Windows 机器的已安装 Python 运行时、新的源码根目录和另一端口；未把它冒充另一台电脑复现、无缓存重新下载依赖或新账号云端联调。

报告需要中文字体。Windows 默认使用系统微软雅黑；Linux 可通过 `REPORT_FONT_PATH` 指向合法可用的中文 TrueType 字体，并须重新检查 PDF 排版。Docker 配置是备选，当前尚未取得镜像构建和远程运行验收记录。

## 本地 Git 与后续提交

```powershell
git status --short
git log -1 --format=fuller
```

当前没有远程地址。后续由团队在选定的 Git 平台创建仓库并配置真实 remote 后再推送；不要提交 `backend/.env`、`.venv`、`storage` 或私有项目资料。源码权属与团队提交承诺由团队确认，本副本没有擅自附加开源许可或替团队签署授权。

`源码仓库_v0.6.bundle` 是当前发布历史的 Git 恢复备份。若压缩工具省略隐藏的 `.git`，可在另一个空目录执行 `git clone --branch main 路径/源码仓库_v0.6.bundle 室在人为_恢复源码`，恢复当前发布历史和全部已跟踪文件。恢复不会包含密钥、原机 Chroma 数据或尚未配置的 remote。
