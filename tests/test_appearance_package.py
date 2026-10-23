"""Check the new payload and strict baselines without any live deployment."""
import hashlib
import importlib.util
import shutil
import zipfile
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
RELEASES=ROOT/'.sandbox/releases'
TAGS=['plw:0.3.1-device-library-20261021-r2','plw:0.3.1-reader-smooth-20261022',
      'plw:0.3.1-reading-workspace-20261022','plw:0.3.1-ui-design-20261022-r2']


def test_appearance_bundle_sources_hashes_and_backup_order():
    sha=lambda body:hashlib.sha256(body).hexdigest()
    archive=RELEASES/'PLW-Appearance-20261022.zip'
    bootstrap=RELEASES/'appearance-bootstrap-20261022.py'
    entry=(RELEASES/'Install-PLW-Appearance-20261022.ps1').read_text(encoding='utf-8-sig')
    assert sha(archive.read_bytes())=='f1601b1683ea93c7ea8d07b2e8bc4257532d3f9074ef0b3b1b1d0c75672cb7cf'
    assert sha(archive.read_bytes()) in entry and sha(archive.read_bytes()) in bootstrap.read_text()
    assert sha(bootstrap.read_bytes()) in entry
    assert "'python3 -B -'" in entry and 'StrictHostKeyChecking=yes' in entry
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for line in z.read('payload.sha256').decode().splitlines():
            digest,name=line.split('  ',1)
            assert sha(z.read(name))==digest
        for name,source in {
            'ui_workbench.py':'src/plw/ui_workbench.py','ui_theme.py':'src/plw/ui_theme.py',
            'design_tokens.css':'src/plw/design_tokens.css',
            'reader.css':'src/plw/reader/reader.css','library.css':'src/plw/reader/library.css',
            'reader.js':'src/plw/reader/reader.js',
            'install_appearance_hotfix.sh':'scripts/install_appearance_hotfix.sh',
            'verify_appearance_base.py':'scripts/verify_appearance_base.py',
            'verify_appearance_ui.py':'scripts/verify_appearance_ui.py',
        }.items():assert z.read(name)==(ROOT/source).read_bytes().replace(b'\r\n',b'\n')
        installer=z.read('install_appearance_hotfix.sh').decode()
        assert all(tag in installer for tag in TAGS)
        assert installer.index(' backup\n')<installer.index('armed=1')<installer.index('compose up -d --no-build --pull never\nok=0')
        assert 'tailscale ' not in installer and 'systemctl ' not in installer
        assert 'ui_theme.py' in z.read('Dockerfile').decode()
        for name in z.namelist():
            if name.endswith('.py'):compile(z.read(name),name,'exec')


@pytest.mark.parametrize('tag',TAGS)
@pytest.mark.parametrize('mutation',['ui_workbench.py','reader/library.css','ui_theme.py'])
def test_four_exact_baselines_accepted_unknown_edits_rejected(tmp_path,tag,mutation):
    base=tmp_path/'base'
    shutil.copytree(ROOT/'.sandbox/shelf-baseline-proof',base)
    with zipfile.ZipFile(RELEASES/'PLW-Device-Library-20261021-r2.zip') as z:
        for name in ['reader.js','device_library.js','library_ui.js','library.css']:
            (base/'src/plw/reader'/name).write_bytes(z.read(name))
        (base/'src/plw/reader_runtime.py').write_bytes(z.read('reader_runtime.py'))
    if tag!=TAGS[0]:
        archive={TAGS[1]:'PLW-Reader-Smooth-20261022.zip',TAGS[2]:'PLW-Reading-Workspace-20261022.zip',TAGS[3]:'PLW-UI-Design-20261022-r2.zip'}[tag]
        with zipfile.ZipFile(RELEASES/archive) as z:
            for short,target in [('reader.js','reader/reader.js'),('reader_runtime.py','reader_runtime.py'),
                ('ui_workbench.py','ui_workbench.py'),('reader.css','reader/reader.css'),
                ('workbench.css','workbench.css'),('design_tokens.css','design_tokens.css'),('library.css','reader/library.css')]:
                if short in z.namelist():(base/'src/plw'/target).write_bytes(z.read(short))
    spec=importlib.util.spec_from_file_location('appearance_base',ROOT/'scripts/verify_appearance_base.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.verify(base,tag)
    file=base/'src/plw'/mutation
    file.write_bytes((file.read_bytes() if file.exists() else b'')+b'\n# unknown change\n')
    with pytest.raises(ValueError):module.verify(base,tag)
