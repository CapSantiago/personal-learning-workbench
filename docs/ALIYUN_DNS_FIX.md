# 阿里云 DNS 与 Tailscale 兼容修复

适用范围：已验证的Ubuntu主机eth0，DNS为100.100.2.136和100.100.2.138。不要直接套用到其他网络。

2026-10-17实测：Tailscale ts-input丢弃100.64.0.0/10来源，导致阿里云DNS回复无法到达，ACME域名解析超时、HTTPS握手失败。四条精确例外生效后，DNS解析及ACME目录200恢复，Windows直连证书校验成功，登录页200；用户随后提供成功登录主页面截图。

每条例外同时要求eth0、单个DNS地址、UDP/TCP源端口53、连接状态ESTABLISHED及方向REPLY。其余CGNAT防护保持原样，不全局关闭netfilter，不修改SSH规则、应用账号、数据库或资料。

## 持久化安装

包包含aliyun_dns_exception.sh、install_aliyun_dns_exception.sh和本说明，不含学习资料。上传到/root，先与提供的SHA-256核对，再解压到一个全新目录，例如/opt/plw-dns-fix-20261017。不要解压进原PLW离线包目录，它的清单拒绝额外文件。

在新目录执行：

```bash
bash install_aliyun_dns_exception.sh
```

安装器先检查现有临时规则，然后创建：

- /usr/local/sbin/plw-aliyun-dns-exception
- /etc/systemd/system/tailscaled.service.d/90-plw-aliyun-dns.conf

已有同名文件或链接时拒绝覆盖，不编辑其他systemd配置。ExecStartPost在tailscaled每次启动后最多等待30轮链建立，再幂等补充四条例外。安装本身只重新读取systemd配置，不主动重启Tailscale。

保留已成功的Workbench公网连接或VNC，测试重启：

```bash
systemctl restart tailscaled
/usr/local/sbin/plw-aliyun-dns-exception check
resolvectl flush-caches
timeout 20s resolvectl query acme-v02.api.letsencrypt.org
```

随后从客户端再次检查HTTPS登录和Tailscale状态。服务重启会短暂中断tailnet连接。服务器整机重启仍须单独验收，不能只凭脚本语法校验标记为通过。若网络设置变化，要重新核对接口与DNS地址。

## 定向回滚

仅在确认以下两个文件就是本包创建且未被其他维护修改后，移除本包的drop-in：

```bash
rm -- /etc/systemd/system/tailscaled.service.d/90-plw-aliyun-dns.conf
systemctl daemon-reload
/usr/local/sbin/plw-aliyun-dns-exception remove
rm -- /usr/local/sbin/plw-aliyun-dns-exception
```

remove只删除四条完全匹配的带标记规则，不清空任何链或恢复整套防火墙。移除后原DNS/证书故障可能重现，保留公网SSH/VNC管理连接。

## 验证边界

- 原四条临时规则及DNS/ACME访问：用户已在Linux执行成功。
- 新脚本：本地Bash语法校验；未在Windows调用真实iptables或修改系统设置。
- 新systemd drop-in安装、Tailscale重启、整机重启：尚待云端执行，不声称已经完成持久化。

来源：[Tailscale CGNAT互操作](https://tailscale.com/docs/reference/cgnat-interoperability)、[iptables conntrack语义](https://man7.org/linux/man-pages/man8/iptables-extensions.8.html)。
