"""Create an immutable accent/header/sidebar update; does not deploy it."""
import hashlib
import re
import zipfile
from pathlib import Path


def main():
    repo=Path(__file__).resolve().parents[1]
    releases=repo/'.sandbox/releases'
    stage=releases/'PLW-Appearance-20261022'
    archive=releases/(stage.name+'.zip')
    if stage.exists() or archive.exists():
        raise SystemExit('Release exists; use a new version instead of overwriting')
    files={
        'ui_workbench.py':'src/plw/ui_workbench.py', 'ui_theme.py':'src/plw/ui_theme.py',
        'workbench.css':'src/plw/workbench.css', 'design_tokens.css':'src/plw/design_tokens.css',
        'reader.css':'src/plw/reader/reader.css', 'library.css':'src/plw/reader/library.css',
        'reader.js':'src/plw/reader/reader.js', 'reader_runtime.py':'src/plw/reader_runtime.py',
        'install_appearance_hotfix.sh':'scripts/install_appearance_hotfix.sh',
        'verify_appearance_base.py':'scripts/verify_appearance_base.py',
        'verify_appearance_ui.py':'scripts/verify_appearance_ui.py',
        'verify_reading_workspace_ui.py':'scripts/verify_reading_workspace_ui.py',
        'verify_device_library_hotfix.py':'scripts/verify_device_library_hotfix.py',
        'verify_reader_smooth_hotfix.py':'scripts/verify_reader_smooth_hotfix.py',
        'README.md':'docs/APPEARANCE_FIX_20261022.md',
    }
    # Read every source before creating the immutable destination.
    bodies={name:(repo/source).read_bytes().replace(b'\r\n',b'\n') for name,source in files.items()}
    stage.mkdir()
    for name,body in bodies.items():(stage/name).write_bytes(body)
    (stage/'Dockerfile').write_text('ARG BASE_IMAGE\nFROM ${BASE_IMAGE}\n'
        'COPY --chown=10001:10001 reader.js reader.css library.css /app/src/plw/reader/\n'
        'COPY --chown=10001:10001 reader_runtime.py ui_workbench.py ui_theme.py workbench.css design_tokens.css /app/src/plw/\n',encoding='ascii')
    sha=lambda body:hashlib.sha256(body).hexdigest()
    (stage/'payload.sha256').write_text(''.join(sha(p.read_bytes())+'  '+p.name+'\n' for p in sorted(stage.iterdir())),encoding='ascii')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(stage.iterdir()):z.write(p,p.name)
    digest=sha(archive.read_bytes())
    (releases/(archive.name+'.sha256')).write_text(digest+'  '+archive.name+'\n',encoding='ascii')
    old_boot=(releases/'ui-design-bootstrap-20261022-r2.py').read_text(encoding='utf-8')
    old_digest='6ab97e4eac00892e8f1ab1364655e5e4dff30d5ada4d37b90cf6849050a5a55d'
    boot=old_boot.replace('PLW-UI-Design-20261022-r2.zip',archive.name).replace('plw-ui-design-20261022-r2','plw-appearance-20261022').replace('install_ui_design_hotfix.sh','install_appearance_hotfix.sh').replace(old_digest,digest)
    boot=re.sub(r'^allowed=.*$', 'allowed='+repr(sorted(p.name for p in stage.iterdir())),boot,flags=re.M)
    bootstrap=releases/'appearance-bootstrap-20261022.py'
    bootstrap.write_text(boot,encoding='utf-8',newline='\n')
    entry=(releases/'Install-PLW-UI-Design-20261022-r2.ps1').read_text(encoding='utf-8-sig')
    entry=entry.replace('PLW-UI-Design-20261022-r2.zip',archive.name).replace('ui-design-bootstrap-20261022-r2.py',bootstrap.name).replace(old_digest,digest).replace(sha(old_boot.encode()),sha(bootstrap.read_bytes()))
    entry=entry.replace('即将更新 PLW 界面：紧凑品牌与导航、统一学习页面和阅读工具。先核对旧版、隔离检查和完整备份，再切换；失败尝试恢复。','即将更新 PLW 外观：修复标题重叠与侧栏悬停，优化品牌标识，新增六种强调色。先核对旧版、隔离检查和完整备份，再切换；失败尝试恢复。')
    entry=entry.replace('界面更新服务已启动。重新登录检查导航、课件阅读和批注。原下载库不用清空，不必先运行旧更新包。此输出仅确认服务启动，实际设备体验仍待验收。','外观更新服务已启动。重新登录后，在“课程与设置 → 外观设置”更改主题强调色。原下载库不用清空，不必先运行旧更新包。此输出仅确认服务启动，实际电脑与 iPad 体验仍待验收。')
    (releases/'Install-PLW-Appearance-20261022.ps1').write_text(entry,encoding='utf-8-sig',newline='\n')
    print(f'{archive}\nBytes: {archive.stat().st_size}\nSHA256: {digest}')


if __name__=='__main__':main()
