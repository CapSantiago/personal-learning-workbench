# 云端准备测试报告

## reader-rangefix实际部署后，真实阅读仍空白

- 用户安装截图确认 `plw:0.3.1-reader-rangefix-20261017` 构建并启动，输出 READER RANGE HOTFIX STARTED；完整框架检查通过：首次identity长度1048591、范围65536、worker2186232→474803字节。完整备份complete=true、4文件，原数据集不变，阅读副本大小29613390且摘要与原件一致。没有执行失败回退演练。
- 用户同时提供的真实浏览器截图仍为空白，提示“正在读取课件…”，缩略图也未显示。此次部署和合成检查不能视为解决实际阅读；完整处理链gzip缺陷已复现并修正，但尚不能证明它是实际失败的唯一因素。
- 下一步需取得用户已登录浏览器中plw-reader请求的实时状态/响应或HAR，再区分worker、初始PDF、范围请求和网络停滞；不继续根据画布空白推断原因或打新包。浏览器接管运行时本轮仍初始化失败，未获取登录会话。

## readerfix部署后真实阅读仍失败与完整处理链回归

- 用户实际截图：重新登录成功，阅读器新加载提示显示已接收1.0MB，但页面/缩略图仍空白。不能把已部署、ready、健康或原81项测试通过记成用户阅读成功。
- 本地复现：加入生产st.App所用create_streamlit_middleware后，旧代码的200 PDF被gzip，响应不再有原始Content-Length；PDF.js范围发现要求identity和原始长度。新增回归在旧代码失败，显式identity后通过。此前裸Starlette烟雾遗漏框架压缩层，现验证器已加入真实中间件及首次完整200检查。
- 新补丁仅变更reader_runtime.py的响应表示，PDF阅读/下载显式identity，vendor保持自己选择的gzip/identity；不改变课件、前端、数据库、登录或网络配置。新包12655字节，ZIP摘要/载荷与Bash语法通过；Linux实际部署、真实阅读与标记仍待验收。
- 最终相关回归82项通过（20.10秒）；独立真实中间件烟雾通过：`PDF discovery identity length 1048591; range 65536 bytes; worker 2186232 -> 472948 bytes`。没有因此重跑无关业务测试或改写原发布ZIP。
- 用户恢复本机Tailscale后助手客户端Running、SelfOnline=true；外部HTTPS登录页200、TLS验证通过、0.074584秒。不是登录后PDF请求的检查，不能代替用户页面验收。

## 2026-10-17 阅读加载补丁实际部署（用户执行日志）

- ZIP与全部载荷摘要、旧镜像及模块检查通过；离线构建 `plw:0.3.1-readerfix-20261017` 成功。镜像配置摘要 `sha256:cd3eba9a601ee5cf53bd39d22ecbe7b913c74d3415c8c28e54797412b02be488`，manifest list `sha256:2bb485ec6337bf90d907888512375319f621fd45e0a3b9dbc5862b0a666dc94d`。
- 容器内实际检查通过：`PDF range 65536/1048591 bytes; worker 2186232 -> 474803 bytes`。这是隔离合成检查，不是用户实际阅读页面已显示的证据。
- 切换前备份 `c02bac3c-0cb3-4c15-ba2b-10f4aa3cc2c9`，4文件、59550445字节、schema4、complete=true，原数据集不变；阅读副本 `4671e11e-7a63-4436-ab28-2ccfd46fdece` 摘要与原件一致。ZIP59553321字节，SHA-256 `e3660b8d00cfdb938695854b2f7916eb202c10beb7d39a2cb6f22dc7860f85c1`。
- 容器启动并通过安装器回环健康，输出 `READER LOADING HOTFIX STARTED`；旧环境 `/srv/plw/private/deploy.env.before-readerfix.otp9vSjp`。未执行失败回退演练。真实浏览器第一页、翻页与标记保存待用户验收。
- 本轮助手客户端 Tailscale 返回 NoState；普通域名解析失败，固定已知私网IP连接超时，因此未完成外部HTTPS登录页复测，不能从客户端失败反推云服务故障。

## 2026-10-17 手机热点与阅读加载补丁准备

- 热点下客户端TSMP 27ms、DISCO 29–39ms、ICMP 37–60ms；同一2MiB合成文件 Taildrop 10.34秒完成。原Wi-Fi的SCP对照167秒使用不同工具，不写成严格吞吐倍数。未修改网络配置、重启Tailscale或新增公网服务。
- 用户刷新后云端PDF阅读仍空白，35页元数据和导入ready不等于页面渲染成功。本地原件第一页只读渲染正常，尚未取得该空白时刻资源请求的响应状态。
- 阅读加载补丁相关81项Windows合成测试通过（22.99秒），前端语法、Bash语法通过；独立ASGI检查确认206只返回64KiB，worker 2186232→472948字节，身份验证/跨站/篡改/旧数据集保护保留。原部署包不改动。
- 新ZIP `PLW-Reader-Loading-fix-20261017.zip` 21716字节，CRC及载荷核对通过。尚未上传或执行Linux容器内检查、备份/切换/健康检查及真实阅读验收；安装器包含这些部署检查与失败回退。正常网页上传和原Wi-Fi下性能也未验收。

