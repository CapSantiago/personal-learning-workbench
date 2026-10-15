# Personal Learning Workbench (PLW)

Windows 11 本地优先的个人学习工作台，以课程课件整理、电子书式阅读和标记为核心，逐步补充任务与 Markdown 笔记。

**当前阶段：M2 资料管理与完整备份恢复。支持学期课程、逐文件复制或引用、资料检查、完整备份、恢复切换和回滚。当前仍只开放合成验收数据；任务和正式笔记编辑将在后续阶段实现。**

**课件阅读优先：原生 PDF、PPT/PPTX 都是正式目标。** R0 独立原型已验证 PDF 直接阅读、PPT 转换、翻页/缩放/旋转和几何标记保存；全量 263 项测试通过。课程书架、书签/文字批注、正式备份接入等仍按 R1/R2 实施。用户要求的全部标记范围保留，详见 [专项计划](docs/COURSEWARE_READER.md)及[实际验证结果](docs/R0_READER_RESULTS.md)。

## 试用 R0 合成课件阅读原型

打开 <http://127.0.0.1:8503>，选择合成 PDF 或 PPT 转换结果，使用翻页、缩放、框选、荧光笔和手写。这是独立技术验证页面，不能导入真实文件，标记暂不属于 M2 备份。

若原型服务已停止，在 PowerShell 7 中运行：

```powershell
& 'E:\Projects\PLW\.venv\Scripts\python.exe' -X utf8 -B 'E:\Projects\PLW\scripts\reader_probe\launch.py' --run '968c198e-a06e-4438-8910-6cf634af2c15'
```

它仅监听 127.0.0.1:8503/8504，不替换下面的 M2 入口。此命令复用已生成的合成样本；从零复现还需现有 bundled runtime 和本机 PowerPoint，因此不是可分发安装包。

## 已确认的实现边界

- Python 3.14.3 专属虚拟环境；未使用或更改 Anaconda、SRTP、ROS 环境。
- Streamlit 本地浏览器界面，通过本机路径导入；内置 Markdown 编辑为未来优先方案。
- 源码：`E:\Projects\PLW`。
- 真实学习数据候选：`E:\PLW-Data`；备份候选：`E:\PLW-Backups`。目前没有创建这两个目录。
- 当前合成数据仅位于 `E:\Projects\PLW\.sandbox`，不是将来的生产数据目录。
- M0 的根路径限制是有意的；此探针不能直接移动到其他路径后继续使用。

## 启动 M2

使用 PowerShell 7，无需激活任何虚拟环境：

```powershell
& 'E:\Projects\PLW\.venv\Scripts\python.exe' -X utf8 -B 'E:\Projects\PLW\scripts\launch.py'
```

浏览器打开 <http://127.0.0.1:8501>。终端内按 Ctrl+C 停止。启动器不会自动打开浏览器，也不会设置开机启动。

也可以在 PowerShell 7 执行 `E:\Projects\PLW\scripts\start.ps1`。如果执行策略阻止该脚本，直接使用上面的 Python 命令，不必修改系统执行策略。

服务显式监听 127.0.0.1，关闭使用统计，保留 CORS/XSRF 防护，禁用静态目录暴露。启动器在实际服务进程持有锁；换端口也不能重复启动同一项目。端口占用时，可在 Python 命令后加入 `--port 8502`。

## 学期与课程怎么使用

1. 首次进入时，点击“创建 M2 合成工作区”。普通查看或刷新不会初始化数据库。
2. 到“学期管理”创建合成学期；日期可留空，填写时采用 `YYYY-MM-DD`。
3. 到“课程工作台”选择学期，填写课程名称、教师、学分、时间、考核方式等。
4. 在课程列表搜索名称、教师或备注，打开课程主页并编辑。
5. 需要新建另一条记录时点击“继续新建学期/课程”。重复提交同一表单会复用已创建的记录；修改该表单内容后复用请求会被拒绝。
6. 归档后默认隐藏，可勾选“显示已归档”查看和取消归档。归档学期会让其课程默认隐藏，但保留历史数据与原有课程状态。

学分可清空为“未设置”。同名学期和课程会显示额外标识。两个标签页同时编辑时，旧版本不能覆盖新版本；错误发生后输入会保留，可点击“放弃编辑并重新载入”读取最新内容。

M2 活动数据库位于 `.sandbox\m2\datasets\<数据集 ID>\plw.sqlite3`，由 `control\active.json` 指向。普通使用无需手动编辑这些文件。M1 的 `.sandbox\m1\plw.sqlite3` 保持独立，没有自动迁移到 M2。不要将真实课程或资料输入合成环境。

## 资料管理怎么使用

1. 打开“资料管理”，点击“生成合成来源样例”。样例位于 `.sandbox\m2\sources`，已有同名不同内容的文件不会覆盖。
2. 逐个选择课程、来源路径和存储方式：托管复制保留原文件；外部引用只保存路径。
3. 点击“添加资料”。重复提交同一请求不重复创建；另一份文件先点击“继续添加另一份资料”。
4. 在资料详情点击“完整检查文件状态”，查看正常、缺失、不可访问或内容可能变化。
5. 外部文件移动后可“更新引用路径”。如允许指向不同内容，原始路径与基线哈希仍保留，状态继续显示内容可能变化。
6. 默认“隐藏资料记录（保留文件）”只隐藏索引，不删正文和关系。托管正文永久删除须先隐藏、没有任务/笔记/章节关联，再输入精确资料 ID 单独确认。外部引用没有删除原文件入口。

