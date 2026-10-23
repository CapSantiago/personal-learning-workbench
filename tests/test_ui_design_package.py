"""Deployment safety for an aggregate UI update; only synthetic reconstructions."""
import hashlib
import importlib.util
import shutil
import zipfile
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
RELEASES=ROOT/'.sandbox/releases'
TAGS=['plw:0.3.1-device-library-20261021-r2','plw:0.3.1-reader-smooth-20261022','plw:0.3.1-reading-workspace-20261022']


def test_ui_design_bundle_hashes_sources_and_backup_order():
    sha=lambda data:hashlib.sha256(data).hexdigest()
    archive=RELEASES/'PLW-UI-Design-20261022-r2.zip'
    bootstrap=RELEASES/'ui-design-bootstrap-20261022-r2.py'
    entry=(RELEASES/'Install-PLW-UI-Design-20261022-r2.ps1').read_text(encoding='utf-8-sig')
    # This delivered release is immutable; later appearance changes have their
    # own source-parity test and must not invalidate its historical payload.
    assert sha(archive.read_bytes())=='6ab97e4eac00892e8f1ab1364655e5e4dff30d5ada4d37b90cf6849050a5a55d'
    assert sha(archive.read_bytes()) in entry and sha(archive.read_bytes()) in bootstrap.read_text()
    assert sha(bootstrap.read_bytes()) in entry
    assert "'python3 -B -'" in entry and 'StrictHostKeyChecking=yes' in entry
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for line in z.read('payload.sha256').decode().splitlines():
            digest,name=line.split('  ',1)
            assert sha(z.read(name))==digest
        for name,source in {
            'reader.js':'src/plw/reader/reader.js',
            'install_ui_design_hotfix.sh':'scripts/install_ui_design_hotfix.sh',
            'verify_ui_design_base.py':'scripts/verify_ui_design_base.py',
        }.items():assert z.read(name)==(ROOT/source).read_bytes().replace(b'\r\n',b'\n')
        install=z.read('install_ui_design_hotfix.sh').decode()
        for tag in TAGS:assert tag in install
        assert install.index(' backup\n')<install.index('armed=1')<install.index('compose up -d --no-build --pull never\nok=0')
        assert 'tailscale ' not in install and 'systemctl ' not in install
        assert 'design_tokens.css' in z.read('Dockerfile').decode() and 'library.css' in z.read('Dockerfile').decode()
        for name in z.namelist():
            if name.endswith('.py'):compile(z.read(name),name,'exec')


@pytest.mark.parametrize('tag',TAGS)
@pytest.mark.parametrize('mutation',['ui_workbench.py','reader/library.css'])
def test_exact_old_releases_accepted_unrelated_edits_rejected(tmp_path,tag,mutation):
    base=tmp_path/'base'
    shutil.copytree(ROOT/'.sandbox/shelf-baseline-proof',base)
    with zipfile.ZipFile(RELEASES/'PLW-Device-Library-20261021-r2.zip') as z:
        for name in ['reader.js','device_library.js','library_ui.js','library.css']:
            (base/'src/plw/reader'/name).write_bytes(z.read(name))
        (base/'src/plw/reader_runtime.py').write_bytes(z.read('reader_runtime.py'))
    if tag!=TAGS[0]:
        archive='PLW-Reader-Smooth-20261022.zip' if tag==TAGS[1] else 'PLW-Reading-Workspace-20261022.zip'
        with zipfile.ZipFile(RELEASES/archive) as z:
            for short,target in [('reader.js','reader/reader.js'),('reader_runtime.py','reader_runtime.py'),
                                 ('ui_workbench.py','ui_workbench.py'),('reader.css','reader/reader.css'),('workbench.css','workbench.css')]:
                if short in z.namelist():(base/'src/plw'/target).write_bytes(z.read(short))
    spec=importlib.util.spec_from_file_location('ui_design_base',ROOT/'scripts/verify_ui_design_base.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.verify(base,tag)
    file=base/'src/plw'/mutation
    file.write_bytes(file.read_bytes()+b'\n/* unknown edit */\n')
    with pytest.raises(ValueError,match='Unexpected baseline:'):module.verify(base,tag)
