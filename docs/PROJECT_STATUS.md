# PLW 项目状态

2026-10-22 外观后续修正：课程标题/教师说明与选择器重叠已通过取消 caption 负边距补偿并纵向分层修复；侧栏悬停改浅中性底/轻阴影，深色文字图标不再被通用 primary-hover 同色覆盖。PLW 改原创圆角几何字标，设置分组稳定标识。新增“课程与设置 → 外观设置”，六种强调色及恢复默认，工作区 control 原子保存，不改学习数据库；页面/侧栏背景固定，黄色主按钮深字，阅读器/设备库继承主题。真实完整 Streamlit+Edge 六色/刷新/375-1440宽度/200%字/长标题检查、18张主页面状态回归及13种适配稳定性通过，191项Python、48项JS、4份部署验证器本机进程、PS7/Git Bash解析通过。新包63,834字节，SHA256 `f1601b1683ea93c7ea8d07b2e8bc4257532d3f9074ef0b3b1b1d0c75672cb7cf`，入口 `.sandbox/releases/Install-PLW-Appearance-20261022.ps1`，接受四个已交付基线，完整备份后切换/失败尝试回退。云端尚未部署，物理iPad未验收；正式数据与设备下载库未动。[修改清单](APPEARANCE_FIX_20261022.md) · [验收证据](APPEARANCE_VERIFICATION_20261022.md)。

2026-10-22 UI/UX 渐进美化：已按用户要求安装 UI/UX Pro Max 2.15.0（固定提交623a9a90…），先提交审查、问题清单、统一规范与分阶段方案，再改呈现层；营销布局/衬线字体匹配不适用，采用经核对的简约与通用UX规则并明确项目适配判断。重点重做侧栏PLW书页标识/紧凑品牌/左对齐分层导航，首页主次操作、课程/任务与读者/下载库统一语义变量、字体、焦点及触屏目标，手机顶部导航不再透出滚动文字。未改schema、业务服务、SQL、保存/下载/认证/路由；reader.js及runtime与上一reading-workspace包字节一致。完整Streamlit+Edge合成库22张最终截图、375/768/1024/1440与触屏横竖屏、任务完成/恢复、下载8/8及全复用、课程详情和笔记通过；13种最终适配情形稳定缩放、重复重算0、1600x1000正文top237px/高702px。216项Python、48项JS、3份容器用验证器在本机进程及PS7/Bash解析通过；不是Linux镜像或物理iPad验收。最终包59,707字节SHA256 `6ab97e4eac00892e8f1ab1364655e5e4dff30d5ada4d37b90cf6849050a5a55d`，入口`.sandbox/releases/Install-PLW-UI-Design-20261022-r2.ps1`，严格接受device-library-r2/smooth/reading-workspace三旧版，先隔离验证和完整备份再切换、失败尝试回退。云端尚未部署，待用户本机一次SSH认证；正式数据和设备下载库未动。[审查与方案](UI_UX_REVIEW_20261022.md) · [文件清单与验收](UI_UX_VERIFICATION_20261022.md)。

2026-10-22后续：按用户要求将书架改为阅读主界面，并合并“整页适配114/117来回跳”“首页只显示四门课”两项。原home确有[:4]硬截断，已显示全部活动课程；管理功能统一进入“课件工具”“课程选项”，顶部两行切换栏，正文/批注进入首屏，所有原有排序、确认移除/撤销、导入、下载、版本/OCR等入口保留。固定缩放控件尺寸、稳定滚动条槽、适配向下取整留2px，避免布局尺寸反馈；不能据截图确定具体浏览器内部bug。完整Streamlit+Edge本机13种视口/旋转/缩略图/横竖PDF情形稳定后每15次100ms采样均单一zoom、重算事件0、无溢出，1600x1000下正文top237.17px/高702px。七门活动课程全显、归档排除、最后一门导航验证通过，物理iPad尚待确认。149项Python（含3项发布/严格旧基线验证）与48项JS检查通过；两已发image由不可变归档重建完整字节基线均通过，额外修改UI会拒绝。三份云端用合成验证器在本机进程通过，双PowerShell/Bash解析通过；不是Linux镜像或云端验收。包56,487字节SHA256 9680819286c518fdf477937ec818f1e204baeb63f099b00b98843886cdb0f97c，入口`.sandbox/releases/Install-PLW-Reading-Workspace-20261022.ps1`。支持device-library-r2或smooth一次升级；保留PDF设备库、账号/标记、原生HTTPS。云端尚待用户终端一次SSH认证执行。[阅读工作区说明](READING_WORKSPACE_20261022.md)。

