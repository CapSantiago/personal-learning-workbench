# PLW 外观与布局修正

本次沿用 Streamlit、SQLite 与现有阅读器，按 UI/UX Pro Max 的可读性、交互反馈和响应式原则渐进调整。

## 修改内容

- 课程标题、学期/教师与课件选择器分层排布。紧凑样式移除段落底边距时，同时取消 Streamlit 对 caption 容器的负边距补偿，避免实际文字超出容器而与下一控件重叠。
- 侧栏悬停和按下使用浅中性色与轻阴影，文字和图标保留深色；规则置于通用主按钮样式之后，修复同色背景覆盖文字的问题。选中项继续有左侧强调线。设置分组使用稳定标识保留展开状态。
- PLW 使用原创圆角几何字标，配紧凑书页图形。不请求外部字体，仍保留可访问的 PLW 文本。
- 新增“课程与设置 → 外观设置”：绿、黑、紫、蓝、黄、橙六种纯色强调方案及恢复默认绿色。按钮、边框、焦点、选中状态、首页进度及阅读器/下载库共同使用主题；页面与侧栏背景保持中性。黄色主按钮使用深色字，避免白字对比不足。

## 保存与数据边界

主题保存于学习工作区的 `control/ui-preferences.json`，原子写入并使用工作区锁。它是网站共享设置；电脑或 iPad 刷新/重新打开时读取同一设置，已打开的其他窗口不会被强制实时刷新。

此设置独立于学习数据库和课件。没有数据库迁移，不改变课程、课件、阅读进度、批注、认证或设备下载库。学习数据备份继续沿用原有完整备份协议；主题偏好不包含在学习数据备份中，切换/恢复学习数据集不会重置该网站设置。设置文件损坏时回退绿色并提示，不静默覆盖文件。

阅读下载、PDF.js 版本、翻页/保存协议及 native HTTPS 方案保持现状。此次外观更新不承诺提高网络下载带宽，也不要求清空设备下载库。

## 文件清单

- `src/plw/ui_theme.py`：六种强调色与持久保存。
- `src/plw/ui_workbench.py`：外观设置入口、主题注入、品牌标记、标题层级与侧栏分组标识。
- `src/plw/design_tokens.css`、`src/plw/workbench.css`：语义颜色、品牌、悬停、标题间距与原生进度条。
- `src/plw/reader/reader.css`、`library.css`：阅读工具、缩略图和下载按钮的主题继承与文字对比。
- `tests/test_ui_theme.py`、`tests/test_appearance_package.py`、`scripts/verify_accent_ui_browser.cjs`：保存与数据边界、打包基线、真实浏览器检查。
- `scripts/install_appearance_hotfix.sh`、`verify_appearance_base.py`、`verify_appearance_ui.py`、`package_appearance.py`：受控更新与隔离验收。
- `tests/test_ui_design_package.py`：旧发布包按固定哈希验证，不要求其等同后续版本源文件。

## 更新与回滚

更新包 `PLW-Appearance-20261022.zip` 可从四个已交付版本升级：device-library-r2、reader-smooth、reading-workspace、ui-design-r2。仅接受已知文件哈希，不覆盖未知修改。无需先重复安装旧包。

本机 PowerShell 7 执行：

```powershell
& "C:\Program Files\PowerShell\7\pwsh.exe" -NoProfile -File "E:\Projects\PLW\.sandbox\releases\Install-PLW-Appearance-20261022.ps1"
```

服务器密码只在终端输入。安装先校验包/旧版，在无网络隔离容器中检查设备库、保存、课程列表和主题表单，再创建完整学习数据备份及旧部署配置副本，最后切换镜像。启动失败会尝试恢复旧镜像配置；不删除旧镜像、备份或课件。若安装报错，保留输出，先检查原因再重试。

本地验证和云端部署是两件事。安装器显示“服务已启动”仅确认服务健康，不代替电脑/iPad 实际验收。实际测试证据与限制见 `docs/APPEARANCE_VERIFICATION_20261022.md`。
