# AgenticRAG 界面视觉方案与生图提示词

> 历史归档：以下概念提示词对应已退役演示模式，不作为当前实现要求或验收依据。当前真实页面截图在 `../screenshots/real-*.png`。

状态：视觉方案已准备，尚未调用图片生成服务，也未生成效果图。
本文件用于新的 UI 概念图，不修改已实现的项目页面。

## 统一视觉方案

专业的中文智能问答工作台。沿用现有 AgenticRAG 名称、浅色中性背景和绿色主操作，提升文字可读性、内容密度、信息层级和控件一致性。暖色仅用于警告，冷灰用于次级信息，不将整个界面染成绿色。

四张独立桌面效果图：

1. 智能问答首页：导航、历史、常用问题、输入与附件预览。
2. 问答与执行详情：完整答案、来源、工具和真实步骤时间线。
3. 工具中心：协议筛选、工具列表、参数 schema 详情。
4. 系统概览：运行环境、模型能力表格、配置与连接状态。

沿用已实现功能，不出现知识库上传管理、模型编辑、工具启停、权限或计费入口。数据统一标注演示模式；不添加用户量、准确率、成功率等没有依据的经营指标。

## 每张图共用的前置提示词

Use case: ui-mockup.
Asset type: high-fidelity desktop application UI concept, one complete screen per image.
Primary request: redesign the existing AgenticRAG Chinese AI question-answering and retrieval workbench into a polished, practical professional product interface. This is an application screen, not a landing page or promotional poster.
Style: precise flat frontend UI, front-on view, crisp legible simplified Chinese typography, clean alignment, carefully spaced dense information, restrained hairline borders, subtle shadows only for floating popovers. Consistent line icons and 6-8px corner radii. No browser chrome or device frame.
Visual system: white main surface, cool neutral light gray sidebar and workspace, dark graphite text, emerald primary actions matching the existing product, restrained cyan information accents and amber warning states. Avoid purple gradients, beige surfaces, large illustrations, glowing decorations, artificial perspective, and excessive floating cards.
Composition: landscape desktop viewport. Fixed narrow left sidebar, compact top toolbar, clear main work surface. Sidebar and top toolbar retain exactly the same dimensions and styling across all four screens. Strong contrast and comfortably readable text. Content never overlaps or clips. Use symbols for common tools, text for primary commands, segmented controls for mode selection.
Shared text, verbatim: "AgenticRAG", "智能问答", "工具中心", "系统概览", "新建会话", "历史会话", "演示模式", "真实服务".
Shared navigation: brand at the top left, emerald new-conversation button, three navigation entries, history search and a few realistic conversation titles. Top right contains a compact demo/live segmented switch with demo selected. Do not add account administration, billing or unsupported editing actions.
Accuracy: all data is an explicitly marked demo example. No invented accuracy, user counts, token spending, model verification success or commercial analytics. Do not add text describing the visual design itself. No watermark.

## 图一：智能问答首页

Append to the shared prompt:
Page: intelligent Q&A new-conversation state. Highlight "智能问答" in the sidebar.
Main surface: a modest "AgenticRAG" heading and the subtitle "智能问答与检索工作台" above a focused query input area. Four compact suggested-question items, neatly aligned, avoiding a marketing hero. Main content should feel usable immediately rather than like an introduction page.
Exact suggested questions: "理解 AgenticRAG", "探索本地知识", "分析技术方案", "计算与推理".
Composer near the lower center: spacious multiline input with "输入你的问题", a visible small image thumbnail attachment with a remove icon, paperclip button, two clearly readable selectors "自动决策" and "离线演示模型", and an emerald arrow send button. Keep filename and image preview inside the composer without excessive space.
Show a small honest mode label "离线演示 · 本地样例". No execution timeline for a request that has not run. Keep the right side closed so the input and conversation space remain dominant.
History examples: "AgenticRAG 的核心组成", "流式问答交互设计", "本地知识检索".
Desired output: one finished desktop UI concept image of this page.

## 图二：问答与执行详情

