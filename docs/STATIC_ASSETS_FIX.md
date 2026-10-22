# 私有站点静态文件传输修复

2026-10-17，适用于已经应用入口修复的离线云端部署。

## 实际证据与边界

用户提供的 Chrome HAR 仅含 8 个已完成请求，未包含截图中仍 Pending 的请求，也没有业务 WebSocket 记录：

- 根文档 197.7ms，HTTP/2；因此 HTTP/1.1 六连接上限不适用于这次记录。
- 主脚本 449225 字节，传输约 5 秒，总计 5977.8ms；客户端声明接受 gzip/br/zstd，但响应没有 Content-Encoding。
- 只有 75 字节的脚本等待首字节 5962.7ms，下载 0.484ms。尚不能把所有延迟都归因于文件大小或带宽。
- 所有已完成静态文件均为 `Cache-Control: private, no-store`，重新打开无法利用浏览器文件缓存。
- 同期用户样本 CPU 0.56%、可用内存约 1.1GiB、10 秒平均发送 0.02Mbps；不足以认定资源或带宽持续满载，也不排除其他时段网络停滞。

修复已经确认的压缩/缓存问题，不承诺解决尚未解释的全部连接停滞。浏览器控制运行时初始化失败，助手没有接管浏览器或获得真实登录会话。

## 变更范围

PrivateAccess 验证登录、Host、HTTPS、Origin 和请求方法后，仅对带 8 位版本标记的 `/static/js`、`/static/css`、`/static/media` 框架文件启用传输策略。只有框架明确标记 immutable、返回 200、类型匹配且不设置 Cookie 的响应可缓存，使用 `private, max-age=86400, immutable`。

客户端允许 gzip 且不是 HEAD/Range 时，为这类路径启用 Starlette gzip，级别 5、最小 1024 字节。编码变体使用 Vary 和弱 ETag。登录页面、HTML 回退、学习数据、PDF、备份、上传和 WebSocket 原有验证保留；不开放匿名静态资源，也不改变数据库。

## 验证状态

- 更新：用户 13:24 的 Linux 日志确认包与基线检查、离线构建、镜像内合成验证、完整备份及新镜像回环健康均通过。已切换 `plw:0.3.1-assetsfix-20261017`，真实浏览器表现待验证。下文“待执行”是发布前阶段记录，以本项为准。
- 云端合成输出 `index 2471 -> 1128 bytes` 实际验证的是一个 index 命名的小片段，原验证器依赖目录枚举顺序。源码现按 HTML 的 module script 确定主入口；这是验证工具修正，原已发布 ZIP 不修改，已安装站点不需因此重跑。
- Windows：`pytest tests/test_private_assets.py tests/test_private_auth.py tests/test_cloud_compat.py -q`，56 passed，18.19 秒。
- 测试使用真实 Streamlit 静态处理器，覆盖流式 gzip 字节还原、私人缓存、匿名/跨站/失效会话拒绝、HEAD、Range、条件请求、HTML 回退和 Cookie 响应。
- 本地镜像内合成检查同款验证器通过：实际主脚本 449225 → 138832 字节；这里只在 Windows 直接运行验证器，不代表 Linux 容器已执行。
- Linux 衍生镜像构建、镜像内合成检查、正式部署及 Windows/iPad 体验：仍待执行。安装器会先在不挂载正式数据、无网络的容器中校验真实框架主脚本，再生成完整备份后更新。

## 离线安装

发布文件：`PLW-Static-Assets-fix-20261017.zip`。使用配套 `.sha256` 文件核验外层包；不要覆盖此前入口或 DNS 补丁包。

在 Windows PowerShell 7 上传：

```powershell
scp -o HostKeyAlgorithms=ssh-ed25519 "E:\Projects\PLW\.sandbox\releases\PLW-Static-Assets-fix-20261017.zip" "E:\Projects\PLW\.sandbox\releases\PLW-Static-Assets-fix-20261017.zip.sha256" root@100.104.174.9:/root/
```

然后在云端 root 终端执行（目标目录必须尚不存在，防止混用旧文件）：

```bash
(
set -euo pipefail
cd /root
sha256sum -c PLW-Static-Assets-fix-20261017.zip.sha256
test ! -e /opt/plw-static-assets-fix-20261017
mkdir /opt/plw-static-assets-fix-20261017
python3 -m zipfile -e /root/PLW-Static-Assets-fix-20261017.zip /opt/plw-static-assets-fix-20261017
bash /opt/plw-static-assets-fix-20261017/install_static_assets_hotfix.sh
)
```

仅接受现有 `plw:0.3.1-entryfix-1381e66` 且 PrivateAccess 文件与原入口补丁一致的运行环境。目标镜像 `plw:0.3.1-assetsfix-20261017`。不编辑原离线包，不运行 init，不重启 Tailscale。备份失败则不更新；切换后健康失败则恢复旧环境并尝试启动旧镜像。实际故障回退仍需实机验收。

启动后需要重新登录（进程内会话失效）。先打开课程管理，检查骨架控件是否完成，再在同一设备重新打开一次查看缓存；iPad 也单独验收。记录主脚本 Content-Encoding、Cache-Control、Timing 和仍 Pending 的请求，不能仅用登录页或健康接口推断业务恢复。

## 手工恢复旧镜像

如果更新后健康正常但浏览器出现新问题，使用安装器打印的确切 `Previous environment` 路径。先确认其 `PLW_IMAGE=plw:0.3.1-entryfix-1381e66`，再恢复该快照至 `/srv/plw/private/deploy.env`，执行原 Compose 的 `up -d --no-build --pull never`。保留当前/旧镜像、所有备份和日志；无需回滚数据库。
