# PDF 首次响应与 Streamlit 默认压缩冲突修复

## 已复现的问题

上一版 readerfix 在裸 Starlette 路由测试中支持206，但真实 st.App 还会添加 Streamlit 的 SelectiveGZipMiddleware。此层默认不排除 application/pdf；浏览器声明接受 gzip 时，PDF 的首次200响应被压缩，流式输出去掉 Content-Length。

项目捆绑 PDF.js 的 validateRangeRequestCapabilities 要求初始响应具有原始 Content-Length、Accept-Ranges: bytes，并且 Content-Encoding 为 identity（或不提供）。否则禁用范围读取。用户新截图显示“正在读取课件 · 已接收1.0MB”，没有总量且仍空白，与此问题相符；真实浏览器还须在新部署后验收，不能将本地复现当成已修复用户页面。

新增回归先在旧 readerfix 代码失败：经过实际 Streamlit 中间件后，返回的是 gzip 数据而非原始 PDF。修正后通过。上轮测试仅覆盖裸路由，漏掉这一层，原81项通过不能证明实际 st.App 范围发现有效。

## 最小修改

- 对已校验阅读 PDF 及 PDF 下载明确返回 Content-Encoding: identity，让框架保留原始长度并跳过二次压缩；206响应保持相同字节表示。
- 已校验的内置 vendor 响应也明确选择 gzip 或 identity，防止外层框架覆盖 gzip;q=0 的拒绝。
- 不修改 PDF.js、前端组件、课件字节、数据库、登录配置、DNS、代理或公网访问范围。

验证使用实际 create_streamlit_middleware 和 PrivateAccess，包含完整200发现响应、HEAD、64KiB范围、身份验证、跨站、篡改拒绝、注销和vendor压缩；上一版仅裸路由的烟雾脚本不再作为范围发现验收依据。完整框架下的PDF下载与正常网页上传仍需用户实际验证。

## 部署

只接受当前 plw:0.3.1-readerfix-20261017，并校验旧模块摘要，生成新镜像 plw:0.3.1-reader-rangefix-20261017。原包和已安装目录保持不变。安装前完整备份，保存旧环境；切换后的命令/健康失败会尝试回退旧镜像，不重置数据，也不重启Tailscale。

电脑 PowerShell 上传：

```powershell
scp -o HostKeyAlgorithms=ssh-ed25519 -o HostKeyAlias=100.104.174.9 -o StrictHostKeyChecking=yes "E:\Projects\PLW\.sandbox\releases\PLW-Reader-Range-fix-20261017.zip" "E:\Projects\PLW\.sandbox\releases\PLW-Reader-Range-fix-20261017.zip.sha256" root@47.98.151.12:/root/
```

阿里云 root 终端：

```bash
(
set -euo pipefail
cd /root
sha256sum -c PLW-Reader-Range-fix-20261017.zip.sha256
test ! -e /opt/plw-reader-range-fix-20261017
mkdir /opt/plw-reader-range-fix-20261017
python3 -m zipfile -e PLW-Reader-Range-fix-20261017.zip /opt/plw-reader-range-fix-20261017
bash /opt/plw-reader-range-fix-20261017/install_reader_range_hotfix.sh
)
```

用户最新截图已确认Linux镜像构建、完整框架检查、完整备份与启动成功，出现 READER FULL STACK CHECK PASSED 及 READER RANGE HOTFIX STARTED；但重新登录后的真实阅读仍停在“正在读取课件…”，页面/缩略图空白，不能记为阅读修复完成。下一步获取已登录浏览器的实际plw-reader请求状态/响应，不重新初始化、不删除已导入资料，也不继续仅凭空白打新包。
