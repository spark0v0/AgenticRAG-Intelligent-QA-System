# 前端设计说明

## 核实结论

本轮开始时工作区已经有大量未提交修改，包括 `frontend/`、`api/workbench.py`、`memory/sqlite_memory.py`、`utils/execution.py`。这些代码被保留并继续完善，没有 reset 或删除用户数据。最初“只有 dashboard.html、轨迹只在内存”的观察适用于更早版本，不能作为本轮初始状态。

已实现的业务基础：路由、规划、工具检索、生成、规则评审；本地 HashEmbeddings + Chroma + 词法混合检索；工具注册、示例 stdio MCP、LangChain Runnable 适配。规则评分不是准确率；知识图谱来自配置。Dify 是 Python 包装，未发布插件。

本轮工作重点：补完独立 Vue 工程、真实接口接入、流式生命周期、运行隔离、事务持久化、核心验证、可运行交付及文档。不能把原有后端研究能力全部归为本轮前端个人实现。

## 选型

| 技术 | 对应需求与取舍 |
| --- | --- |
| Vue 3 / script setup / Composition API | 按业务职责组合状态、展示与资源生命周期 |
| TypeScript | SessionSummary、Message、QueryRequest/Result、Source、ToolCall、ExecutionEvent 判别联合 |
| Vite / Vue Router | 独立开发代理、生产构建；页面路由懒加载 |
| Pinia | 多会话、当前会话、处理模式、模型、运行状态和执行记录 |
| Element Plus | 复用表单、输入、选择器、数字输入、开关、对话框及移除确认；供应商生命周期、运行分析、会话和流消费由本项目实现 |
| Fetch / ReadableStream | POST 同时提交问题与图片，无需 EventSource 的额外任务创建连接 |
| markdown-it / DOMPurify / highlight.js | Markdown 解析、安全净化和有限语言高亮 |
| SCSS / CSS 变量 / @lucide/vue | 响应式样式、主题与维护中的图标库；旧 lucide-vue-next 安装时已被标记 deprecated，改用官方后继包 |
| SQLite | 标准库即可支持事务、唯一约束和运行历史；Chroma 保留检索职责 |
| Vitest / Vue Test Utils / Playwright | 流与状态逻辑、Markdown 组件及少量完整业务冒烟 |

不用 Vue Flow：当前需求是执行记录，不是工作流编辑，时间线可直接表达真实节点与多次生成。使用已有 npm 锁文件，避免双包管理器。无性能基线，不引入虚拟列表或声称优化百分比。

## 目录和职责

```text
frontend/src/
  api/client.ts              Fetch、HTTP 错误与 API 路径
  api/sse.ts                 UTF-8 解码、SSE 帧重组、终态和身份校验
  api/settings.ts            供应商增删改、连接检查与默认模型
  types/index.ts             接口类型、运行状态和事件判别联合
  stores/workbench.ts        会话缓存、历史恢复、运行资源与并发控制
  composables/useAutoScroll.ts  是否跟随与回到底部
  composables/useClipboard.ts   复制反馈和计时器清理
  composables/useRunAnalysis.ts 节点归并、耗时投影、安全来源链接
  components/AppSidebar.vue     会话搜索和导航
  components/ChatComposer.vue   输入、中文 IME、模型与附件选择
  components/MessageBubble.vue  用户/助手消息与运行入口
  components/MarkdownContent.vue  安全 Markdown、代码高亮与复制
  components/ExecutionPanel.vue  按运行聚合节点、来源与工具调用
  views/ChatView.vue            问答布局、详情展开、滚动容器
  views/ToolsView.vue           只读工具 schema 与筛选
  views/SystemView.vue          只读模型能力和环境信息
  views/ProvidersView.vue       供应商表单、模型发现、能力声明与默认选择
  views/RunsView.vue            分页运行索引、瀑布选择、证据、回答与导出
  router/ styles/
```

没有额外封装只转发 store 方法的 useChat/useStream：目前只有一个问答入口，流协议解析已从状态仓库分离，继续包一层没有实际复用价值。未来增加嵌入式聊天入口时再抽取。

## 状态所有权

- 服务端权威数据：最终答案、来源、工具结果、评审、运行终态与阶段起止记录。客户端 completed 事件替换整条回答，刷新结果与最终记录一致。
- Pinia 共享状态：处理模式、模型选择、会话缓存、当前 ID、每会话草稿/附件/消息/事件。busy 和所选来源等由 computed 派生。
- 非响应式资源：按 run_id 索引的 AbortController、文本缓冲与 timer，避免代理浏览器资源。
- 组件局部状态：搜索条件、详情 tab、导航展开、文件读取、滚动跟随。
- localStorage：主题、所选模型/处理模式、当前真实会话 ID；不保存 Key、图片或回答文本。启动时移除旧模式状态，只迁移旧真实会话指针，模型不存在时使用后端默认档案。未提交的输入刷新后不会自动恢复；失败/取消的已提交输入可从后端恢复。

