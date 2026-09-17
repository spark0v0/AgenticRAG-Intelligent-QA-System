# 简历与面试材料

以下描述对应仓库实现。投递前请亲自完成操作脚本并阅读代码，按自己参与、理解和验证的范围修改，不把 AI 辅助产出的全部代码描述为独立原创。

## 简历版本

**项目名称：AgenticRAG 智能问答与检索工作台**

项目介绍：基于已有 Python AgenticRAG 后端完善的 Vue 3 AI 应用，围绕多轮问答、检索来源、执行观察与历史恢复建立可操作的中文工作台，用于个人学习与项目展示。

技术栈：Vue 3、TypeScript、Vite、Pinia、Vue Router、Element Plus、SCSS、Fetch SSE、markdown-it、DOMPurify、highlight.js；FastAPI、AsyncOpenAI、SQLite、Chroma；Vitest、Vue Test Utils、Playwright、GitHub Actions。

- 基于 Vue 3、TypeScript 与 Element Plus 实现问答、供应商管理及运行分析工作台，统一浅深主题和窄屏布局；实现动态模型表单、连接检测、能力配置及默认模型切换，区分凭据配置、接口连接与生成成功状态。
- 使用 POST Fetch SSE 消费供应方真实增量，通过 UTF-8 分块解码、事件重组、session/run 身份校验及 60ms 批量更新，处理断流恢复、会话竞争和 Critic 多轮草稿替换。
- 以 Pinia 管理会话与运行状态，结合 AbortController 和后端任务取消，处理重复提交、后台会话执行、完成与取消竞争，失败时恢复输入且不自动重放请求。
- 将后端真实节点事件映射为可选择的耗时瀑布，支持服务端分页筛选、节点输入输出与工具详情、证据来源回看及单轮 JSON 导出；配合 SQLite 事务恢复最终回答和元数据，以少量核心冒烟验证流程。

不写用户量、并发量、准确率、商业上线经历或性能提升百分比。GitHub Actions 当前可写“配置工作流”，未推送运行前不能写“云端流水线通过”。真实联调范围以 `verification.md` 为准，不把测试夹具耗时当作模型性能。

## 亮点与证据

| 亮点 | 代码入口 | 操作路径 | 验证证据 |
| --- | --- | --- | --- |
| 组件与页面设计 | `frontend/src/components/`、`views/`、`styles/main.scss` | `/chat`、`/tools`、`/system`，切换窄屏和主题 | `tests/browser/workbench.spec.ts`、`docs/screenshots/real-*.png` |
| SSE 协议与终态 | `frontend/src/api/sse.ts`、`stores/workbench.ts`、`src/models/client.py` | 发起真实问答，观察增量，停止或刷新 | `frontend/tests/unit/core.test.ts`、`tests/test_workbench_smoke.py`、真实联调 metrics |
| 会话与异步隔离 | `stores/workbench.ts`、`src/api/workbench.py` | 运行时切换会话，回到原会话停止，手动重试 | Vitest 竞态用例、Playwright 取消重试和恢复 |
| 可追踪运行与存储 | `ExecutionPanel.vue`、`src/utils/execution.py`、`src/memory/sqlite_memory.py` | 回答下方执行详情，切换来源/工具，刷新回看 | SQLite 迁移/取消后重试测试、历史一致性验证 |
| 可操作的供应商配置 | `views/ProvidersView.vue`、`api/settings.ts`、`src/api/providers.py` | `/providers` 添加/编辑、检查连接、设默认 | `test_provider_settings.py`、Playwright 表单冒烟、新供应商真实问答 |
| 运行分析交互 | `views/RunsView.vue`、`composables/useRunAnalysis.ts` | `/runs` 搜索、选择节点、证据、导出、回到会话 | `workspace-runs.png`、`workspace-evidence.png`、`workspace-metrics.json` |

## 面试讲解

