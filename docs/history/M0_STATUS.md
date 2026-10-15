# PLW 项目状态

更新日期：2026-10-11（Asia/Shanghai）  
当前阶段：**M0 本轮授权的文档、隔离环境与合成技术验证已完成；人工验收项尚未全部完成。未进入 M1。**

## 1. 已确认决策

- 用户确认执行上一轮推荐的 M0 最小任务。
- 采用 Streamlit 本地浏览器 + 本机路径导入；未来笔记优先内置编辑。
- Python 3.14.3 使用 `E:\Projects\PLW\.venv`，不复用 Anaconda base。
- SQLite 3.50.4；探针使用 DELETE 日志、FULL 同步、逐连接启用外键与有限 busy_timeout。
- 原始需求中的生产能力按 M1–M5 分期实现。M0 不能管理真实学习资料。

## 2. 本轮实际创建的内容

| 内容 | 位置与用途 |
| --- | --- |
| 产品、设计、备份恢复文档 | docs/PRD.md、DESIGN.md、BACKUP_RESTORE.md |
| 使用说明和状态 | README.md、本文件 |
| 独立环境及依赖锁 | .venv、pyproject.toml、requirements.lock.txt |
| 合成技术验证程序 | app.py、src/plw_probe/core.py、src/plw_probe/__init__.py |
| 自动化测试 | tests/test_core.py、tests/test_app.py |
| 启动与运行配置 | scripts/launch.py、start.ps1、.streamlit/config.toml |
| 网络与浏览器验证辅助 | scripts/offline_probe_server.py、browser_smoke.cjs |
| 测试产物 | .sandbox 内的合成文件、演示库、测试运行目录、浏览器配置、截图与报告 |

没有创建 `E:\PLW-Data` 或 `E:\PLW-Backups`；最后一次检查两者均不存在。没有真实课程数据库、真实学习文件导入、依赖升级到全局环境、系统配置更改或学习资料上传。

`.sandbox` 中存在有意保留的失败测试产物，以及多次浏览器验证产生的少量成功演示记录。它们不是真实学习资料，也不是生产备份。尚未初始化 Git 仓库或创建提交。

## 3. 环境与依赖结果

| 项目 | 实际值/结果 |
| --- | --- |
| 系统 | Windows 11，64 位 |
| 执行终端 | PowerShell 7 |
| 项目解释器 | E:\Projects\PLW\.venv\Scripts\python.exe |
| Python | 3.14.3 |
| SQLite 运行库 | 3.50.4 |
| Streamlit | 1.65.0 |
| pytest | 9.1.1 |
| pip check | No broken requirements found. |
| 传递依赖 | 已按实际安装结果写入 requirements.lock.txt |

仅向项目虚拟环境安装 Streamlit、pytest 及它们解析出的依赖；没有安装 PDF 内嵌组件。浏览器测试使用已有 bundled Node/Playwright 与系统 Edge，没有向项目安装 npm 包。

## 4. 实际执行的自动化测试

在 `E:\Projects\PLW` 中执行：

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 -B -m pytest -q
```

**结果：24 passed in 3.82s。**其中核心测试 21 项，界面测试 3 项；最终完整运行无警告。

| 覆盖范围 | 实际结果 |
| --- | --- |
| 中文、空格路径；托管复制和外部引用 | 通过 |
| 原始文件 SHA-256 与修改时间保持不变 | 通过 |
| 相同操作 ID 幂等，异路径/模式复用 ID 拒绝 | 通过 |
| 越界、缺失、目录、非法模式与 UUID | 通过 |
| Windows junction 与源文件硬链接拒绝 | 通过，使用项目内合成对象 |
| 复制异常、数据库 COMMIT 异常 | 故障注入通过，未产生成功资料记录 |
| 外键、CHECK、事务回滚 | 通过 |
| 拒绝非本探针数据库和覆盖既有目标 | 通过 |
| 初始渲染与普通重跑不调用写入服务 | 通过 |
| 提交失败保留表单并显示错误 | 通过 |

故障注入不能视为已完成真实断电、物理磁盘写满或全部权限场景的验证。没有执行 M1 迁移测试或 M2 完整备份恢复测试。

## 5. 实际浏览器与启动验证

启动测试服务：

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 -B '.\scripts\launch.py' --offline-probe
```

