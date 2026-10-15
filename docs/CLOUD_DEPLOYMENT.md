# PLW 私有云部署（0.3.1 准备版）

GitHub 账号：**CapSantiago**。目标是单人、免费优先、无需自购域名，保留 Streamlit + SQLite。代码已准备；没有云账号实机、没有本机 Linux Docker 引擎，不能把本手册当作已上线或已完成容器验收。

## M1 结论与最少改造

实际检查了配置、数据访问、资料上传、阅读、登录、数据库迁移和完整备份链路。主要障碍是 `msvcrt`、Windows 绝对路径校验、数据库内 Windows 路径 CHECK，以及云端备份缺少浏览器下载。已增加 Windows/Linux 锁、可配置存储根、追加004迁移、ZIP运输层及 Docker 配置。业务服务和阅读器继续复用。

旧001–003 SQL保持原样。schema4仅放宽资料来源元数据，实际托管文件仍按内部相对路径定位；恢复副本中的行、关联和文件哈希必须不变。Windows现有schema3仍能使用0.3.1本地模式；Linux/私人网站必须schema4。旧0.3.0不能读取schema4，需要回退旧代码时恢复对应旧备份，不能降写版本号。

## 免费资源核实（2026-10-15）

- [Oracle Always Free 官方说明](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)：当前A1免费总量为每月1500 OCPU小时、9000 GB小时，相当于总计2 OCPU/12GB，不采用旧教程4 OCPU/24GB。账号控制台最终额度与Always Free Eligible标记必须再核对。
- 启动盘与块卷合计200GB，最多5个卷备份，免费卷须在home region。磁盘持久化不等于不会因删除卷、账号停用或资源回收丢失。应用备份、ZIP、恢复副本和Docker层都会占空间。
- 免费资源可能出现out of host capacity，实际库存不能在未登录账号时确认。7天内CPU、网络和A1内存均符合官方低使用阈值时可能被回收；不要制造虚假负载绕过限制。
- [Oracle 注册FAQ](https://www.oracle.com/cloud/free/faq/)：需要有效支付卡核验，可能有临时预授权；免费层无SLA。不要升级付费账号、添加收费资源或把试用金误认为永久免费。
- [Tailscale Personal](https://tailscale.com/pricing)当前个人非商业使用免费，最多6用户；本项目只需1人。数据服务在云VM上，Windows关机不影响已运行的云服务。联网仍是必要条件。

没有创建云账号、实例或收费资源。建议先尝试一个Always Free A1 Ubuntu ARM64实例，额度内分配2 OCPU/6–12GB；容量以控制台为准。不能获取A1时先停下来选方案。替代顺序：已有常开设备+Tailscale（电脑关机目标需另一设备在线）；[Google Cloud免费Compute](https://cloud.google.com/free/docs/free-cloud-features#compute)可进一步评估，但小内存、地区、出网与公网IPv4计费要单独核对，不能直接承诺全免费。免费临时容器/静态托管不替代本项目的持久磁盘。收费VPS须由用户另行选择。

## 架构与持久化

```text
Windows / iPad / iPhone（同一Tailscale账号）
  → HTTPS https://<云主机>.<tailnet>.ts.net
  → 云主机 Tailscale Serve
  → 127.0.0.1:8501 → 单进程PLW容器 → SQLite + 托管文件
```

Compose使用Linux host网络。应用只监听云主机回环地址，没有公开8501端口，也没有Funnel。宿主机运行Tailscale，容器不持有Tailscale Token，不增加第二个应用实例。

| 宿主机目录（示例） | 容器目录 | 内容 |
|---|---|---|
| /srv/plw/data | /var/lib/plw/data | SQLite、托管课件、PDF、笔记历史、活动指针、恢复副本 |
| /srv/plw/backups | /var/lib/plw/backups | 完整备份目录、下载ZIP、导入验包副本 |
| /srv/plw/private | /run/plw-private（只读） | account.json：HTTPS地址、账号和加盐密码校验值 |

这些宿主机目录必须在代码仓库外。更新代码/镜像不替换卷；不要执行清空目录、删除卷或重新初始化现有库的命令。运行UID/GID为10001，不使用root运行应用。

## 目标Linux机器的首次部署

前置：自行完成Oracle免费实例创建；准备Git、Docker Engine+Compose和Tailscale（只使用官方安装说明）。这些安装与云端操作本轮未执行。

1. 从已确认的私有仓库克隆代码：`git clone https://github.com/CapSantiago/personal-learning-workbench.git`。私有仓库需要GitHub授权；不要把Token写入URL，也不要上传学习库。
2. 在Linux宿主机创建专用持久目录并设置权限：

```bash
sudo install -d -m 0700 -o 10001 -g 10001 /srv/plw/data /srv/plw/backups /srv/plw/private
cp .env.example .env
docker compose build plw
```

3. 按下节准备Tailscale，取得云主机的完整 `https://...ts.net` 地址。使用无隐私内容的主机名：HTTPS证书的主机名会进入公开证书透明度日志。
4. 交互创建账号配置，密码不放命令行或Git：

```bash
docker run --rm -it --user 10001:10001 \
  --mount type=bind,src=/srv/plw/private,dst=/run/plw-private \
  plw:0.3.1 python scripts/setup_private.py --cloud-defaults --config /run/plw-private/account.json
bash scripts/cloud_compose.sh run --rm --no-deps plw python scripts/launch_private.py --config /run/plw-private/account.json --check
```

5. 用合成资料先验收：可启动后明确创建空库，或先通过维护命令 `cloud_data.py ... init` 创建。正式旧资料用备份恢复迁入，不能先建测试课程再把正式库直接覆盖进去。

```bash
bash scripts/cloud_compose.sh up -d
bash scripts/cloud_compose.sh ps
bash scripts/cloud_compose.sh logs --tail 60 plw
```

`/plw-health`仅回环探针可调用，不含路径或学习记录；有库时检查可读、schema与恢复状态。新空库允许healthy；这不代表所有功能已验收。

## Tailscale与设备连接

依据：[Serve官方说明](https://tailscale.com/docs/features/tailscale-serve)、[Serve命令](https://tailscale.com/docs/reference/tailscale-cli/serve)、[客户端下载](https://tailscale.com/download)。

1. 云主机安装并登录Tailscale；Windows安装客户端，iPad/iPhone从App Store安装Tailscale，使用同一个个人账号登录。
2. iPad/iPhone按系统提示允许VPN配置，打开连接。这里的VPN用于自己的私有设备互通。
3. 在tailnet启用MagicDNS和HTTPS，核对访问控制只包含自己的设备；不要邀请或分享外部用户。
4. 云主机执行 `tailscale serve --bg --https=443 http://127.0.0.1:8501`，按提示启用HTTPS，之后执行 `tailscale serve status` 确认显示“within your tailnet”。不要执行 `tailscale funnel`。
5. 把输出的完整HTTPS根地址填入PLW账号配置。iPad Safari打开该地址，再输入PLW单账号密码。不能使用iPad自己的127.0.0.1地址。
6. 核对未登录课件拒绝访问、上传/PDF.js worker/WebSocket/下载正常，再用不同网络验证。Serve负责HTTPS，PLW登录仍保留；本轮只验证代理协议契约，真实Tailscale连通和证书待实测。

云实例需有联网能力及可管理入口。不要因“私有访问”删掉管理连接；不自动修改云防火墙。公网8501/80/443均无需为PLW打开。

## 功能边界与M3–M5

PDF、批注、任务、笔记使用同一个云库；PPT/PPTX完整上传保留原件，Windows导出PDF后通过网页绑定阅读版。网站不调用PowerPoint/Windows OCR/动画导出。Windows本地模式继续保留原能力，本地库与云库互不覆盖。

M3：免费账号库存与证书 → 合成部署、重启/重建持久化、备份恢复 → 确认迁移范围 → 完整备份迁移 → 真机不同网络验证。M4：确认私有仓库后接入Git与更新脚本。M5：先真机定位触控问题，再局部修复；不预先重写前端。

PWA本轮延期：Streamlit壳由服务端提供，简单注册Service Worker不能提供离线工作台。可先用Safari“添加到主屏幕”，但独立显示、重新登录与下载仍需真机验收。低侵入manifest/图标/更新提示放在后续；不缓存私人PDF/API/登录响应，不承诺后台同步。PDF下载离线阅读已保留。
