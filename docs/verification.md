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

测试服务使用 `tests/browser_server.py` 和临时数据库，覆盖会话、取消、来源、供应商表单、运行分析及知识库上传到引用的流程。不要占用测试端口 8010。无 Chrome 时安装 `npx playwright install chromium` 并移除 `PLAYWRIGHT_CHANNEL`。

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
