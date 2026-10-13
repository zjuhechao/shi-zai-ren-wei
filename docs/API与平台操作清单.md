# API与平台操作清单

## 一、先处理已经暴露的密钥

聊天中出现过的 DeepSeek 密钥应立即在 DeepSeek 开放平台后台删除或停用，并重新创建一枚新密钥。新密钥只写入本机 `backend/.env`，不要发到聊天、微信、邮件、截图、演示视频或源码压缩包中。

## 二、DeepSeek：智能体与多模态

用途：图片可见特征提取、RAG工具编排、计算工具调用和答复生成。

需要准备：

1. DeepSeek 开放平台账号；
2. 一枚新 API Key；
3. 账号有可用余额或赛事算力；
4. 模型使用 `deepseek-flash`。

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

用途：把政策、标准、价格和因子原文转成向量，写入本地 Chroma，实现语义检索。DeepSeek 当前没有公开文本嵌入接口，所以这一项必须单独配置，或改用本地中文嵌入模型。

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

v0.6配置完成后，推荐启动网页，在“技术状态”中选择“同步已核对资料”。系统只同步审核名单内且指纹一致的资料，未变化的已入库文档不会重复生成向量。命令行必须明确指定文档ID，例如仅处理已核对的单份文件：

```powershell
.\.venv\Scripts\python.exe backend\scripts\ingest_knowledge.py --reviewed --document-id DOC-FAC-0001
```

入库完成后启动程序，页面顶部应显示“文本向量服务已配置”和“本地Chroma RAG已建立”。若入库报告显示跳过文件，应按原因修复路径、OCR文本或清单字段，不得把跳过的文件计入知识库。

## 五、不使用第二个平台的替代方案

可在本机部署中文嵌入模型，例如 BGE 中文小模型，再把向量写入同一个 Chroma。该方案需要提前下载模型和依赖、记录模型版本，并在断网环境完成检索验收。未完成本地模型下载和测试前，只能称为“待配置RAG”，不能用关键词匹配替代并声称已实现语义向量检索。

## 六、现场演示前检查

- `backend/.env` 存在且不在提交压缩包中；
- 页面显示后端、DeepSeek、向量服务、Chroma、Python五项状态；
- 先用一条政策问题检查RAG返回文档标题和链接；
- 先用一张完成授权和脱敏的照片检查多模态结果；
- 计算结果与手算样例一致；
- 断网时切换离线校验演示，不把离线结果称作API或RAG结果。
