# Personal Learning Workbench — 技术设计与实施计划

版本：M2 实施状态与课件阅读优先设计基线  
日期：2026-10-11  
状态：M1 数据层与学期/课程已实现；M2 资料、完整备份、恢复及回滚已实现，并通过自动化及真实浏览器合成验收。M3 任务和 M4 章节/笔记业务仍为后续设计，真实学习数据仍禁止使用。

优先级修订：先实施 R0/R1/R2 课件阅读专项，再继续原 M3/M4/M5。R0 已实现隔离合成原型并通过核心路径验证，正式阅读版本/课程 UI/备份仍待 R1/R2。原生 PDF 直接阅读，PPT/PPTX 经转换后进入同一组件，PDF 路径不依赖 Office。用户要求的全部标记范围保留。详细方案见 [COURSEWARE_READER.md](COURSEWARE_READER.md)，本轮实际 263 项测试与浏览器/重启结果见 [R0_READER_RESULTS.md](R0_READER_RESULTS.md)。

M1 历史全量自动化测试为 125 passed in 3.90s。M2 实施轮全量为 247 passed in 22.92s：既有 M0/M1 共 125 项、资料 28 项、共享存储/锁/工作区 45 项、备份恢复 43 项、M2 UI 6 项。真实浏览器 ee294401 在 2026-10-11T07:15:07.610Z 至 2026-10-11T07:15:13.026Z 通过 7 项合成场景，覆盖导入重试及引用/隐藏、备份外部排除、错误确认不切换、新集恢复与旧集保留、回滚及回滚前副本、两份来源 hash/mtime 和 M1 数据库不变，以及零观测外连/JavaScript/console 错误。上述为 M2 历史结果；R0 实施轮已重跑包含它们的 263 项测试，详见 R0_READER_RESULTS.md。

首次 M2 浏览器检查发现复用课程组件的成功提示未由宿主页显示，已修复并增加 UI 测试；最后报告显示调整后另执行 6 项 UI 测试并通过（2.43s）。完整操作系统断网仍未测试，最后启动/重启检查按 PROJECT_STATUS.md 实际记录；合成备份恢复通过不等于真实资料已经开放，或笔记编辑等后续学习闭环已经完成。

## 1. 决策与边界

| 项目 | 采用方案 | 原因与边界 |
| --- | --- | --- |
| 产品 | Windows 11、本地、单用户 | 无需服务器账号、AI API 或联网即可学习 |
| Python | 已选 Python 3.14.3，项目独立 .venv | M0 验证依赖可用性；不升级系统 Python，不改 Conda/ROS |
| UI | 保留 Streamlit 外壳，先验证独立 JavaScript 阅读组件 | 高频翻页/绘画留在前端，完整操作才提交；重跑、丢笔迹或状态重置须在 R0 排除 |
| 数据库 | 标准库 sqlite3，DELETE 日志、FULL 同步 | V1 单进程、短事务、有限数据量，降低 WAL 伴随文件管理复杂度 |
| 文件 | pathlib、shutil、hashlib、同卷临时文件 | 通过服务层管理；不声称数据库事务能原子提交文件操作 |
| 笔记 | UTF-8 Markdown 文件，版本元数据在 SQLite | 内置编辑优先；保留可携带文件与明确历史版本 |
| 数学公式 | Streamlit Markdown/LaTeX 能力，M4 离线验证 | 禁止把 CDN 联网成功作为离线可用证据 |
| 课件阅读 | 拟采用固定 PDF 阅读版 + 本地 PDF.js + 独立标记层 | 内嵌阅读成为核心门槛；PowerPoint 用于原件/动画；本机转换和组件整合尚待 R0 验证 |
| 测试 | pytest + 临时合成数据 | 测试不能读取或改写真实学习资料 |
| 发布 | 优先可复现的虚拟环境与 PowerShell 7 启动说明 | 单文件打包、离线安装包后置 |

### 1.1 备选方案比较

| 方案 | 适用性 | 代价 | 结论 |
| --- | --- | --- | --- |
| Streamlit + sqlite3 + 阅读组件 | 保留课程资料和备份，组件承接页面/绘画 | 需验证前端生命周期、重跑、PDF 传输和持久保存 | R0 首选验证；不能仅靠普通表单实现流畅标注 |
| PySide6 + sqlite3 | 原生文件对话框、桌面交互、快捷键 | Qt 学习与分发成本更高，UI 工作量增加 | 若原生拖放/编辑成为核心再评估 |
| FastAPI + 独立前端 | 连续阅读、手写与复杂交互 | 需维护 API、前后端和构建工具链 | 若 R0 证明 Streamlit 组件无法满足阅读/绘画门槛，再迁移 UI，复用数据与备份服务 |
| SQLite ORM | 模型映射和复杂查询较多时有价值 | 增加依赖与抽象，仍需理解迁移和事务 | V1 使用小型仓储封装 sqlite3 |
| SQLite WAL | 并发读写更密集时有价值 | 需处理伴随文件与检查点 | V1 不采用；出现实测瓶颈后再决策 |

切换 UI 不应重写文件导入、备份和课程业务规则。若 Python 3.14 的必要依赖不能完成 M0 验证，记录具体失败后评估另建项目专用环境；不能默默修改已有全局环境。

### 1.2 运行与安装

离线运行指依赖已经安装后，基础功能不发送外网请求、不读取 CDN、不需要 API key。首次安装依赖可能需要网络；完整离线安装需要另外准备与目标 Python/Windows 架构匹配的包集合，当前不宣称已经完成。

