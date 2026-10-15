# 本地知识库：启动、设计与操作

## 概述

知识库支持用户文档管理、异步索引、检索预览、限定范围问答与证据定位。文档、任务与片段存储于 SQLite，语义向量存储于独立 Chroma collection，后台索引线程与聊天请求分开执行。

所有命令均在项目根目录执行，使用项目自己的 `.venv`。

## Windows 启动

首次安装（PowerShell，当前项目根目录）：

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt -c requirements-verified.txt
npm --prefix frontend ci
npm --prefix frontend run build
```

语义模式首次准备，运行公开中文模型下载，不调用回答供应商：

```powershell
$env:PYTHONUTF8 = '1'
& .\.venv\Scripts\python.exe scripts/prepare_embedding.py
```

使用 FastEmbed 0.7.4 / CPU ONNX 的 `BAAI/bge-small-zh-v1.5`，输出 512 维向量。首次准备会下载公开模型及缓存，下载量取决于分发格式，缓存与依赖还会占用额外磁盘空间。运行无需 GPU 或嵌入服务 API Key；首载与索引消耗本机 CPU/RAM，嵌入线程数为 2。

来源：[FastEmbed 模型列表](https://qdrant.github.io/fastembed/examples/Supported_Models/)、[BGE 中文小模型](https://huggingface.co/BAAI/bge-small-zh-v1.5)。

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-workbench.ps1
# 或：
& .\.venv\Scripts\python.exe -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --workers 1
```

打开 `http://127.0.0.1:8000/knowledge`。前端构建由 FastAPI 提供；`/knowledge` 刷新走 SPA，API 仍在 `/api` 下。代码更新后重新构建并重启服务。仅支持单进程；不要为此工作队列配置多个 Uvicorn worker。

开发时先启动后端，再 `npm --prefix frontend run dev`，沿用现有 `/api` 代理。真实问答需已有供应商配置；知识库管理和检索预览不需要回答模型。关键词模式完全不需要嵌入模型，语义模式缺少模型会明确失败，准备模型后点“重试”。不会静默改用哈希向量。

## 使用流程

1. 创建知识库，选择中文语义与关键词融合，或明确选择仅关键词。当前不支持在线更换该库的索引模型。
2. 上传 TXT、Markdown、文本型 PDF。任务依次显示等待、提取文字、切分、索引、可检索。只有实际知道片段总数后才展示 `已处理 / 总数`。
3. 可按名称搜索、按状态筛选，失败可重试、运行中可取消。重建失败会保留原有已提交索引，界面同时显示旧索引可用和本次任务失败。
4. 展开“检索预览”，可单独检索关键词、语义或融合结果，也可选择“三种模式对比”并排查看排名、原始分数和片段。只执行本地检索，不调用回答模型；仅关键词库会明确显示语义与融合不可用。
5. 点击“基于资料提问”，进入问答。问答入口显示当前知识库，支持本地或本地加联网；选库后禁止快速回答和仅联网这种绕过当前知识库的组合。
6. 答案来源与运行分析均可打开证据面板，查看回答采用的快照、完整片段、章节/实际 PDF 页码与原文。文本按提取后的字符区间定位；PDF 可在抽屉内按页阅读、缩放和返回引用页，也保留原文链接。
7. 删除文档立即排除检索，再异步删除向量、文件和片段。删除知识库会清理所有文档，成功后自动移除；部分失败保留可操作的“重试清理”。历史回答的来源快照保持不变，面板实时标注原文不可用。

未选择用户知识库时，旧版“项目内置资料”入口仍明确标注并保持兼容。它仍使用原有中文二元分词、BM25 与哈希向量融合，不能称为成熟语义检索。**选择用户知识库后不会检索项目源码、配置图谱或其他知识库**。

## 文件限制与边界

| 项目 | 限制 |
| --- | --- |
| 每次文件数 | 1～8 |
| 单文件大小 | 10 MiB，不能为空 |
| 整个请求 | 32 MiB，含 multipart 封装；无 Content-Length 也计数 |
| 文本 | UTF-8 / UTF-8 BOM，拒绝二进制控制字符 |
| PDF | 校验 PDF 魔数，实际解析；拒绝加密、损坏、无文字扫描件 |
| 解析上限 | 500 页 PDF、200 万字符 |
| 文件名 | 最多 160 字符，拒绝路径分隔符和非法字符；存储名由服务器生成 |

