"""Immutable CSS-only release and strict previous-release acceptance."""
from pathlib import Path
import hashlib,zipfile
import pytest

ROOT=Path(__file__).resolve().parents[1]
RELEASE=ROOT/'.sandbox/releases'

def test_scroll_spacing_package_and_baseline(tmp_path):
    sha=lambda body:hashlib.sha256(body).hexdigest()
    archive=RELEASE/'PLW-Scroll-Spacing-20261023.zip'
    boot=RELEASE/'scroll-spacing-bootstrap-20261023.py'
    entry=(RELEASE/'Install-PLW-Scroll-Spacing-20261023.ps1').read_text(encoding='utf-8-sig')
    assert sha(archive.read_bytes()) in entry and sha(archive.read_bytes()) in boot.read_text()
    assert sha(boot.read_bytes()) in entry and 'StrictHostKeyChecking=yes' in entry
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for line in z.read('payload.sha256').decode().splitlines():
            digest,name=line.split('  ',1);assert sha(z.read(name))==digest
        assert z.read('workbench.css')==(ROOT/'src/plw/workbench.css').read_bytes().replace(b'\r\n',b'\n')
        assert z.read('Dockerfile').decode().count('COPY ')==1
        install=z.read('install_scroll_spacing_hotfix.sh').decode()
        assert install.index(' backup\n')<install.index('armed=1')<install.index('compose up -d --no-build --pull never\nok=0')
        scope={'__name__':'synthetic_verifier'};exec(compile(z.read('verify_scroll_spacing_base.py'),'baseline','exec'),scope)
        with zipfile.ZipFile(RELEASE/'PLW-Appearance-20261022.zip') as old:
            for name in scope['EXPECTED']:
                target=tmp_path/'src/plw'/('reader/'+name if name in ('reader.js','reader.css','library.css') else name)
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(old.read(name))
        scope['verify'](tmp_path,'plw:0.3.1-appearance-20261022')
        css=tmp_path/'src/plw/workbench.css';css.write_bytes(css.read_bytes()+b'\n/* unknown */')
        with pytest.raises(ValueError):scope['verify'](tmp_path,'plw:0.3.1-appearance-20261022')
