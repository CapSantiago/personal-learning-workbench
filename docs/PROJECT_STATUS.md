# PLW 项目状态

更新：2026-10-17，Asia/Shanghai。源码版本 **0.3.1**；新学习库/云端目标 **schema4**，已有Windows本地schema3保持兼容，不自动迁移。GitHub账号：**CapSantiago**。云端空库已启动，Windows已通过私有HTTPS登录；iPad功能、持久化重启及完整备份下载验收待完成。

## 2026-10-17 管理连接恢复与Tailscale登录

### 当前访问排错进展

- 用户实机日志确认入口修复包校验、离线衍生镜像构建、合成检查通过；更新前生成完整备份`PLW-2e5fd5d2-3223-4451-aaad-e9855d38ca16.zip`，SHA-256 `2913b64ae8625ecb1879dbdbfae0c84246a1467b11693e75f246c037f9a51764`，原dataset_id保持`fe2dfea7-f600-4f01-9d12-ab38a917ad8d`。部署切至`plw:0.3.1-entryfix-1381e66`，启动健康重试后通过；旧环境快照`/srv/plw/private/deploy.env.before-entryfix.wXfBgg5J`。随后助手Windows实测普通登录页200、证书通过（0.126秒），外部顶层入口303、登录页200，原403已消失。用户更新后重新登录、业务操作、整机重启和失败回退仍待验收。
- 安装日志最初两次空响应产生JSONDecodeError，后续健康检查通过；已修正源码启动轮询对空响应的处理，属于诊断输出修正，不需在已成功的服务器重跑。原发布ZIP不更改；若未来再次使用应生成新版本文件和摘要。
- 用户保存UDP41641规则后，Windows实测云节点已直连公网41641，12ms；HTTPS登录页200、证书验证正常，该次请求0.138秒。后续再次对照普通访问200、外部顶层导航403，说明旧入口误拦仍未修复。下列香港中继记录是此前状态。
- 已准备独立入口修复包`PLW-Entry-Forbidden-fix-20261017.zip`（10100字节，SHA-256 `7cf784a522463b8f8df37d4b1f2c8e72523ea943bdab49193043ee848780bd36`）。相关测试41通过（12.59秒），额外合成检查在修复模块通过、旧模块被成功识别为失败，Bash语法和ZIP CRC通过。Linux构建、备份、更新及回退尚未执行；参见[入口更新说明](ENTRY_NAVIGATION_FIX.md)。
- 最新用户截图确认已登录Streamlit云端主页，显示独立空库首次课程引导。Windows系统代理保持开启，PLW绕过项已实际生效；既有Windows学习资料尚未迁移。
- 新连接实测：云节点经DERP(hkg)中继，三次172/175/185ms，尚未直连。本机UDP可用、NAT映射随目标变化；建议先检查云端UDP41641入方向规则，不能承诺仅开放该端口一定建立直连。3Mbps带宽也限制大文件首次传输；暂不建议购买升级。
- DNS持久化工具与[操作说明](ALIYUN_DNS_FIX.md)已准备：精确四条例外、幂等检查和定向移除，systemd ExecStartPost在Tailscale每次启动后补充。安装、服务重启与整机重启仍需用户实机验收。

- 用户实机确认eth0的DNS为100.100.2.136/138；tailscaled日志中ACME域名解析超时，ts-input对100.64.0.0/10的DROP计数持续增长。添加仅限eth0、这两个DNS、UDP/TCP源端口53、ESTABLISHED/REPLY的四条带标记例外后，解析恢复且ACME目录返回200。规则目前仅运行时生效，持久化脚本已准备，尚未在Linux安装/验收。
- 代理在Windows真实执行Tailscale状态、域名解析、TCP443及TLS测试：电脑已连接，云节点在线；DNS修复后证书校验成功，匿名入口303重定向到登录页，跟随重定向200。未输入网站密码或验证已登录功能。
- 本机Clash Verge的系统代理开启时，同网址经127.0.0.1:7897出现TLS握手失败，绕代理直连200；需在Clash Verge为PLW域名及对应Tailscale IP添加系统代理绕过项。此结论来自同机对照，不是推测；代理配置未被自动修改。
- 另复现跨站顶层导航403：旧PrivateAccess拒绝所有Sec-Fetch-Site: cross-site。已局部修复，仅允许无Origin、navigate/document的GET进入根路径或登录页；仍需登录，其他跨站读取、上传、POST、iframe和WebSocket限制保留。Windows相关测试41通过，11.96秒；云端旧镜像尚未应用修复。手动从地址栏输入网站地址可避开这一导航问题。

以下为此前同日的阶段记录，以本节最新进展为准。

