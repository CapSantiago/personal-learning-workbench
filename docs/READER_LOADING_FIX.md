# 私人网站 PDF 加载修复（2026-10-17）

后续发现：本版裸路由支持范围请求，但未覆盖 Streamlit 内置压缩对首次200响应的影响。用户部署后仍空白；加入实际中间件的回归测试已复现默认gzip使范围发现失效。请参见 [PDF 首次响应修复](READER_RANGE_FIX.md)。原ZIP与原安装目录不覆盖。

## 适用范围

仅用于当前 `plw:0.3.1-assetsfix-20261017` 部署，生成衍生镜像 `plw:0.3.1-readerfix-20261017`。原离线包、账号配置、数据集和旧镜像保留。安装前检查当前镜像、环境和四个旧模块的摘要；不匹配即停止，不覆盖未知版本。

此次修复针对已确认的加载不足：原同源 PDF 路由完整读取后返回 200，没有 Accept-Ranges；阅读器脚本没有压缩；首次加载只有空白画布与“已保存”，缺少加载提示。用户截图的空白具体停在哪一项请求仍未取得，不能把这些代码问题当作已确认的唯一根因。

## 变更

- 注册的 PDF 改由框架 FileResponse 提供 HEAD、206 分段读取及无效范围 416。每次读取仍核对安全路径、活动数据集和完整 SHA-256，保持登录、跨站保护与 private/no-store；不发布任意路径。
- PDF.js 使用 64KiB 范围请求，关闭整份流式下载与自动预取，缩略图等当前页显示后再开始。PDF 对象间依赖可能需要多个范围，不承诺只取 64KiB 就能显示任意文档。
- 只压缩通过原有清单摘要校验的内置 JS/CSS/WASM，尊重 gzip;q=0；PDF、用户媒体、课件与备份不压缩、不放进共享缓存。阅读 worker 实测 2186232 → 472948 字节。
- 增加与保存状态分开的阅读器/课件加载提示及接收量。修改 PDF 传输与显示，不改变数据库结构、课件原件或笔记。

## 部署

在 Windows PowerShell 上传修复包及摘要。公网 SSH 仍使用此前核实的主机密钥别名：

```powershell
scp -o HostKeyAlgorithms=ssh-ed25519 -o HostKeyAlias=100.104.174.9 -o StrictHostKeyChecking=yes "E:\Projects\PLW\.sandbox\releases\PLW-Reader-Loading-fix-20261017.zip" "E:\Projects\PLW\.sandbox\releases\PLW-Reader-Loading-fix-20261017.zip.sha256" root@47.98.151.12:/root/
```

随后在阿里云 root 终端执行：

```bash
(
set -euo pipefail
cd /root
sha256sum -c PLW-Reader-Loading-fix-20261017.zip.sha256
test ! -e /opt/plw-reader-loading-fix-20261017
mkdir /opt/plw-reader-loading-fix-20261017
python3 -m zipfile -e PLW-Reader-Loading-fix-20261017.zip /opt/plw-reader-loading-fix-20261017
bash /opt/plw-reader-loading-fix-20261017/install_reader_loading_hotfix.sh
)
```

安装器离线构建、隔离合成检查，生成当前云学习库的完整备份，保存旧环境，再切换镜像和检查本地健康。切换后的命令错误/健康失败会尝试恢复旧环境与镜像；不会自动恢复/重置数据库。不重启 Tailscale 或主机。新镜像成功启动不等于真实阅读验收，仍须重新登录查看第一页、跳页和标记保存。

## 验证与限制

- 用户最新 Linux 安装输出确认外层 ZIP、全部载荷与四个旧模块基线检查通过；离线镜像构建成功，容器内检查 `PDF range 65536/1048591 bytes; worker 2186232 -> 474803 bytes` 通过。压缩结果随运行环境略有差异，解压后字节一致性检查通过。
- 切换前完整备份 `c02bac3c-0cb3-4c15-ba2b-10f4aa3cc2c9`，4个文件、59550445字节，complete=true，数据集保持 `fe2dfea7-f600-4f01-9d12-ab38a917ad8d`。阅读副本 `4671e11e-7a63-4436-ab28-2ccfd46fdece` 为29613390字节、摘要与原件一致。备份ZIP为59553321字节，SHA-256 `e3660b8d00cfdb938695854b2f7916eb202c10beb7d39a2cb6f22dc7860f85c1`。
- 新镜像 `plw:0.3.1-readerfix-20261017` 已启动并通过安装器回环健康检查；旧环境 `/srv/plw/private/deploy.env.before-readerfix.otp9vSjp`。未触发失败回退，不能视为回退演练完成。真实浏览器阅读和标记保存仍待用户验收。
- Windows 81 项访问、登录、静态资源和离线下载相关测试通过（22.99秒）；前端模块语法检查通过。
- 独立烟雾检查以约1MiB合成载荷确认只返回64KiB；代理 HTTPS 下的认证、注销、跨站、篡改拒绝和内置 worker 压缩通过。合成载荷不是用户课件，不用于证明 PDF 视觉渲染。
- 用户原 PDF 在本地渲染第一页正常，35页；与已导入托管原件的摘要一致。云端真实网页仍空白，部署后的阅读与标注待用户验收。
- 本机没有可用 Linux Docker 引擎；上述镜像内检查与启动健康来自用户在 ECS 的实际安装日志。浏览器控制运行时不可用，没有从中获得用户登录会话。本轮外部连通复测时，本机 Tailscale 返回 NoState，域名解析失败，固定已知私网地址连接也超时；不能将此记为服务器故障，也不能宣称真实网页阅读已修复。
- 用户 Wi-Fi 上 Tailscale 原生 SCP 2MiB 约167秒；手机热点的 Taildrop 同一合成文件约10.34秒完成，工具不同，不当作同协议严格测速。热点 TSMP 27ms，原网络约200ms。切换网络改善不等于 Wi-Fi 路径已修复；现有3Mbps公网出站也可能影响大 PDF 阅读，但不是之前低上传速率的直接证明。

DNS 例外的启动持久化尚未安装验收，不应为了此补丁重启 tailscaled。正常网页上传与此前 Wi-Fi 下隧道低吞吐仍单独待验证。
