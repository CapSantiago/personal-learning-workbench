"""Validate the shipped small update, including exact deployed base hashes."""
from pathlib import Path
import hashlib,json,re,zipfile
ROOT=Path(__file__).resolve().parents[1]

def test_smooth_package_sources_and_entry_hashes():
    release=ROOT/'.sandbox/releases';archive=release/'PLW-Reader-Smooth-20261022.zip';bootstrap=release/'reader-smooth-bootstrap-20261022.py';entry=(release/'Install-PLW-Reader-Smooth-20261022.ps1').read_text(encoding='utf-8-sig')
    digest=lambda body:hashlib.sha256(body).hexdigest()
    assert digest(archive.read_bytes())=='6f679e0c0339e620b9abf310b31652ca67f0965cc8997eb97da4a069ee95a0e1'
    assert digest(archive.read_bytes()) in bootstrap.read_text() and digest(archive.read_bytes()) in entry
    assert digest(bootstrap.read_bytes()) in entry and "'python3 -B -'" in entry
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for line in z.read('payload.sha256').decode().splitlines():
            sha,name=line.split('  ',1);assert digest(z.read(name))==sha
        for name,source in [('reader.js','src/plw/reader/reader.js'),('reader_runtime.py','src/plw/reader_runtime.py'),('install_reader_smooth_hotfix.sh','scripts/install_reader_smooth_hotfix.sh'),('verify_reader_smooth_hotfix.py','scripts/verify_reader_smooth_hotfix.py')]:
            compile(z.read(name).decode('utf-8'),name,'exec') if name.endswith('.py') else None
        docker=z.read('Dockerfile').decode();assert docker.count('COPY ')==2
        assert 'plw:0.3.1-device-library-20261021-r2' in docker and 'reader.js' in docker and 'reader_runtime.py' in docker
        installer=z.read('install_reader_smooth_hotfix.sh').decode()
        assert installer.index(' backup\n')<installer.index('armed=1')<installer.index('compose up -d --no-build --pull never\nok=0')
        assert 'tailscale ' not in installer and 'systemctl ' not in installer
        with zipfile.ZipFile(release/'PLW-Device-Library-20261021-r2.zip') as old:
            for name in ('reader.js','reader_runtime.py','device_library.js'):assert digest(old.read(name)) in installer
