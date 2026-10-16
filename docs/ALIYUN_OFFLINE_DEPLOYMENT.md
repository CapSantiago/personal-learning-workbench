# 阿里云离线部署（PLW 0.3.1）

更新：2026-10-17。适用于已购买的杭州 ECS、Ubuntu 24.04 x86_64、2核2GB、40GB、3Mbps。Docker 29.9.1、Compose v5.6.0；离线构建和两容器合成验收已通过。Tailscale已登录，Serve私有入口、PLW账号、独立空云库已配置，Compose服务启动且回环健康检查通过。当前从第4节客户端访问验收继续，不重复prepare、configure或init。真实学习资料尚未迁移。

服务器访问 Docker Hub 超时。使用 Windows 下载并校验官方 Python 镜像、PyPI wheel 和 Tailscale 静态包，再通过 Workbench 上传。没有更换 Streamlit/SQLite 架构、付费加速器或第三方公共镜像代理。此包不含真实学习数据或登录配置。

## 1. 上传并验证

本地包和 SHA-256 旁文件位于项目 `.sandbox/releases`，文件名为 `PLW-0.3.1-offline-linux-amd64-20261016.zip`。在 Workbench 左侧文件管理中上传到服务器 `/root/`。先与本地 `.sha256` 的值核对：

```bash
cd /root
sha256sum PLW-0.3.1-offline-linux-amd64-20261016.zip
```

匹配后解压到新的目录；如果目录已存在，停下来检查，不覆盖旧部署：

```bash
test ! -e /opt/plw-offline-20261016 && mkdir -m 0755 /opt/plw-offline-20261016
python3 -m zipfile -e /root/PLW-0.3.1-offline-linux-amd64-20261016.zip /opt/plw-offline-20261016
cd /opt/plw-offline-20261016
python3 verify_offline_bundle.py /opt/plw-offline-20261016
```

务必确认第一条创建目录的命令成功后再解压。不要把从不明来源下载的 ZIP 放入该流程。

## 2. 导入镜像、断网构建和隔离验收

**已构建镜像后的PDF夹具兼容修复**：若镜像构建已完成，但offline_smoke.py的PdfWriter子进程退出1，可上传最新源码中的`scripts/resume_linux_acceptance.sh`到服务器`/root`，执行`bash /root/resume_linux_acceptance.sh /opt/plw-offline-20261016`。它复用原镜像，不触及学习目录，修正Linux stdout的定位兼容写法后，用两个新容器验证合成卷；其他异常会显示子进程stderr供排查。成功应显示两份passed及ACCEPTANCE PASSED。

**首个20261016离线包的Docker29兼容修复**：若输出`Loaded base image identity mismatch.`，不要跳过检查或改原包清单。该包的config摘要与Docker29导入后manifest摘要不同。上传小包`PLW-Docker29-fix-20261016.zip`，校验SHA-256 `61808942f00aa17dd869b6cb20951ad2721ab86957018a9f2ff9c22fd5406381`后，在新的`/root/plw-docker29-fix-20261016`目录解压，执行：

```bash
python3 /root/plw-docker29-fix-20261016/resume_offline_prepare.py --bundle /opt/plw-offline-20261016
```

小包不能解压进原部署目录，原清单会拒绝额外文件。兼容启动器重新核对原包及镜像config/四层哈希，计算containerd导入清单摘要后继续原prepare流程，原目录文件保持不变。后续install-tailscale/configure/init/start仍使用原安装器。新源码安装器已直接调用兼容验证器。

```bash
bash install_offline.sh prepare
```

脚本先核对完整文件清单，拒绝篡改、额外文件、链接和不安全路径，然后导入 Python 镜像并核对 image ID。Docker 构建使用 `--network=none --pull=false`，pip 仅从本地 wheelhouse 安装。Dockerfile 中不指定需要额外下载的外部构建前端。

随后在 `/var/tmp/plw-acceptance.*` 新目录、无网络容器内创建合成课程、两页 PDF、阅读版本、高亮、书签、进度、Markdown 公式笔记和已完成任务，生成完整 ZIP 并恢复至另一合成学习库。第二个容器验证同一测试卷的内容哈希及关联。结果保留供检查；不挂载 `/srv/plw/data`，不复制正式资料。

最后应有 seed/check 两份 `passed: true` 和 `PREPARED`（续跑脚本为`ACCEPTANCE PASSED`）。2026-10-16用户提供的Linux实机续跑结果已通过，证据保留于`/var/tmp/plw-acceptance.xda3fje0`。这验证了两个合成容器之间的数据保留，正式Compose服务重启/更新仍须单独验收。

