# 接口与存储

## 兼容与扩展

旧 `/query`、`/status`、`/tools`、`/sessions`、`/sessions/{id}`、`/sessions/{id}/cancel`、`/visualization/{id}`、`/requirements-audit` 保留，增加等价 `/api` 前缀。仅接受省略 mode 或 `mode=live`；`mode=demo` 返回 422。前端不再发送 mode。

`/tools` 同时是旧 API 与页面路径：浏览器 `Accept: text/html` 返回 SPA，其余客户端返回旧 JSON；`/api/tools` 永远返回 JSON。脚本调用旧 `/tools` 不应声明接收 HTML。

| 接口 | 变化 |
| --- | --- |
| POST /query | 保持完整 JSON；新增运行标识、结构化来源与元数据。此旧入口不消费客户端 run_id |
| POST /query/stream | 新增 POST SSE；body 支持 query/session_id/run_id/model_profile/context/images |
| POST /runs/{run_id}/cancel | 仅取消指定运行；返回 cancelled 及已有运行终态/result，解决完成抢先取消的竞态 |
| GET /sessions/{id} | messages 中有 id/run_id/result；附带 runs、trace，包含失败和取消运行 |
| GET /visualization/{id}?run_id=... | 可筛选一次运行的持久化事件 |
| GET /status | 模型档案含 configured、connection_verified、last_success_at；成功记录来自当前进程的实际回答，不主动探测 |
| GET /api/runs?search=&status=&offset=0&limit=30 | 分页查询摘要，不返回全部回答；limit 最大 100，返回 items/total |
| GET /api/runs/{id} | 单轮完整记录及持久化 events，未知 ID 为 404 |
| GET/POST /api/settings/providers | 列表/新增供应商；响应仅含 has_key，不含密钥 |
| PUT/DELETE /api/settings/providers/{id} | 修改/移除本机供应商；不删除历史记录 |
| POST /api/settings/providers/{id}/check | 请求模型列表，返回 ok/message/models；不创建付费 completion |
| PUT /api/settings/default-model | body: {profile_id}；影响后续请求默认模型 |

请求 context 只接收 thinking_mode/location/retrieval_mode/strategy，不能从浏览器注入 provider、api_key 或 model_config。图片 schema、最大长度、思考模式与模型档案均校验。不支持的参数返回 422；同会话并发/重复运行 ID 返回 409。运行后错误通过 error 事件传达，因为 HTTP 已经是 200。

## SSE 协议

```text
id: 5
event: delta
data: {"type":"delta","seq":5,"session_id":"...","run_id":"...","timestamp":0,"data":{"text":"回答增量","generation":1}}

```

空行结束事件。timestamp 是服务端 Unix 秒；seq 在单运行单调增加。POST 不做自动重连/重放。心跳是注释帧。客户端流式 TextDecoder 保留 UTF-8 跨字节状态，缓冲不完整 SSE 帧，处理同 chunk 多帧，缺少终态的 EOF 判为意外断流。

| type | 含义 |
| --- | --- |
| started | 最早提供运行 ID、会话 ID 和模式 |
| stage | node/stage_id/round/status/input/output/metadata/start/end/duration |
| tool | call_id、协议、参数、状态、结果摘要、耗时与错误 |
| retrieval_round | 实际检索重试序号与策略 |
| answer_start | 新生成轮开始，客户端清空上轮草稿 |
| sources | 本轮来源映射和已有证据片段，generation 关联生成轮 |
| transport | stream/buffered，区分真实增量与完整结果 |
| delta | 仅回答文本增量，generation 必须匹配当前轮 |
| notice / info | 可公开的系统提示与执行摘要 |
| completed | 最终 QueryResult，整体替换草稿，来源以最终结果为准 |
| error / cancelled | 本次终态，保留未完成草稿；不进入正常对话上下文 |

不保存每个 token 事件，避免 SQLite 写放大；存阶段、来源、工具、轮次与终态摘要，最终文本在消息/运行表。已生成失败草稿存入 run.result.answer。completed 持久化为精简成功标记，实时事件仍传完整 result。

SSE 队列有容量限制；客户端过慢会停止该轮，终态事件优先进入队列。连接已断开时仍可能只能通过历史记录核对。OpenAI SDK 禁用自动重试；不支持流的配置显式发送 buffered。OpenAI 兼容生成、路由及工具选择采用异步上下文关闭连接；Ollama/Xinference 和部分同步工具仍在线程中运行，取消只保证停止后续流程。

## SQLite 与迁移

供应商配置独立保存在 `data/settings/providers.sqlite3`，环境变量 `AGENTICRAG_SETTINGS` 可覆盖。providers 保存设置 JSON、保护后的 secret 和连接检查结果；preferences 保存默认模型。自动创建表，重复启动幂等。原 YAML 继续作为只读配置，不自动改写或导入凭据；新模型 ID 为 `managed:<provider UUID>:<model ID>`，不会覆盖文件配置 ID。

供应商 body：name、protocol（openai/deepseek/ollama/xinference）、base_url、api_key、clear_key、timeout_seconds、models。models 每项有 model_name/label/supports_vision/supports_streaming/enabled/max_tokens；同供应商模型 ID 唯一。OpenAI 兼容地址为 `/v1` 等基础地址；Ollama 为根地址，Xinference 为 `/v1`。远程仅 HTTPS，本机可 HTTP，拒绝 URL 中的用户凭据、query 和 fragment。修改时空 Key 保留原值，clear_key 显式清除。Ollama/Xinference 当前强制完整结果模式。