2026-10-22：用户确认native HTTPS续装成功且实际可下载；读取本机真实结果`native-https-result-20261021-160334-d34458`，候选/原网址/最终认证与安装均通过，原443同8MiB为403.4KiB/s、直连409.5KiB/s，完整SHA通过，Serve严重降速已消除。新的反馈是已下载课件翻页仍被“保存中”锁住。源码确认go()/按钮在pending时阻塞，position触发整页rerun并重建画布。已准备reader-smooth独立更新：同源认证JSON动作接口在线程池执行原幂等/版本检查，300ms合并未发进度且单个操作串行重试，翻页/拖动不等待ACK；离屏绘制后替换、相邻页预绘制、每文档4张/32MiB有界大图复用，PDF长期设备库保持不变。116项Python相关回归+1项发布包检查、48项JS唯一检查通过，真实54/35页Edge独立组件测试在3秒保存延迟/人为503下连续翻页与重试/刷新/课件往返通过，命中绘制约0.4–0.8ms、未预绘制页73/117ms；无组件触发器和重复PDF下载，物理iPad尚未验收。Bash与双PowerShell解析、两份容器用验证器在本地进程通过；未在Linux构建或部署。31,915字节包SHA256 `6f679e0c0339e620b9abf310b31652ca67f0965cc8997eb97da4a069ee95a0e1`，入口`.sandbox/releases/Install-PLW-Reader-Smooth-20261022.ps1`，先严格旧基线、容器合成检查、完整备份再切换，失败回退。实际云端更新仍需用户本机一次SSH密码，不清下载库、不改原生HTTPS。[连续翻页说明](READER_SMOOTH_20261022.md)。下方native r3未运行记述为此前阶段，现以上述实测成功为准。

2026-10-22：已读取10月21日15:54完整只读端口证据：IPv4 `100.104.174.9%tailscale0:443` 与IPv6监听均属于tailscaled PID832，/proc socket inode24107/24111交叉确认；原Serve配置仍完整，新服务not-found。r2识别器遗漏ss地址中的`%tailscale0`接口后缀，导致listeners为空并在预检安全退出，并非未知程序。r3仅规范化地址匹配，保留原始端点与实时MainPID严格核对；真实输出、错误/缺失/混合PID拒绝及交接回退纳入89项通过测试，PowerShell7/5.1解析通过。10,340字节不可变续装包SHA256 `2b7fa406bb8861c3ac2561b1cb63db45fbbb1aba753f98dbdc650d0f4dfd73b6`，复用原始已校验Caddy至新-r3目录，保留两次旧目录；不重传18 MB。入口`.sandbox/releases/Resume-PLW-Native-HTTPS-20261021-r3.ps1`。仍待用户本机SSH认证执行；未宣称Linux候选证书、实际443测速或课件/iPad修复完成。下方等待原始证据/r2尚未执行记录为历史阶段。[r3说明](NATIVE_HTTPS_REPAIR_20261021.md)。

2026-10-21 r2续装再次停在预检：用户日志与本机`native-https-result-20261021-154934-8e50d2/ports.json`一致，100.104.174.9:443标为blocked但listeners为空，19196/19444空闲；仍未到配置快照/候选启动/入口切换。空解析结果不能证明其他程序占用，也不足以确认tailscaled拥有实际冲突套接字。暂停继续发安装修订，准备只读`Inspect-PLW-HTTPS-Port-20261021.ps1`，采集原始ss、主进程PID、/proc TCP443行与对应socket inode进程映射，不读取账号/私钥或改变服务。等待用户终端一次SSH认证取得原始证据；未宣称根因是端口文本格式或修复完成。