**为什么选这些技术？** Vue 3/TS 对应岗位与复杂交互；Pinia 管共享业务状态，Router 做页面懒加载。Element Plus 提供表单、选择器、开关和弹窗，业务配置映射和异步逻辑由项目实现。CSS 即可实现真实耗时瀑布，无需 Vue Flow 或工作流编辑。沿用 npm 锁文件，避免迁移包管理器带来额外成本。

**组件怎么拆？** App 负责导航和连接初始化；ChatView 负责布局和滚动；Composer 管文件读取与输入；MessageBubble 管一条消息；MarkdownContent 管安全渲染；ExecutionPanel 聚合一次运行。API 适配不放组件。

**Pinia 管什么？** 模型/处理模式、会话列表、每会话草稿、消息、事件和 activeRun。搜索词、详情 tab、导航展开属于局部状态。AbortController 和计时器放非响应式 Map；busy、当前消息和来源通过 computed 派生。

**TypeScript 如何约束？** QueryRequest/Result、Message、Source、RunRecord 等类型约束接口；ExecutionEvent 以 type 为判别字段，让 switch 内 data 自动收窄。网络输入仍需运行时 envelope 检查，TS 不能替代后端校验。

**为什么使用 POST SSE？** 请求携带模型、问题、图片和上下文，Fetch 能用 POST 加 ReadableStream；不必先创建任务再用 EventSource 订阅。代价是自行处理解码、帧重组、取消和断流，不自动重连重发可能计费的请求。

**分块与终态？** TextDecoder stream 模式保留跨 chunk UTF-8 状态，缓冲到空行才解析事件；同 chunk 可含多个事件。session/run 校验归属，seq 去重；EOF 无终态就提示中断。草稿按 generation 分轮重置，最终回答整体替换，数据库提交值是权威结果。

**取消与竞态？** 一个会话只能有一轮 activeRun；切换会话时闭包继续写原 conversation。历史加载用版本号和 AbortController 防旧响应覆盖。停止按 run_id 发往后端再终止读取；成功提交可能先于取消，采用服务端已提交结果。AsyncOpenAI 关闭连接，但同步工具线程与供应方是否停止计算/计费不能保证。

**安全与渲染性能？** Markdown 禁止原始 HTML，再经 DOMPurify；禁用远程图片，来源只允许 http/https。增量 60ms 合并，草稿暂缓高亮，终态后仅高亮注册语言。页面及详情懒加载。60 条长消息测量正常后没有加入虚拟列表；测量值见验证记录，不声称百分比优化。

**可视化依据？** stage_id/call_id 标识实际执行，round 区分重新生成；起止和 duration_ms 来自真实边界。前端按 ID 合并状态，仅显示经过的节点。质量分数标记“评审参考”，执行摘要不是模型内部思维链。

**测试风险？** 覆盖 SSE 中文分块、异常 EOF、错误恢复、跨会话隔离、草稿替换、安全 Markdown、取消竞态；Python 验证事务、JSON 幂等迁移与上游关闭；浏览器串联关键流程。不追求覆盖率数字。

**限制与后续？** 单进程本机应用、无鉴权；历史未分页、图片 base64 存储；部分供应方完整返回，同步外部工具只能协作取消；图谱为配置关系，MCP 为示例，Dify 未发布。优先图片文件化与历史分页，再按实际瓶颈考虑任务队列和更多供应方适配。

## 贡献边界

新增可讲解点：供应商表单的 Key 不回填，不放 localStorage/Pinia；留空保留与显式清除分开。后端管理路由限本机并拒绝跨站写入，Windows 使用 DPAPI。运行页列表与详情分别用版本号/AbortController 管竞态；选择活动运行时有 2 秒轮询，离页清理。图形宽度来自真实节点耗时，界面状态不能伪造验证成功。

已有后端：智能体划分、规则路由/规划/评审、HashEmbeddings + Chroma + 词法检索、工具注册及 LangChain/Dify 包装。

本次完善：真实路径收敛、Vue 工作台与响应式设计、类型及运行状态、真实 SSE 与异步关闭、执行记录和事务持久化、迁移兼容、关键验证及求职材料。不要将已有算法、外部 SDK 或组件库能力全部归为自己实现。