相同内容可以作为独立资料记录保留，详情会提示重复候选。失败操作可点击“核对文件操作”：完整暂存文件可以继续提交；缺失、不一致或未知残留保留供检查，不会自动重拷来源或删除现场。

## 完整备份、恢复与回滚

1. 打开“数据与备份”，点击“创建完整备份”。成功结果显示位置、文件数量和外部引用排除清单。
2. 备份包含数据库、保留的托管文件及全部已登记笔记版本；外部文件正文不包含，也不会在备份时自动读取原文件。当前笔记版本覆盖通过合成测试验证，正式笔记编辑尚未提供。
3. 输入备份目录，点击“验证并预览备份”，检查清单、哈希、数据库与关系。
4. 确认恢复时输入页面显示的当前数据集 ID。系统先制作恢复前完整副本，再恢复到新数据集、验证并切换；不会覆盖旧数据目录。
5. 如需撤回本次恢复，输入当前数据集 ID，点击“保存当前副本并回滚”。回滚前的新数据也会另存完整副本。
6. 中断恢复须先“核对并结束中断维护”，或在可用时回滚。普通页面不能绕过未核对的恢复日志继续写入。

普通备份位于 `.sandbox\m2\backups`，恢复前与回滚前副本位于 `.sandbox\m2\rollback`。旧数据集、失败目录、残留和备份均不自动清理。存在失败文件操作、缺失内部正文或未知内部文件时，完整备份会拒绝成功，不能只备份 SQLite 冒充完整备份。

详见 [备份与恢复操作手册](docs/BACKUP_RESTORE.md)。同盘副本不能保护整盘故障；当前合成实现也不等于正式发布或真实资料已获准导入。

## 重新运行保留的 M1

停止当前服务后，在启动命令末尾加 `--m1`。入口为 `app_m1.py`，仍只使用旧 M1 合成数据库。不要把 M2 数据目录交给旧入口。

## 重新运行保留的 M0 验证

停止当前服务后，在启动命令末尾加 `--m0`。入口为 `app_m0.py`；以下仍是独立技术探针：

1. 点击“生成合成样例”，生成中文空格文本、单页 PDF 和最小演示数据库。
2. 保持文本路径，选择“托管复制”，点击“提交验证”。
3. 再次提交同一操作 ID，应返回同一记录。刷新页面也不新增记录。
4. 点击“使用新的操作 ID”，再选择“外部引用”并提交。
5. 查看右侧中文、行内公式、矩阵、积分和分段函数。
6. 点击“用默认阅读器打开合成 PDF”。程序只报告 Windows 是否接受打开请求；阅读器是否正确显示需要人工查看。

只有 `E:\Projects\PLW\.sandbox\m0\sources` 内的普通文件可作为来源。系统不会允许输入真实课程路径；请勿把真实资料手动放入合成目录。样例已存在时不会覆盖，不同内容会报错。

复制/提交失败会保留失败或待检查操作与可能存在的内部半成品，不会报告成功，也不会自动删除文件。这不是完整 M2 恢复实现。

## 在全新项目环境中复现依赖

本机的 `.venv` 已经准备完成，日常启动不需要执行本节。以下用于将来 `.venv` 不存在时重建；不要对已有环境重复执行创建命令：

```powershell
& 'C:\Users\张梓灏\AppData\Local\Python\pythoncore-3.14-64\python.exe' -X utf8 -I -m venv 'E:\Projects\PLW\.venv'
& 'E:\Projects\PLW\.venv\Scripts\python.exe' -X utf8 -m pip install --disable-pip-version-check --no-cache-dir --index-url https://pypi.org/simple -r 'E:\Projects\PLW\requirements.lock.txt'
& 'E:\Projects\PLW\.venv\Scripts\python.exe' -X utf8 -m pip check
```

当前锁定 Streamlit 1.65.0、pytest 9.1.1 及其实际安装的传递依赖。锁文件限定版本，不是携带所有安装包的离线发行包，也没有构建跨平台兼容保证。

首次安装需要网络或事先准备匹配的本地 wheel 集合；运行不需要 AI API。完整 V1 的离线验收仍需逐阶段补充。

## 测试与证据

从项目目录运行：

```powershell
Set-Location -LiteralPath 'E:\Projects\PLW'
& '.\.venv\Scripts\python.exe' -X utf8 -B -m pytest -q
```

测试使用 `.sandbox\test-runs` 和项目内 pytest 缓存/临时区；这些位置只能存合成产物。不要把需要保留的资料放入 pytest 临时区。测试不会清理源资料或旧备份。

