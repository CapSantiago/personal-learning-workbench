# Windows开发与私人网站更新

维护者GitHub账号：**CapSantiago**。本地目录 `E:\Projects\PLW` 已初始化main分支。用户已确认并创建私有仓库：[CapSantiago/personal-learning-workbench](https://github.com/CapSantiago/personal-learning-workbench)。本轮先发布代码，云端Docker与Tailscale仍待实际环境。

## 代码与数据边界

`.gitignore`排除学习数据库、课件、ZIP、环境、私钥、账号与.env；`.dockerignore`和Dockerfile只放运行文件。提交前审查 `git status --short` 和 `git diff --cached`，忽略规则不是泄密检测器。不要 `git add -f` 私人文件。

Windows修改代码 → 专属环境合成测试 → 审查提交 → 推送私有GitHub → 云主机执行更新命令。测试不读写生产库。运行版本在“使用说明”和健康探针中显示；发布前检查pyproject和db.APP_VERSION一致。

## 日常提交与推送

```powershell
Set-Location -LiteralPath 'E:\Projects\PLW'
& '.\.venv\Scripts\python.exe' -X utf8 -B -m pytest -q
git status --short
# 按本轮实际修改的文件选择性暂存，再审查
git diff --cached --stat
git diff --cached
git commit -m 'Describe the change'
git push origin main
```

Git凭据由已有Git Credential Manager管理，不把Token或密码写入远程URL、项目或日志。`.gitattributes`将迁移SQL和PDF.js供应资源设为原字节保存，保证Windows历史备份恢复到Linux时迁移校验和仍匹配。

现有完整Windows测试使用本机先前生成的合成PDF及Windows OCR/Office条件；干净克隆还需准备这些测试条件，不能声称任意新机器直接跑全套。云端运行镜像不包含测试样本，PDF处理依赖由服务器清单安装。云主机克隆同一私有仓库，用仅需读取该仓库的凭据；不把Token、SSH私钥写进项目、Docker镜像、.env.example或日志。

## 一条命令更新（脚本待Linux实跑验收）

```bash
bash scripts/update_cloud.sh origin/main
# 或传入已发布tag/commit；避免使用未更新的本地main分支
```

脚本持有更新锁，fetch后按明确commit导出独立代码目录，先构建新镜像；构建失败时旧服务继续运行。成功后在旧服务上生成完整备份，再更新单个容器、等待health，失败则恢复旧镜像。数据目录始终绑定在容器外，脚本没有迁移、删除或替换学习库步骤。

更新成功后将镜像选择保存到忽略的.env.release。后续用 `bash scripts/cloud_compose.sh ...` 维护，包装脚本同时读取.env和.env.release。旧镜像ID保存在 `.sandbox/previous-cloud-image`，旧镜像与备份不自动删除。

此自动回退适用于**相同schema**更新。新版本需要迁移时健康检查拒绝，脚本回退程序；应先停服，在新镜像中通过完整备份恢复到新副本、验证并确认，再启动。回退跨schema版本时须同时恢复对应完整备份，不改迁移历史、不跳过校验。

## 后续验收

M4实机测试：故意构建失败、故意健康失败、成功更新、重启后镜像选择保留、同一PDF/批注/笔记/任务仍在、旧镜像能恢复。确认全流程后才考虑GitHub Actions；现在不放自动部署凭据、不创建复杂流水线。

M5：iPad Safari横屏/竖屏、Apple Pencil笔迹、手指滚动/缩放、缩略图跳页、断线重连和保存冲突需要真机。现有Pointer Events与触控布局继续复用；未观察到问题前不替换阅读器或前端框架。