## 3. 安装并登录 Tailscale

```bash
bash install_offline.sh install-tailscale
tailscale up --hostname=plw
```

安装使用 Tailscale 官方静态包内的两个 Linux 程序和 systemd 单元，不依赖 Docker Hub。存在旧安装时拒绝覆盖。不自动更改云安全组、不启用 Tailscale SSH、子网路由或公网 Funnel。

打开 `tailscale up` 显示的登录链接，用自己的个人账号登录并授权这台服务器。该操作需要用户亲自完成。iPad、iPhone 从 App Store 安装 Tailscale，Windows 安装官方客户端，使用同一账号。登录信息与密钥不放进聊天、GitHub 或部署包。

登录后配置私有 HTTPS：

```bash
tailscale serve --bg --https=443 http://127.0.0.1:8501
tailscale serve status
```

根据提示在自己的 tailnet 启用 HTTPS，核对显示 `within your tailnet`，记下 `https://plw.<你的网络>.ts.net`。此时应用还未启动，出现后端未就绪不等于证书配置失败。不要执行 Funnel。

## 4. 建立独立空学习库并启动

```bash
bash install_offline.sh configure
```

按提示输入上一步的 HTTPS 根地址、PLW 单账号名称和至少12字符密码。密码仅在服务器交互输入，不回显、不保存明文。学习目录、备份目录和账号目录独立存放，均在代码目录外。已有数据或配置时脚本拒绝覆盖。

```bash
bash install_offline.sh init
bash install_offline.sh start
bash install_offline.sh status
```

`init` 只用于首次空库；检测到活动学习库时拒绝运行。`start` 仅启动本地已构建镜像，不访问镜像仓库，也不开放公网8501。健康通过不等于真机阅读/触控功能全部验收。

所有日常设备先连接 Tailscale，再用浏览器打开私有 HTTPS 地址并登录 PLW。云服务器保持运行，Windows关机不影响云端服务。离线阅读仍是预先下载 PDF 到设备，不能离线打开完整 Streamlit 工作台。

## 5. 数据、备份、更新

- 第一次部署先使用空库与合成资料，不自动迁移 `E:\PLW-Data`。正式迁移单独确认后，通过完整备份包校验和隔离恢复进行。
- 云端完整备份从“数据与备份”生成并下载到 Windows；原始 PDF 不包含全部 PLW 批注与笔记，不能替代完整备份。详见 [CLOUD_DATA_BACKUP](CLOUD_DATA_BACKUP.md)。
- 此离线包不是 Git checkout，不要在这里运行原 `update_cloud.sh` 或直接 `git pull`。后续更新先准备新包、隔离验收、完整备份，再切换镜像；保留旧镜像、旧部署目录和数据。含 schema 变化时先走独立恢复验证。
- 不能通过 `docker compose down -v`、删除持久目录、复制本地数据库覆盖云库来“更新”。镜像与云端学习库分别管理。
- 初次访问成功后再收紧当前默认安全组中的公网 SSH/RDP 规则，保持 Workbench 管理通道；本脚本不改安全组。

## 当前实际状态与限制

- 官方Python镜像、43个服务器wheel、Tailscale静态包已核对，用户已上传离线包并在Linux实际完成镜像导入、构建及两容器合成验收，36文件哈希一致。不是正式网站的Compose重启/更新验收。
- Tailscale已登录、Serve私有入口已配置；PLW单账号预检与独立空库初始化通过，Compose服务启动且回环健康返回ok、版本0.3.1。输出时Docker为health: starting，需复查；尚未确认客户端HTTPS访问与设备功能，不得称为跨设备验收完成。
- 用户可通过Workbench公网与密码认证管理实例，VNC也已成功；私网路径仍失败。Tailscale对CGNAT来源的防护可能与阿里云内部服务地址冲突，需要只读查看实际防火墙规则后确定，不直接删除防护规则。
- 本机Linux Docker引擎仍不可用。浏览器控制工具因Windows路径错误初始化失败；服务器命令由用户执行并提供日志，不能描述为代理已直接操作服务器。正式资料尚未迁移。

官方来源：[Docker 导入归档](https://docs.docker.com/reference/cli/docker/image/load/)、[Tailscale 静态安装](https://tailscale.com/docs/install/static)、[Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve)。
