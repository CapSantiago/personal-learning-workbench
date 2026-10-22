# PLW UI/UX 渐进美化验收记录

日期：2026-10-22。Skill、实施前审查和方案见 [审查文档](UI_UX_REVIEW_20261022.md)；规则见 [设计系统](../design-system/plw/MASTER.md)；云端入口和回退说明见 [更新说明](UI_DESIGN_UPDATE_20261022.md)。

## 已实现

1. 重点重做侧边栏：36px 书页标识、20px PLW 名称、中文说明；统一左对齐导航，分层课程列表和克制的选中提示。没有添加外部图标库或字体请求。
2. 用 `design_tokens.css` 同时为原生界面与两个 Shadow DOM 组件提供配色和字体，统一焦点、控件边界与状态。
3. 首页最近阅读保留一个主按钮，课程入口改为紧凑列表；课程、详情、任务日期表单、笔记沿用同一视觉规范。
4. 桌面阅读区保持全宽和首屏优先；触屏阅读按钮目标至少 44×44 CSS px，工具按组换行。窄组件隐藏重复滑杆和百分比，保留缩放选择器、加减、手势和全部批注功能。
5. 手机导航栏背景与焦点留白避免滚动文字透过展开按钮。支持减少动态效果。

## 真实浏览器检查

环境：Windows、Python 3.14.3、Streamlit 1.65.0、Node 24.18.0、Playwright 启动本机 Edge。运行完整 Streamlit 应用及生产阅读路由，不是静态效果图。界面验证仅使用 `.sandbox/test-runs` 下新建的合成学习库，外部资源请求在浏览器测试中阻止。

修改前记录：[12 张页面记录](../.sandbox/ui-design-before-2393d358-2e7f-44b6-a791-cfcb44e09fba/)。最终记录：[22 张截图和报告](../.sandbox/ui-design-after-b4b75460-a540-44c9-879e-ba86a59e711b/report.json)。

| 检查 | 结果 |
| --- | --- |
| 首页七门活动课程、三份最近课件、长中文标题、归档排除 | 通过 |
| 课程切换、课件工具入口、排序/导入/下载等折叠入口 | 通过 |
| 1440 桌面、1024/768 平板、375 手机、812 横屏 | 已检查；18 个页面状态均无主页面横向溢出 |
| 侧栏在手机展开/收起，品牌与导航可见 | 通过 |
| 任务完成、存档详情、恢复待办 | 通过 |
| 课程搜索、课程详情/编辑字段、Markdown 笔记预览 | 通过 |
| 设备库 8/8 清单项保存；再次更新全部复用 | 通过 |
| 阅读工具窄屏边界、粗指针 820×1180 / 1180×820 按钮目标 | 通过；关键阅读按钮至少 44 CSS px |
| 真实键盘焦点 | 下一页按钮有 2px 焦点环；导航仍保留原生键盘操作 |
| 减少动态效果、主应用根字号 200% | 通过重排；不是完整辅助技术认证 |
| 浏览器脚本错误与 Streamlit 异常 | 未发现 |

颜色抽检：正文 / 画布 11.24:1，辅助文字 / 画布 5.74:1，主按钮白字 6.70:1，控件边界 / 白色 3.35:1。不是对所有第三方组件和状态的完整 WCAG 认证。

阅读稳定性另由 `verify_shelf_layout_browser.cjs` 检查：[最终结果](../.sandbox/ui-design-fit-a502f02f-db25-4f19-bb0b-c62ba1b74336/report.json)。5 种桌面宽度、手动缩放恢复、旋转、预览开关、平板、纵向 PDF 及旋转，共 13 情形；每种稳定后 15×100ms 采样检查缩放不往返、无重复重算或画布适配溢出，最终均为稳定缩放且重复重算 0。1600×1000 下正文 top 237px、高 702px，阅读区域仍在首屏。