2026-10-21首版HTTPS安装失败跟进：用户截图显示EADDRINUSE发生在端口预检，未写配置快照/建立服务/切换入口。定位安装器错误：要求现用443空闲，且没有按Serve确实存在的内核监听交接端口。r2核对占用者PID，仅允许已知tailscaled现用443；候选验收后先释放旧443再启动新服务，回退先停新再恢复旧，覆盖null空配置。9,941字节独立续装包，复用严格校验的已上传二进制，保留旧目录并复制到新的-r2目录，不重传18 MB、不碰学习数据。入口`.sandbox/releases/Resume-PLW-Native-HTTPS-20261021-r2.ps1`；云端未执行，未宣称修复上线。[r2交接修正](NATIVE_HTTPS_REPAIR_20261021.md)。

2026-10-21 HTTPS对照已完成：同一8MiB随机数据，内核Tailscale404.6KiB/s与公网SSH434.8KiB/s完整校验；Serve HTTPS仅210,944字节/45秒、4.58KiB/s，curl28超时，首字节73.5ms，合成端点亦可复现约88倍差异。临时Serve已关闭、原配置一致。严重停顿已定位到Serve HTTPS路径，不能再单独归咎于PDF/设备存储或购买带宽。准备官方Caddy2.11.7私有内核HTTPS替代，保留原网址/证书/应用认证/镜像/数据；候选、原443及最终认证三阶段验收，速度≥直连65%且SHA完整，独立systemd回退保护。12专项（含真实TLS/认证/WebSocket与安装故障模拟）、62既有认证访问回归及双宿主解析通过。包18,234,256字节，SHA256 00b07175829b38069df3680ab5a311dd6f5554cf232cfc152e1f690f67936755；云端安装尚待用户SSH密码，不能宣称下载或课件/iPad修好。[修复说明](NATIVE_HTTPS_REPAIR_20261021.md)。

2026-10-21实测更新：用户完成r2下载库安装，当前镜像已由服务器报告确认为plw:0.3.1-device-library-20261021-r2。四次2MiB接收均校验通过，公网SSH409–524KiB/s、Tailscale私有端口390–396KiB/s；服务器CPU约4.87%、可用内存1142MiB，Tailscale实际数据直连无DERP增量。主机全局TCP重传+1504，不能算作指定PDF连接精确丢包率；当前购买出带宽仍未直接核实。原测试绕过Serve HTTPS，不能等同网页下载正常。准备同一8MiB数据的直连/临时私有前台HTTPS/公网SSH定向对照，6项隔离/清理/接收检查通过；该云端补测需用户本机一次SSH认证，未执行、不宣称首传慢修复，不改热点、阅读器或全局TCP参数。详见[实测及补测边界](TRANSFER_CHECK_20261021.md)。下方“r2尚未执行/等待四次对照”为此前阶段记录，以上述新实测为准。

下载速度核实：用户已看到设备下载库和持久权限批准，但首份28.2MB文件仍传输缓慢。代码无固定字节速率限制，串行队列只影响批量并发；此前50秒内容间断与套餐出带宽仍须分开。用户不清楚ECS出口配置，本机免密SSH不可用。已准备单次密码的同服务器2MiB×4下行对照，公网SSH回环与Tailscale私有监听、限时、随机数据和摘要检查，采集计数/CPU/内存/重传；不改应用或网络。3项端点/实际PS接收专项通过，真实服务器测量等待用户本机登录；未读取购买带宽，未宣称根因或修复完成。工具：.sandbox/releases/PLW-Transfer-Check-20261021/Check-PLW-Transfer.ps1。

下载库安装跟进：用户已通过SSH并完成首包载荷校验，安装在旧镜像工作台源码摘要检查退出；未进入构建、备份或容器切换。已从原始离线 ZIP 重现：cachefix 精确插入保留922个CRLF，实际原包UI摘要09dfa4a7…，首版误使用规范LF摘要13171adc…。r2严格接受两种已知完整字节身份，其他内容仍拒绝并仅报告摘要/换行计数。9项安装器专项测试通过，应用载荷与首包逐字节一致。新增36,907字节r2包、独立目标目录和镜像，保留旧失败目录；r2尚未在云端执行，真实服务器若另有差异仍会停止。[安装修订说明](DEVICE_DOWNLOAD_LIBRARY.md)。

