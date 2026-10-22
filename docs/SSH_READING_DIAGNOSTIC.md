# SSH 加密传输阅读对照（2026-10-18）

## 16:06 采集后的当前工具

同步日志已确认两个正确的 64 KiB 范围响应在内容传输中停顿约 52/51 秒，结束时仍未收齐，服务器没有资源饱和。当前工具改为固定目标 CONNECT 经 SSH 转发，避免 SOCKS 代理侧私有域名 DNS 不确定性；下文两条手动命令保留为早期方案，不需要再执行。

执行 `.sandbox/releases/PLW-SSH-Access-20261018/Open-PLW-SSH.ps1`，本机 127.0.0.1:1081 经验证主机密钥的公网 SSH 连接服务器临时 127.0.0.1:18181，后者只允许固定 PLW 域名:443 并连接自己的 100.104.174.9:443。复用当前 PLW 专用 Chrome 配置，保持 HTTPS 证书/登录，只改变此窗口的数据路径；网站和系统代理不改。服务器程序不写文件，断开后退出，最长 30 分钟。密码仅在本地输入。

本地四路并发字节往返、拒绝其他目标/端口/方法、证书核验与 HTTPS 探测测试通过。尚未实际建立服务器通道或取得阅读验收，不声称已永久修复。详见 [最新诊断](COURSEWARE_DIAGNOSIS_20261018.md)。

## 目的与边界

rangefix后的用户专用Chrome HTTP/1.1/禁QUIC/直连窗口曾显示第25页，缩略图可逐步显示，但随后第15页仍卡住。收起缩略图20秒也未恢复，因此不能把HTTP/2、原Wi-Fi或缩略图当作已确认的唯一根因。

此前真实PDF经公网SSH/SCP约6秒、4.4MB/s，而Tailscale隧道SCP严重偏慢。临时SSH SOCKS通道用于只替换访问ECS的传输路径，再检查同一网站是否稳定。只绑定本机127.0.0.1，不修改系统代理、云端防火墙、数据库或站点配置；保留HTTPS原域名、证书和网站登录。此通道只解决电脑上的诊断访问，不代表iPad已经修复。

Chrome的SOCKSv5对目标连接使用代理侧域名解析，见[Chromium代理说明](https://github.com/chromium/chromium/blob/main/net/docs/proxy.md)。Tailscale内核网络模式的Serve为服务器本机连接设置本地监听，见[官方实现](https://github.com/tailscale/tailscale/blob/main/ipn/ipnlocal/serve.go)。当前ECS实例是否可经此路径连接仍需实际验证，不从源码推断为已成功。

## 电脑 PowerShell：建立临时通道

```powershell
ssh -N -D 127.0.0.1:1081 -o ExitOnForwardFailure=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -o HostKeyAlgorithms=ssh-ed25519 -o HostKeyAlias=100.104.174.9 -o StrictHostKeyChecking=yes root@47.98.151.12
```

使用此前已核实的ED25519主机密钥别名，不接受未知新密钥。输入当前服务器密码后保持窗口打开；成功连接后无输出是正常现象。Ctrl+C关闭通道，无后台自动重连或持久服务。

## 另一个 PowerShell：打开专用窗口

```powershell
Start-Process "C:\Program Files\Google\Chrome\Application\chrome.exe" -ArgumentList "--user-data-dir=E:\PLW-SSH-Test-20261018","--disable-http2","--disable-quic","--proxy-server=socks5://127.0.0.1:1081","https://plw.tail066864.ts.net"
```

保留上一窗口的HTTP/1.1、禁QUIC条件；在新的独立目录改用SSH代理。网站重新登录后检验第15页、连续翻页/跳页，不重传已有PDF。新目录也隔离了旧浏览器状态，因此即使本次成功，仍须谨慎区分缓存/会话状态与数据路径影响。

通道打开后，助手可先通过 `curl --socks5-hostname 127.0.0.1:1081` 只读检查HTTPS登录页和证书。若通道或Serve本机监听不可达，先报告具体错误，不改站点为公开访问、不关闭TLS验证。

## 本地真实文档检查

原35页PDF用捆绑PDF.js 5.6.205、原worker在Node24测试进程中解析和渲染。Node使用已有@napi-rs/canvas，自定义CanvasFactory，测试进程补齐Node缺少的Uint8Array.toHex和Map.getOrInsertComputed；未修改网站或捆绑JS。全文件已在内存，不能用此结果证明网络范围加载或真实浏览器生命周期正常。

第15页正文与第14/16页缩略图并发：正文1059ms，临近缩略图494/1172ms；已载入第15页的缩略图77ms，第25页缩略图246ms。第15页PNG已视觉检查有正常内容。这说明该页可由同版解析器处理，不等于排除网页渲染调度或网络问题。

以上SSH通道尚未由用户建立，未取得稳定阅读对照结果。本轮不生成新应用补丁。