真实 54 页与 35 页课件的独立生产组件检查：[结果](../.sandbox/reader-smooth-cff79178-deb6-4660-94ec-a2ccabbefe41/report.json)。3 秒保存延迟下连续翻页、图形仍属于原页面、503 后原 ID 重试、刷新保留页码与标记、A→B→A 不重复下载，均通过。

## 自动检查

- 216 项 Python 回归通过：课程/任务/归档恢复、导航、排序、阅读保存、认证、下载库，以及 3 种已发版本的严格更新基线与未知修改拒绝。
- 48 项 JavaScript 检查通过：设备长期下载、完整性、增量复用、错误恢复、有界 PDF/画布复用、异步保存。
- 3 份部署用验证器在本机进程通过：完整框架 PDF/worker/认证、后台保存、合成 Streamlit UI。不是 Linux 镜像运行验收。
- PowerShell 7 和 Bash 解析通过；ZIP CRC、全部载荷摘要、入口/引导摘要、当前源码对应检查通过。
- 对比上一份 reading-workspace 发布包，阅读器 JS 与 runtime 字节不变。UI AST 仅变更导航、首页及三处样式加载，并增加统一样式读取函数；SQL、业务服务和 schema 未改。

可复现主要检查：

```powershell
& .\.venv\Scripts\python.exe -B scripts/run_ui_design_browser.py after
& .\.venv\Scripts\python.exe -B scripts/run_ui_design_browser.py fit scripts/verify_shelf_layout_browser.cjs
```

## 本轮修改文件清单

| 文件 | 用途 |
| --- | --- |
| `src/plw/ui_workbench.py` | 呈现容器、主次按钮、侧栏品牌与统一样式加载；原回调和业务处理保留 |
| `src/plw/design_tokens.css`（新增） | 一份语义颜色、字体与圆角定义 |
| `src/plw/workbench.css` | 主界面、侧栏、课程/任务、焦点和手机重排 |
| `src/plw/reader/reader.css` | 阅读器视觉、工具组、触屏与焦点；保留稳定适配规则 |
| `src/plw/reader/library.css` | 设备下载库样式及长标签换行 |
| `scripts/ui_design_fixture.py`（新增） | 隔离合成学习库、本机实际网站 |
| `scripts/run_ui_design_browser.py`、`scripts/verify_ui_design_browser.cjs`（新增） | 服务就绪检查、浏览器交互与截图 |
| `scripts/verify_ui_design_base.py`、`scripts/install_ui_design_hotfix.sh`、`scripts/package_ui_design.py`（新增） | 严格基线、备份/回退和不可变打包 |
| `tests/test_ui_design_package.py`（新增） | 更新安全与已发版本重建测试 |
| `tests/test_reading_workspace_package.py` | 旧包改为固定身份验证，允许后续 UI 独立演进，不重写旧 ZIP |
| 本审查、设计系统、更新说明、验收文档和 `PROJECT_STATUS.md` | 设计决策、操作与证据 |

没有改变此前未提交的其他认证、阅读或数据修复文件；它们仍保留在工作区。

## 交付与限制

最终包：`.sandbox/releases/PLW-UI-Design-20261022-r2.zip`，59,707 字节，SHA-256 `6ab97e4eac00892e8f1ab1364655e5e4dff30d5ada4d37b90cf6849050a5a55d`。入口：`.sandbox/releases/Install-PLW-UI-Design-20261022-r2.ps1`。

云端尚未部署；入口需要用户在本机终端完成一次现有 SSH 密码认证。安装前校验、隔离检查和完整备份均写入脚本；切换失败尝试恢复。正式学习库、原件和浏览器下载库未被本轮本机测试更改。

物理 iPad、Safari 和 Pencil 尚未实机验收；平板竖屏打开侧栏时阅读宽度有限，可使用现有收起侧栏或“专注阅读”。本轮仅统一浅色主题；不迁移框架、不新增完整日历功能、不承诺首次下载提速。Streamlit 的服务端操作仍会按原方式重运行；未来升级其版本需重新检查依赖 testid 的 CSS。
