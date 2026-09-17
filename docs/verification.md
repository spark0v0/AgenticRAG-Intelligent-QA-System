# 实际验证记录

日期：2026-09-18（Asia/Shanghai）。环境：Windows / PowerShell、Node 24.19、npm 11.6、Python 3.13、系统 Chrome。下列结论来自本次本机执行，不代表 CI 云端或所有供应方均通过。

## 项目核实

| 类别 | 代码结论 |
| --- | --- |
| 已有可用基础 | Vue 3/Pinia/Router 工程、SSE 协议、SQLite 存储；已有 RAG 智能体与 Chroma 混合检索、工具注册、规则评审 |
| 本轮修复 | 移除演示产品路径/模拟生成/模型错误伪成功；真实模型状态、异步连接关闭、模型选择一致性、UI 布局与元数据回看 |
| 可直接接入 | 配置中的模型档案、工具列表、会话历史、运行事件、来源、原有 API 与 `/api` 别名 |
| 仍有缺口 | 知识库管理、工具/模型配置写入、复杂图谱与 Dify 发布，没有虚构管理控件 |

## 核心检查

| 实际执行 | 结果与覆盖 |
| --- | --- |
| `npm run lint` | 通过，src ESLint |
| `npm run format:check` | 通过，src Prettier |
| `npm run build` | vue-tsc 类型检查与 Vite 生产构建通过 |
| `npm run smoke` | 7 项通过：中文 UTF-8 分块/多帧、缺终态与身份不匹配、安全 Markdown、跨会话与草稿替换、断流恢复、旧模式指针迁移、取消完成竞争 |
| Python 核心冒烟 | 4 项：JSON 幂等迁移、不破坏原文件；取消首轮并重试及最终元数据；实际 SDK + MockTransport 增量/关闭；退役 mock 提供方不得成功 |
| 原有 Python 相关用例 | 参数校验、工具超时、DeepSeek 图片拒绝、视觉附件链路，共 4 项；生成回答使用测试目录夹具，非视觉模型实测 |
| Playwright | 2 项通过：问答/取消/重试/恢复/来源/工具筛选/SPA 刷新/390px 窄屏；60 条长消息恢复、编辑及回到底部 |
| 正常启动与代理 | 8000 生产页面及 5173 `/api/status` 实际可访问；返回 live、3 个模型档案、6 个工具 |

Python 共执行上述 8 个不同用例，没有跑全量算法评估或付费批量测试。测试模型数据仅从 `tests/` 注入；浏览器服务使用系统临时 SQLite/Chroma，正常运行不导入测试模块。

过程中发现并修复：Element Plus 默认宽度覆盖导致停止按钮被遮挡；读取系统状态时不必要地初始化模型 HTTP 客户端；演示键残留；模型错误被当作正常答案；普通请求自动尝试备用模型。系统 pytest 临时目录权限异常时改用新的 `.cache/pytest-*` 专用目录，没有清理原目录。

## 真实服务联调

通过 `tests/serve_real_smoke.py` 读取现有模型配置，使用 `.cache/real-service-smoke/` 隔离 SQLite/Chroma；检索范围限定仓库 README 和 src，未使用用户私人文档作为截图证据。脚本不会被 CI 自动执行。

- **DeepSeek V4 Pro / deepseek-v4-pro**：一次真实检索问答完成。实际经过 Router → Retriever → Generator → Critic，3 轮检索、1 轮生成、6 个结构化来源。没有为了截图替换模型输出。
- 问题：“用三点概括本地资料中 AgenticRAG 的核心模块，标注来源，回答不超过150字。”
- 浏览器从发送到首次可见增量 **22627ms**，到输入重新可用 **23975ms**。包含网络、工具选择、检索、供应方等待、传输与浏览器交互，不是纯模型 TTFT 或纯 Vue 渲染耗时。
- 最终文本与 SQLite 恢复值一致；刷新历史恢复通过。回答内容仍需人工核实，不能从一次调用推断准确率。
- 第二次真实请求在增量出现后停止，后端保存 `cancelled`，输入恢复。未自动重试该请求，未验证供应方内部是否停止计算/计费。
- `mode=demo` 返回 422；真实页面没有演示切换。页面脚本错误和控制台 error 记录为空。

自动截图读取已关闭 SSE 响应体曾失败；随后通过已保存运行补取证据，没有重新发送第一轮问答。记录见 `screenshots/real-service-metrics.json`。

## 界面与性能

真实截图：

- [问答与执行时间线](screenshots/real-workbench-desktop.png)
- [来源与证据](screenshots/real-sources.png)
- [窄屏问答](screenshots/real-workbench-mobile.png)
- [欢迎界面](screenshots/real-welcome.png)
- [工具中心](screenshots/real-tools.png)
- [系统概览](screenshots/real-system.png)
- [真实取消](screenshots/real-cancelled.png)

检查桌面 1440×1000 与窄屏 390×844：页面无横向溢出，输入/停止按钮可操作；另在最新生产构建检查了 320px 宽度及主题切换，输入操作区仍在视口内、无页面脚本错误。代码和模型表允许各自横向滚动。截图由页面直接截取，已目视检查。旧 `workbench-*.png` 属于退役演示版本，保留但不用于当前验收。

最近生产构建（十进制 kB）：入口 JS 134.23 / gzip 52.22，Chat 懒加载 JS 313.83 / gzip 118.88，执行详情 6.08 / gzip 2.63；工具 2.87、系统 3.03。入口 CSS 22.47，Chat CSS 26.84。

长会话夹具：60 条消息，其中 30 条回答各 2445 字符。导航到全部消息可见 378ms，填写输入并确认 22ms；包含自动化调度，不作为纯渲染耗时或通用性能保证。文件在 `frontend/test-results/evidence/history-metrics.json`。夹具首增量 853ms 不能当作公网模型指标。没有基线对照或提升百分比，也没有因此引入虚拟列表。

## 未验证与限制

- Ollama、Xinference、豆包视觉、真实天气/网络搜索、完整 Dify 发布未进行本轮外部联调。图片链路已实现并以隔离夹具验证，不声称真实视觉识别已验收。
- 本次真实问答没有触发 Critic 再生成；前端多轮草稿替换由 Vitest 验证。更多真实修订和外部故障组合留作后续。
- GitHub Actions 已配置，未推送或远端运行。没有负载压测、商业部署或精度评价。
- 本机单 worker；尚无认证。Chroma 首次索引初始化同步执行，历史全量加载、图片 base64 存储适合当前规模，后续应分页和媒体文件化。
- OpenAI 兼容请求取消会关闭异步连接；同步工具和 Ollama/Xinference 在线程内运行，可能持续至超时。前端 AbortController 不能证明上游模型停止计算。
- JSON 是一次幂等导入，不做后续双向同步；旧记录缺失的来源/轨迹无法补造。原始数据和退役样例保留，没有 reset 或清库。
- 规则评审、HashEmbeddings、配置式图谱、示例 MCP 属于当前实现边界，能力审计表不能替代实际验证。

P2 缺口和最小接口建议见 `roadmap.md`。优先维护可靠问答与存储，再按实际需要扩展管理能力。
