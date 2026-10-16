# 云端数据与Windows备份

## 2026-10-16 首次阿里云部署边界

当前离线安装包只包含代码、官方Python镜像、Linux依赖和Tailscale安装包；**不是学习数据备份**，不含`E:\PLW-Data`、已有课程或登录配置。首次云端先建空库，正式资料需用户确认迁移范围后另行生成完整备份、校验并隔离恢复，不能用本地SQLite直接覆盖云库。部署步骤见[阿里云离线部署](ALIYUN_OFFLINE_DEPLOYMENT.md)。

云库是日常主库，Windows原始课件是资料来源；Windows本地PLW库是另一套库，不自动与云库同步。批注、任务和笔记必须通过完整备份保留，只有原始PDF/PPT不够。

## 网页手动备份

私人网站“数据与备份” → “生成完整备份包” → 校验成功后“下载完整备份包”。同时复制显示的ZIP SHA-256。在Windows保存后执行：

```powershell
Get-FileHash -LiteralPath '你下载的完整备份包.zip' -Algorithm SHA256
```

ZIP只是原格式1备份目录的运输包装；包括manifest.json、manifest.sha256、完成标记和payload，payload包括数据库、托管课件、阅读PDF、Markdown历史。标记、进度、任务、章节都在数据库中。外部引用原件不包含，报告逐条说明；OCR和播放缓存可重建，不包含。账号配置与密码不打包。

单包及解压量上限20GiB，逐文件校验，不将整个ZIP读入Streamlit会话内存。链接12小时有效，必须登录，篡改后拒绝下载。ZIP不加密，保存到自己的受控磁盘；已下载文件不再受网站密码保护。备份文件不自动清理，定期检查空间并人工保留合适版本。

## 命令与恢复

以下在Linux代码目录执行，配置固定在容器内。初始化、恢复及回滚需要停止应用；维护进程持有同一服务锁，避免恢复过程中重新启动写入实例。创建备份可在线执行，使用已有写屏障和SQLite backup API。

```bash
# 备份在线主库，同时生成ZIP，输出清单与整包SHA-256
bash scripts/cloud_compose.sh exec -T plw python scripts/cloud_data.py --config /run/plw-private/account.json backup
# 查看活动数据集ID与schema
bash scripts/cloud_compose.sh exec -T plw python scripts/cloud_data.py --config /run/plw-private/account.json status
# 以下是明确的维护窗口
bash scripts/cloud_compose.sh stop plw
# ZIP须事先保存到映射的备份目录，如 /srv/plw/backups/incoming.zip
bash scripts/cloud_compose.sh run --rm --no-deps plw python scripts/cloud_data.py --config /run/plw-private/account.json verify --archive /var/lib/plw/backups/incoming.zip
# 新空库使用EMPTY；已有库必须填写上方查得的准确活动UUID
bash scripts/cloud_compose.sh run --rm --no-deps plw python scripts/cloud_data.py --config /run/plw-private/account.json restore --archive /var/lib/plw/backups/incoming.zip --confirm EMPTY
bash scripts/cloud_compose.sh up -d
```

`verify`只解包至新import-UUID目录并验证，不切换库。`restore`再次验证，先为原库生成回滚备份，再恢复到新数据集、校验文件和关联、迁移该新副本，最后切换活动指针。原库、原备份都保留。失败残留保留诊断，不自动覆盖或删除。空间至少预留完整备份、ZIP和恢复副本，不能只留一份课件容量。

回滚：停服务后用 `cloud_data.py ... rollback --confirm 当前活动UUID`；会先保留回滚前副本，再切回旧数据集。旧schema3只由支持它的程序读取，不能拿0.3.0直接打开schema4。

## Windows本地迁往云端

先确认范围和时间窗口，在原Windows PLW中生成完整备份；使用本项目 `backup_transfer.pack_backup` 包装经验证的备份目录。此操作必须由后续明确迁移步骤执行，本轮没有备份或上传正式学习数据。复制ZIP到云端backup目录，核对整包SHA，再按上方恢复；不要复制一个正在写入的SQLite文件。

Windows路径在旧库中保留为来源元数据，托管文件通过相对路径读取。外部引用在Linux不能读取Windows盘符，需要先选择上传完整文件或接受索引未包含状态。恢复不会访问这些外部路径。

## 隔离恢复演练

为演练准备独立数据/备份目录和单独账号配置（配置中的路径及Compose bind需同时指向演练目录），用同一版本镜像在停服状态恢复合成ZIP。不要挂载Windows正式库或云端正式data目录，不与正式服务同时监听8501。核对课程/资料/笔记/任务/标记数量、PDF页码、文件SHA、PRAGMA integrity_check和foreign_key_check，再切回正式配置。Docker停止、重建镜像、重新部署后各复核一次。

本轮Windows合成ZIP恢复与schema3→4回滚已纳入测试；实际Linux卷、云端下载到Windows及真机流程仍待目标环境验收。自动备份与自动下载后续再做，不把同一台免费VM的副本当作唯一备份。