- 用户已通过VNC登录，确认云助手服务启动；重新读取systemd配置并重启云助手后，控制台状态恢复正常。Workbench私网连接仍失败，切换公网与密码认证后成功。用户已自行更换截图中暴露的密码；不记录密码或授权凭证。
- 用户新截图确认原部署包328文件清单通过。离线安装器发现既有Tailscale而拒绝覆盖，随后`tailscale up --hostname=plw`及`tailscale status`正常返回，列表包含当前Linux节点`plw`。本轮不重复安装，不重复prepare。
- 注意潜在CGNAT冲突：Workbench私网来源`100.104.0.0/16`属于Tailscale的`100.64.0.0/10`防伪规则范围。[Tailscale官方规则说明](https://tailscale.com/docs/reference/netfilter-modes)指出非tailscale0接口收到该来源范围时会丢弃。这与公网成功/私网失败相符，但尚未检查此服务器规则或计数器，不能记为已确认根因。只读核查后再决定是否需要最小网络修复，不关闭防火墙或全局取消防护。
- 用户提供`tailscale serve status`确认Serve入口为HTTPS、`tailnet only`，根路径代理至`http://127.0.0.1:8501`。这是私有入口配置结果，不等于已验证证书签发或浏览器端到端访问。
- 用户提供最新完整日志：单账号配置预检`valid: true`，平台linux、PDF依赖就绪、监听127.0.0.1:8501。随后初始化独立空云库，Compose容器`plw-plw-1`启动，回环`/plw-health`两次返回`ok: true, version: 0.3.1, initialized: true`。此结果来自用户实机执行，不是代理远程运行。
- 最后快照为`Up 5 seconds (health: starting)`，Docker自身健康状态仍需复查；不能将应用回环检查直接记为容器已healthy。真实HTTPS证书与登录、PDF.js浏览器交互、Compose重启/更新、真实备份下载及设备验收仍待执行。没有迁移Windows正式资料，也未把云端空库覆盖到本地。
- 下一步：在设备安装/连接同账号Tailscale，访问私有HTTPS并登录PLW，先用合成资料验收；通过后再测试重启持久化及完整备份恢复，正式资料迁移另行确认。

## 2026-10-16 阿里云部署推进

### 最新实机结果（用户执行并提供终端日志）

- `resume_linux_acceptance.sh`的SHA-256与原部署包328文件清单通过；镜像`plw:0.3.1-offline-21dab82`在Linux/AMD64构建成功，镜像ID为`sha256:2c6b5a778bb57f6dbf2c6402b9f75cd4f85e92af7d1463d21fb2912ed76ba5e9`。
- 两个独立容器的seed/check均`passed: true`：schema4、中文PDF上传、两页阅读副本、高亮、书签、进度、Markdown公式笔记、任务完成、完整ZIP备份、隔离恢复；36个合成文件哈希一致。证据目录`/var/tmp/plw-acceptance.xda3fje0`。
- 此结果证明合成数据在两个容器之间保留，不等于Compose正式服务重启/更新、HTTPS登录、PDF.js浏览器交互或iPad真机验收。未迁移真实学习资料。
- 下一步：使用原离线安装器安装Tailscale，用户本人登录授权，配置私有HTTPS及PLW单账号，再初始化新的空云库并启动。保留原部署包与合成证据，不重复prepare。

### 先前排错记录（其中“待验证”描述当时状态）

- 最新用户日志确认离线Docker构建已到`#15 DONE 37.8s`，随后合成验收在子进程生成PDF时退出1，错误输出被CalledProcessError隐藏，未开始正式网站服务。
- 原验收脚本直接让PdfWriter写stdout，而pypdf需要tell/定位能力。已改为先写BytesIO再输出字节，并保留子进程错误详情。实际pypdf的不可定位stdout回归通过，Windows新合成seed/check与36文件哈希验证通过；云端续跑结果待用户提供。
- 提供`scripts/resume_linux_acceptance.sh`：校验原包、复用现有镜像、仅在内存修正旧验收脚本，在新的合成卷用两个容器执行seed/check。不重新构建、不改原包、不挂载正式数据目录。已核对原包中的替换目标、Python编译与Bash语法；当前不声称Linux功能验收已通过。

- 用户实机反馈：221MB部署ZIP校验OK、328条文件清单通过、Python基础镜像已成功Docker load；随后旧安装器误将Docker29返回的manifest摘要与config摘要比较而停止，尚未构建PLW。
- 已按containerd导入规则从原始config与四层内容重建清单，得到`sha256:86dec9b258fdaaf77fe397b059e1ad87210afcdfca5a028c9d795c6b65d0d1ba`，与用户实机inspect完全一致。新增兼容验证器同时核对平台、层序列、config和重建清单摘要，不跳过校验。
- 生成3042字节修复包`.sandbox/releases/PLW-Docker29-fix-20261016.zip`，SHA-256 `61808942f00aa17dd869b6cb20951ad2721ab86957018a9f2ff9c22fd5406381`。在原部署目录之外运行，原包字节及清单保持不变，仅在内存替换旧校验步骤后继续prepare。19项相关测试通过，生成的Bash语法通过；云端补丁执行和应用构建仍待用户输出。

- 用户已自行购买杭州 ECS 年付99元套餐：Ubuntu24.04 x86_64、2核2GB、40GB、3Mbps；账户操作和付费由用户完成。用户终端输出确认 Docker29.9.1、Compose v5.6.0、服务active，Git2.43.0已安装。
- ECS无法直连Docker Hub，拉取Python基础镜像超时；阿里云官方加速器停止同步最新镜像，改用Windows中转的离线部署包，不使用收费加速或不明公共代理。
- 官方Python镜像、43个Linux/AMD64 CPython3.14依赖wheel、Tailscale官方静态安装包已下载并逐项核对SHA-256。镜像另核对配置、压缩层和解压层摘要。离线pip解析覆盖全部服务器依赖，无本机依赖安装。
- 增加离线包清单校验、限定文件提取、分阶段安装脚本与合成验收脚本。仅prepare阶段构建及测试；账号设置/Tailscale授权另行交互，不内置任何真实密码。真实学习数据不进入包。
- Windows合成seed/check两进程通过：课程、中文PDF、阅读副本、高亮/书签/进度、笔记/公式、任务完成、完整ZIP及隔离恢复，36个文件哈希保留。针对离线包、云兼容、认证的37项pytest通过。Bash安装脚本语法通过。此处不是Linux容器执行结果。
- 浏览器控制工具初始化/重试仍因Windows中文路径的`permission path cannot be represented losslessly`失败，没有接管阿里云Workbench，也未取得其他服务器认证通道。网站上传/容器运行/私有HTTPS/真机访问尚未执行，不能声称上线。
- 下一步按[阿里云离线部署](ALIYUN_OFFLINE_DEPLOYMENT.md)：上传校验 → prepare导入构建与隔离验收 → Tailscale用户授权 → 单账号配置 → 新空云库 → 私有HTTPS验收。正式学习资料不自动迁移。
- 离线包已实际生成并重新读取校验：`.sandbox/releases/PLW-0.3.1-offline-linux-amd64-20261016.zip`，329个文件、221463298字节；SHA-256为`fe4e9db84497e91facaf9efb5ea4118b1291c866482ec14dad274fd9b4817bd5`。包内源码对应`21dab82`，已推送并核对GitHub远程；后续仅状态文档变化不改变该包快照。
- 最后只读尝试既有SSH通道，因本机没有已验证的服务器ED25519主机密钥而停止（StrictHostKeyChecking=yes），未接受未知密钥、未输入密码、未运行远程命令。需要恢复浏览器控制或用户核对主机指纹后建立SSH管理通道。

以下为此前阶段记录；“没有云实例”等表述只描述2026-10-15状态。

## 当前阶段

- **M1已完成**：检查项目结构、运行入口、Windows依赖、配置、路径、数据库、上传、登录、阅读、备份与现有测试。首次审计时无Git；后续已初始化main，并确认创建CapSantiago/personal-learning-workbench私有仓库。Docker27.5.1客户端存在但引擎未运行，WSL没有发行版。
- **M2代码准备、Windows验收、Linux离线构建与合成容器验收已完成**。正式Compose启动、健康检查、重启及更新持久化仍待验收。本机没有安装Docker/WSL或修改系统。
- M3已准备Tailscale部署步骤、完整ZIP备份下载与迁移维护命令；用户已购买阿里云实例，真实Tailscale授权、HTTPS及正式资料迁移尚未执行。
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

1. 已在阿里云AMD64完成构建与合成容器验收；继续正式Compose空库启动、健康检查、账号登录与PDF核心浏览器功能、重启及重建持久化、恢复/回滚。剩余项目完成前M2不算最终全部验收通过。
2. M3：在现有阿里云实例上完成Tailscale登录/HTTPS；新空云库验证后，在确认范围后迁移正式完整备份。真实iPad/iPhone不同网络、Windows关机后访问、跨设备批注保存、PDF下载离线均待测。
3. M4：源码已推送并克隆校验；有云主机后实跑成功更新、构建失败、健康失败、旧镜像回退、版本显示及数据保留。
4. M5：在真机上定位后局部修复触控、横竖屏、笔记任务编辑；基础manifest/图标/更新提示不阻塞上线，不开发离线双向同步。

## 文档和证据

- [CLOUD_DEPLOYMENT](CLOUD_DEPLOYMENT.md)：最小方案、免费政策、Docker/Tailscale步骤、当前限制。
- [CLOUD_DATA_BACKUP](CLOUD_DATA_BACKUP.md)：下载、校验、迁移、恢复与隔离演练。
- [UPDATE_WORKFLOW](UPDATE_WORKFLOW.md)：Git边界、更新脚本及回退。
- [CLOUD_TEST_REPORT](CLOUD_TEST_REPORT.md)：已执行/待执行测试矩阵。
- 本轮证据：`.sandbox/cloud-implementation/`；浏览器：`.sandbox/test-runs/cloud-browser-95b93260-a98a-4b1d-aee1-aa01ada2108e/evidence/`。
- 上一版0.3.0状态保存在[history/V030_STATUS.md](history/V030_STATUS.md)。