浏览器脚本由本机已有 Node 运行，参数指向已有 Playwright 模块目录。使用新的独立 Edge 配置；非回环 HTTP(S)/WebSocket 请求被拦截，Python 进程的非回环 socket/DNS 请求被拒绝。未修改系统网络、防火墙或注册表。

最终浏览器报告：**passed=true**。对应 `.sandbox/browser-smoke.json`，最终执行时间为 `2026-10-11T06:03:15Z` 至 `06:03:34Z`（北京时间 14:03 左右）。

| 验证 | 结果 |
| --- | --- |
| 托管复制后重复提交 | 仅新增一条记录 |
| 浏览器刷新 | 不新增记录 |
| 第二个独立标签页提交相同 ID | 复用同一记录 |
| 外部引用 | 成功，源文件 SHA-256 不变 |
| 中文 Markdown、行内/块级公式、矩阵、积分、分段函数 | 正常渲染，零 KaTeX 错误；已查看截图 |
| 浏览器非回环请求 | 受测流程中 0 条 |
| 浏览器页面/控制台错误 | 0 条 |
| Python 非回环连接阻止日志 | 未生成，受测期间未记录外连尝试 |
| 默认 PDF 阅读器 | Windows 接受打开合成 PDF 的请求；未自动确认阅读器画面 |
| 监听地址 | 实测仅 127.0.0.1:8501 |
| 同项目换端口重复启动 | 拒绝，退出码 2 |
| 已占用端口 | 使用临时回环监听实测拒绝，退出码 3 |
| PowerShell 启动入口 | 从 E:\ 执行 scripts/start.ps1 成功，自动定位项目并使用专属解释器 |

证据：`.sandbox/browser-smoke.json`、`.sandbox/browser-smoke.png`、`.sandbox/final-checks.json`。

离线探针服务停止后，已通过普通启动脚本重新启动 M0 预览，地址为 <http://127.0.0.1:8501>。这不是开机服务；退出启动进程后需按 README 手动重启。

测试过程中第一次浏览器脚本因 Streamlit 重跑期间暂时存在两个表单而失败；已修正等待稳定 DOM 的逻辑，之后两次验证通过。这里没有把首次失败记录当成应用通过证据。

审查修复：统一合成 PDF 文件名；启动锁改由实际服务进程持有；锁文件拒绝链接和多硬链接。

## 6. 未完成验证与已知限制

1. **人工 PDF 验收：**查看默认阅读器，确认能看到 “PLW M0 - Synthetic PDF” 单页内容；当前只验证打开请求被接受。
2. **真实断网验收：**本轮证明受限浏览器请求和 Python socket 条件下的 M0 流程可用，不是操作系统级全面断网证明；不覆盖外部 PDF 阅读器、尚未实现的课程/任务/笔记/备份功能。后续每个里程碑补充离线验收。
3. **生产文件可靠性：**长路径、大文件、真实占用/权限限制、物理空间不足、复制时文件变化、任意进程中断和完整恢复由 M2 扩展验证。
4. **网络探针范围：**offline_probe_server 是测试辅助，不是安全边界，不能控制原生扩展或系统其他进程的全部网络行为。
5. **日志观察：**浏览器连接关闭/测试服务停止期间出现一次 Windows asyncio `ConnectionResetError [WinError 10054]` 回调日志。浏览器与资料验证均通过、测试服务已停止，未发现数据异常；尚未归因或修复该断连日志，后续运行稳定性测试应跟踪。
6. **安装复现：**已记录精确包版本；未在第二台机器重建环境，未制作离线 wheel 包或桌面安装包。
7. **工程范围：**探针不提供生产数据库迁移、课程 CRUD、真实笔记编辑、PDF 内嵌、备份或恢复，不得把它直接当作 V1 使用。

## 7. 执行工具说明

本轮中途 Windows 执行沙盒报错“permission path cannot be represented losslessly / setup refresh had errors”。随后经自动审批使用同样已授权的项目范围执行测试与本机服务验证，没有扩大业务操作范围。该工具运行问题不是 PLW 应用测试失败。

## 8. 下一步

下一开发阶段：**M1 数据层与学期/课程管理**。

按 DESIGN 的顺序建立生产模块、数据库版本迁移和关系约束，先使用独立合成数据集；不要把 M0 的 probe.sqlite3 迁移成真实学习数据库。真实资料继续等 M2 完整备份与恢复演练通过。

本轮在 M0 停止，不自动进入 M1。正式 V1 的验收状态全部保持待实施。
