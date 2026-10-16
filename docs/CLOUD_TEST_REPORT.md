# 云端准备测试报告

## 2026-10-16 阿里云离线部署补充

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
