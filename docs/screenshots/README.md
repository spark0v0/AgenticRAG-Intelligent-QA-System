# 截图来源

- `workspace-*.png`：最新前端完善的真实页面，生产服务 8005；`workspace-citation.png` 为引用定位，`workspace-runs-mobile.png` / `workspace-runs-list-mobile.png` 为手机端分屏导航，`workspace-provider-form-mobile.png` / `workspace-dark-form.png` 为表单。使用正常 API 和已有真实历史，没有注入模拟回答；Key 输入为空。
- `workspace-metrics.json`：本轮截图、引用跳转、导出、窄屏检查的实际结果。`newModelRequest: false`；`previousModelVerification` 明确保留上一轮模型联调记录，不作为本轮新增调用。

- `real-*.png`、`real-service-metrics.json`：当前真实配置页面与少量供应方联调，隔离会话存在 `.cache/real-service-smoke/`。成功/失败范围以 metrics 和 `../verification.md` 为准。
- `workbench-desktop.png`、`workbench-mobile.png`、`smoke-metrics.json`、`history-metrics.json`：此前演示模式的历史材料，原地保留，不作为本轮验收证据。
- 最新测试夹具截图及性能记录位于 `frontend/test-results/evidence/`，不会覆盖真实页面。

人工联调先运行 `tests/serve_real_smoke.py`，再显式设置 `AGENTICRAG_REAL_SMOKE=1` 执行 `frontend/scripts/real-smoke.mjs`。它使用已有 DeepSeek 档案，最多发送一次完整检索问答和一次取消请求，可能消耗供应方配额；不自动重试或更换模型。测试存储和正常工作台存储隔离。