2026-10-21：按用户“下载一次长期复用、一键更新全部课件”的要求完成设备下载库。文件以 Blob 存入 IndexedDB，不随阅读实例或三文档内存淘汰释放；同内容去重，摘要/大小验证，原子保存，批量增量更新，失败保留已完成与旧文件，配额不足不自动删除；显示持久权限真实状态并支持从本机另存文件。所有未移除课件的最新阅读 PDF 与托管 PDF/PPT/PPTX 原件覆盖跨课程；清单/下载仍经过现有认证与完整性检查。43项 JS 与197项 Python 回归通过，真实54/35页课件保存后重开模拟数据库、关闭PDF测试服务再渲染57次通过。数据库使用 fake-indexeddb；真实Chrome/iPad界面和物理持久性尚未验收，浏览器控制工具仍无法初始化。35,368字节独立包及兼容5.1解析、转交7执行的单密码入口准备完成，接受严格compatfix/fullfilefix基线；云端未部署，不宣称首传或整站离线冷启动已修复。[下载库说明](DEVICE_DOWNLOAD_LIBRARY.md)。

安装入口跟进：用户截图确认此前 compatfix 已启动，随后 fullfile 入口在 Windows PowerShell 5.1 解析阶段报错，尚未执行其云端更新。已在同机 5.1 复现3个解析错误，原因是无 BOM UTF-8 中文脚本被旧宿主按本地编码解码；入口已改为 UTF-8 BOM，并在旧宿主自动转交 PowerShell 7。5.1 与 7.6.6 解析均0错误，原 ZIP/远程引导摘要保持不变。无需重传课件、回滚或再次运行兼容包；fullfile 云端安装仍待用户终端输入密码完成。

最新：用户反馈兼容更新后仍卡于《第二讲-机器人结构与驱动方式》第5/54页，持续阅读尚未修好。已完成整份 PDF 接收+大小/SHA-256 校验后交给 PDF.js 字节解析，15秒无进度中止并有限续传，失败可重试；保留文档缓存并在逐出时取消下载。真实54页与不同的35页课件，经生产认证/中间件/路由接收后关闭测试HTTP服务器，使用本地支持资源及独立worker，54页与课件往返共57次渲染通过（无后续PDF请求）；29项下载/缓存与182项相关回归通过。20,105字节独立更新包和单密码入口已准备，仅更新reader.js，严格接受compatfix基线；本轮没有云端部署，Chrome/iPad真实阅读仍待验收，首次整文件下载仍取决于网络。上传目前可完成但慢，本次不宣称改善上传。[完整说明](READER_FULLFILE_FIX.md)。

20:36 用户确认 cachefix 已启动，电脑/iPad均空白；iPad截图明确报 Map.getOrInsertComputed 缺失。旧现代库在缺少该 API 时复现同错，先前 Node 测试手工补齐该 API 不能代表浏览器兼容。现改用同版本官方 legacy 主库和 worker、补充资源摘要：移除 Map/Hex/Promise 方法的主线程与独立工作线程真实渲染通过，HTTP分段/往返缓存通过（81ms、0新增请求），12项缓存和182项相关回归通过。独立兼容包729,881字节及单密码安装入口已准备，云端尚未更新；回退工具未执行，旧缓存单独安装入口已撤回。[兼容性修复](READER_COMPAT_FIX.md)。

后续：校验版 SSH 通道已实际通过 HTTPS、真实 Chrome 参数/日志及流量检查。前三分钟 444 个 PDF 请求全部完成、约 46.55 MB，没有此前超过 50 秒的内容读取停顿；用户仍反馈慢且切换回来重读。已确认前端新开课件会销毁上一份文档，完成最近 3 份/96 MiB 原始 PDF 字节预算的缓存修复及过期任务隔离。12 项专项、180 项相关回归、真实 HTTP PDF A→B→A 检查通过（返回84ms、下载/校验请求0）。独立17,880字节包和一次密码安装脚本已准备，云端尚未安装；不宣称首次加载或两设备问题全已修复。[缓存修复记录](READER_CACHE_FIX.md)。

16:22 临时通道未取得有效对照：用户在自动打开的窗口中更卡，但 18 次代理采样全部零连接/字节、浏览器日志未生成；不能认定窗口实际走了 SSH，也不能认定 SSH 更慢。已准备先探测通道、核验新 Chrome 参数/日志与实际流量的校验版，真实执行待用户本地 SSH 登录。应用与网络配置未修改。[当前排查记录](COURSEWARE_DIAGNOSIS_20261018.md)。

