# 私有HTTPS下载路径修复

## r3：按真实接口绑定监听输出修正识别

2026-10-22处理用户返回的10月21日原始证据：`.sandbox/releases/https-port-evidence-20261021-155448-bf84ae.json`。原始`ss`报告IPv4端点为`100.104.174.9%tailscale0:443`，PID832；IPv6端点亦为同PID，`v6only:1`。systemd MainPID/ExecMainPID均832，/proc TCP与TCP6的inode24107/24111分别关联PID832的fd28/29。原Serve配置与已知根代理一致，新native服务not-found/inactive。两次安装均未切换网站。

r2按冒号分离端口后直接匹配IP，遗漏`%tailscale0`后缀，所以误报blocked且listeners为空。r3匹配前移除接口后缀和IPv6括号，报告中仍保留原始地址；允许占用443的条件仍为每一个匹配监听的所有PID与实时tailscaled MainPID完全一致。不硬编码832，不按进程名称盲目放行，其他地址/未知占用仍停止。独立v6only的IPv6地址不与新IPv4绑定冲突。

保留实际ss全监听及systemd输出作为`tests/fixtures/https-port-20261021.json`，验证正确、错误、缺失及混合PID，还覆盖带后缀的完整安装交接。89项native HTTPS及既有认证/访问测试通过，含真实本地Caddy TLS、完整响应和WebSocket；PowerShell7及5.1仅解析检查通过，执行仍用7。旧r2归档SHA固定并保持不变。

新入口`.sandbox/releases/Resume-PLW-Native-HTTPS-20261021-r3.ps1`，包10,340字节，SHA256 `2b7fa406bb8861c3ac2561b1cb63db45fbbb1aba753f98dbdc650d0f4dfd73b6`。源自原始目录的全部已知文件/清单验证通过后，只复制已上传二进制和许可证到新的`/opt/plw-native-https-20261021-r3`，再写入小型修正版。原始目录及失败r2目录均保留；不执行旧缓存字节码。流程沿用r2的候选验收、独立回退保护、先释放旧443再启新服务，以及回退先停新再恢复旧入口的顺序。

**云端r3尚未运行。** 用户终端一次SSH密码后才会真正检验Linux证书获取、systemd限制及吞吐。需要候选与原网址8MiB下载完整校验、速率至少直连65%和认证检查全部通过才接受。原网址保持不变，不清除设备下载库数据、不切热点、不重启tailscaled。若部署成功，人工回退使用`python3 /opt/plw-native-https-20261021-r3/rollback_native_https.py`；此前r2/首版路径为历史说明。

## r2：修正现用端口的交接并续装

用户首版安装日志在`socket.bind((100.104.174.9, port))`预检以EADDRINUSE退出，未写原配置快照、未建立新服务、未修改Serve入口。首版错误要求包含现用443在内的所有端口空闲，还试图在旧入口占用时启动新入口；回退顺序也没有考虑两个内核监听的冲突。这是安装器设计错误，不是课件问题。

核对官方1.104.1 `ipn/ipnlocal/serve.go`：Serve除远程netstack处理外，还会在Tailscale地址上为本机连接建立内核监听。因此现有443监听是正常状态。此前Windows用空闲端口的本地TLS验证和未模拟这个内核监听的安装测试，未覆盖真实交接条件。

r2预检会记录每个端口状态与相关PID；现用443只接受与systemd tailscaled MainPID一致的已知监听，未知占用或占用测试端口时停止，不杀进程、不关闭tailscaled。绑定探测使用与Go监听兼容的SO_REUSEADDR，绝不使用SO_REUSEPORT。

新流程先完成19444候选HTTPS验收，再检查旧配置/占用者不变、建立独立回退监督，移除已知Serve的443项，等待端口可绑定，然后启动新443服务。回退先停用新代理、核实inactive/disabled，再恢复原Serve。空Serve JSON为null的情况也覆盖。

新增小型续装入口`.sandbox/releases/Resume-PLW-Native-HTTPS-20261021-r2.ps1`，只传9,941字节ZIP（SHA256 `d376700dd0e68e82c8b3ab56aec7d00f4db6665b7c538d7c792a9f44a63f99a4`）。严格校验首版目录内的二进制、源码和清单，复制已上传的Caddy到新的`/opt/plw-native-https-20261021-r2`，不重传18 MB，不覆盖旧目录，不执行旧字节码。若文件变化或旧目录存在表示已进入后续阶段的新增文件，则拒绝自动续装。新目标已存在也会停止。

验证补充包括现用443由tailscaled持有、未知PID拒绝、候选未通过时保持旧入口、丢失off响应后回退、真实占用套接字先释放再恢复、旧包校验复用/变化拒绝/不加载旧字节码、空配置及新小包摘要。云端r2尚未执行；安装完成仍需关闭旧PLW标签页、重新打开原网址，以建立新入口连接并验收真实课件/iPad。

下方首版说明为历史设计；其中先启动新443再关闭旧443及回退先恢复旧入口的顺序，以本节r2为准。手动回退路径亦更新为：`python3 /opt/plw-native-https-20261021-r2/rollback_native_https.py`。

## 实际定位结果

用户执行HTTPS对照后，结果目录为`.sandbox/releases/PLW-HTTPS-Transfer-Check-20261021/result-20261021-150505-0fefa5/`。同一份8 MiB随机数据、同一台ECS、同一客户端当前网络，顺序测试：

