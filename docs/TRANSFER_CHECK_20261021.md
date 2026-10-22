# 2026-10-21 首次下载路径实测与后续核验

## 已实际取得的结果

用户运行工具后，完整报告保存于 `.sandbox/releases/PLW-Transfer-Check-20261021/result-20261021-144711-986922/`。四次均完整接收2 MiB随机数据并通过SHA-256校验。

|路径|第1次 KiB/s|第2次 KiB/s|按总字节/总时间 KiB/s|
|---|---:|---:|---:|
|公网SSH回环转发|524.0|408.9|459.34|
|Tailscale私有HTTP直连|395.9|389.7|392.76|

当前容器镜像确认为 `plw:0.3.1-device-library-20261021-r2`，运行中，无OOM或重启。CPU测试期间整体约4.87%，可用内存约1142 MiB。实际Tailscale数据走IPv4直连，DERP数据计数未增加；不能把Peer中的home relay地区当作正在中继的证据。

测试期间主机全局TCP RetransSegs增加1504，OutSegs增加6485。这是需要追查的重传信号，**不是该PDF连接23%的精确丢包率**。接口无采集到的丢包/错误、qdisc无丢弃或overlimit，不代表云平台出口没有限速。

按这次短测平均速率外推29,613,390字节，公网SSH约63秒、Tailscale约74秒。该值只是同速估算，不是实际28 MB课件测试。购买记录曾有3 Mbps套餐描述，但当前购买/升级后的出带宽配置没有直接读取，**不能由测速反推已核实套餐上限**。

## 本次测量未覆盖的层

第一次工具的Tailscale路径是100.104.174.9:19193上的内核TCP HTTP端点，没有经过当前网站443上的Serve HTTPS代理、应用认证、文件校验或浏览器本地保存。2 MiB测试也不足以证明长文件持续传输没有停顿。

网站代码没有固定KB/s限制。批量队列串行不等于每个文件被限速；IndexedDB空间配额是容量而不是速度。已完成并校验保存的文件会本机复用。此前全文件反复校验和PDF.js兼容问题是已发现的独立问题，不足以解释当前所有传输停顿。

## 定向补测工具

入口 `.sandbox/releases/PLW-HTTPS-Transfer-Check-20261021/Check-PLW-HTTPS-Transfer.ps1`。用户在本机终端输入一次现有root密码，主机密钥严格匹配既有ED25519。保持现有网络，在网站停止下载后执行。

同一份8 MiB内存随机数据依次经：内核Tailscale直连、Serve HTTPS、公网SSH回环。每条最多45秒、最多24 MiB，不读取真实课件或账号配置，不提取网站登录信息。HTTPS必须通过正常证书校验，未使用 `-k`。

为了隔离Serve，在**未占用的私有19443端口**启动前台会话，代理回环19194；不修改现有443根入口，不启用Funnel、不开放公网端口、不改防火墙或全局TCP参数。随机单次nonce只允许读取合成数据，停止端点只允许回环。校验前台配置仅增加期望的一项，发现占用或并发配置变化即停止。正常结束终止该前台会话，并核对临时端口消失与原配置一致；不执行全局reset/restore。

CLI由独立的165秒timeout监督，异常时也有会话存活上限；内存端点READY后180秒自动结束。若其他客户端同时修改配置，只报告不一致，不覆盖其他人的配置。结果含部分接收字节、curl退出状态与完整文件SHA，不把timeout当成功。端口被现有ACL拒绝、TLS失败、零字节连接失败不能算有效吞吐对照。

已通过6项隔离/清理/占用/并发变更与实际PowerShell接收检查，加上之前端点3项共9项。前台CLI配置形状/生命周期核对官方1.104.1源码；Tailscale命令在本地测试中使用模拟进程，**真实服务器Serve对照尚待执行**。curl使用HTTP/1.1合成端点，该结果用于判断Serve传输影响，不等同于浏览器HTTP/2、生产文件接口或iPad端到端验收。

## 修复决策

若Serve明显比同路径内核TCP低或出现停顿，优先隔离/更换HTTPS入口实现，保留原网址、TLS和应用认证，再做真实课件验证。若三条都近似同速，进一步读取云控制台实际出带宽配置和传输重传证据，不能直接购买升级。若合成Serve也正常而真实课件慢，回到实际认证下载与浏览器保存过程取证。

当前没有据此修改云端网站、Tailscale版本、拥塞控制、MTU或付费配置；首次下载慢尚未宣称修复。

参考：
- [Tailscale Serve性能问题18307](https://github.com/tailscale/tailscale/issues/18307)：含1.104.1仍低速的用户记录，只作为待验证线索，不是本实例根因证明。
- [官方Serve CLI](https://tailscale.com/docs/reference/tailscale-cli/serve)
- [1.104.1前台会话实现](https://github.com/tailscale/tailscale/blob/v1.104.1/cmd/tailscale/cli/serve_v2.go)
- [阿里云网络带宽说明](https://www.alibabacloud.com/help/en/ecs/user-guide/network-bandwidth/)