16:06 同步诊断新结果：PDF 范围读取已实际工作，但两个 64 KiB 响应内容分别出现约 52/51 秒间断，记录结束仍未收齐；服务器无资源饱和、OOM、重启或采集到的应用异常，四模块摘要匹配。当前重点为传输路径停顿，准备单窗口公网 SSH 加密访问绕行；不再切热点或叠加应用补丁。工具本地验证通过，真实用户 SSH 登录和稳定阅读结果尚待确认，iPad 未修复。[同步证据与下一步](COURSEWARE_DIAGNOSIS_20261018.md)。

最新补充（2026-10-18）：上传能够完成但慢，阅读仍间歇卡住；停止反复热点对照。真实 PDF 本地导入与渲染正常，范围请求逐次全文校验的放大开销已实测，但尚不足以解释线上停顿。一次同步只读采集工具已准备，等待真实服务器与浏览器同时取证，没有新产品部署。[本轮定位记录](COURSEWARE_DIAGNOSIS_20261018.md)。

更新：2026-10-17，Asia/Shanghai。源码版本 **0.3.1**；新学习库/云端目标 **schema4**，已有Windows本地schema3保持兼容，不自动迁移。GitHub账号：**CapSantiago**。云端空库已启动，Windows已通过私有HTTPS登录；iPad功能、持久化重启及完整备份下载验收待完成。

## 2026-10-17 管理连接恢复与Tailscale登录

### 当前访问排错进展

