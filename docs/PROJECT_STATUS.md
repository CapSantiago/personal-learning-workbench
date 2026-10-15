# PLW 项目状态

更新：2026-10-15，Asia/Shanghai。源码版本 **0.3.1**；新学习库/云端目标 **schema4**，已有Windows本地schema3保持兼容，不自动迁移。GitHub账号：**CapSantiago**。当前仍是本机网站，尚未部署云端。

## 当前阶段

- **M1已完成**：检查项目结构、运行入口、Windows依赖、配置、路径、数据库、上传、登录、阅读、备份与现有测试。首次审计时无Git；后续已初始化main，并确认创建CapSantiago/personal-learning-workbench私有仓库。Docker27.5.1客户端存在但引擎未运行，WSL没有发行版。
- **M2代码准备与Windows验收已完成；Linux容器验收未完成**。用户明确选择先完成代码与Windows测试，容器测试留待环境就绪；没有安装Docker/WSL或修改系统。
- M3已准备Tailscale部署步骤、完整ZIP备份下载与迁移维护命令；没有创建云实例、配置真实Tailscale或迁移正式学习资料。
- M4代码托管已完成：已初始化本地main，验证账号并创建[CapSantiago/personal-learning-workbench私有仓库](https://github.com/CapSantiago/personal-learning-workbench)，首次提交`b9bd36d`已推送。云端更新/失败回退未实际运行。
- M5沿用现有响应式PDF.js阅读器；真机Safari/Pencil待验证，PWA基础改造延期，不承诺整站离线。

## 实际改造

1. 平台边界：`platform_lock.py`提供Windows msvcrt/Linux flock，写屏障保留；锁键在Linux区分大小写。存储/数据库根来自配置，项目根由文件位置解析，云端不依赖E盘或Codex运行时。Linux原子指针发布增加目录fsync。
2. 追加`004_portable_material_paths.sql`：仅放宽资料来源路径元数据为Windows或POSIX，旧001–003不改。使用SQLite受控表重建，事务前暂时关闭FK执行，提交前检查所有外键，事务后重新开启；失败回滚。托管正文按相对路径读取，不改旧行。
3. Windows现有schema3本地模式继续可用。云端需要schema4；升级通过完整备份恢复到新副本完成，原库/原备份保留。没有运行正式库迁移。
4. Dockerfile、compose.yaml、.env.example、.dockerignore：Python3.14单进程、非root、代码只读、宿主机独立持久目录、Linux host网络下仅回环8501、内部健康检查。云端账号与镜像/学习备份分离。
5. 云端“生成完整备份包/下载完整备份包”：复用原格式1清单与payload，ZIP逐文件校验、登录保护、下载时SHA复核；拒绝路径跳转/链接/重复/超量，恢复只在新目录验证后切换。备份包不含账号配置。
6. `cloud_data.py`提供status/init/backup/verify/restore/rollback；恢复与初始化持有服务锁。`setup_private.py --cloud-defaults`提供Docker路径，密码交互输入。云端屏蔽内部目录展示和未处理错误详情。
7. `update_cloud.sh <ref>`按明确Git commit构建，更新前备份，健康失败退回旧镜像；不自动迁移schema、不删除卷。脚本只有语法校验，实际Docker部署与回退仍待验收。

## 实际验证结果

- **最终全量Windows pytest：579 passed in 121.12s，无跳过**。包含原566项与新13项。日志：`.sandbox/cloud-implementation/final-tests.txt`。
- 第一批核心150项通过。首轮全量574通过/2失败，是历史schema3测试固定版本及故障注入目标未随004更新；已保持原验证目的修正，并在最终579项中通过。
- 新覆盖：schema3→4保留旧库、关联与内容；迁移004故意失败的完整回滚；POSIX来源元数据；ZIP隔离恢复、恶意路径与损坏拒绝；登录下载及篡改拒绝；内部健康边界；Windows旧schema3首页可用且数据库字节不变。
- `pip install --dry-run --ignore-installed --only-binary=:all:`分别解析Linux ARM64/AMD64、CPython3.14依赖成功，未安装软件。报告：`arm64-dependencies.json`、`amd64-dependencies.json`。这是安装包解析，不是Linux运行证明。
- Docker Compose配置解析退出0；两个Bash部署脚本分别语法检查通过。没有执行Docker build/up/restart。
- Windows独立合成网站实际Edge浏览器：原5组私有阅读/下载/上传PDF/注销断连/设备文件离线打开通过；新820px平板尺寸备份生成、原生ZIP下载、复制链接匿名401通过，无外部请求或浏览器错误。
- 浏览器下载的ZIP通过维护CLI校验，并恢复至另一隔离目录；新库schema4。合成服务进程重启后7个数据文件/指针哈希不变。**不是容器重启测试。**
- Windows正常启动器8501健康HTTP200；合成私人网站8505健康HTTP200、version0.3.1。只监听127.0.0.1。

## GitHub首次发布验收（2026-10-15续轮）

- 用户确认新建`personal-learning-workbench`私有仓库。API验证现有凭据的登录账号为CapSantiago，创建后确认private=true；凭据仅在内存使用，未写入代码、远程URL或报告。
- 首次提交357个源码/文档文件，约19.4MB；提交清单没有学习数据库、PDF/PPT、ZIP备份、账号配置、Token、私钥或虚拟环境。源码令牌/私钥格式扫描无发现，忽略规则不被视作绝对泄密检测。
- `.gitattributes`让迁移SQL及PDF.js资源保持原始字节；211个敏感文件在暂存区和GitHub重新克隆中均与本机原件一致，避免换行转换破坏历史校验和。
- GitHub远程重新克隆后，独立合成配置运行`launch_private.py --check`通过，未创建学习数据目录。不是Linux容器或完整579项在新克隆中重跑。
- Git直连失败后，仅为发布/克隆命令使用当前系统已有代理；没有修改系统代理或全局Git配置。本轮只修改代码托管配置与文档，没有执行应用功能测试、云部署或正式数据操作。
- 证据：`.sandbox/github-index-audit.json`、`github-repository.json`、`github-clone-report.json`。当前Docker引擎仍不可用，Oracle账号状态尚待用户确认。

## 正式数据与费用说明

审计前后`E:\PLW-Data`除可重建cache外135个文件哈希完全一致：无新增、无修改。正式数据库、课程、课件、笔记及活动指针没有被迁移或写入。测试全部在`.sandbox/test-runs`。没有上传学习资料、创建云账号/实例、购买域名/服务、修改Conda/ROS/SRTP环境或系统设置。

按2026-10-15 Oracle官方文档，Always Free A1为总计2 OCPU/12GB，启动盘/块卷合计200GB，存在库存不足及闲置回收；账号实际可用性尚未验证。Tailscale个人非商业计划免费。来源与操作步骤见CLOUD_DEPLOYMENT。无法获得免费资源时先向用户说明，不擅自升级收费。

## 下一步与验收门槛

1. 准备可用Linux Docker环境（用户后续提供云端或本机环境），构建ARM64镜像、独立空卷运行、账号登录与PDF核心功能、重启及重建持久化、完整恢复/回滚。此项完成前M2不算最终验收通过。
2. M3：用户注册Oracle并确认免费库存、Tailscale登录/HTTPS；先合成部署，再在确认范围后迁移正式完整备份。真实iPad/iPhone不同网络、Windows关机后访问、跨设备批注保存、PDF下载离线均待测。
3. M4：源码已推送并克隆校验；有云主机后实跑成功更新、构建失败、健康失败、旧镜像回退、版本显示及数据保留。
4. M5：在真机上定位后局部修复触控、横竖屏、笔记任务编辑；基础manifest/图标/更新提示不阻塞上线，不开发离线双向同步。

## 文档和证据

- [CLOUD_DEPLOYMENT](CLOUD_DEPLOYMENT.md)：最小方案、免费政策、Docker/Tailscale步骤、当前限制。
- [CLOUD_DATA_BACKUP](CLOUD_DATA_BACKUP.md)：下载、校验、迁移、恢复与隔离演练。
- [UPDATE_WORKFLOW](UPDATE_WORKFLOW.md)：Git边界、更新脚本及回退。
- [CLOUD_TEST_REPORT](CLOUD_TEST_REPORT.md)：已执行/待执行测试矩阵。
- 本轮证据：`.sandbox/cloud-implementation/`；浏览器：`.sandbox/test-runs/cloud-browser-95b93260-a98a-4b1d-aee1-aa01ada2108e/evidence/`。
- 上一版0.3.0状态保存在[history/V030_STATUS.md](history/V030_STATUS.md)。