运行转换：idle → submitting；只有收到 delta 才进入 streaming；完整结果模式维持 submitting；完成、错误、取消分别进入 success/error/cancelled。再次发送建立全新 run_id。提交互斥绑定会话，不阻止其他会话运行。

## 生命周期和竞态

1. 发送前生成 session_id、run_id，快照请求参数并创建该轮用户/助手消息。禁止同一会话重复发送。
2. SSE envelope 校验 run_id/session_id；seq 去重。异步闭包始终写所属 conversation，不读取“当前会话”作为结果目标。
3. 切换会话保留后台执行。未完成会话立即加入侧栏，可返回停止；历史读取用 AbortController 与版本号丢弃旧响应。
4. 增量 60ms 批量追加；每次 answer_start 清空上一生成轮草稿。completed 采用后端最终回答与来源，防止 Critic 修订拼接。
5. 取消先调用 run 取消接口，再中断读取。若完成抢先提交，以取消接口返回的已保存 success 结果为准。确认失败提示刷新核对，不声称供应方停止计算。
6. finally 只清理本 run 的资源，并检查 activeRun 是否仍是该 run。失败/取消恢复输入；禁止自动重放请求。
7. App 卸载清理请求；图片 FileReader 在组件卸载时 abort。采用 data URL 直接预览，无对象 URL 需要撤销，图片内容只序列化进当前请求与后端附件历史。

## 渲染与交互

Markdown 禁用原始 HTML，再经 DOMPurify 净化；禁止远程图片/iframe/style/form，避免答案中的追踪图片。安全来源链接只接受 http/https，新页面链接带 noopener/noreferrer。流动草稿暂缓代码高亮，终态后只高亮注册的 JS、TS、Python、JSON、CSS 语言。

路由与执行详情懒加载。用户向上阅读时停止滚动跟随，新增文本不抢位置；回到底部重新跟随。输入处理 isComposing 与 229，Shift+Enter 保留换行。图片每轮最多 4 张，每张不超过 4MiB，类型 PNG/JPEG/WebP/GIF，与 API schema 一致。服务端还校验 MIME/data URL 与 base64 长度；本轮不做完整图片内容解码检测。

时间线使用实际 stage_id 聚合开始/结束事件，每个生成轮保留独立 round。工具注册状态与本次执行状态分开；真实 duration_ms 来自后端 perf_counter，不从一个时间戳推测。仅显示已发生节点，未发生节点不伪装成等待流程。事件是系统执行摘要，不展示或虚构模型内部思维链。

## 性能边界

当前小规模会话搜索在内存过滤；后端历史接口会读取全部消息，暂不分页。当前长会话测量在 `frontend/test-results/evidence/history-metrics.json`，包含导航到 60 条消息可见的总耗时和输入确认时间，不能当作纯 Vue 渲染耗时。真实模型与夹具数据分开记录，最新构建体积见验证记录。

## 本轮界面完善

采用炭黑导航、白色工作区、钴蓝主操作；检索节点使用青色、评审使用珊瑚色，成功/失败有独立状态色。字体优先微软雅黑/PingFang，避免外部字体请求；字号固定，正文 14～16px，页面标题 23～27px。CSS 变量维护浅色/深色主题，Element Plus 组件使用同一主色。侧栏固定宽度、输入区停靠、消息限制阅读宽度；窄屏导航收起，运行索引转为可横向滚动的列表。新增设计样式集中在 `styles/workspace.scss`，原有消息/Markdown/详情基础样式仍在 `main.scss`。

没有新增 UI 框架或图编辑依赖。Element Plus 负责成熟表单与弹窗的基础交互，业务组件负责配置映射、错误恢复与提交状态。常用问题只填入草稿。供应商检测仅请求模型列表，`check_ok` 不等于生成成功；系统页 `connection_verified` 仍只来自本次进程中完成的真实回答。

## 新页面的状态边界

供应商数据和表单草稿属于页面局部状态，不进入 Pinia/localStorage。Key 仅停留在表单内存与保存请求中，保存/关闭后清空；已保存 Key 只返回 has_key。后端更改配置后刷新共享模型列表，不重建正在运行的问答系统。每个运行仍使用已经捕获的配置字典；旧配置的回答成功不会把新配置误标为已验证。

运行分析通过 `/runs` 分页查询摘要，通过 `/runs/{id}` 获取单轮详情；URL query 保存所选 run，支持刷新和从消息跳转。搜索防抖 250ms；列表和详情各有 AbortController/版本号，旧响应不能覆盖新选择。进行中的选中运行每 2 秒刷新，离页清理轮询和连接。瀑布位置来自真实 started_at，条长来自 duration_ms；小于一个像素的节点设最小可见宽度，数字耗时仍是真实值。未结束节点不估造耗时，视图不重放 token。

来源展示后端证据，不推断句子级引用。节点期间的工具通过时间区间归属，只称「节点期间的工具调用」，不捏造父子 ID。导出是单轮已脱敏服务端记录，仍包含问题、回答和证据，需自行确认是否适合分享。
