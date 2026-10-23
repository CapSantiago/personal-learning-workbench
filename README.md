# PLW · Personal Learning Workbench

个人学习工作台：把课程、课件阅读、批注、任务和笔记放在一起。

基于 **Python / Streamlit / SQLite**。基础学习功能不需要 AI API。当前版本 **0.3.1**，提供源码运行方式；尚非独立安装软件或多用户 SaaS。

## 功能

- **课程书架**：课程与课件排序、批量导入、归档和撤销。
- **阅读与批注**：PDF/PPT 阅读副本、缩略图、搜索、缩放、旋转、框选、荧光笔、手写及书签。
- **阅读连续性**：进度与批注保存、文档复用，翻页不等待服务器保存完成。
- **设备下载库**：课件下载一次、本机长期复用，一键增量更新；电脑和平板各自保存。
- **学习管理**：任务、截止日期、已完成任务存档、章节与知识点、Markdown 笔记及版本历史。
- **数据保护**：完整备份、校验与恢复；归档课程保留已有学习内容。
- **界面**：阅读优先布局、六种强调色、桌面与平板/手机响应式布局。

## 快速开始（Windows）

准备 Git、**Python 3.14** 和 **PowerShell 7**。在 PowerShell 7 中执行：

```powershell
git clone https://github.com/CapSantiago/personal-learning-workbench.git
Set-Location personal-learning-workbench
py -3.14 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements-server.lock.txt
```

`requirements-server.lock.txt` 同时安装 PDF 结构检查所需的 pypdf 和 AES 支持；不会自动配置服务器。无需 Codex 或维护者的本机环境。

每次在仓库目录启动时，指定自己的数据目录与 PDF Python：

```powershell
$env:PLW_DATA_ROOT = Join-Path $env:LOCALAPPDATA 'PLW\data'
$env:PLW_BACKUP_ROOT = Join-Path $env:LOCALAPPDATA 'PLW\backups'
$env:PLW_WORKSPACE = $env:PLW_DATA_ROOT
$env:PLW_PDF_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
& .\.venv\Scripts\python.exe -X utf8 -B scripts/launch.py
```

打开 **http://127.0.0.1:8501**。欢迎页确认创建空学习库后，添加学期和课程，导入 PDF 即可阅读、批注。按 Ctrl+C 停止。端口占用时在启动命令末尾加 `--port 8502`，访问对应端口。

无需激活环境或修改系统执行策略。后续使用同一数据目录；更新代码前先在应用中创建完整备份。

### PPT 与可选能力

优先使用 PDF 体验基础功能。PPT/PPTX 自动转 PDF 需要 Windows 桌面版 PowerPoint，以及安装在标准位置 `C:\Program Files\PowerShell\7\pwsh.exe` 的 PowerShell 7；转换失败仍保留原件，可自行导出 PDF 后导入。OCR、动画与内嵌视频处理还有额外系统/图像运行时条件，不属于基础快速启动范围。

### Linux 与私人网站

仓库提供 Docker/Compose 和登录保护入口，另见 [部署文档](docs/CLOUD_DEPLOYMENT.md)。需要自行配置账号、HTTPS、持久数据目录与备份；Windows 的 `scripts/launch.py` 不能直接用于 Linux/macOS。

默认本机启动仅监听 `127.0.0.1`。公开源码不会公开维护者网站或学习库，也不会让别人的手机直接访问你的本地地址。每个部署使用自己的空学习库；当前不提供独立多用户租户隔离。

## 数据与限制

- 数据库、课件、密码及设备下载副本不随仓库分发。请将学习数据保存在仓库外。
- 设备库保存在浏览器网站存储中。清除网站数据会删除该设备的副本，不删除服务器原件；不是整站离线冷启动或离线批注同步。
- 图形批注保存在 PLW 数据库中，当前不写回原 PDF；版本变化不自动迁移旧页批注。
- 物理 iPad Safari/Pencil、笔压、防误触和复杂 PPT 仍有验证边界；响应式测试不等于全部设备实机认证。
- 当前有部分维护者专用诊断、热修复脚本及历史路径记录。新部署直接使用源码，不要照抄现有服务器的热修复命令。

## PDF 导入问题排查

如果显示“已保存待处理”，表示原件已保存，阅读副本尚未生成，不要删除学习库。更新代码与依赖并重启后，可重新选择同名同内容文件重试导入，系统会复用已有资料。

- 带权限加密标记但无需打开密码的 PDF：自动用空密码正常读取，保持原文件字节，不因加密标记一概拒绝。
- 真正需要打开密码：先在 PDF 软件中用已知密码解锁并导出，再导入。PLW 不尝试猜测密码。
- 缺少 pypdf/cryptography 或 PDF Python 路径无效：按具体环境提示修正；这类问题不应被误报为课件已加密。
- 未配置 `PLW_PDF_PYTHON` 时使用启动 PLW 的当前 Python，不再依赖维护者的 Codex 路径。

## 开发与贡献

```powershell
& .\.venv\Scripts\python.exe -B -m pytest tests/test_private_auth.py tests/test_private_assets.py tests/test_ui_theme.py -q
```

CI 运行上述干净检出核心测试。历史完整专项部分依赖未分发的 `.sandbox` 合成样本、不可变发布包或专用运行时，暂不保证全新克隆中全部 `pytest` 测试可运行。实际全新设备安装仍需核对 Python 与系统依赖。

欢迎提交 Issue 和 Pull Request，见 [贡献指南](CONTRIBUTING.md)；安全问题见 [SECURITY](SECURITY.md)。

## 文档

- [更新记录](CHANGELOG.md)
- [备份与恢复](docs/BACKUP_RESTORE.md)
- [设备课件下载库](docs/DEVICE_DOWNLOAD_LIBRARY.md)
- [设计系统](design-system/plw/MASTER.md)
- [项目状态与验收边界](docs/PROJECT_STATUS.md)

## 许可证

项目自有代码采用 [MIT License](LICENSE)。PDF.js、字体、CMap、WASM 等第三方资源保留各自许可证，见 [第三方说明](THIRD_PARTY_NOTICES.md)。许可证不授予用户上传课件的再分发权。
