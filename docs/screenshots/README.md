# 界面截图

`clean-*.png` 展示未配置模型与数据时的桌面和窄屏界面。

`frontend/scripts/capture-workspace.mjs` 要求工作台没有供应商、会话和运行记录，默认输出到 `frontend/test-results/screenshots/`。设置 `WORKBENCH_SCREENSHOT_DIR` 可选择输出位置；发布前检查截图是否包含凭据或私人内容。

Playwright 业务截图写入 `frontend/test-results/`，使用隔离服务夹具，不作为真实模型输出示例。
