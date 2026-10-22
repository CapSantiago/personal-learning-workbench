"""Exact shipped workspace code and both immutable predecessor identities."""
import hashlib,importlib.util,zipfile
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]

def test_workspace_package_and_entry_are_exact():
    releases=ROOT/'.sandbox/releases';archive=releases/'PLW-Reading-Workspace-20261022.zip';bootstrap=releases/'reading-workspace-bootstrap-20261022.py';entry=(releases/'Install-PLW-Reading-Workspace-20261022.ps1').read_text(encoding='utf-8-sig')
    sha=lambda body:hashlib.sha256(body).hexdigest()
    assert sha(archive.read_bytes())=='9680819286c518fdf477937ec818f1e204baeb63f099b00b98843886cdb0f97c'
    assert sha(archive.read_bytes()) in bootstrap.read_text() and sha(archive.read_bytes()) in entry
    assert sha(bootstrap.read_bytes()) in entry
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for line in z.read('payload.sha256').decode().splitlines():
            digest,name=line.split('  ',1);assert sha(z.read(name))==digest
        # The delivered archive is immutable; later UI revisions have their own
        # release and source checks rather than rewriting the previous bundle.
        for file,source in [('reader.js','src/plw/reader/reader.js'),('reader_runtime.py','src/plw/reader_runtime.py'),('install_reading_workspace_hotfix.sh','scripts/install_reading_workspace_hotfix.sh')]:
            assert z.read(file).decode()==(ROOT/source).read_text(encoding='utf-8-sig')
        installer=z.read('install_reading_workspace_hotfix.sh').decode();assert 'tailscale ' not in installer and 'systemctl ' not in installer
        assert installer.index(' backup\n')<installer.index('armed=1')
        for file in ('verify_device_library_hotfix.py','verify_reader_smooth_hotfix.py','verify_reading_workspace_ui.py'):assert f'< "$ROOT/{file}"' in installer
        for name in z.namelist():
            if name.endswith('.py'):compile(z.read(name),name,'exec')

@pytest.mark.parametrize('tag',['plw:0.3.1-device-library-20261021-r2','plw:0.3.1-reader-smooth-20261022'])
def test_reconstructed_deployed_base_is_accepted_and_changed_ui_is_rejected(tmp_path,tag):
    import shutil
    base=tmp_path/'base';shutil.copytree(ROOT/'.sandbox/shelf-baseline-proof',base)
    archive='PLW-Device-Library-20261021-r2.zip' if 'device-library' in tag else 'PLW-Reader-Smooth-20261022.zip'
    with zipfile.ZipFile(ROOT/'.sandbox/releases'/archive) as z:
        (base/'src/plw/reader/reader.js').write_bytes(z.read('reader.js'));(base/'src/plw/reader_runtime.py').write_bytes(z.read('reader_runtime.py'))
    spec=importlib.util.spec_from_file_location('shelf_base',ROOT/'scripts/verify_reading_workspace_base.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.verify(base,tag)
    file=base/'src/plw/ui_workbench.py';file.write_bytes(file.read_bytes()+b'\n# unrelated edit\n')
    with pytest.raises(ValueError,match='Unexpected baseline: ui_workbench.py'):module.verify(base,tag)