浏览器验证使用本机已有的 Node/Playwright 和 Edge，不额外安装依赖。M2 脚本为 `scripts\browser_m2.cjs`；M1 脚本为 `scripts\browser_m1.cjs`，须启动 `--m1`；M0 脚本为 `scripts\browser_smoke.cjs`，须启动 `--m0`。每次运行创建独立浏览器配置，拦截非回环页面请求，并增加少量合成记录，不自动清理。

可用以下模式启动进程内网络探针：

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 -B '.\scripts\launch.py' --offline-probe
```

它拒绝该 Python 进程的非回环 socket 连接与 DNS 查询，不改变防火墙或系统网络。它不是操作系统级的完整网络隔离，也不控制外部 PDF 阅读器。

实际结果见 [项目状态](docs/PROJECT_STATUS.md)。最近完整回归 **263 项通过**（含 R0 新增 16 项）；M2 浏览器报告和截图为 `.sandbox\browser-m2.json`、`.sandbox\browser-m2.png`。M1/M0 历史证据分别使用 `browser-m1`、`browser-smoke` 前缀。

## 当前文件

```text
app.py                         M2 入口
app_m1.py                      保留的 M1 入口
src/plw/ui_m2.py                资料、备份、恢复和工作区界面
src/plw/materials.py            双模式导入、状态与文件操作核对
src/plw/backups.py              完整备份、验证、恢复与回滚
src/plw/workspace.py            数据集身份与活动指针
src/plw/storage.py              路径、复制、SHA-256、原子 JSON
src/plw/locking.py              线程和 Windows 进程写屏障
src/plw/ui.py                   学期与课程界面
src/plw/services.py             业务校验、查询、幂等创建、版本冲突
src/plw/db.py                   连接、路径约束、事务与版本迁移
src/plw/migrations/001_core.sql 初始关系结构，schema 仍为 1；脚本保持不变
app_m0.py                      保留的 M0 界面
src/plw_probe/core.py           合成文件、最小 SQLite、复制/引用与幂等探针
tests/test_core.py              路径、文件、SQLite 约束及故障测试
tests/test_app.py               保留的 M0 界面测试
tests/test_db.py                数据库约束、迁移和 Windows 路径测试
tests/test_courses.py           学期课程业务、并发与幂等测试
tests/test_m1_app.py            M1 界面、归档、冲突与表单测试
tests/test_workspace.py         路径、工作区、锁及恢复日志守卫
tests/test_materials.py         导入、故障核对、来源保护与删除确认
tests/test_backups.py           完整备份、损坏拒绝、切换失败和回滚
tests/test_m2_app.py             M2 界面与确认流程
scripts/launch.py               本机启动、端口检查、进程锁
scripts/start.ps1               PowerShell 7 启动入口
scripts/offline_probe_server.py Python 进程内网络探针
scripts/browser_smoke.cjs       可选的浏览器自动化验证
scripts/browser_m1.cjs          M1 多标签页浏览器验收
scripts/browser_m2.cjs          M2 复制/引用、备份、恢复与回滚验收
requirements.lock.txt          已通过验证的完整包版本
docs/                          产品、设计、状态、备份恢复文档
```

## 常见问题

- **提示 already running：**已有本项目进程。使用已有页面，或在原启动终端按 Ctrl+C 停止；不要删除锁文件尝试绕过。
- **端口被占用：**选择另一本机端口，不绑定 0.0.0.0。
- **来源或数据库路径被拒绝：**当前有意限制合成目录，并拒绝符号链接、目录联接和硬链接。真实资料导入尚未启用。
- **编辑冲突：**保留输入，先记录需要保留的修改，再点击“放弃编辑并重新载入”；系统不会自动覆盖另一页的更新。
- **数据库版本不兼容：**停止操作并检查文件来源；未知数据库、未来版本或迁移校验变化不会被自动重置。
- **同操作 ID 更换模式报错：**这是避免误重试的保护；点击“使用新的操作 ID”。
- **M2 操作失败/未完成：**先核对文件操作。缺失或不一致现场不能自动解决，完整备份将保持阻断；不要手工删除日志或把状态改成成功。
- **恢复中断或旧页面被拒绝：**到“数据与备份”检查真实活动集与恢复记录，明确确认后核对或回滚；数据集切换后重新载入表单。
- **PDF 未显示：**先看 Windows 默认阅读器；无关联或打开失败会显示错误，不自动安装阅读器。
- **备份在哪里：**当前只有 `.sandbox\m2\backups` 的合成备份；它们不是你的真实学习资料备份。

## 设计与下一步

- [产品需求](docs/PRD.md)
- [架构、数据关系与 M0–M5 计划](docs/DESIGN.md)
- [当前状态和实际验收结果](docs/PROJECT_STATUS.md)
- [备份恢复操作手册](docs/BACKUP_RESTORE.md)
- [课件阅读、标注与专项验收计划](docs/COURSEWARE_READER.md)

M2 主应用保持原样；R0 已有隔离阅读原型，扩展保真与性能未执行项见验证报告。接下来先做 R1 原生 PDF 版本与完整恢复，再连接课程书架和基础标记，随后 R2 及原 M3/M4/M5。真实资料路径的启用仍需作为明确的独立步骤处理。