- HTTP/1.1测试窗口曾显示真实第25页，缩略图可逐步加载，但用户随后第15页再次卡住，收起预览也未恢复；稳定性问题仍未解决，不能归结为HTTP/2或缩略图的单一问题。同版PDF.js本地全文件并发渲染第15页通过，准备经公网SSH加密通道做数据路径对照，尚未建立或验收。没有继续打应用补丁。
- 10月18日新HAR确认worker首次错误为ERR_CONNECTION_RESET；PDF首次响应已正确提供identity/29613390字节长度/Accept-Ranges，随后ERR_ABORTED符合PDF.js转范围读取时主动取消整份GET的逻辑。后续pending请求没有收录在4条HAR中，实际范围下载未验收。本机网关与原Wi-Fi慢速测试一致，已请用户用安装rangefix后的版本重新做热点阅读对照，暂不继续打补丁。
- 10月18日用户请求截图：worker首次45.66秒网络失败，完整错误码被截断；随后fake-worker模块导入200/259ms，PDF首次请求200/45.75秒、另一fetch仍pending。等待当前新HAR确认完整错误与请求/响应头，不据此断言文件损坏或继续打补丁。未认证登录页助手复测200，不等于实际阅读通过。
- 用户截图确认reader-rangefix已构建、通过实际框架合成检查、生成完整备份并启动，但重新登录后真实课件依然空白，提示“正在读取课件…”。阅读仍未验收通过；接下来获取已登录浏览器的plw-reader请求状态，暂停基于截图猜测继续打补丁。
- 当前：用户恢复本机Tailscale后已登录，readerfix仍在“已接收1.0MB”处空白。已用实际Streamlit中间件复现首次PDF响应被默认gzip并丢失原始长度，使PDF.js禁用范围读取；上轮裸路由测试漏掉此层。新最小响应修复已准备，实际框架链检查通过；尚未部署，真实阅读待验收。[后续修复说明](READER_RANGE_FIX.md)。本机客户端现Running，HTTPS登录页200/证书通过，此前NoState记录为历史状态。
- 最新 Linux 安装日志确认阅读加载补丁已部署：ZIP/载荷/旧模块基线通过，衍生镜像构建、容器内64KiB分段与worker压缩检查通过；切换前完整备份 `PLW-c02bac3c-0cb3-4c15-ba2b-10f4aa3cc2c9.zip`（59553321字节，SHA-256 `e3660b8d00cfdb938695854b2f7916eb202c10beb7d39a2cb6f22dc7860f85c1`），含真实PDF阅读副本且原数据集不变。`plw:0.3.1-readerfix-20261017` 启动并通过回环健康检查，旧环境 `/srv/plw/private/deploy.env.before-readerfix.otp9vSjp`；真实页面/翻页仍待用户确认。助手当前客户端 Tailscale NoState，外部域名解析及私网连接失败，不把客户端状态记为服务器故障。
- 最新：用户切到手机热点后隧道 TSMP 27ms、同一2MiB合成文件 Taildrop 10.34秒完成；原网络 TSMP 约200ms、原生SCP 2MiB约167秒。用户刷新后真实PDF仍空白。阅读加载修复已准备（分段读取、验证过的内置脚本gzip、加载提示），81项相关测试及独立烟雾通过，部署包21716字节；未部署、实际阅读待验收。详见 [阅读加载修复](READER_LOADING_FIX.md)。
- 最新实际结果：用户公网 SCP 约 4.4MB/s、28MB 约 6 秒，而 Tailscale 原生 SCP 只有约 12.2KB/s、2MiB 约 2 分 47 秒，严重低吞吐可在网页之外复现。一次性助手已由用户运行成功：先生成完整备份 `PLW-6e2eef06-ee03-4289-8877-1d201df02600.zip`，再将真实“概述.pdf”导入“大三上／机器人技术基础”，ready 且托管原件 SHA-256 通过；实际浏览器阅读待确认，正常网页上传仍未恢复。Windows DISCO 约 15ms 与实际隧道 TSMP 约 200ms 存在差异，用户同意手机热点对照，待切换复测。详见 [上传连接诊断](UPLOAD_CONNECTION_REPORT.md)。
- 上传对照新增：用户公网 SCP 传 28MB 仅约 6 秒、显示 4.4MB/s，暂存 `/root/plw-probe-f20b8bb6.pdf`；独立 HTTP/1.1 浏览器测试仍慢，不能归因于 HTTP/2 单一因素。准备哈希/数据集/课程保护及完整备份的一次性导入助手，合成验证与 Bash 语法通过，真实导入待执行。Tailscale 与网页代理路径还需进一步区分。
- 最新上传问题：28.2 MB PDF 超过三分钟未完成。默认模式 Chrome NetLog 证实上传实际缓慢推进（两次采样约 10.5/21 KiB/s），经 DIRECT 路径；HTTP/2 PING 失败后触发整份 PUT 从头重传。此前仅按未完成请求的 Stalled 推断“未发送”已纠正。拟用独立 Chrome 配置的 HTTP/1.1 上传做对照，根因及最终修复仍待验证；详见 [上传连接诊断](UPLOAD_CONNECTION_REPORT.md)。
- 最新用户验收：静态资源补丁部署后重新打开并登录，用户确认“明显变快，控件能正常出现”。这是实际体验改善，不能等同于全部功能或两台设备逐项验收完成；课程创建、PDF 阅读/笔记保存、DNS 持久化和重启验证仍待完成。
- 13:24 用户 Linux 日志：静态资源修复包与所有载荷校验通过，旧镜像检查及离线衍生构建通过；镜像内合成检查 `index 2471 -> 1128 bytes`，实际选中一个 index 命名的小片段，不是 HAR 中 449225 字节的主入口。备份 `4c6a0ed9-942d-4a57-8f8f-cb8c139be1fa` complete=true、dataset_id 不变，ZIP SHA-256 `937f610cda1fa7f8fe06bb0ca1e742111f10e985da27f89ca3525826350b6a41`。新镜像 `plw:0.3.1-assetsfix-20261017` 启动并通过回环健康检查；旧环境 `/srv/plw/private/deploy.env.before-assetsfix.c1u6yICE`。真实浏览器压缩头、缓存及卡顿改善仍待用户验收。源码验证器已改为按 HTML module 入口定位，原已安装包不覆盖，不需要因此重跑安装。
- 最新：Windows/iPad 都反馈课程与学期管理卡顿。用户容器 healthy；负载 0.14/0.06/0.01、CPU 0.56%、可用内存约 1.1GiB、10 秒平均发送 0.02Mbps，不能据此购买升级或宣称没有网络停滞。用户 HAR 只含 8 个已完成请求，均 HTTP/2；主脚本 449225 字节、约 6 秒，静态文件没有压缩且全部禁止缓存；75 字节脚本也等待首字节约 6 秒。静态压缩/私人缓存修复已准备，完整连接停滞原因及上线后的改善仍待验证，参见 [静态文件修复](STATIC_ASSETS_FIX.md)。浏览器接管工具在初始化 MXC sandbox 时失败，重启和切换 Chrome 未恢复，助手未获取页面控制或真实登录会话。
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
