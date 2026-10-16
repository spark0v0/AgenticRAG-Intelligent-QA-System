# AgenticRAG 智能搜索与问答系统

基于 Vue 3 与 FastAPI 的智能问答工作台。通过 Router（路由）、Planner（规划）、Retriever（检索）、Generator（生成）、Critic（评审）五类智能体按需协作，结合本地知识库与联网资料生成带引用的回答，让检索依据和执行过程可查看、可追溯。

![问答工作台](docs/screenshots/clean-chat-1440.png)

## 主要能力

- **流式问答**：多轮对话、模型与检索范围选择、图片输入、停止生成；支持 Markdown、代码高亮与复制。
- **会话管理**：搜索、置顶、重命名、草稿恢复和完整 Markdown 导出；长会话先加载最近 20 轮，加载更早消息时保持阅读位置。
- **本地知识库**：上传 TXT、Markdown、文本型 PDF，查看索引状态并重试失败任务；支持关键词、BGE 语义及混合检索，并排比较三路结果。
- **联网与证据**：接入 Tavily，可与本地资料组合检索；回答引用关联原文片段，PDF 支持站内阅读、翻页、缩放和引用页定位。
- **执行分析**：展示实际经过的智能体节点、检索轮次、工具调用和耗时，支持历史运行回看。界面提供明暗主题与窄屏布局。

## 技术栈

| 模块 | 技术 |
| --- | --- |
| 前端工程 | Vue 3、TypeScript、Vite、Pinia、Vue Router |
| 界面与阅读 | Element Plus、SCSS、markdown-it、DOMPurify、highlight.js、PDF.js |
| 通信与后端 | Fetch / SSE、AbortController、FastAPI、Pydantic、HTTPX |
| 检索与存储 | FastEmbed / BGE、ChromaDB、BM25、RRF、Tavily、SQLite |
| 工程检查 | openapi-typescript、ESLint、Prettier、Vitest、Playwright、pytest、GitHub Actions |

路由决定处理路径，复杂问题按需规划子任务，检索器收集证据后交给生成器回答，评审模块检查引用并触发受限修订。具体实现见 [系统架构](docs/architecture.md)。

## 快速开始

环境：**Python 3.13、Node.js 24.15+、npm**。以下命令在 Windows PowerShell 中执行。

```powershell
git clone https://github.com/spark0v0/AgenticRAG-Intelligent-QA-System.git
cd AgenticRAG-Intelligent-QA-System
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -c requirements-verified.txt
npm --prefix frontend ci
.\start.bat
```

启动器构建前端、启动 FastAPI 并打开 [问答工作台](http://127.0.0.1:8000/chat)。日常可直接双击 `start.bat`；保留窗口，按 `Ctrl+C` 停止。接口文档见 [Swagger UI](http://127.0.0.1:8000/docs)。

```powershell
.\start.bat -Port 8001      # 更换端口
.\start.bat -NoBrowser      # 不自动打开浏览器
```

脚本只使用本项目的 `.venv`。修改后端代码后，先停止旧服务再启动；端口冲突不会强制结束其他进程。

## 首次配置

### 回答模型

在「模型供应商」中添加服务地址、凭据和模型 ID，设为默认模型后开始问答。支持 OpenAI 兼容接口、DeepSeek、Ollama 和 Xinference。

OpenAI 兼容接口与 DeepSeek 支持真实流式响应；Ollama、Xinference 及关闭流式的配置使用完整结果模式。图片能力需按模型实际支持情况配置。连接检查只获取模型列表，首次问答成功后才记录生成调用成功状态。

### 本地知识库

创建知识库、上传文件，等待索引完成后，在问答输入区选择该库。文本需为 UTF-8，PDF 需包含可提取文字；不支持扫描件 OCR。上传限制为每次 8 个文件、单文件 10 MiB、整个请求 32 MiB。

关键词模式无需嵌入模型。语义或混合模式首次使用前执行：

```powershell
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe scripts/prepare_embedding.py
```

默认使用 `BAAI/bge-small-zh-v1.5`，通过 FastEmbed / ONNX Runtime 在 CPU 上运行。模型首次下载后保存在本地；缺失时明确报错，不以哈希向量替代。索引维护与检索对比见 [知识库说明](docs/knowledge-workbench.md)。

### Tavily 联网搜索

首次可将 [`.env.example`](.env.example) 复制为 `.env`；已有文件直接编辑，保留原配置：

```dotenv
WEB_SEARCH_PROVIDER=tavily
TAVILY_API_KEY=your_tavily_api_key
```

重启后端，选择「联网搜索」或「本地 + 联网」。后端通过 HTTPX 直接调用 Tavily Search API，使用网页标题、链接与摘要作为证据，不依赖 MCP 或 Tavily SDK。

未指定搜索服务且没有 Tavily Key 时，使用覆盖有限的 Wikipedia / DuckDuckGo 即时答案接口；显式选择 Tavily 但缺少 Key 会报错。

## 本地开发

保持后端运行，在另一个终端启动 Vite：

```powershell
npm --prefix frontend run dev
```

访问 [开发页面](http://127.0.0.1:5173)。`/api` 默认代理到端口 8000；其他后端地址通过 `VITE_API_TARGET` 设置。开发与生产使用相同 API 路径。

```powershell
npm --prefix frontend run api:check     # 接口类型一致性
npm --prefix frontend run lint
npm --prefix frontend run smoke
npm --prefix frontend run build         # 类型检查与生产构建
```

后端与浏览器测试使用隔离数据和服务夹具，不需要真实 API Key。运行方法与已执行结果见 [验证记录](docs/verification.md)。

```text
frontend/src/   页面、组件、状态管理、接口与业务类型
src/agents/    五类智能体
src/core/      执行流程编排
src/knowledge/ 文档解析、索引任务与知识库检索
src/retrieval/ 项目资料检索
src/api/       FastAPI 接口
src/memory/    SQLite 持久化
src/tools/     搜索及外部工具
src/models/    模型供应商适配
scripts/       启动与模型准备
tests/         后端检查与隔离夹具
```

## 数据与使用边界

- 面向本机单用户、单进程运行，未提供公网认证或多 worker 任务协调。
- SQLite 保存会话、运行和业务状态，ChromaDB 保存检索向量；原文与模型缓存在 `data/knowledge/`。凭据仅留后端，`.env`、数据目录和测试产物不提交 Git；备份前先停止服务。
- 用户知识库可使用 BGE 语义嵌入；未选知识库时，旧版项目资料检索使用 BM25 与哈希向量。Critic 检查引用结构，不保证逐句事实正确。
- 停止生成会取消后续执行并关闭支持取消的连接；同步工具可能执行至检查点或超时。完整导出及跳转指定历史运行仍可能读取整段会话。
- Function Calling 为可选工具选择适配；MCP 提供本地示例，Dify 提供工具封装，尚未发布完整插件。

## 更多文档

[系统架构](docs/architecture.md) · [前端设计](docs/frontend-design.md) · [接口与存储](docs/api-and-storage.md) · [知识库维护](docs/knowledge-workbench.md) · [验证记录](docs/verification.md) · [后续规划](docs/roadmap.md)