Append to the shared prompt:
Page: a completed knowledge retrieval conversation in demo mode. Highlight "智能问答".
Composition: left navigation, wide center conversation, narrower right execution detail panel. Center answer is visually dominant. The right panel is an attached workspace pane separated by a fine border, not an oversized floating card.
User message: "请介绍 AgenticRAG 的核心组成".
Assistant answer heading: "AgenticRAG 的核心组成". Show a short, readable answer explaining Router, Retriever, Generator and Critic, two concise paragraphs, a small numbered list and one neatly highlighted TypeScript code block. Use realistic sparse citation markers such as [S1]. Place icon actions for copying and viewing details below the answer.
Right pane title: "执行详情". Tabs, verbatim: "执行过程", "来源", "工具". Select "执行过程".
Timeline: show only the executed nodes "意图路由", "信息检索", "答案生成", "质量评审" in that order. Completed check icons, small timing labels explicitly part of the demo example, clear connecting line, one expanded retrieval node with a concise input/output summary. No fabricated internal reasoning chain and no unexecuted Planner node.
Below timeline: an understated "评审参考" area with "规则评分，非事实准确率". Include a compact source row "S1 · demo-knowledge.md" with a short evidence excerpt. All example values remain illustrative demo data, not claimed benchmark results.
Bottom composer: ready for a follow-up, clear model/mode selectors and send control. Do not make code blocks or long file names overflow.
Desired output: one finished desktop UI concept image of this page, visually consistent with the first image.

## 图三：工具中心

Append to the shared prompt:
Page: read-only tool directory. Highlight "工具中心" in the sidebar.
Main heading: "工具中心". Compact top controls: tool search field "搜索工具", segmented protocol filter with "全部", "Function Calling", "MCP", "Native". Avoid marketing copy and large KPI cards.
Use an organized tool list with aligned columns for name, protocol and registration state. Show the existing tools "本地知识检索", "知识关系查询", "数学计算", "项目能力查询". Tool status is "已注册"; never label registration as successful execution or connectivity verification.
Select "数学计算". Show a right-side attached detail inspector containing "calculator", protocol "Function Calling", short description "计算数学表达式", timeout "3 秒", status "连接未验证", and a readable compact input schema: expression, string, required. Include a small code snippet {"expression":"2+3"} as an example, not an execution result.
No enable toggles, run buttons or edit buttons because the current project exposes read-only tool metadata here. Clear selected row treatment, quiet dividers, ample readable spacing, balanced white and neutral gray surfaces.
Desired output: one finished desktop UI concept image of this page, preserving the identical shell design.

## 图四：系统概览

Append to the shared prompt:
Page: read-only system environment and model capabilities. Highlight "系统概览".
Main heading: "系统概览". Under the heading use a compact unframed status strip with "服务已连接", "演示模式", "SQLite" and "ChromaDB". Do not show invented uptime, request totals, accuracy, cost or traffic charts.
Primary section: a clean model profile table with columns "模型", "提供方", "图片输入", "回答模式", "连接状态". Include one offline demo row: "离线演示模型", "Mock", "仅附件演示", "模拟增量", "本地样例". Where a genuine provider row is illustrated, label it "未验证" and "配置声明支持" rather than falsely indicating a verified connection.
Secondary section: structured key-value rows for "会话存储", "执行记录", "数据隔离", showing "SQLite", "按运行保存", "演示与真实分离". Small neutral labels and fine separators; no nested cards.
At the bottom show a restrained amber note titled "取消边界", with short text "同步工具可能执行至超时". Keep configuration and verification status visually distinct. No configuration save buttons, upload controls, API keys, secret values or environment paths.
Desired output: one finished desktop UI concept image of this page, preserving the identical shell design.

## 生成与验收

生成方式尚未选择：本会话未提供内置 image_gen 工具。备用 CLI/API 方式需用户明确选择，并在本地配置 OPENAI_API_KEY。

如选择 API，使用 imagegen 技能自带 CLI，四张图分别调用各自提示词。建议横向 1536x1024 或 2048x1152，较高质量以保持中文与界面细节。每张图生成后检查中文、导航一致性、控件是否符合项目能力、是否有文字重叠，再交付 PNG；图像模型生成的细小文字仍需人工检查。

效果图仅为待落地的视觉方案。实际采用时，应将设计转换为 Vue/CSS 并重新验证交互，不能以效果图代替已运行页面截图。
