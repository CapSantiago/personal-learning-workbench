"""Build a CSS-only derivative of the immutable appearance release."""
from pathlib import Path
import hashlib,re,zipfile

def main():
    repo=Path(__file__).resolve().parents[1];release=repo/'.sandbox/releases'
    stage=release/'PLW-Scroll-Spacing-20261023';archive=release/(stage.name+'.zip')
    if stage.exists() or archive.exists():raise SystemExit('Release exists; use a new version')
    sha=lambda data:hashlib.sha256(data).hexdigest()
    old_archive=release/'PLW-Appearance-20261022.zip'
    old_digest='f1601b1683ea93c7ea8d07b2e8bc4257532d3f9074ef0b3b1b1d0c75672cb7cf'
    assert sha(old_archive.read_bytes())==old_digest
    with zipfile.ZipFile(old_archive) as old:
        names=['verify_device_library_hotfix.py','verify_reader_smooth_hotfix.py','verify_reading_workspace_ui.py','verify_appearance_ui.py']
        bodies={name:old.read(name) for name in names}
        install=old.read('install_appearance_hotfix.sh').decode()
        install=re.sub(r'  plw:0\.3\.1-device-library[^\n]+', '  plw:0.3.1-appearance-20261022) ;;',install)
        install=install.replace('NEW=plw:0.3.1-appearance-20261022','NEW=plw:0.3.1-scroll-spacing-20261023').replace('"$ROOT/reader.js"','"$ROOT/workbench.css"').replace('verify_appearance_base.py','verify_scroll_spacing_base.py').replace('before-appearance','before-scroll-spacing')
        install=install[:install.rfind("printf 'APPEARANCE")]+"printf 'SCROLL SPACING UPDATE STARTED: %s\\nPrevious environment: %s\\nReopen the website. Reading-page scroll space and Today course heading spacing are updated. Existing device downloads remain usable.\\n' \"$NEW\" \"$snapshot\"\n"
        expected={name:sha(old.read(name)) for name in ['ui_workbench.py','ui_theme.py','design_tokens.css','workbench.css','reader.js','reader.css','reader_runtime.py','library.css']}
    validator='''from pathlib import Path
import hashlib,sys,streamlit
def verify(base,tag):
 if tag!='plw:0.3.1-appearance-20261022' or streamlit.__version__!='1.65.0':raise ValueError('Unexpected baseline version')
 for name,digest in EXPECTED.items():
  target=Path(base)/'src/plw'/('reader/'+name if name in ('reader.js','reader.css','library.css') else name)
  if target.is_symlink() or not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest()!=digest:raise ValueError('Unexpected baseline: '+name)
 print('SCROLL SPACING BASE CHECK PASSED')
if __name__=='__main__':verify('/app',sys.argv[1])
'''.replace('def verify(', 'EXPECTED='+repr(expected)+'\ndef verify(',1)
    bodies.update({'workbench.css':(repo/'src/plw/workbench.css').read_bytes().replace(b'\r\n',b'\n'),
        'install_scroll_spacing_hotfix.sh':install.encode(),'verify_scroll_spacing_base.py':validator.encode(),
        'README.md':(repo/'docs/SCROLL_SPACING_20261023.md').read_bytes().replace(b'\r\n',b'\n'),
        'Dockerfile':b'ARG BASE_IMAGE\nFROM ${BASE_IMAGE}\nCOPY --chown=10001:10001 workbench.css /app/src/plw/workbench.css\n'})
    stage.mkdir()
    for name,body in bodies.items():(stage/name).write_bytes(body)
    (stage/'payload.sha256').write_text(''.join(sha(p.read_bytes())+'  '+p.name+'\n' for p in sorted(stage.iterdir())),encoding='ascii')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(stage.iterdir()):z.write(p,p.name)
    digest=sha(archive.read_bytes())
    old_boot=(release/'appearance-bootstrap-20261022.py').read_text(encoding='utf-8')
    boot=old_boot.replace(old_archive.name,archive.name).replace(old_digest,digest).replace('plw-appearance-20261022','plw-scroll-spacing-20261023').replace('install_appearance_hotfix.sh','install_scroll_spacing_hotfix.sh')
    boot=re.sub(r'^allowed=.*$', 'allowed='+repr(sorted(p.name for p in stage.iterdir())),boot,flags=re.M)
    bootstrap=release/'scroll-spacing-bootstrap-20261023.py';bootstrap.write_text(boot,encoding='utf-8',newline='\n')
    entry=(release/'Install-PLW-Appearance-20261022.ps1').read_text(encoding='utf-8-sig')
    entry=entry.replace(old_archive.name,archive.name).replace(old_digest,digest).replace('appearance-bootstrap-20261022.py',bootstrap.name).replace(sha(old_boot.encode()),sha(bootstrap.read_bytes()))
    entry=re.sub(r"Write-Host '即将更新[^\n]+", "Write-Host '即将修复阅读页底部滚动余量和首页课程标题遮挡。仅更新界面样式，先校验、隔离验证和完整备份，再切换。'",entry)
    entry=re.sub(r"Write-Host '外观更新[^\n]+", "Write-Host '界面间距更新服务已启动。重新打开网站检查滚动和首页；无需清空或重新下载课件。实际设备体验仍待验收。'",entry)
    (release/'Install-PLW-Scroll-Spacing-20261023.ps1').write_text(entry,encoding='utf-8-sig',newline='\n')
    print(archive,archive.stat().st_size,digest)

if __name__=='__main__':main()