## 2026-10-17 真实 PDF 暂存导入与网络对照

- 用户提供的 SCP 结果：公网 28MB 约 6 秒、4.4MB/s；Tailscale 原生 SCP 2MiB 约 2 分 47 秒、12.2KB/s。网页之外也复现低吞吐，未确定具体网络根因，未把临时导入当作网页上传已修复。
- 用户云端执行日志：一次性助手摘要匹配，完整备份 `PLW-6e2eef06-ee03-4289-8877-1d201df02600.zip` 生成，已知数据集保持不变；“概述.pdf”导入“大三上／机器人技术基础”，ready，托管原件大小/哈希通过。material_id=`d807ec6a-9e0a-4fe1-b81b-2aa504028e03`，edition_id=`4671e11e-7a63-4436-ab28-2ccfd46fdece`。
- 以上确认真实资料已入库和阅读准备完成，不代表真实浏览器阅读/标注、导入后的完整备份恢复或正常网页上传验收。助手未获取云端密码或浏览器登录会话，未初始化/重置现有库。

## 2026-10-17 13:24 静态资源修复部署

- 部署后用户重新打开并登录，反馈“明显变快，控件能正常出现”，确认静态传输修复已带来实际体验改善。尚无更新后的 HAR，也没有两台设备分别完成全部业务流程的证据。
- 用户执行日志：外层 ZIP 与 6 个载荷 SHA-256 通过；旧入口修复镜像与 PrivateAccess 文件检查通过，离线构建 `plw:0.3.1-assetsfix-20261017` 成功。
- 镜像内无正式数据、无网络的合成检查通过：压缩片段 2471 → 1128 字节，认证/跨站/缓存保护检查通过。此前 `glob('index.*.js')` 在 Linux 选择了小片段，不能把这条日志写成主入口压缩验证；源码验证器现改读 HTML module 入口，原安装包保持不变。
- 更新前完整备份 ID `4c6a0ed9-942d-4a57-8f8f-cb8c139be1fa`，2 个数据文件、schema4、complete=true、dataset_id 未变；ZIP 325395 字节，SHA-256 `937f610cda1fa7f8fe06bb0ca1e742111f10e985da27f89ca3525826350b6a41`。
- 新容器启动、回环健康轮询通过，安装器输出 STATIC ASSETS HOTFIX STARTED；旧环境快照 `/srv/plw/private/deploy.env.before-assetsfix.c1u6yICE`。未触发回退，不代表失败回退已验收。
- Windows/iPad 重新登录、主入口实际 gzip/缓存和管理页响应：待用户验证。Tailscale DNS 例外持久化也仍待安装验收。

## 2026-10-17 私有HTTPS访问与网络修复

- 用户最新Linux日志：入口热修包校验通过、离线构建完成、容器合成检查通过、完整备份`2e5fd5d2-3223-4451-aaad-e9855d38ca16`生成且complete=true，现有dataset_id不变。新镜像`plw:0.3.1-entryfix-1381e66`启动，健康轮询最初空响应导致解析报错，随后重试成功并打印ENTRY HOTFIX STARTED。源码已安静处理空响应，原发布ZIP保持不变。
- 更新后Windows真实网络复测：普通登录页200、证书校验0、0.126秒；外部顶层入口303、登录页200。云端入口403修复已验证。尚未由用户确认更新后实际登录和业务操作，不能把HTTP检查视为功能验收；失败回退也未触发测试。
- 最新：用户保存UDP41641入方向规则后，Windows探测直连47.98.151.12:41641、12ms；登录页HTTP200、证书校验通过、请求0.138秒。此前香港中继数据不代表当前路径。
- 再次对照旧云镜像普通访问200、外部顶层导航403。入口修复包已准备，认证/云兼容41测试通过（12.59秒）；额外合成检查对新模块通过，对21dab82旧模块如预期失败，Bash语法与ZIP CRC通过。无本机Linux Docker引擎；不得把这些结果记为云端更新、备份或回退已经通过。
- 用户实机日志：阿里云DNS100.100.2.136/138被Tailscale CGNAT规则覆盖，域名解析超时使ACME申请失败。仅放行eth0上这两个地址的UDP/TCP53已建立回复后，解析6ms返回，ACME目录HTTP200。
- Windows实际网络测试：直连入口303、登录页200、证书验证成功；经既有Clash代理时握手失败。用户配置PLW系统代理绕过后，最新截图确认已登录云端应用主页。没有由助手输入账号密码或自动化认证。
- 最新Tailscale三次探测经香港中继为175/172/185ms，未建立直连；UDP可用，NAT映射随目标变化。尚未读取当前云安全组，也未改动安全组。
- 源码入口导航修复：相关Windows测试41通过，11.96秒。仅允许根路径和登录页的顶层GET导航，跨站接口、iframe、写入及WebSocket限制保留；修复尚未应用云端旧镜像。
- DNS持久化包已生成，3个文件3637字节，ZIP CRC及两脚本Bash语法通过。新的systemd钩子尚未在Linux安装或进行重启测试；不能把临时规则成功记为持久化已完成。
- iPad真实业务操作、跨设备批注可见、完整备份下载与隔离恢复、Compose重启/更新和Windows关机后访问仍待验收。