同一知识库按 SHA-256 去重，不同知识库允许同一文件；同名不同内容用不同标识保存，不覆盖旧文件。API 不返回本地绝对路径。管理写请求沿用本机来源检查及 `X-Workbench-Request: 1`。

解析与嵌入在线程执行，取消为阶段/页/批次间协作式取消。一个正在运行的 PDF 页提取或 ONNX 批次不能立即强制杀死，但取消后不会提交新索引。这里没有 OCR、Office 解析、用户权限、多租户、复杂工作流或新的演示模式。

## 前端职责

| 代码 | 职责 |
| --- | --- |
| `frontend/src/types/knowledge.ts` | 文档、知识库、索引任务、证据与状态类型 |
| `frontend/src/api/knowledge.ts` | 请求适配、FormData、管理请求头、原文安全路径 |
| `frontend/src/stores/knowledge.ts` | 共享知识库目录、问答所选知识库、服务端上传限制 |
| `frontend/src/composables/useKnowledgeDocuments.ts` | 文档读取、仅有活动任务时轮询、切库请求版本校验、取消与离页清理 |
| `KnowledgeView.vue` | 页面协调、库操作、筛选条件 |
| `RetrievalPreview.vue` | 单模式检索、三路对比、同片段编号、局部请求取消与切库清理 |
| `KnowledgeUpload.vue` | 文件选择/拖放、前端限制与反馈 |
| `DocumentTable.vue` | 文档状态、真实进度、重试/取消/删除事件 |
| `EvidenceButton.vue` | 可复用证据抽屉、快照与现存原文状态 |

延续原来的中文字体、蓝色主操作、CSS 变量及深浅主题，未引入第二套设计系统。基础 Select/Dialog/Drawer/确认框来自 Element Plus，业务请求隔离与索引任务展示是本项目实现。文档列表采用普通表格，窄屏在表格内横向滚动；未为未经测量的大规模列表引入虚拟滚动。

## API 与数据

所有新接口前缀为 `/api/knowledge`。写操作带 `X-Workbench-Request: 1`。

| 方法与路径 | 功能 |
| --- | --- |
| `GET /knowledge` | 库目录、上传限制、嵌入模型说明 |
| `POST /knowledge` | `{name, mode: keyword或hybrid}` 创建 |
| `PATCH /knowledge/{kb}` | `{name}` 重命名 |
| `DELETE /knowledge/{kb}` | 异步删除库及其资料 |
| `GET /knowledge/{kb}/documents` | 文档与最新任务状态 |
| `POST /knowledge/{kb}/documents` | multipart，多个 `files` 字段，返回重复标识 |
| `POST /knowledge/{kb}/documents/{doc}/retry` | 幂等排队重试/重建；有活动任务不重复排队 |
| `POST /knowledge/{kb}/documents/{doc}/cancel` | 取消当前索引 |
| `DELETE /knowledge/{kb}/documents/{doc}` | 删除/重试清理 |
| `POST /knowledge/{kb}/search` | `{query, mode}`，返回证据与 empty/indexing/not_ready/no_match/ready 状态 |
| `POST /knowledge/{kb}/compare` | `{query}`，同一候选集的三路结果、排名细项和分阶段耗时；各路可独立返回 unavailable/error |
| `GET /knowledge/{kb}/documents/{doc}/evidence/{chunk}` | 原文可用性、完整片段、实际位置 |
| `GET /knowledge/{kb}/documents/{doc}/original` | 原始文件；已删除返回 410 |

原 `/query` 和 `/query/stream` 在 `context` 增加 `knowledge_base_id`。知识库不存在或组合模式冲突会拒绝请求。Retriever 只执行 `library_search`，组合路径才额外执行 `web_search`；即使 Planner 给出其他工具提示也不能绕过范围。

### 检索对比的读法

对比接口沿用正式问答的分词、BM25、向量阈值和 RRF 实现，一次读取有效候选片段、最多执行一次查询嵌入，分别返回 `keyword/semantic/hybrid` 结果，每路最多显示 6 条。语义路径失败时保留关键词结果，语义与融合返回 `error`，不会将关键词结果伪装成成功的融合检索。

