# 测试与开发检查

## 前端

在项目根目录运行：

```powershell
npm --prefix frontend run lint
npm --prefix frontend run format:check
npm --prefix frontend run smoke
npm --prefix frontend run build
```

构建包含 `vue-tsc` 类型检查。Vitest 覆盖 SSE 中文分块与异常断流、会话隔离、取消和草稿替换、Markdown 安全渲染及知识库范围恢复。

## 后端

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_workbench_smoke.py tests/test_provider_settings.py tests/test_agent_upgrade.py tests/test_knowledge_smoke.py -q
```

核心检查覆盖事务持久化、JSON 幂等迁移、供应商设置、Tavily 请求适配、知识库上传与重复识别、跨库隔离、任务恢复、重建失败和删除一致性。模型与网络调用使用隔离夹具，不默认消耗付费配额。

Windows 系统临时目录不可用时，指定新的工作区临时目录：

```powershell
$testRoot = Join-Path (Get-Location) ('.cache/pytest-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest tests/test_knowledge_smoke.py -q --basetemp=$testRoot
```

## 浏览器核心流程

```powershell
cd frontend
$env:WORKBENCH_PYTHON = (Resolve-Path ..\.venv\Scripts\python.exe).Path
$env:PLAYWRIGHT_CHANNEL = 'chrome'
npm run smoke:browser
```

测试服务使用 `tests/browser_server.py` 和临时数据库，覆盖会话、取消、来源、供应商表单、运行分析及知识库上传到引用的流程；其中长会话夹具输出渲染与滚动基线。不要占用测试端口 8010。无 Chrome 时安装 `npx playwright install chromium` 并移除 `PLAYWRIGHT_CHANNEL`。

额外运行真正经过 Vite 的接口与交互回归（需要空闲端口 5179）：

```powershell
$env:WORKBENCH_VITE = '1'
npm run smoke:browser
Remove-Item Env:WORKBENCH_VITE
```

此命令启动临时后端 8010 和 Vite 5179，检查知识库、供应商、会话、运行、SSE 与原文链接，以及首轮取消刷新、手动换库重试、库被删除的提示、上传反馈归属和删除焦点。默认命令使用构建后的 FastAPI 页面；两条路径均用同一份隔离模型夹具，不能用其耗时代表真实供应商。

截图与结果写入 `frontend/test-results/`，不进入源码目录。若浏览器临时目录受限，可将当前终端的 `TEMP` 和 `TMP` 指向项目 `.cache/browser-temp`。

## 检索比较

```powershell
.\.venv\Scripts\python.exe scripts/prepare_embedding.py
.\.venv\Scripts\python.exe scripts/compare_knowledge.py
```

比较脚本使用已下载的真实 BGE 模型，在隔离数据库中对固定资料执行关键词、语义和混合检索，报告写入 `.cache/knowledge-retrieval-probe.json`。小样本用于观察排序和路径是否可运行，不能作为召回率或性能提升结论。

## 外部服务检查

真实回答模型与 Tavily 需另行配置，可在界面手动提交少量问题并检查来源、事件和历史一致性。连接检查只验证模型列表接口；自动化夹具通过不代表真实供应商联调成功。外部请求可能消耗账户配额。

## 持续集成

`.github/workflows/workbench.yml` 执行前端静态检查、核心单元测试、构建、Python 测试及 Playwright 流程，失败时可下载运行产物。执行结果以对应 GitHub Actions 运行记录为准。

## 本地回归记录（2026-10-05）

环境：Windows、项目自身 `.venv`（Python 3.13）、Node 24.19、Chrome 154；数据全部使用临时数据库与测试资料。未调用付费模型或 Tavily，未在用户真实历史库上做迁移试验。

| 检查 | 结果 |
| --- | --- |
| ESLint / Prettier / vue-tsc + Vite build | 通过 |
| Vitest 核心与回归 | 15 项通过 |
| Python workbench / knowledge / agent upgrade / providers | 23 项通过（20 + 3 分批运行） |
| FastAPI 构建页面 Playwright | 6 项通过 |
| Vite 5179 → 临时 FastAPI 8010 | 2 项通过 |

覆盖首次取消及失败快照、旧 SQLite 增量迁移与重复初始化、快照字段白名单、库与会话切换、手动重试、取消完成竞争、终稿来源一致性、HTML 代理响应、文档动作契约、反馈归属与焦点。浏览器核心流程覆盖桌面 1440px 与窄屏 390px；知识库截图在 `frontend/test-results/production/`，问答截图与性能原始记录在 `frontend/test-results/evidence/`，均由 Git 忽略。

长会话夹具一次本机测量：60 条消息，30 条回答，每条 5228 字符并含 60 行 TypeScript。导航到历史可见 527ms；数据解析完成到 Vue/Markdown DOM 提交 363.5ms；含两帧等待的渲染窗口 388.3ms；记录到一个 355ms 主线程长任务；输入确认 32ms（含自动化开销），滚动至两帧后 7.5ms。初次批量恢复会短暂阻塞主线程，当前夹具恢复后的输入与回到底部通过。此为基线，不代表所有设备表现，也不是优化前后对比；本轮未引入虚拟列表或新渲染策略。

构建产物：主 JS 149.60kB（gzip 57.76kB），Markdown 模块 182.48kB（gzip 73.55kB），以 Vite 输出的十进制 kB 计。60ms 增量批量更新及流结束后高亮为原有能力，本次未将其计算为新增优化。

限制：真实供应商流式、上游计算是否中断、其他浏览器和线上 CI 未在本轮验证；已配置工作流不等于已有远端通过记录。客户端未发送/尚未被服务端接受的请求不属于已持久化运行，刷新不能恢复其草稿或选项。旧记录缺失的原始参数无法补造；只能提示确认并参考已有结果恢复。Python 检查存在 Starlette/AnyIO 兼容别名弃用警告，不影响本次结果。


## 界面调整检查（2026-10-05）

范围：导航、问答输入区、检索范围控件、知识库布局及全局明暗主题；复用现有业务逻辑，没有更换检索算法或新增模型调用。

- `npm run lint`、`npm run format:check`、`npm run build`（含 vue-tsc）通过；既有 Vitest 15 项和 Playwright 6 条流程通过。
- 使用 Edge 和临时后端数据库检查 1440×1000、390×844 页面。问答、知识库、运行分析、工具、供应商及系统页在窄屏无页面级横向溢出；文档表格保留容器内横向滚动。
- 通过 Vite 5179 连接隔离后端 8010，实际完成文本上传、索引、知识库问答和时间线查看；检查检索范围单选与手机导航的打开、Escape 收起及焦点恢复。浏览器未捕获页面脚本异常。
- 检查浅色、深色问答界面和桌面执行面板，截图保存在 Git 忽略目录 `.cache/ui-refresh/`。截图中的模型、文档与回答为隔离测试夹具，不代表真实供应商回答或性能结果。
- 本次未调用真实回答模型或 Tavily，未增加测试依赖或重复运行 Python 算法测试。移动端使用浏览器视口模拟，未进行真机键盘和触摸测试。


## 蓝白主题与布局检查（2026-10-07）

本轮重新整理中性灰阶、蓝色强调与深色主题，调整问答输入和检索选项层级、知识库横向分组与文档工作区、工具卡片及运行分析容器。业务接口与 AI 检索算法沿用现有实现。

- ESLint、vue-tsc、Vite build、Prettier 检查通过，既有 Vitest 15 项和生产构建上的 Playwright 6 条核心流程通过。
- 通过 Vite 5179 → 隔离后端 8010 检查创建知识库、上传文档、索引状态、知识库问答与执行面板；浏览器未记录页面脚本异常。
- 检查 1440×960 桌面与 390×844 窄屏的问答、知识库、运行分析、工具、模型供应商和系统页，没有页面级横向溢出。另检查浅色/深色主题、手机导航 Escape 和焦点恢复。文档表格与知识库分组允许容器内部横向滚动。
- 截图及一次性视觉检查脚本保存在 Git 忽略目录 `.cache/ui-blue/`，图中资料和回答属于隔离夹具；不包含用户配置和凭据。
- 未请求真实供应商或 Tavily，未新增依赖和测试框架。窄屏检查使用浏览器模拟，尚未覆盖手机真机的软键盘行为。


## 字体与内容布局检查（2026-10-08）

参考 Linux DO 的通栏导航、列表结构与阅读密度，调整问答首页、侧栏、知识库分类、工具列表、消息阅读区及亮暗主题。中文使用本地 Noto Sans SC Variable，英文及数字使用本地 Inter；字体许可证随构建分发。

- ESLint、Prettier、vue-tsc / Vite build 通过；现有 Vitest 15 项及生产构建上的 Playwright 6 条核心流程通过（27.8 秒）。覆盖上传与引用、取消、范围恢复、重试、历史、多会话、供应商表单和长消息滚动，未新增测试框架或 Python 算法测试。
- Vite 5179 连接隔离后端 8010 完成创建知识库、上传索引、问答和执行详情查看；检查 1440×960、390×844 下的六个页面、明暗主题及移动导航 Escape / 焦点恢复，没有页面级横向溢出或页面脚本异常。额外检查问答页 320px 和 768px 布局；320px 的模式与模型控件改为分行。
- 最后复核发现空白会话被消息自动跟随逻辑滚到底部：已将跟随限定到含消息会话，新建会话从顶部显示。重新构建、Lint 以及问答 / 长历史两条相关流程通过；320px 回归确认欢迎标题在视口内、scrollTop 为 0，正式页面也复核通过。
- 浏览器字体检查确认中文使用自托管字体。一次开发页面加载记录 11 个 WOFF2 请求，响应体合计 634,324 字节；完整生产字体资源 99 个、合计 4,555,472 字节，按 unicode-range 使用时加载，不等于首屏全部下载。此为字体体积记录，不是性能提升结论。
- 新增固定版本的字体资源依赖 `@fontsource-variable/noto-sans-sc@5.3.0`，Inter Latin 文件 48,256 字节。安装检查发现现有依赖审计提示，在原有版本约束内更新 DOMPurify 3.4.15 → 3.4.16、source-map-js 1.2.1 → 1.2.2；更新后 npm 审计报告 0 项，Markdown 核心测试随上面的验证通过。
- 截图、一次性检查脚本和字体原始记录位于 Git 忽略目录 `.cache/ui-forum/`；图中问答、模型与资料来自隔离夹具。正式服务仅检查页面加载，没有提交真实模型或 Tavily 请求。
- 窄屏为浏览器视口模拟，未验证手机真机软键盘；外部供应商生成及线上部署不属于本轮验证。字体首次加载增加资源传输，加载失败时使用系统字体回退。

## 交互细节检查（2026-10-11）

保留当前视觉风格，重点检查键盘导航、局部错误反馈和知识库表单恢复。

- 窄屏导航使用 `inert` 隔离背景，支持 Tab / Shift+Tab 循环、Escape 关闭、点击当前路由收起，以及切换桌面宽度后清理遮罩。新增主内容跳转入口，隐藏图片输入不参与键盘导航。
- 历史刷新使用独立加载和错误状态，不再把该操作失败显示为整个服务断线；失败保留已有列表，支持重试。会话搜索和文档筛选可清空并返回输入焦点。
- 知识库创建失败在弹窗内显示错误、保留输入；展开动画不抢走用户已操作的控件焦点。创建成功直接采用返回结果，不依赖额外列表请求确认成功。读取失败、空库和筛选无结果分别呈现。
- ESLint、Prettier、vue-tsc / Vite build 通过。既有 Vitest 15 项、6 条业务浏览器流程通过；新增 3 条交互回归分批通过。修复前复现了导航焦点越界、历史错误归属及弹窗错误不可见问题。回归还覆盖 320 / 390 / 1440px 宽度、重开弹窗、取消后保留输入和创建请求计数。
- 浏览器使用本机 Edge、临时数据库和隔离供应商夹具。测试定位到下拉框内部输入的点击被文本层遮挡，改用键盘展开；功能回归移除依赖字体加载完成的截图步骤，避免将截图资源等待误判为业务失败。
- 未运行新的 Python 算法测试，未调用真实模型或 Tavily。未验证手机真机软键盘、完整屏幕阅读器体验及其他浏览器；本次未新增依赖、提交或推送 Git。

## 阅读与详情交互检查（2026-10-12 至 2026-10-13）

沿用现有字体、主题与内容布局，调整代码块标题栏、局部复制反馈、多行输入和窄屏执行详情，不更改 AI 后端及检索流程。

- ESLint 无警告、Prettier、vue-tsc / Vite build 通过，既有 Vitest 15 项通过。生产构建上的 Playwright 10 条核心流程通过（37.4 秒），其中本轮新增 1 条阅读交互检查。
- 新检查覆盖剪贴板内容与局部反馈、长代码横向滚动、输入框增高与缩回、390px 执行抽屉、标签方向键和 Home、Tab 焦点约束、两层抽屉分别 Escape 关闭及焦点返回，以及切换至桌面后移除遮罩、320px 无页面级横向溢出。其余流程覆盖问答取消重试、历史恢复、知识库上传与引用、供应商配置和长会话。
- 首次运行的新检查遗漏了历史列表夹具，补齐后正常恢复会话；Windows 剪贴板返回 CRLF，断言按平台差异统一换行后比较，未修改业务复制内容来迎合测试。
- 通过隔离 FastAPI 8010 实际生成夹具回答，目视检查 1440×960 桌面侧栏、390×844 执行抽屉和深色代码块。浏览器未记录 error 日志。截图在 Git 忽略目录 `.cache/ui-reading/`，所有回答和模型为测试夹具。
- 未新增依赖、付费模型请求或 Tavily 调用；未重复 Python 算法测试。仍未验证手机真机软键盘、完整屏幕阅读器及其他浏览器；本轮没有新的性能提升测量结论，也未提交或推送 Git。

## Windows 启动器检查（2026-10-13）

- 根目录 `start.bat` 调用 Windows PowerShell 启动脚本，使用 ASCII 内容及 CRLF 规则，支持 `-Port` 和 `-NoBrowser`；原 PowerShell 启动命令保持兼容。
- 从项目外的工作目录运行 `start.bat -Port 8001 -NoBrowser`，完成 vue-tsc / Vite 构建，随后 `/chat` 返回 HTTP 200。再次运行正确识别已有页面，没有创建第二个服务；另用隔离 TCP 监听器确认端口冲突会报错，不结束占用进程。
- PowerShell 语法解析、ESLint、Prettier 和既有 Vitest 15 项通过。此前同一批界面改动的 10 条浏览器流程结果见上节，启动器不改变业务接口。
- `NoBrowser` 用于自动化检查，未自动安装缺失依赖或下载模型；首次安装步骤仍见 README。启动后的浏览器打开依赖 Windows 默认浏览器关联。