## 2026-10-17 云端空库启动（用户执行日志）

- Tailscale已登录，Serve状态为`tailnet only`，根路径代理至127.0.0.1:8501。尚未验证客户端HTTPS连接及证书。
- 单账号配置预检通过：`valid: true`、linux、PDF依赖就绪、回环监听，预检本身未创建学习库。后续init已创建新的独立空云库，没有迁移Windows正式数据。
- Compose容器`plw-plw-1`启动，安装器start/status的回环健康均返回`{"ok":true,"version":"0.3.1","initialized":true}`。
- 输出时容器仅运行5秒，Docker显示`health: starting`；需要后续确认healthy，不能记为已通过。正式服务重启/重新部署持久化、跨设备HTTPS登录、真实浏览器阅读标注、云备份下载及Safari/Pencil仍待执行。
- 本轮只更新文档，未重复执行Windows测试，未由代理取得服务器登录或操作正式学习数据。

以下2026-10-16内容为历史阶段记录，其中待执行项以最新记录为准。

## 2026-10-16 阿里云离线部署补充

### 最新结果：Linux合成容器验收通过

用户执行并提供日志：续跑脚本SHA-256及原部署包328文件清单通过，`plw:0.3.1-offline-21dab82`镜像构建成功。Linux/AMD64镜像ID为`sha256:2c6b5a778bb57f6dbf2c6402b9f75cd4f85e92af7d1463d21fb2912ed76ba5e9`。

两个独立容器seed/check均通过schema4、中文PDF上传、两页PDF阅读副本、高亮、书签、阅读进度、Markdown公式笔记、任务完成、完整ZIP备份与隔离恢复；36个合成文件哈希一致，末尾`ACCEPTANCE PASSED`。证据目录`/var/tmp/plw-acceptance.xda3fje0`。测试不挂载正式学习库。

尚未执行：正式Compose服务启动/重启/更新、私有HTTPS登录、Linux站点PDF.js浏览器交互、真实云端备份下载、Tailscale注册及iPad/iPhone真机测试。服务层合成验收不代替这些检查。

### 先前排错记录（以下待执行项是当时状态）

- 最新实机日志：离线镜像构建完成`#15 DONE 37.8s`；首次容器验收已运行至PDF夹具生成，子进程退出1，原CalledProcessError未展示stderr。构建完成不等于应用验收通过。
- PDF夹具修复：PdfWriter改用BytesIO，子进程失败展示有限stderr。用实际pypdf与明确拒绝tell/seek的stdout替身验证，生成PDF可读且为两页；Windows合成seed/check再通过，36文件哈希一致。续跑脚本只对旧容器中的测试代码做内存替换，Bash/Python语法通过；Linux续跑待验证。

- 续轮实机输出：部署ZIP与文件清单通过，Docker load成功；旧config-ID比较失败。用户提供的四层DiffID与本地逐字节验证结果一致；按containerd源码重建899字节manifest的摘要与实机返回的`86dec9...d1ba`完全一致，定位为安装器兼容缺陷，尚未执行应用构建。
- 修复回归：`pytest tests/test_offline_image_identity.py tests/test_offline_bundle.py -q`，**19 passed in 0.15s**；覆盖Docker29真实摘要向量、旧config-ID、错误ID/平台/层/descriptor拒绝、归档内容验证、不改原安装器的内存替换。新安装器及生成的兼容Bash语法通过。补丁ZIP CRC通过，实际cloud resume待验证。

