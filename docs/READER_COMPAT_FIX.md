# 2026-10-18 空白阅读器的浏览器功能兼容修复

## 已确认的错误

用户确认 cachefix 启动后，电脑与 iPad 都无法显示课件。iPad 截图的实际错误为 `this.#methodPromises.getOrInsertComputed is not a function`，发生于 PDF.js 渲染路径。这是浏览器缺少现代 Map 方法导致的执行错误，该次空白不应继续按带宽或传输等待处理。

先前本地 PDF 测试给 Node 手工补了 `Map.getOrInsertComputed` 和 `Uint8Array.toHex`，使这些测试不能证明浏览器原生支持。前端缓存测试与服务器健康检查也没有覆盖浏览器运行时，这个验收缺口必须纠正。截图表明是当前库的运行时兼容错误；不能仅凭更新时序把它认定为缓存保留算法本身导致。

## 修复范围

使用已安装官方 `pdfjs-dist` **5.6.205** 自带的 `legacy/build/pdf.mjs` 和 `legacy/build/pdf.worker.mjs`。该包 README 明确为缺少最新 JavaScript 原生功能的环境提供 legacy 目录。与原库和 worker 保持同一版本；没有下载不明替代库或混用版本。

同时更新主线程、工作线程入口及供应资源摘要清单，保留原现代构建字节。新增兼容资源仍须通过清单摘要校验、登录和跨站检查，并使用原 gzip/私有 no-store 响应规则。不改课程数据、账号、网络设置、PDF 原件或已完成的缓存逻辑。

## 验证证据

- 独立旧构建对照：主动移除 Map 方法，真实 PDF 渲染复现 `this[#methodPromises].getOrInsertComputed is not a function`，与截图同类错误。
- 主线程兼容检查：主动移除 Map 方法、Uint8Array 十六进制方法和 Promise.withResolvers，不手工补这些方法；官方 legacy 构建安装自身兼容功能后，真实 35 页课件的第 1、15、25 页渲染成功。第 15 页 PNG 已视觉核对有内容。
- 独立工作线程检查：另起 Node Worker，在其自身环境也移除上述三个方法，使用原库公开 PDFWorker/消息端口接口运行真实解析及渲染，三页均通过。该测试避免主线程中的补齐结果掩盖工作线程缺失。
- HTTP 认证/Streamlit 分段接口与同一真实 PDF 的 A15→B1→A15 测试通过：返回 81 ms，新 PDF 请求和全文校验均为0，缩略图复用。A/B 用两个独立文档标识、相同内容，不是 Safari UI 自动化结果。
- 新增两个兼容入口的实际 ASGI 验证覆盖 gzip 后摘要、JavaScript 类型、未登录拒绝、跨站拒绝、摘要不符拒绝。包内合成检查验证兼容 worker 2,358,232 字节压缩至 509,108 字节，PDF 初始长度及 206 身份编码保持正确。
- 12 项缓存行为回归继续通过。实际 Safari/Windows 页面仍需部署后验收；这里没有宣称已在真实设备恢复。

相关 Python 回归最终为 182 项通过（37.34 秒）。兼容包 `PLW-Reader-Compat-fix-20261018.zip` 已生成，729,881 字节、9 个文件，SHA-256 `caf26df1d000be1769724d2190801cfb37f1dae936f85b77f92e94f4920a4bd1`。包 CRC、全部载荷摘要、两份官方资源清单摘要、本地引导摘要、PowerShell 与 Bash/Python 语法均通过。用户一次密码安装入口 `.sandbox/releases/Install-PLW-Reader-Compat-20261018.ps1` 已准备；真实 Linux 构建与设备阅读尚未执行。

可重复检查工具：`scripts/verify_reader_browser_compat.cjs`（参数为测试 PDF 路径，绘图依赖可通过 NODE_PATH 指向已有运行时）和 `scripts/reader_compat_worker.mjs`。无需手工补 Map/Hex/Promise 方法。

## 部署与恢复

本次基线为已确认启动的 `plw:0.3.1-reader-cachefix-20261018`，目标 `plw:0.3.1-reader-compatfix-20261018`。仅复制 reader.js、同版两份兼容库及新摘要清单。继续核对基线、离线构建、隔离检查、更新前完整备份、健康失败自动恢复旧镜像。健康通过仅代表服务启动，不能替代实际阅读验收。

此前准备的回退工具尚未执行。旧 rangefix 仍使用现代构建，回退不保证消除截图中的缺失功能错误。缓存单独更新包作为历史保留，旧安装入口停止推荐；本次修复不重新导入、重置或回滚学习数据。
