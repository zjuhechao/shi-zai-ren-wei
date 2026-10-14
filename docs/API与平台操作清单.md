# API与平台操作清单 v0.6.2

本次资料与应用分发为 r4（2026-10-14）。[公开仓库](https://github.com/zjuhechao/shi-zai-ren-wei)提供源码与 `downloads/app-windows-v0.6.2.zip`；应用是需 Python 的本地网页应用，不是公网后端。优先使用 `configure-keys.bat` 隐藏输入本人 Key，完整教学见[下载后运行与配置](下载后运行与配置.md)。Windows 启动入口只允许回环地址，不允许 `0.0.0.0` 或局域网地址；HTTP Host 检查不是用户鉴权。

## 一、先处理已经暴露的密钥

聊天中出现过的 DeepSeek 密钥应立即在 DeepSeek 开放平台后台删除或停用，并重新创建一枚新密钥。新密钥只写入本机 `backend/.env`，不要发到聊天、微信、邮件、截图、演示视频或源码压缩包中。

## 二、DeepSeek：智能体与多模态

用途：RAG工具编排、计算工具调用、定性方案和答复生成；图片可见特征提取是已接入的待验收入口，需要单独取得授权并验证账号模型能力，本轮不声称已完成照片效果验收。

网页在问答、照片、资料入库和新方案生成前要求确认云端传输及可能费用。直接使用问答或新方案 JSON API 时，必须显式发送布尔值 `consent_cloud: true`，不能用字符串 `"true"`、数字 `1` 或省略字段代替；否则不执行云端任务。不要把密钥放进问题、项目上下文、照片说明或知识正文。

需要准备：

1. DeepSeek 开放平台账号；
2. 一枚新 API Key；
3. 账号有可用余额或赛事算力；
4. 本版配置默认 `deepseek-flash`；调用权限、Responses 接口及图片输入能力以自己的账号实际验证为准，配置完成不等于已联通。

在 `backend/.env` 填写：

```text
LLM_PROVIDER=deepseek
LLM_API_KEY=你的新密钥
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-flash
VISION_MODEL=deepseek-flash
LLM_REASONING_EFFORT=none
```

官方说明：

- 快速开始：https://api-docs.deepseek.com/en/
- 图像输入：https://api-docs.deepseek.com/guides/vision/
- 工具调用：https://api-docs.deepseek.com/guides/tool_calls/
- Responses API：https://api-docs.deepseek.com/guides/responses_api/

## 三、阿里云百炼：文本向量RAG

用途：把政策、标准、价格和因子原文转成向量，写入本地 Chroma，实现语义检索。本项目没有使用 DeepSeek 文本嵌入；当前可运行实现采用百炼兼容向量 API，因此必须独立配置并实际入库，没有关键词检索或本地模型降级冒充 RAG。

平台操作：

1. 登录阿里云百炼并开通模型服务；
2. 创建或选择华北2（北京）业务空间；
3. 生成该业务空间的 API Key；
4. 确认账号可调用 `text-embedding-v4`；
5. 在控制台复制带业务空间ID的 OpenAI 兼容 Base URL。

在 `backend/.env` 填写：

```text
EMBEDDING_PROVIDER=dashscope
EMBEDDING_API_KEY=你的百炼密钥
EMBEDDING_BASE_URL=https://你的WorkspaceId.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIMENSIONS=1024
EMBEDDING_BATCH_SIZE=10
```

官方说明：

- 向量模型：https://help.aliyun.com/zh/model-studio/embedding
- OpenAI兼容向量接口：https://help.aliyun.com/zh/model-studio/text-embedding-synchronous-api
- 获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key

## 四、RAG入库

v0.6.2 配置完成后，先离线预检，再核对云端发送授权。预检不会生成向量，也不证明云服务可用：

```powershell
.\.venv\Scripts\python.exe backend\scripts\ingest_knowledge.py --audit-only
```

可以在网页“技术状态”选择“同步已核对资料”。系统只同步审核名单内且指纹一致的资料；只有文档正文、元数据及完整分块内容均匹配时才跳过，分块策略、版本或路径等变化可能触发重新嵌入并计费。命令行必须明确指定文档 ID，例如仅处理已核对的单份文件（正文发送给百炼，产生 API 费用）：

```powershell
.\.venv\Scripts\python.exe backend\scripts\ingest_knowledge.py --reviewed --document-id DOC-FAC-0001
```

入库完成后彻底停止并重新启动自己的程序，检查真实rag_chunks。仅显示“已配置”不能证明Key有效或服务联通。若入库报告跳过文件，按原因修复路径、正文或清单，不把跳过或计划片段计入知识库。

单份知识文件最多 50 MiB、最多两千个解析片段；过大文件先拆分并分别复核。含疑似密钥的正文会被阻断，自动筛查不能替代人工授权和脱敏。

## 五、未实现的其他向量路线

本地中文嵌入模型（例如 BGE）仅是可能的后续研究方向，本版没有相应适配器、模型下载或检索验收，不是当前可用功能，也不会在百炼不可用时自动切换。若以后更改技术路线，需要团队明确同意并另外实现、记录版本及测试；现阶段仍按申请书的 API + Chroma RAG 路线操作。

## 六、现场演示前检查

- `backend/.env` 存在且不在提交压缩包中；
- 页面显示后端、DeepSeek、向量服务、Chroma、Python五项状态；
- 先用一条政策问题检查RAG返回文档标题和链接；
- 先用一张完成授权和脱敏的照片检查多模态结果；
- 计算结果与手算样例一致；
- 无Key或断网时可本地测算并下载固定16页青禾假设PDF；不把它冒充新输入的API/RAG生成结果。

### 离线与在线检查命令

以下两项只做本地检查或配置存在检查，不产生远程模型调用：

```powershell
.\.venv\Scripts\python.exe backend\scripts\check_readiness.py --json
.\.venv\Scripts\python.exe backend\scripts\check_connectivity.py
```

`check_readiness.py` 不读取私人 `.env`，其 PASS 只代表无密钥本地演示通过；云连接、RAG 质量、照片及新智能 PDF 另行验收。`check_connectivity.py` 会读取本人本机配置，但默认仅报告配置是否存在，不显示密钥。

确认授权和费用后，才执行在线连接或客户流程验收。连接检查最多尝试一次 LLM 和一次向量调用；客户流程会执行实际问答与检索，可能有多次调用：

```powershell
.\.venv\Scripts\python.exe backend\scripts\check_connectivity.py --online
.\.venv\Scripts\python.exe backend\scripts\verify_customer_demo.py --online --base-url http://127.0.0.1:8000
```

SDK 的 LLM、向量传输重试已关闭（`max_retries=0`）。新方案的结构化内容校验失败时，只可追加一次纠错生成，合计最多两次模型生成尝试；这不是网络重试。智能体仍可能多轮调用工具，模型生成、检索向量化、主动重试或重新入库均可能计费。浏览器超时不证明服务器或云端已经取消，不要连续点击重试。

## 七、照片和输入限制

每次允许一至五张静态 JPEG、PNG、WebP 或 GIF；单张最多 10 MiB、合计最多 32 MiB、单张不超过 2500 万像素。后端会校验真实图片字节与声明格式、像素数和动画属性；损坏文件、伪装格式或动画不会发送给云模型。上传前先缩图、取得授权并去掉人脸、门牌、账单和联系方式等私人内容；模型账号和供应商接口还可能有更低限制。

项目上下文最多 32 KiB，并限制嵌套、字段及单项文本长度；普通 JSON 请求体最多 128 KiB。不接受非有限数值、工具参数重复键和疑似密钥，错误信息会脱敏。上述是本地原型的输入保护，不等于公网鉴权、完整隐私识别或工程合规认证。
