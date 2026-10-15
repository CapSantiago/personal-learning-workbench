# PLW 私人网站部署候选版

此文保留0.3.0 Windows候选版步骤。0.3.1已增加Linux/Docker源码准备及ZIP备份，当前免费优先路线为Oracle + Docker + Tailscale，实际容器/云端验收待完成，见 [CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md)。

本轮只完成部署准备：没有选购服务器/域名，没有上传真实学习资料，也没有开放本机网络访问。部署包不含账号、密码、学习库、备份或用户课件。当前候选版目标是 **Windows、Python 3.14、单进程**；Linux 容器移植尚未完成，购买服务器前先结合成本和转换要求决定系统。

## 课件如何跨设备与离线使用

浏览器文件选择上传会保存完整原件，PDF 阅读副本也独立保存到学习库；设备不需要访问来源电脑路径。网站上线后，电脑、手机和 iPad 登录同一账号，读取同一个服务器库。

在课件页面展开“下载与离线阅读”，点击“下载 PDF 到设备”，保存到手机/iPad 的“文件”后，断网可使用设备上的 PDF 阅读器打开。下载文件包括静态页面，不包含 PLW 标记，也不回传离线修改。网站页面、任务编辑和同步本身仍需网络；未做整站 PWA 离线缓存。外部引用原件仍依赖原路径，不能随服务器迁移；其已生成的 PDF 可以独立下载。迁移前应另行上传完整原件。

## 服务器准备与配置

1. 解压代码包到专属程序目录，例如 `C:\PLW\app`。用 `release-manifest.json` 核对文件 SHA-256。不要把学习库放进程序目录。
2. 在新服务器安装/准备 Python 3.14，创建专用虚拟环境。使用该环境执行 `python -m pip install -r requirements-server.lock.txt`。这一安装步骤本轮没有在用户电脑执行；全新服务器的依赖安装仍需实机验收。
3. 学习数据和备份使用两个独立本机目录，例如 `C:\PLW-Data` 和 `C:\PLW-Backups`。登录配置放在第三个独立目录，例如 `C:\PLW-Private\account.json`，设置该目录的访问权限，仅服务器运行账号/管理员可读。不要把它放入代码包或学习备份。
4. 交互执行 `python scripts/setup_private.py --config C:\PLW-Private\account.json`。输入选定的 HTTPS 根地址、账号、至少12字符密码、数据/备份目录及该虚拟环境的 Python 完整路径。密码只用于生成带随机盐的 scrypt 校验值，明文不保存、不出现在命令行。
5. 执行 `python scripts/launch_private.py --config C:\PLW-Private\account.json --check`。此检查不创建学习库。正式地址必须 HTTPS，HTTP预览仅允许 `.sandbox/test-runs` 下的合成库。
6. 执行 `python scripts/launch_private.py --config C:\PLW-Private\account.json`。应用只绑定 `127.0.0.1:8501`。使用一个服务进程，不配置多 worker。首次访问需要登录，再明确确认创建学习库。

正式脚本和原本地 `launch.py` 是独立入口；本地版仍按原方式离线运行。不要在同一个数据目录同时启动两个入口，也不要让多个服务器通过共享磁盘打开同一 SQLite 数据库。

## HTTPS 反向代理

准备 Caddy 并绑定已选域名。使用 `deploy/Caddyfile`，在启动 Caddy 的进程中设置 `PLW_DOMAIN` 为域名、`PLW_PORT` 为8501，然后先 `caddy validate --config deploy/Caddyfile`，再启动。模板覆盖外部Host及协议头，反向代理全部路径和WebSocket，不公开任何磁盘目录。服务器只放行HTTPS入口及证书所需HTTP入口，不能对外开放8501。

模板本轮未在真实域名/证书环境启动验证，不能据此宣称网站已上线。Caddy 的自动 HTTPS 和 WebSocket 代理行为依据 [HTTPS 官方说明](https://caddyserver.com/docs/quick-starts/https) 与 [反向代理官方说明](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)。目标服务器仍需验证证书签发、上传、阅读worker、下载和断线重连。

## 登录保护

自定义 ASGI 入口覆盖全部 HTTP 和 WebSocket 请求，只有登录表单公开。账号不开放注册；密码使用 scrypt（N=2^17、r=8、p=1）、随机盐与恒定时间比较。会话 Cookie 为 HttpOnly、SameSite=Strict，正式网站必须 Secure；会话存于单进程内存，12小时到期，重启撤销全部登录。5分钟内最多5次登录尝试，错误提示不区分账号和密码。

退出需要同源POST及会话CSRF令牌；退出/到期主动关闭既有WebSocket，不只保护页面按钮。下载链接即使被复制也必须有登录会话，全部私有响应禁止共享缓存。不会把凭据写入学习库、日志或发布包。修改密码可用设置工具生成新配置文件，停服后切换配置并重启；旧文件由管理员保管，脚本不自动覆盖或删除。

中间件挂载基于已锁定的 Streamlit st.App API；该 API 官方标为实验性，因此依赖升级需重新验收全部边界。[Streamlit 官方接口](https://docs.streamlit.io/1.57.0/develop/api-reference/server/st.app)；密码参数参考 [OWASP 密码存储说明](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)。

## 网站候选版的功能边界

- PDF 上传、阅读、标记、任务、笔记、课程和完整备份沿用已有服务。
- PPT/PPTX 保存完整原件，可下载到自己的设备打开。网站不调用桌面 PowerPoint；在课件下方“生成阅读副本 / 添加新版本”上传已导出的 PDF，绑定到原课件。旧版本与标记保留。
- 网站模式不提供电脑路径导入、系统程序打开、Windows OCR 或 PowerPoint 动画导出。现有本地模式继续保留这些能力。无头转换、服务器OCR/媒体流程需要单独验证后再启用，不能当作本轮已交付功能。
- 单个上传200 MB，代理允许210 MB以容纳表单开销；每批20份/500 MB。大文件和弱网压力测试尚待目标服务器完成。
- 当前以Windows路径与锁为基础，不声称可直接部署到Linux或通用静态网站托管。

## 迁移、备份、更新与回滚

先在目标服务器用合成资料验收。正式迁移须确认范围并生成现有库的完整备份：数据库、托管原件、阅读PDF、笔记历史和标记同时迁移。验证备份清单、文件哈希、外键和记录数量；外部引用明确标记未包含。通过恢复流程导入新数据集，验证后切换，保留本地原库。不要只复制SQLite，不自动上传学习数据。

服务上线后由用户选定一个主库；本地库与网站库不会自动双向同步。服务器备份仍需额外复制到独立存储，当前模板没有擅自创建定时任务或配置外部备份服务。

升级前创建完整备份、暂停写入、停服并保留旧代码包，再换新代码包、运行预检和必要的数据库恢复式迁移，验证后启动。版本0.3.0仍用schema3，无数据库迁移。若回退代码涉及更高schema，需要同步恢复对应的完整数据集，保留回退前新增数据，不让旧程序直接写入新schema。

## 上线前必须实测

目标Windows服务器的独立安装与重启；Caddy配置/证书；不同网络上的电脑、手机、真实iPad Safari登录；未登录PDF/原件/上传/备份/WebSocket拒绝；退出和过期会话断开；大文件和弱网上传；设备下载PDF后断网可读；完整备份恢复与回滚。完成后再进行真实资料迁移。