Windows secret 使用 DPAPI 用户级加密；其他系统为目录 0700/文件 0600 的本机明文存储。该库不适合作为跨用户凭据备份。保存不改变运行中的配置快照；配置更新使旧的实际生成验证失效。模型列表检测返回前比较连接配置，旧检测不能把新地址/Key 标为连接成功。

保留 `memory/session_memory.py` 旧实现供历史代码参考，RAG 主链已使用 `memory/sqlite_memory.py`。

- sessions：会话 ID 与创建时间。
- messages：每轮 user/assistant、run_id 与 payload；保存附件或回答元数据。
- runs：本轮状态、问题、起止、最终结果/失败草稿与错误。
- events：run_id + seq 联合主键，保存执行事件。
- turns：兼容已有 get_history/get_session 接口的问答投影；成功轮次与 messages 在同一事务更新。
- migrations：旧 JSON 文件路径的导入记录。

构造 SessionMemory 时创建缺失表与索引。遇到 `.json` memory_path，读取原 JSON，写入同名 `.sqlite3`；原文件不变。用来源路径+会话+索引哈希固定旧 turn ID，事务内写 migration 记录，重复启动不重导入。不是持续双向同步：首次导入后对旧 JSON 的追加不会再次自动导入。

可以主动执行同一迁移，命令可重复：

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe -c "from memory.sqlite_memory import SessionMemory; SessionMemory('data/memory/sessions.json')"
```

唯一局部索引约束同会话只能有一条 running；应用层也互斥。成功答案、消息、来源元数据和 success 在单事务提交。SQLite WAL + 10 秒 busy timeout 支持本机并发写入；没有吞吐压测或多进程运行协调。仅上下文限制最近轮次，持久历史不再截断。服务启动首次初始化系统时将遗留 running 标记 error；中断节点可能缺少 end 事件，不能伪造耗时。

备份在服务停止后复制 SQLite 与原 JSON；运行中备份应使用 SQLite backup API，不能只复制主文件而忽略 WAL。没有自动删库或自动回滚旧数据。新 schema 对已有初版 turns/runs/events 库执行 CREATE IF NOT EXISTS，旧 turns 补建 messages。

## 生产与安全边界

2026-09-18 前端完善未变更后端 API 或数据库结构，无需新的数据迁移。前端引用跳转复用 Generator 已有 `source_map[].citation_id` 与 `[Sx]` 约定，不持久化额外推断关系。供应商 422 校验复用 `detail[].loc/type/msg`，客户端只接受安全消息并保留字段路径；连接检查 HTTP 成功不代表业务成功，仍须判断 `ok`。

FastAPI 同源提供 SPA 与 API，无需跨域白名单。构建后启动服务，GET 已知前端路径返回 index；未知路径 404。默认 127.0.0.1，单 worker。若外接反向代理，关闭 SSE 响应缓冲，保持长连接超时；不需要 Nginx 才能本机运行。

`/providers` 是 SPA 页面。`/runs` 和 `/tools` 同时兼容 HTML 页面和旧 JSON 路由，`/api/runs`、`/api/tools` 始终为 API。供应商管理仅接受本机来源和本机 Host，写操作必须包含 `X-Workbench-Request: 1`，拒绝外站 Origin；这用于本机工作台的跨站防护，**不是公网身份认证**。API 参数错误不返回 Pydantic 原始 input，防止回显输入 Key。

`public_data` 递归去掉凭据键、model_config/raw_response，并对已知环境密钥与常见 URL token 做替换。检索排除配置、环境文件、测试及退役样例，并在分块前过滤已知密钥。用户请求与第三方内容仍可能包含任意敏感文本；此过滤不是通用 DLP。公开截图使用隔离历史和仓库公开资料，回答仍来自真实供应方。

`connection_verified` 不由模型列表检测设置，只在真实生成成功后设置。图片能力来自 provider/模型默认值或配置声明，不保证所有兼容供应方都实现视觉接口。只接受 openai/deepseek/ollama/xinference 提供方，拒绝 mock 和未实现提供方。完整结果和流式生成均禁止自动切换备用模型；模型失败进入错误终态。更严格的认证、媒体内容校验、会话分页和多进程任务队列属于后续改进。

## 演示模式退役

不删除原数据：`data/demo/`、`.cache/browser-demo/` 原地保留，正常服务没有读取入口。旧 `docs/demo-knowledge.md`、`docs/ui-concepts/`、`docs/screenshots/workbench-*.png` 及旧 metrics 属于历史样例材料，不作当前产品证据。新截图使用 `real-` 前缀。`AGENTICRAG_DEMO_DATA` 不再生效。

浏览器启动只将 `rag-session-live` 迁移为 `rag-session`（已有新指针优先），移除 `rag-mode`、`rag-session-demo`、`rag-session-live`。不导入旧演示数据库。若用户曾自行将演示数据复制到真实库，系统无法可靠辨识其来源，不会擅自删记录。

自动化夹具位于 `tests/workbench_fixtures.py`，只有测试服务导入；临时 SQLite/Chroma 与真实数据隔离。`tests/serve_real_smoke.py` 是人工执行的真实服务联调入口，读取现有模型档案，使用 `.cache/real-service-smoke/` 保存隔离记录；不会被 pytest 或 CI 自动启动。
