"""Build a new immutable, password-once private-site update. Never deploys."""
import hashlib
import re
import zipfile
from pathlib import Path


def main():
    repo=Path(__file__).resolve().parents[1]
    releases=repo/'.sandbox/releases'
    stage=releases/'PLW-UI-Design-20261022-r2'
    archive=releases/(stage.name+'.zip')
    if archive.exists() or stage.exists():
        raise SystemExit('Release already exists; use a new version rather than overwriting')
    stage.mkdir()
    files={
        'ui_workbench.py':'src/plw/ui_workbench.py', 'workbench.css':'src/plw/workbench.css',
        'design_tokens.css':'src/plw/design_tokens.css', 'reader.css':'src/plw/reader/reader.css',
        'library.css':'src/plw/reader/library.css', 'reader.js':'src/plw/reader/reader.js',
        'reader_runtime.py':'src/plw/reader_runtime.py',
        'install_ui_design_hotfix.sh':'scripts/install_ui_design_hotfix.sh',
        'verify_ui_design_base.py':'scripts/verify_ui_design_base.py',
        'verify_reading_workspace_ui.py':'scripts/verify_reading_workspace_ui.py',
        'verify_device_library_hotfix.py':'scripts/verify_device_library_hotfix.py',
        'verify_reader_smooth_hotfix.py':'scripts/verify_reader_smooth_hotfix.py',
        'README.md':'docs/UI_DESIGN_UPDATE_20261022.md',
    }
    for name, source in files.items():
        (stage/name).write_bytes((repo/source).read_bytes().replace(b'\r\n',b'\n'))
    (stage/'Dockerfile').write_text('ARG BASE_IMAGE\nFROM ${BASE_IMAGE}\n'
        'COPY --chown=10001:10001 reader.js reader.css library.css /app/src/plw/reader/\n'
        'COPY --chown=10001:10001 reader_runtime.py ui_workbench.py workbench.css design_tokens.css /app/src/plw/\n',encoding='ascii')
    sha=lambda body:hashlib.sha256(body).hexdigest()
    (stage/'payload.sha256').write_text(''.join(sha(p.read_bytes())+'  '+p.name+'\n' for p in sorted(stage.iterdir())),encoding='ascii')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(stage.iterdir()):z.write(p,p.name)
    digest=sha(archive.read_bytes())
    (releases/(archive.name+'.sha256')).write_text(digest+'  '+archive.name+'\n',encoding='ascii')
    old_boot=(releases/'reading-workspace-bootstrap-20261022.py').read_text(encoding='utf-8')
    old_digest='9680819286c518fdf477937ec818f1e204baeb63f099b00b98843886cdb0f97c'
    boot=old_boot.replace('PLW-Reading-Workspace-20261022.zip',archive.name).replace('plw-reading-workspace-20261022','plw-ui-design-20261022').replace('install_reading_workspace_hotfix.sh','install_ui_design_hotfix.sh').replace(old_digest,digest)
    boot=re.sub(r'^allowed=.*$', 'allowed='+repr(sorted(p.name for p in stage.iterdir())),boot,flags=re.M)
    boot=boot.replace('plw-ui-design-20261022', 'plw-ui-design-20261022-r2')
    bootstrap=releases/'ui-design-bootstrap-20261022-r2.py'
    bootstrap.write_text(boot,encoding='utf-8',newline='\n')
    entry=(releases/'Install-PLW-Reading-Workspace-20261022.ps1').read_text(encoding='utf-8-sig')
    entry=entry.replace('PLW-Reading-Workspace-20261022.zip',archive.name).replace('reading-workspace-bootstrap-20261022.py',bootstrap.name).replace(old_digest,digest).replace(sha(old_boot.encode()),sha(bootstrap.read_bytes()))
    entry=entry.replace('即将更新阅读工作区：紧凑书架、稳定整页适配、首页全部课程。先核对旧版、合成检查和完整备份，再切换；失败尝试恢复。','即将更新 PLW 界面：紧凑品牌与导航、统一学习页面和阅读工具。先核对旧版、隔离检查和完整备份，再切换；失败尝试恢复。')
    entry=entry.replace('阅读工作区服务已启动。重新登录后检查书架布局、整页适配和首页全部课程。原下载库不用清空，不必先运行旧更新包。电脑及 iPad 的实际体验仍待确认。','界面更新服务已启动。重新登录检查导航、课件阅读和批注。原下载库不用清空，不必先运行旧更新包。此输出仅确认服务启动，实际设备体验仍待验收。')
    (releases/'Install-PLW-UI-Design-20261022-r2.ps1').write_text(entry,encoding='utf-8-sig',newline='\n')
    print(f'{archive}\nBytes: {archive.stat().st_size}\nSHA256: {digest}')


if __name__=='__main__':main()