Streamlit 配置绑定 127.0.0.1，保留 CORS/XSRF 保护、关闭使用统计、关闭任意目录的静态文件暴露。端口占用时给出错误或使用明确的本机备用端口，不改为 0.0.0.0。本地访问边界不是面向敌对本机用户的安全沙箱。[Streamlit 配置参考](https://docs.streamlit.io/develop/api-reference/configuration/config.toml)

## 2. 目录与模块

### 2.1 当前 M2 模块与后续扩展

当前使用小型模块实现分层，避免为尚未实现的业务建立空目录。此处列出主要入口和模块，并非全部历史 PoC 文件清单。

~~~text
E:\Projects\PLW\
  README.md
  pyproject.toml                  # 依赖与测试配置
  requirements.lock.txt          # 已锁定依赖
  .venv\                         # 项目独立环境，不纳入版本控制
  app.py                         # 当前 M2 入口
  app_m1.py                      # 保留的 M1 入口
  app_m0.py                      # 保留的 M0 验证入口
  docs\
    PRD.md
    DESIGN.md
    PROJECT_STATUS.md
    BACKUP_RESTORE.md
  tests\
    test_db.py                   # 数据库、schema、迁移和路径边界
    test_courses.py              # 学期/课程服务与实际并发测试
    test_m1_app.py               # M1 UI 自动化
    test_materials.py            # M2 资料、失败核对与来源安全
    test_backups.py              # 完整备份、恢复、回滚与异常路径
    test_app.py                  # 保留的 M0 UI 测试，指向 app_m0.py
  src\plw\
    __init__.py
    config.py
    db.py                        # 路径限制、连接、事务、版本迁移
    services.py                  # 学期/课程业务、校验、幂等与版本冲突
    storage.py                   # 合成路径边界、独占复制与稳定哈希
    locking.py                   # 跨线程及 Windows 跨进程写屏障
    workspace.py                 # 合成工作区、活动数据集和指针切换
    materials.py                 # 资料元数据、文件操作日志及显式核对
    backups.py                   # 清单、完整备份、验证、恢复与回滚
    ui.py                        # 保留的 M1 页面，供 M2 复用
    ui_m2.py                     # M2 合成资料和备份恢复界面
    migrations\001_core.sql      # schema 1；M2 未修改或添加迁移
  scripts\launch.py              # 默认 M2；--m1 / --m0 选择保留入口
  .sandbox\
    m1\                          # M1 合成演示数据
    m2\                          # M2 合成工作区，结构见下节
    test-runs\                   # 合成测试数据库
~~~

当前依赖方向为 ui_m2.py → 学期/课程、资料和备份服务 → db.py、storage.py、locking.py、workspace.py；学期/课程页面复用 ui.py。服务不依赖 Streamlit，文件复制、恢复和业务 SQL 不放入页面回调。接下来先增加 reader/conversion、editions、annotations、frontend 等专项模块；具体是否拆目录依实现复杂度决定，再继续 M3/M4。

001_core.sql 保持已发布内容不变，数据库版本仍为 1；M2 使用原有 materials、关联表和 file_operations，不需要新迁移。tasks、chapters、knowledge_points、notes、note_revisions 尚未有生产服务或编辑界面。备份服务已覆盖所有笔记历史正文，并以合成记录验证此范围。

### 2.2 当前合成工作区与候选真实位置

M2 实际结构如下，全部位于 E:\Projects\PLW\.sandbox\m2。M1 与测试数据库分别保留在 .sandbox\m1 和 .sandbox\test-runs。E:\PLW-Data 与 E:\PLW-Backups 仍只是候选真实位置，不得创建或初始化。

~~~text
E:\Projects\PLW\.sandbox\m2\
  control\
    active.json                  # 活动数据集 ID；不接受任意绝对路径
    restore-journal.json         # 恢复/回滚日志；完成后保留最后状态
    .write.lock                 # 工作区跨线程/跨进程写屏障
  datasets\
    <dataset-id>\
      plw.sqlite3
      config.json               # 数据集标识与必要配置
      managed\<material-id>\payload<safe-extension>
      notes\<note-id>\<revision-id>.md
      .staging\<operation-id>\...
                                 # quarantine 是日志状态，不自动移动残留文件
  backups\<backup-id>\            # 完成验证后才发布 complete.json
  rollback\
    <restore-id>\...              # 恢复前的可验证完整副本
  sources\                       # 明确创建的合成来源；导入只读
~~~

数据库仅保存托管文件和笔记在活动数据集内的相对路径。外部引用使用绝对路径；这意味着换盘、换机器后可能需要重新定位。

生产版本目标仍为源码、学习数据与备份位置分离。当前为可审查的合成验收，工作区位于项目 .sandbox 内，backups 与 datasets 是兄弟目录；这是测试隔离安排，不是生产数据位置决策。当前和候选位置都在 E: 盘，不能抵御整盘故障；真实使用前需确认第二介质备份方案。

## 3. 数据模型

本节原有核心实体仍描述已建立的 schema 1。阅读专项拟新增 reading_editions、edition_pages、reading_progress、annotations，以及独立阅读操作日志；为课程内排序增补字段，必要时复用 chapter_materials。它们尚未创建，字段、坐标约定及外键见 COURSEWARE_READER.md；不得修改已应用的 001_core.sql。

### 3.1 通用约定

- 主键使用应用生成的 UUID 文本，避免把文件名、路径或标题当主键。
- 时间戳使用明确的 UTC ISO 8601 文本；仅日期使用 YYYY-MM-DD。显示时转到用户时区。
- 字符串状态加 CHECK 约束；大小、耗时、排序等数值限定有效范围；必填字段使用 NOT NULL。
- 课程归档和资料逻辑删除用独立时间字段，不丢失原始学习状态。
- 用户输入使用参数化 SQL。搜索中的通配符语义应显式处理。
- 路径、校验和、文件状态属于文件元数据，不代表文件正文保存在数据库中。

### 3.2 核心实体

| 实体 | 主要字段 | 关系与约束 |
| --- | --- | --- |
| semesters | id、name、start_date、end_date、archived_at、created_at、updated_at、revision | 起止日期可空，均有值时结束不早于开始；名称不强制全局唯一；revision 从 1 开始用于乐观并发 |
| courses | id、semester_id、name、teacher、credits、schedule_text、assessment、status、remarks、archived_at、created_at、updated_at、revision | 属于一个学期；学分可空，非空时有限且 0–100；状态 planned/active/completed/paused；revision 从 1 开始 |
| materials | id、course_id、name、material_type、storage_mode、original_path、reference_path、managed_relpath、size_bytes、mtime_ns、baseline_sha256、observed_sha256、hash_checked_at、file_status、last_checked_at、last_error_code、import_state、deleted_at、file_deleted_at、created_at、updated_at | course_id 为主课程；模式与路径字段互斥；状态 normal/missing/inaccessible/possibly_changed/unchecked；导入状态 pending/ready/failed；file_deleted_at 只记录经确认的托管正文删除 |
| tasks | id、course_id、title、task_type、due_kind、due_date、due_at_utc、due_timezone、planned_date、priority、status、estimated_minutes、actual_minutes、remarks、created_at、updated_at、completed_at | 类型 assignment/lab/exam/preview/review/project；状态 todo/doing/done/cancelled；deadline 字段按 due_kind 互斥 |
| chapters | id、course_id、parent_id、title、position、created_at、updated_at | 父章节必须同课程；不能自指和形成环 |
| knowledge_points | id、course_id、chapter_id、title、learning_state、remarks、updated_at、created_at | 可不指定章节；指定后须属于同课程；状态 not_started/learning/understood_not_applied/mastered |
| notes | id、course_id、chapter_id、title、current_revision_id、version、created_at、updated_at、deleted_at | 章节可空且须同课程；version 用于乐观并发检查；当前版本必须属于本笔记 |
| note_revisions | id、note_id、revision_no、body_relpath、sha256、size_bytes、created_at、source_revision_id | .md 正文独立存储且发布后不可变；UNIQUE(note_id, revision_no)、UNIQUE(note_id, id)；恢复历史生成新版本 |
| schema_migrations | version、name、checksum、applied_at、app_version | version 唯一；成功迁移与版本记录同事务提交 |
| create_requests | request_id、entity_kind、payload_json、payload_hash、entity_id、created_at | request_id 为 UUID 主键；entity_kind 为 semester/course；entity_id=request_id；保存原始规范化创建内容及 SHA-256，与实体创建同事务提交 |
| file_operations | id、request_id、kind、entity_id、state、staging_relpath、target_relpath、expected_sha256、payload_json、created_at、updated_at、error_code | request_id 唯一；记录导入、保存笔记、确认删除的可恢复执行状态；payload 保存完成或核对操作所需元数据 |

材料类型先采用课件、教材、作业说明、实验指导、试卷、代码资料、其他等有限枚举，不把扩展名当成唯一类型判断。哈希未知时为 NULL，不能以空字符串冒充已校验。M2 首次导入两种模式均计算 SHA-256；baseline_sha256 保存导入基线，observed_sha256 保存检查结果，检测或明确重连不同内容均不会覆盖基线。未完成内容校验不能展示为“内容已验证”。

tasks.due_kind 为 none/date/datetime：none 不带截止值，date 仅带 due_date，datetime 仅带 due_at_utc 和时区。priority 使用 low/normal/high。SQLite CHECK 负责基本一致性，领域层负责日期解析和业务语义。

### 3.3 关联表

| 表 | 键 | 含义 |
| --- | --- | --- |
| task_materials | PRIMARY KEY(task_id, material_id) | 一个任务可关联多资料，同一资料可用于多任务 |
| note_materials | PRIMARY KEY(note_id, material_id) | 笔记关联来源资料 |
| chapter_materials | PRIMARY KEY(chapter_id, material_id) | 章节整理相关资料 |

三种关联都允许用户显式跨课程选择资料；资料的主课程不变，UI 必须显示来源课程。禁止自动把文件复制一份来表示关联。

关系概要：

~~~text
semesters 1 ── N courses
courses   1 ── N materials / tasks / chapters / knowledge_points / notes
chapters  1 ── N 子章节 / knowledge_points / notes
tasks     N ── N materials   经 task_materials
notes     N ── N materials   经 note_materials
chapters  N ── N materials   经 chapter_materials
notes     1 ── N note_revisions，notes 指向其中一个当前版本
~~~

### 3.4 外键、删除与一致性

- 每个数据库连接在事务开始前启用并读取确认 foreign_keys=ON，不能只在建库时设置一次。SQLite 的外键开关是连接级设置，且事务中切换存在限制。[SQLite PRAGMA](https://www.sqlite.org/pragma.html#pragma_foreign_keys)
- courses 对 semesters、各所属实体对 courses 默认 ON DELETE RESTRICT。正常 UI 提供归档，不以级联删除清空课程内容。
- 关联表对两端可使用 ON DELETE CASCADE，但只影响数据库关联行，绝不触发磁盘文件删除。课程和资料等正常业务不直接硬删。
- chapters 建立 UNIQUE(course_id, id)，parent 使用组合外键 (course_id, parent_id)；notes 和 knowledge_points 的章节使用同样的组合外键。当前 schema 另含递归查询触发器，拒绝插入或修改产生章节环。
- notes 的 (id, current_revision_id) 指向 note_revisions 的 (note_id, id)，确保不能指向其他笔记。必要的循环外键设为可延迟，创建笔记与首个版本在一个事务内完成。
- note_revisions.source_revision_id 若有值，使用同笔记组合约束；版本号和相对文件路径不得重复。
- 索引至少覆盖 courses.semester_id、各 course_id、任务状态/截止、资料名称、笔记更新时间以及关联表反向 material_id 查询。
- 资料移出索引标记 deleted_at；保留资料行、全部关联与磁盘文件。M2 服务提供关联计数，并在存在任一任务/笔记/章节关联时拒绝永久删除；无关联、已隐藏、已完成导入且文件符合基线才允许精确 UUID 确认删除。file_deleted_at 已设置的记录不能仅靠恢复索引恢复正文。
- 物理去重不在 V1：两条托管资料记录拥有各自文件，即使哈希一致。这样一个资料的删除不会破坏另一资料。

## 4. 事务、连接与版本迁移

M1 已实现 db.py 的连接/事务/初始化/迁移边界与 services.py 的学期课程业务，M2 将所有工作区写事务接入统一写屏障。数据库连接和 schema 校验不自动初始化不存在的数据库；必须由明确的初始化入口创建合成数据。

学期/课程创建以 UUID 同时作为 request_id 和新实体 ID。create_requests 保存规范化 JSON 与 SHA-256；相同请求及内容返回当前记录，即使记录后来已编辑或归档；相同请求携带不同内容或用于其他实体类型时抛出 ConflictError。资料另以 file_operations.request_id 保存独立请求和规范化 payload；只有已 committed 且 ready 的相同请求直接返回，参数不同拒绝，未完成请求要求先核对。

学期和课程编辑、归档均检查 expected_revision，并在 SQL 中使用 id 与 revision 条件更新。实际双线程测试证明：同一创建请求同时提交只产生一条实体及一条请求记录；相同 expected_revision 同时编辑恰有一个成功，另一个冲突，版本仅增加一次。

服务返回字典记录，业务异常共同基类为 LearningError。普通课程查询同时隐藏自身归档和所属学期归档的课程；include_archived 可访问历史。归档学期不级联修改课程状态、版本或子记录，普通编辑和新建须先取消归档。查询中的 %、_ 和 ! 按字面量匹配。

### 4.1 连接和并发

统一连接工厂显式配置 journal_mode=DELETE、synchronous=FULL、foreign_keys=ON 和有限 busy_timeout，并校验实际值。启动时检查日志模式；不在进行中的事务里改变 PRAGMA。FULL 是选定的持久性策略，不能替代备份或保证故障硬件绝不丢数据。[SQLite PRAGMA](https://www.sqlite.org/pragma.html)

连接在当前线程、一次服务工作单元内创建和关闭；不把可写 sqlite3 连接放入 Streamlit 全局资源缓存，也不关闭线程检查后任意共享。

显式选择 Python sqlite3 事务策略，不依赖未来可能改变的默认值。建议连接使用 autocommit=True，再以 SQL BEGIN IMMEDIATE / COMMIT / ROLLBACK 管理写事务；此时不能误以为 Connection.commit() 会结束手动事务。异常必须执行对应回滚并关闭连接。[Python sqlite3 事务说明](https://docs.python.org/3.14/library/sqlite3.html#transaction-control)

启动脚本限制一个应用实例。M2 工作区另以 threading.RLock 和 Windows msvcrt 文件锁形成可重入的跨线程/跨进程写屏障，覆盖资料完整操作、备份冻结、恢复切换以及 db.transaction(write=True)。获取屏障后重新核对 active.json；旧浏览器会话持有的失活数据集路径不能继续写入。未核对的恢复日志也阻止普通业务写入。

恢复内部使用 maintenance_barrier，明确允许维护流程在持有同一锁时处理恢复日志和副本；这不是普通页面绕过保护的入口。active.json 更新还比较预期旧数据集 ID，避免用过期选择覆盖当前指针。只读列表不持有长事务；M1 保留入口的独立旧沙盒仍由既有 SQLite 事务规则管理。笔记 version 业务检查在 M4 实施。

### 4.2 迁移

M1 已实现并测试初始迁移、版本及校验和检查和失败回滚。M2 未更改 001_core.sql、未增加迁移，schema 仍为 1；完整备份服务已实现，但自动执行“迁移前完整备份”的升级编排尚未接入。当前只允许合成数据库。以下包含后续真实数据升级前必须补齐的流程。

1. 比较应用支持的 schema 版本与数据库版本；未知新版本拒绝写入。
2. 有真实数据时，迁移前先取得可验证的完整备份；当前仅在合成数据上演练。
3. 在副本上预检，再于明确的维护窗口运行每个版本的 SQL；事务失败回滚。
4. schema_migrations 的校验和防止已发布迁移脚本被静默改写；可同步 PRAGMA user_version 用于快速诊断，但不另立独立版本真相。
5. 对必须重建表的迁移，验证行数、约束、外键和关键字段；不把简单执行 SQL 成功当成迁移成功。
6. 不依赖下迁移撤销数据结构；回滚使用原应用版本和迁移前完整数据副本。

## 5. 文件操作与恢复设计

第 5.1–5.3 节为已实现的 M2 合成资料行为；第 5.4 节仍是 M4 笔记保存设计。资料服务不能访问真实学习文件。

### 5.1 路径规则

- 本地路径输入按路径处理，不拼接成 shell 命令；支持中文和空格。
- M2 文件操作只允许 .sandbox\m2 与 .sandbox\test-runs。来源另限制在 .sandbox\m2\sources 或测试运行下的 sources 目录；不把内部数据库、托管文件当作可任意导入的来源。
- 仅允许普通文件；V1 拒绝 UNC/网络路径、设备路径、目录、以及任一需跟随的 symlink/junction/reparse point。逐级检查祖先，避免只检查最终文件。
- 普通文件还必须只有一个硬链接；实际 Windows 硬链接、目录联接及路径边界由专项测试覆盖。这里只保护应用可观察的正常本机操作，不承诺抵抗具有同一账号权限的敌对进程。
- 托管目标由内部 UUID 和安全文件名生成，拒绝保留设备名、备用数据流语法、路径穿越和尾随点/空格等歧义。
- 目标路径解析后必须仍在指定数据集内，不能覆盖已有文件，不能把外部来源当作删除或替换目标。
- 不开启 Windows 长路径策略；支持范围以 M0/M2 实测为准，超出限制显示可操作错误。
- 数据目录不得位于云同步目录或网络共享中。权限不足时报告，不更改 ACL、不提权写入用户资料。

### 5.2 托管导入

1. 用户确认路径、主课程和存储模式；计算独立 request_id，重复提交可查已有操作结果。
2. 检查来源类型、可读性、大小、修改时间与路径约束，计算稳定 SHA-256；重复内容候选只提示，不自动合并。资料导入目前依赖复制错误报告空间不足，不宣称提前精确预估磁盘空间。
3. 在同一数据库事务中写入 pending 资料及 file_operations 的 planned 记录。分块复制到 .staging/<operation-id>/payload.part，目标以独占创建方式打开，不覆盖已存在文件。
4. 关闭并刷新文件，核对大小和内容；比较来源复制前后状态。来源期间发生变化则中止并报告，不能发布混合内容。
5. 将操作记为 staged；同卷 Windows 无覆盖重命名至 managed/<material-id>/payload<safe-extension>，记为 promoted。原中文文件名保留在资料名称和来源路径中。
6. 再次校验最终文件与基线；短数据库事务将资料改为 ready、状态 normal，并把操作标记 committed。只有此时 UI 显示成功。
7. 失败保留日志与文件现场，不删来源。用户显式执行 reconcile_operations 后，可完成匹配基线的完整暂存/最终文件；没有完整文件则保持 failed，内容不符或暂存/最终文件同时存在则标记 quarantined。不会自动重拷来源、移动残留或删除任何一份文件。

文件系统与 SQLite 不共享原子事务。即使最后数据库提交失败，已复制文件也可能存在；操作日志保存足够的目标和哈希信息供显式核对。当前没有自动清理或忽略失败导入的功能；failed/quarantined 状态阻止完整备份，无法判定时保留现场并人工处理。不能把“有恢复日志”表述为“所有失败均自动恢复”。

### 5.3 外部引用、检查与删除

外部引用只读取得元数据与 SHA-256 并保存路径，不能自动复制、改名或删除原文件。缺失与权限错误分别处理。检查大小和 mtime 可标记可能变化，完整哈希比较可清除仅由元数据变化产生的疑虑；观察结果永不覆盖导入基线。

用户重新定位外部引用时验证新路径和基线；相同内容直接重连，不同内容必须 confirm_changed=True。该确认只允许切换引用路径，保留 original_path 与 baseline_sha256，记录 observed_sha256 与检查时间并继续显示 possibly_changed；M2 没有覆盖基线的接口。托管资料来源路径失效不等于托管文件失效；已完成请求重试不要求原路径仍存在。

解除 task_materials 等关联仅改数据库，关联编辑界面在 M3/M4 实施。移出资料索引是逻辑删除，保留关联和文件。永久删除需已隐藏、无关联、已完成导入、目标内容仍符合基线，并逐字输入资料 UUID；写入 delete_managed_file 日志后仅删除与资料 ID 一致的内部托管目标。成功后记录 file_deleted_at 并保留删除记录，不能拿普通“缺失”状态冒充经确认删除。

删除已生效但数据库未更新时，显式核对可依据已确认意图及目标缺失补记；目标仍在时只标记未执行，不自动继续删除。无备份的永久删除不能回滚正文，外部引用原文件在任何删除路径中均不允许被操作。

### 5.4 笔记保存

以下在 M4 实施。M2 只验证已有合成版本能被完整备份恢复，不提供笔记保存服务。

1. 校验笔记 version 与当前版本文件哈希，冲突时保留编辑内容并拒绝静默覆盖。
2. 把新正文写为 .staging 内的新文件，计算哈希，刷新关闭；旧版本始终保持不变。
3. 发布到新的 revision-id.md，再在单个事务中新增 note_revisions、更新 notes.current_revision_id 和 version、完成 file_operations。
4. 失败由与资料导入相同的操作日志恢复机制处理；未提交版本不可冒充当前正文。
5. 恢复历史版本通过生成新版本完成。V1 不自动清理历史版本；备份包含所有保留版本。

## 6. 备份与恢复概览

完整操作步骤、确认范围与异常处理见 BACKUP_RESTORE.md；当前仅限合成工作区。

阅读专项的实施门槛：R1 首次保存阅读 PDF 和标记时就必须扩展完整备份，不能等 R2。现有清单和文件树严格限制类型，新目录不能直接塞入数据集。新增 schema 前先实现旧 schema 1 备份按旧规则验证、恢复到副本、迁移并验证后切换的兼容路径；原备份不可改写。已登记阅读 PDF 是持久数据，缩略图才可作为派生缓存。下文继续描述当前 M2 实现，不能外推为上述扩展已完成。

M2 已实现完整目录备份、独立验证、恢复前完整回滚副本、恢复到新数据集、活动指针比较切换、恢复日志核对和明确回滚。M2 实施轮的 43 项备份恢复专项测试与真实浏览器验证覆盖相应合成路径；本次文档调整没有重跑。实际断电、真实磁盘耗尽及完整 OS 断网不能由故障注入替代。

M2 使用可检查的备份目录：manifest.json、manifest.sha256、payload/ 中的 SQLite 快照、config.json、托管资料及全部保留 Markdown 版本。incomplete.json 保留最初创建记录；独立验证通过后才创建 complete.json 作为发布标记。不能仅凭 manifest.complete=true 或目录存在宣布完整备份。验证报告从清单派生返回，没有独立 report.json。

备份持有工作区写屏障，发现 pending/failed/quarantined 操作或未完成资料立即拒绝，不自动修复后继续。扫描并核对允许的内部文件树，未知残留、缺失或变更的已登记文件都会阻止完整备份。冻结写入后使用 sqlite3 backup API 取得数据库一致快照，从快照枚举全部托管正文和笔记历史，复制并逐项复核大小、哈希、数据库完整性、外键与逻辑引用；发布后释放屏障。SQLite backup API 只解决数据库快照，不会自动包含磁盘资料。[SQLite Backup API](https://www.sqlite.org/backup.html)

外部引用逐项记录 included=false、原始/当前路径和数据库记录的状态，并明确本次备份未读取或复查外部正文。逻辑隐藏仍存在的托管文件继续纳入；经确认物理删除的资料作为 deleted 清单记录，并验证与删除意图一致。M2 已以合成笔记及历史版本验证备份覆盖，M4 实现后仍须回归。

恢复在持有同一工作区维护屏障的显式页面操作中执行。先验证备份并展示范围，要求输入当前活动数据集 UUID；可同时固定预检后的 manifest SHA-256，拒绝预检后替换清单。写恢复日志、生成旧活动数据集完整回滚副本、复制到新的 UUID 数据集，校验全部正文和数据库关系、比较数据库逻辑内容并重新核对源清单，全部通过后才以预期旧数据集 ID 比较切换 control/active.json。当前只接受匹配的 schema 1，不自动迁移未知版本备份。

旧数据集、新数据集、恢复前副本与日志全部保留，不自动清理。切换使用同卷临时指针文件与替换；若切换后日志未完成，不能假定仍在旧数据集，也不能继续普通写入。显式 reconcile_restore 验证真实指针与相应数据后完成记录；无法判定时保持阻塞。rollback_restore 在验证旧数据集仍与保存副本一致后，先为当前数据制作完整副本，再比较切回旧指针。外部来源从未纳入文件覆盖范围。

目录格式也必须拒绝路径穿越、未知清单条目、重复目标、绝对内部路径、symlink/junction/reparse point 和越界解析。manifest 的哈希是损坏检测，不是数字签名或来源认证。

## 7. UI 与应用安全

- 资料路径导入是主要入口；浏览器上传无法可靠提供原始路径，因此不用于 external_reference。
- 表单明确提交，操作使用 request_id 和数据库约束抵抗重跑重复提交；成功后重新查询真实状态。
- Markdown 禁用原始 HTML/脚本，限制网络图片与嵌入，不生成可访问任意本地文件的 URL。
- 系统打开文件通过平台 API 传入已检查路径，不执行拼接的 shell 命令；V1 禁止一键执行脚本、可执行文件或快捷方式。
- 内嵌阅读须验证本地 PDF.js 资源、前后端消息、文件权限、中文路径和标注几何；未通过时保留现有外部打开能力供使用，但不能宣布阅读专项或完整 V1 已完成。
- 不记录正文或 API 密钥；诊断日志只保留处理问题必需的元数据，分享前去除私人路径。
- 不将 localhost 监听与恶意本机进程防护混为一谈；V1 不提供多用户账号或加密数据库。

## 8. 验证策略与异常路径

自动化分为领域单元测试、真实临时 SQLite/文件系统集成测试、关键 PoC/页面测试。故障注入针对可观察结果，如提交失败后重启能否重建正确状态，而不只是证明某个函数被调用。

| 类别 | 必测情形 | 成功标准 |
| --- | --- | --- |
| 数据关系 | 无效课程、同课程章节约束、允许跨课程资料、重复关联、归档 | 无孤儿和重复关联；跨课程引用来源可见 |
| 任务时间 | 仅日期、具体时间、无截止、完成/取消、跨日 | 今日/近期/逾期边界一致，日期不被当成零点 |
| 文件与路径 | 中文/空格、重名、空文件、大文件、来源变化、缺失、无权限、占用 | 原始内容不变，错误状态准确，无伪成功 |
| 路径边界 | ..、绝对恢复路径、设备名、ADS、UNC、symlink/junction | 拒绝越界，不修改系统或外部路径 |
| 中断恢复 | staged/promoted/提交前后故障、重复 request_id | 幂等恢复或明确待处理，绝不乱删来源 |
| 笔记 | 旧表单保存、外部修改、保存失败、历史恢复 | 无静默覆盖，当前指针及哈希一致 |
| 数据库 | 每连接 FK、忙锁、异常回滚、迁移失败、新版本拒绝 | 状态完整、旧数据可用、错误可解释 |
| 备份 | 一致快照、缺内部文件、未知内部残留、外部引用缺失 | 不能把不完整副本标为完整备份 |
| 恢复 | 清单损坏、哈希不符、路径攻击、磁盘满、切换失败 | 不影响旧活动数据，能按记录回滚 |
| 离线与运行 | 断外网、无 AI 配置、新终端、端口占用 | 基础流程可用，仍仅监听本机 |

不可在当前权限或机器条件下重现的用例应标记“未执行／使用故障注入”，不得写成已验证真实 OS 故障。自动化恢复测试必须至少覆盖一次完整备份 → 空位置恢复 → 比较关系及全部保留文件哈希。

## 9. 按依赖顺序的里程碑

调整后的顺序：**M0 → M1 → M2 → R0 → R1 → R2 → M3 → M4 → M5**。保留原编号与历史，不把阅读专项冒称为已完成 M3。R0/R1/R2 的目标、模块、顺序、自动/手动验收、完成标准及回滚详见 COURSEWARE_READER.md。

- R0：仅合成课件，验证本地转换保真、PDF.js 离线资源、Streamlit 组件生命周期与坐标变换；不迁移活动数据库。
- R1：课程书架/顺序、阅读/续读、书签/文字批注/重点疑问；同批完成版本模型、迁移、旧备份兼容与完整恢复。
- R2：荧光笔/框选/手写、编辑/撤销重做与标记筛选；验证缩放、重启和恢复后的所有几何标注，并完成整套阅读体验验收。

### M0：审计、设计与技术验证

当前进展：保留既有审计、设计和 PoC；M0 的 24 项自动化回归已纳入本轮全量测试。下面保留原阶段的目标与验收边界。

- **目标：** 明确范围、环境、隔离方案、技术风险与验收标准。
- **相关文件：** README、docs 下四份文档、项目依赖配置、保留的 app_m0.py 及 M0 测试、独立 .venv。
- **实现顺序：** 记录环境 → 确认需求与路径 → 建立隔离环境 → 依赖导入与 SQLite/路径/渲染 PoC → 文档交叉核对 → 记录实际结果。
- **自动化测试：** 合成数据验证 SQLite 约束/回滚/备份 API、中文空格路径、临时文件操作；具体已运行项目以状态文档为准。
- **手动验收：** 检查仅改动授权项目；查看本机 PoC；核对真实数据目录未创建、无真实文件导入。
- **完成标准：** M0 交付时文档一致，选定栈的基础启动条件已验证，未完成技术验证明确列出；M0 本身不提前实施 M1 业务。
- **风险与回滚：** 依赖兼容或浏览器验证受限时记录证据，保留可用方案；停止 PoC。仅项目内容可回退，不更改全局环境。

### M1：数据层与课程管理

当前进展：学期/课程服务、合成数据界面、核心 schema、迁移、持久化创建幂等及实际并发冲突已实现。49 项数据库、45 项服务、7 项 UI 自动化测试通过；真实浏览器的 8 项合成场景也已通过，具体范围见本文开头。未完成完整 OS 断网测试，不把本次浏览器验收外推为 M2–M5 已完成。

- **目标：** 可迁移的数据基础，学期/课程创建、编辑、搜索与归档。
- **实际模块：** src/plw/config.py、db.py、services.py、ui.py、migrations/001_core.sql、现保留的 app_m1.py、scripts/launch.py，以及 test_db.py、test_courses.py、test_m1_app.py。
- **实现顺序：** 连接与事务 → 迁移框架及核心关系 schema → 仓储 → 学期/课程服务 → 页面 → 合成数据验收。
- **自动化测试：** 每连接 PRAGMA、FK/CHECK/UNIQUE、组合 FK、允许跨课程资料关系、提交失败回滚、迁移校验和、未知版本拒绝。
- **手动验收：** 建两个学期及同名课程，编辑、筛选、归档、取消归档，重启仍可见；归档不删除历史关联。
- **完成标准：** 课程闭环可用且关系约束有意义地验证；尚未启用真实资料导入。
- **风险与回滚：** schema 缺陷在合成数据中修复；已有数据的未来升级必须迁移前备份。回退应用版本和对应数据副本，不靠删表修复。

### M2：文件管理与备份恢复

当前进展：资料双模式、持久化导入请求、显式操作核对、检查/重连、安全删除语义、完整备份、验证、新数据集恢复、恢复日志核对和回滚已实现。全量 247 项测试及真实浏览器 7 项合成场景通过；完整 OS 断网未执行，最后启动检查以状态文档为准。schema 仍为 1，001_core.sql 未改。

- **目标：** 安全添加两种资料、关联复用、检查/定位、完整备份及失败安全的恢复。
- **实际模块：** src/plw/materials.py、storage.py、locking.py、workspace.py、backups.py、ui_m2.py；db.py 写事务接入屏障，app.py 默认 M2，app_m1.py 保留上一阶段入口；对应合成测试及浏览器验收脚本。
- **实现顺序：** 路径边界 → 操作日志/恢复 → 托管复制与引用 → 去重提示/检查/定位 → 删除语义 → 备份 → 临时恢复与活动数据集切换。
- **自动化测试：** 已执行资料 28、共享边界 45、备份恢复 43、M2 UI 6 项及既有 125 项回归。覆盖来源不变、中文空格、并发重试、引用缺失/变化、复制/提交中断、硬链接/目录联接边界、合成笔记全部历史、损坏清单及文件、未知条目、切换失败与恢复日志。权限、磁盘耗尽和异常退出中部分采用明确故障注入，不能表述为全部实际 OS 故障均重现。
- **界面验收：** 真实浏览器已验证托管/引用导入、相同请求重试、索引隐藏、完整备份、错误确认保护、新数据集恢复、回滚及来源/M1 数据保持不变。系统阅读器打开全部恢复文件、完整断网等未执行动作不能据此算通过；引用移动与重连由真实文件系统专项测试覆盖。
- **完成标准：** 一次端到端完整恢复与关键失败回滚通过，报告清楚列出外部引用正文未包含且未重新检查。当前合成门槛已通过，仍须另行明确真实目录及首次导入范围；不得由测试结果隐含创建真实目录。
- **风险与回滚：** 磁盘空间、来源变化和文件占用；半成品保留日志与现场，未解决失败阻止完整备份。恢复保留旧数据集和前副本；未知切换结果先核对。没有自动清理、忽略失败导入或修复损坏当前集后强制恢复的承诺。

### M3：任务与关联

当前进展：仅 tasks、task_materials 等表结构已建立；任务服务、今日/近期/逾期查询与任务界面尚未实现。

- **目标：** 在已完成的课程阅读首页上补充日常任务闭环，保留继续阅读与书架主入口。
- **预计模块：** domain/tasks、services/tasks、task_materials 仓储、ui/home、ui/tasks。
- **实现顺序：** 时间/状态语义 → CRUD 与关联 → 今日/近期/逾期查询 → 首页与任务详情。
- **自动化测试：** 截止时间边界、完成/取消/重开、计划日期、非负耗时、多个任务复用一份资料、跨课程引用与解除隔离。
- **手动验收：** 创建六类任务，关联多资料，完成后重开；查看逾期和今日分类；打开资料与来源课程。
- **完成标准：** 首页能指向下一步学习动作，分类无明显歧义；任务操作不影响文件正文。
- **风险与回滚：** 时区与重跑重复提交；用明确字段及幂等请求防护。新增查询/页面可回退，迁移按版本处理。

### M4：章节、笔记、公式与阅读关联

当前进展：仅章节、知识点、笔记版本及关联表结构已建立。M0 的渲染 PoC 不代表笔记编辑、版本正文保存、历史恢复或 PDF 业务已经实现。

- **目标：** 在阅读专项基础上增加课程知识组织、可恢复 Markdown 笔记及课件页关联。
- **预计模块：** services/chapters、knowledge_points、notes、note_revisions、ui/notes、阅读版页面链接；备份覆盖回归测试。
- **实现顺序：** 章节及知识状态 → 笔记版本文件保存 → 关联与历史恢复 → 编辑/预览 → 公式离线验证 → 与已有阅读版本/页面双向关联。
- **自动化测试：** 章节环/跨课程章节拒绝、旧版本冲突、文件写入/DB 提交失败、历史恢复生成新版本、保存内容哈希、全部版本备份恢复。
- **手动验收：** 输入中文、行内/块级公式；断网预览；关联跨课程资料；打开 PDF；故意制造外部修改并确认不静默覆盖。
- **完成标准：** 保存成功内容经重启一致，失败时可解释；公式离线可用，笔记与已完成阅读专项的具体版本/页面可相互定位。
- **风险与回滚：** Markdown 网络嵌入、渲染安全、编辑冲突；禁用不合格组件，保留原始 Markdown 与全部版本，回退 UI 不损坏正文。

### M5：体验、测试与发布

- **目标：** 可重复安装/启动、清晰错误处理、完整验收和操作说明。
- **预计模块：** 搜索、配置、日志、启动脚本、依赖锁定、README/操作手册、集成与验收测试。
- **实现顺序：** 体验修正 → 全闭环/异常路径回归 → 新会话启动 → 外网断开验收 → 完整恢复演练 → 文档与发布清单。
- **自动化测试：** 关键服务回归、迁移及备份兼容、目录边界、文件完整性、恢复失败不改变活动集、未开启网络依赖的检查。
- **手动验收：** 未激活 Conda 的 PowerShell 7 启动；本机监听核对；断网完成课程到备份闭环；按手册恢复并回滚；合成数据规模实测。
- **完成标准：** 核心需求验收通过、限制与未执行项公开、依赖可复现；无必需 AI 配置，真实文件的安全门槛可解释。
- **风险与回滚：** 打包差异、依赖漂移、用户误恢复；优先保留已验证虚拟环境发布方式及上一版本，升级前完整备份；不把单文件打包作为首发硬门槛。

## 10. 主要风险与控制

| 风险 | 影响 | 控制与停止条件 |
| --- | --- | --- |
| Streamlit 重跑或多标签页 | 重复导入、旧表单覆盖 | 显式提交、request_id、数据库约束、笔记版本检查 |
| 文件与数据库非原子 | 有文件无索引或相反 | file_operations、唯一目标、显式核对；不能判断时保留并阻止完整备份 |
| 外部引用移动或改变 | 资料不可用、内容不一致 | 状态检查、显式重新定位、基线哈希；不删除原文件 |
| 备份遗漏正文 | 看似成功但无法恢复 | 从快照枚举必需文件、逐项哈希、空位置恢复演练 |
| 恢复路径越界 | 覆盖其他用户文件 | 白名单条目、规范相对路径、拒绝 reparse point、新数据集恢复 |
| 同盘备份 | 整盘故障仍丢失 | 明确限制，完成验证后允许人工保存到第二介质 |
| 阅读组件依赖网络或重跑丢状态 | 离线阅读、手写不可用 | R0 本地资源/生命周期实测；失败不能降低核心验收门槛 |
| PPT 更新或页面坐标变化 | 批注错位、标记指向错误知识 | 固定阅读版本、页面坐标、禁止自动跨版本迁移 |
| 阅读版被当缓存或新 schema 拒绝旧备份 | 标记无页面、旧备份无法恢复 | R1 同步扩充清单/旧版兼容；阅读版持久保留 |
| 版本迁移失败 | 无法启动或数据关系损坏 | 副本预检、事务、版本拒绝、完整回滚副本 |
| 长路径/权限/占用 | 文件处理失败 | 项目内实测、准确错误、有限重试；不改系统设置 |
| 范围扩张 | 无法完成核心闭环 | 优先 R0/R1/R2 阅读体验，再 M3/M4/M5；AI/同步/OCR/提醒保持后置 |

## 11. 仍需在对应阶段核实

- M0–M2 的具体依赖版本、命令及通过/未通过项由 PROJECT_STATUS.md 记录；M1 与 M2 各自的浏览器场景分别登记，完整 OS 断网仍待验证。M2 未安装依赖或修改系统设置。
- 实际创建 E:\PLW-Data 和 E:\PLW-Backups，以及第一次使用真实资料，必须在具备安全门槛后另行明确，不由文档、表结构或 M2 合成测试隐含授权。
- R0 决定 PDF.js 本地资源和 Streamlit 阅读组件的可行性；转换路径存在不等于转换效果已验证。默认阅读器/PowerPoint 原件入口始终保留。
- M5 决定是否有必要提供离线安装包或原生桌面壳；不能把这些选项变成现阶段依赖。
