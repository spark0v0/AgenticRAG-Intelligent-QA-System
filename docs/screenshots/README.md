# 截图来源

`clean-*.png` 是清理个人配置后的实际页面，使用正常 API，展示未配置模型、空供应商和空运行记录；不发送模型请求，不注入模拟回答。旧会话、供应商和测试截图已从当前版本移除。

`frontend/scripts/capture-workspace.mjs` 只允许对无供应商、无会话、无运行记录的工作台截图。默认输出到 Git 忽略的 `frontend/test-results/screenshots/`；需要发布时显式设置 `WORKBENCH_SCREENSHOT_DIR`，并在提交前检查图片。该检查不替代人工隐私审阅。

`real-smoke.mjs` 的真实服务验证需显式授权，使用当前默认模型或 `WORKBENCH_MODEL_LABEL`，结果仅写入 Git 忽略的 `frontend/test-results/real-service/`。它可能消耗配额，本次清理没有执行。