- `documents[].ranking` 包含 `keyword_rank`、`semantic_rank`、`bm25_score`、`cosine_similarity` 和 `rrf_score`。每路取前 50 个候选，语义阈值为余弦相似度 0.35；融合为 `Σ 1/(60 + rank)`。旧 `score` 仍为归一化排名分数，保持原问答契约。
- `timings` 包含候选读取、关键词计算、查询嵌入与向量检索、融合排序、服务端总耗时，单位毫秒。未执行阶段为 null，失败的语义尝试仍记录耗时。计算共用，因此不能视作三次独立请求的速度比较，也不包含网络和浏览器渲染。
- 三列的“片段 N”由本次返回的稳定片段 ID 分配，只用于跨列核对；不是回答引用或逐句支持关系。不同模式分数量纲不同，不得直接比较数值大小或称为准确率。
- 切库、离页、停止等待会取消前端请求读取并丢弃晚到结果；本地 CPU 检索一旦在线程中开始，可能继续执行至结束。预览结果不持久化，重新检索使用当时的有效索引。

来源增加 `kind/knowledge_base_id/document_id/chunk_id/version/document_name/page/heading/start/end`；`page` 仅实际 PDF 页保留，其余不造页码。每轮执行维护稳定的引用编号映射；Generator 不再把同名文档的不同片段合成一个失去位置的来源。Critic 修订沿用该映射，最终答案、来源及历史由原有运行提交机制统一保存。

数据默认全部在当前项目的 `data/knowledge/`：

- `knowledge.sqlite3`：WAL，`libraries/documents/jobs/chunks`。原文版本是内容 SHA-256，片段 ID 由文档标识、版本、切分版本及位置序号稳定生成。
- `files/{随机文档ID}`：原始文件，无客户端路径参与拼接。
- `vectors/`：独立 Chroma，按嵌入/切分指纹分 collection，向量绑定库、文档和任务 generation。
- `models/`：本地下载缓存。

可使用 `AGENTICRAG_KNOWLEDGE_DIR` 和 `AGENTICRAG_EMBEDDING_CACHE` 改变新模块目录，不修改旧会话库或旧 Chroma。测试使用单独目录，语义比较仅共享只读模型缓存。

## 迁移、恢复与重建

新增库采用幂等 `CREATE TABLE/INDEX IF NOT EXISTS`，并记录 schema version 1；已有内部开发版缺少 `libraries.deleting` 时补列。原会话、来源快照、用户 `.env` 和项目检索库不需要迁移，也不自动导入私有文件。

队列在 SQLite 中持久化，单后台索引线程处理；重启时正在解析/切分/索引的任务标记失败并允许重试，尚未开始的任务继续排队；未完成删除继续重试。索引生成先写入新 generation，最后在 SQLite 事务中切换活动片段；失败不替换已有索引。检索过滤库 ID、已提交 generation 和配置指纹，因此不使用中间索引或混合向量空间。

当前只支持一个固定中文模型，模型、维度及切分版本均记录在元数据中。开发者更换模型/维度/切分实现时必须更新 `embedding.FINGERPRINT` / `parsing.SPLITTER`，并在页面逐文档点击“重建”。指纹不一致的旧索引不会参与查询；原文件与历史快照不被删除。没有提供任意模型热切换界面。

备份请停止当前服务后整体复制 `data/knowledge`（模型可重新下载），不要只复制正在写入的 SQLite 主文件。不要通过删除真实数据目录修复索引。

## 检索选择与已知限制

中文分词沿用已有二元分词；BM25 和真实语义候选经 RRF 融合，按稳定片段 ID 去重。切分按段落/句界尽量保持结构，每片最多 420 字符、相邻约 60 字符重叠，PDF 不跨页。语义查询由 Chroma 执行，范围仅包含当前库已提交的 generation。

固定比较可重跑：`.venv\Scripts\python.exe scripts/compare_knowledge.py`。结果写入 `.cache/knowledge-retrieval-probe.json`，比较固定资料在关键词、语义和融合模式下的排名与耗时。样本规模有限，仅用于检查检索路径；尚未建立覆盖实际业务的召回率或性能基准。

全量 BM25 候选仍在内存计算，适合当前个人本地规模；未验证大量文档、多进程、多用户并发或超大 PDF。PDF 提取和 ONNX 取消受单次同步调用边界限制。模型级事实核验、OCR、更强中文分词、海量索引与 reranker 均为后续议题。