- 用户提供的ECS终端输出：Docker29.9.1、Compose v5.6.0、active。随后docker pull Python基础镜像连接Docker Hub超时；不是PLW容器验收通过。
- Windows通过Docker官方Registry接口下载Linux/AMD64基础镜像，SHA-256验证配置、压缩层和解压层；归档重新读取/摘要校验。43个Linux wheel按此前固定版本解析报告的PyPI哈希逐一验证，离线pip --dry-run --ignore-installed --no-index解析全部依赖退出0。
- `scripts/offline_smoke.py seed`和独立进程`check`在Windows合成目录通过：真实生成的两页PDF、上传、阅读副本、高亮、书签、进度、笔记、任务完成、完整备份及隔离恢复；36文件哈希一致。它们不使用正式资料，也不代表Linux执行。
- `pytest tests/test_offline_bundle.py tests/test_cloud_compat.py tests/test_private_auth.py -q`：**37 passed in 10.87s**。包括篡改、额外Python文件、危险路径、重复/缺失条目拒绝。
- `bash -n scripts/install_offline.sh`退出0。安装器支持断网构建和两个容器之间的独立合成卷检查；目前尚未在Linux实际执行。
- 真实云端上传、Docker load/build/run、Tailscale注册/HTTPS、用户登录、Safari/Pencil、电脑关机后访问、云端下载备份：**待执行**。浏览器控制运行时因Windows路径错误无法初始化，没有建立其他已认证服务器连接。
- 实际归档验收：329个文件、221463298字节，外层ZIP CRC和全部清单SHA-256通过，Python镜像归档中的config与四个解压层摘要再次通过；Tailscale限定提取及ELF文件头通过，未执行Linux程序。源码提交`21dab82`已推送，GitHub远程SHA与本机一致。Compose配置解析退出0。
- 只读SSH连接在主机信任检查阶段失败（未知ED25519主机密钥），没有接受新主机密钥或执行服务器命令。当前阻塞是缺少可用且可信的服务器控制通道，不能把离线准备当成网站上线。

日期：2026-10-15；源码0.3.1；Windows11、Python3.14.3、Streamlit1.65.0。所有样本为独立合成资料，没有使用正式库做测试。

| 检查 | 实际结果 | 限制 |
|---|---|---|
| 全量pytest | 579通过，121.12秒，无跳过 | Windows运行 |
| 现有schema3本地首页 | 通过，未自动迁移，DB字节不变 | 合成旧库 |
| Windows正常启动 | 127.0.0.1:8501健康200 | 只验证本机 |
| 课程/PDF/标记/进度/笔记/任务 | 现有及新增服务/UI测试通过 | 不等于iPad真机 |
| schema3→4 | 副本迁移、保留关联与文件、回滚通过 | POSIX字段在Windows SQLite验证 |
| 004迁移故意失败 | 原schema3文件字节及关联不变 | 合成库 |
| 完整备份ZIP | 打包、下载、整包与逐文件校验、隔离恢复通过 | 包不加密 |
| 私人备份链接 | 登录可下载、匿名401、篡改409 | 回环HTTP合成站；原HTTPS登录回归见V030 |
| 浏览器 | Edge原5组私有阅读流程+820px备份UI通过 | 平板尺寸模拟，无真实Safari |
| 进程重启 | 7个文件和指针哈希不变 | 不是容器重启 |
| Compose配置 | config --quiet退出0 | 无Docker引擎 |
| 发布脚本 | Bash语法通过 | 更新、失败回退未运行 |
| Linux ARM64/AMD64依赖 | 二进制包dry-run解析成功 | 未安装/执行、未构建镜像 |
| 正式数据 | 135文件前后哈希相同，无新增 | 排除可重建cache |
| Docker启动/重启/重建 | 未执行 | 用户选择待环境就绪补做 |
| Tailscale真实证书/网络 | 未执行 | 未登录云账号/设备 |
| iPad/iPhone、电脑关机访问 | 未执行 | 需真实云端与设备 |

运行日志与JSON：`.sandbox/cloud-implementation/`。浏览器报告：合成根下`evidence/private-site-browser.json`、`cloud-backup-browser.json`；包含原生下载ZIP与截图。损坏/失败测试残留只在沙盒保留，不自动清理。

首轮全量发现2项历史测试把最新迁移固定成003；已将“当前最新”断言改为实际最新，并让“003故意失败”继续只针对001–003。新增004故意失败测试后全量通过。未将失败或未执行项目记作通过。

## GitHub发布续轮

同日已创建并确认CapSantiago/personal-learning-workbench为私有仓库，首次推送b9bd36d。357文件提交范围审查通过；211个迁移和PDF.js文件在暂存区与远程新克隆中字节一致。新克隆独立运行部署配置预检通过，未创建学习库。此轮没有改应用逻辑，未重复运行579项测试，也未运行Linux容器。没有启用GitHub Actions或收费服务。