|路径|接收|耗时|平均速率|完整校验|
|---|---:|---:|---:|---|
|Tailscale内核TCP直连|8,388,608 B|20.246 s|404.6 KiB/s|通过|
|Serve HTTPS|210,944 B|45.003 s|4.58 KiB/s|超时，未完成|
|公网SSH回环|8,388,608 B|18.843 s|434.8 KiB/s|通过|

Serve返回200，首字节约73.5 ms；后续响应内容传输严重缓慢。相对直连本次观察到约88倍吞吐差异。这发生在合成数据上，不依赖PLW认证、PDF.js、文件哈希或IndexedDB，明确缩小了严重停顿的位置。测试临时入口已关闭，原Serve配置核对一致，DERP数据发送计数没有增加。

这是Serve路径的定位证据，不是确定gVisor内部哪一个bug的抓包证明，也不等于当前购买带宽已经核实。直连约400 KiB/s依然意味着28 MB首传大约一分钟；修复不会无限提高服务器出口能力。

## 修复内容

保持`https://plw.tail066864.ts.net`，以官方Caddy 2.11.7的内核TCP HTTPS入口替代Serve的用户态443处理。Caddy仅绑定`100.104.174.9:443`，协议h1/h2、不启用HTTP/3，不启用HTTP重定向入口或公网Funnel。证书通过官方Caddy/Tailscale集成在握手时向本机tailscaled获取；不导出证书私钥、不改变现有网站认证。

代理将Host固定为原网站域名、X-Forwarded-Proto固定为https，保留原Origin及Cookie。原Streamlit端口、镜像、账号、数据、备份与浏览器设备下载库均不修改，不重启应用容器或tailscaled。

代理作为独立systemd服务运行，随tailscaled停止/重启，失败重试。为了沿用现有本地证书访问权限，它以root身份运行，能力限制为绑定低端口，并启用只读系统、保护home、私有临时目录、禁止提权及限制地址族；学习数据、备份、账户配置和系统密码文件对该服务不可访问。管理API关闭，专用状态目录0700。

## 分阶段验收与回退

本地入口：`.sandbox/releases/Install-PLW-Native-HTTPS-20261021.ps1`，需要用户在现有SSH终端输入一次root密码。约18 MB程序包从电脑经已验证主机密钥的公网SSH传入服务器；不要求服务器访问Docker Hub。包及每个载荷都有SHA-256校验，原始官方Linux/Windows发行压缩包与发布的SHA-512清单一致。

1. 严格核对原Serve只有已知私有443根代理、无Funnel/前台会话，应用镜像为device-library-r2。端口/目标目录/已有服务冲突停止。
2. 先在私有19444端口启动原生HTTPS候选，原网站入口不变。客户端用同一8 MiB数据比较直连和候选HTTPS；二者必须完整接收并校验SHA-256，候选速度须达到直连的65%以上。检查登录页200、匿名根303、匿名文件401、跨源请求403。失败不切换。
3. 建立独立240秒systemd回退监督，再启动仅绑定私有443的Caddy。服务器本机证书和登录检查通过后，才移除原Serve的443项；不执行全局Serve reset。
4. 客户端再通过**原网址443**下载同一8 MiB并检查速度、完整性和认证。未确认、失联或失败将恢复旧Serve入口。
5. 移除临时合成路由并重启新代理，客户端再次确认认证及临时路由已回到401。确认后才启用开机服务并原子写入接受标记，取消回退计时。完成后仍需实际课件和iPad验收。

控制端点仅允许SSH回环访问；合成数据使用单次随机路径，不映射任何真实文件。候选进程有180秒独立生存上限。回退只恢复保存并校验过的已知Serve根代理，然后停用新服务；遇到另一客户端改变443时不覆盖它。原配置快照保存在`/opt/plw-native-https-20261021/serve-before.json`，目录0700、快照0600。

必要时在既有root SSH会话手动回退：`python3 /opt/plw-native-https-20261021/rollback_native_https.py`。不要删除安装目录或重复运行入口来处理报错。

## 本地验证和边界

12项专项检查通过，包括真实官方Caddy的TLS、完整10 MB合成响应、原应用认证/CSRF登录、跨源拒绝、已登录WebSocket往返；严格旧配置、控制端点边界、回退不覆盖其他443、接受后回退监督不执行、切换前拒绝、失去off响应时恢复、最终移除测试路由、包源码一致性。另62项既有访问/认证回归通过。PowerShell7及5.1解析通过，旧宿主入口转交7执行，文件带UTF-8 BOM。

这些是Windows本地真实代理检查和Linux安装流程的模拟故障测试；**尚未执行云端安装，不能记为Linux/systemd或真实课件/iPad验收通过**。Caddy证书获取在云端候选阶段实际检验，失败保留旧入口。

既有阿里云DNS四条例外未被本修复更改或清除，其跨重启持久化仍属待验证事项；本次不重启服务器或tailscaled。尚未核实购买的当前出口上限，不建议基于本次停顿直接付费升级。

参考：[Tailscale官方Caddy证书集成](https://tailscale.com/docs/integrations/web-servers/caddy/caddy-certificates)、[官方Caddy TLS说明](https://caddyserver.com/docs/caddyfile/directives/tls)、[Caddy2.11.7发行版](https://github.com/caddyserver/caddy/releases/tag/v2.11.7)。
