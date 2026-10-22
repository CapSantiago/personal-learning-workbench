"""Exercise the installer preflight with the immutable offline deployment UI."""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import zipfile

import pytest

REPO=Path(__file__).resolve().parents[1]
RELEASES=REPO/'.sandbox/releases'
spec=importlib.util.spec_from_file_location('device_library_base',REPO/'scripts/verify_device_library_base.py')
check=importlib.util.module_from_spec(spec);spec.loader.exec_module(check)
spec=importlib.util.spec_from_file_location('device_library_patch',REPO/'scripts/patch_device_library_ui.py')
patcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(patcher)


@pytest.fixture
def original_ui():
    with zipfile.ZipFile(RELEASES/'PLW-0.3.1-offline-linux-amd64-20261016.zip') as archive:
        data=archive.read('app/src/plw/ui_workbench.py')
    before=b"'pages':edition['page_count'],'state':state"
    after=b"'pages':edition['page_count'],'bytes':edition['size_bytes'],'digest':edition['pdf_sha256'],'state':state"
    assert data.count(before)==1
    data=data.replace(before,after,1)
    assert b'\r\n' in data
    return data


def make_base(tmp_path,tag,ui):
    src=tmp_path/'src/plw';(src/'reader').mkdir(parents=True)
    candidates={
        'private_auth.py':RELEASES/'static-assets-fix-20261017/private_auth.py',
        'private_assets.py':RELEASES/'static-assets-fix-20261017/private_assets.py',
        'reader_runtime.py':RELEASES/'reader-range-fix-20261017/reader_runtime.py',
        'reader/reader.js':RELEASES/('reader-compat-fix-20261018/reader.js' if 'compatfix' in tag else 'reader-fullfile-fix-20261018/reader.js'),
    }
    for name,source in candidates.items():shutil.copyfile(source,src/name)
    (src/'ui_workbench.py').write_bytes(ui)
    (tmp_path/'assets/pdfjs').mkdir(parents=True)
    shutil.copyfile(RELEASES/'reader-compat-fix-20261018/manifest.json',tmp_path/'assets/pdfjs/manifest.json')
    return tmp_path


def test_original_installer_failure_is_reproduced(original_ui):
    actual=hashlib.sha256(original_ui).hexdigest()
    assert actual=='09dfa4a7c1af510285d3af2bd94f4c1b68eb873f817eff31ebdec7134b66fcd2'
    assert actual!='13171adc616aeedd169d93c2eb7be6ed8d3093bf30140e440a626bd033ad64d5'


@pytest.mark.parametrize('tag',list(check.READERS))
@pytest.mark.parametrize('crlf',[True,False])
def test_preflight_and_ui_patch_on_both_known_images_and_newline_forms(tmp_path,original_ui,tag,crlf):
    data=original_ui if crlf else original_ui.replace(b'\r\n',b'\n')
    base=make_base(tmp_path,tag,data);result=check.verify(base,tag)
    assert result['ui_workbench.py'] in check.UI
    target=base/'src/plw/ui_workbench.py';patcher.patch(target)
    assert hashlib.sha256(target.read_bytes().replace(b'\r\n',b'\n')).hexdigest()==patcher.AFTER_DIGEST
    with pytest.raises(ValueError):patcher.patch(target)


@pytest.mark.parametrize('change',['ui','reader','vendor','tag'])
def test_other_baseline_changes_are_still_rejected(tmp_path,original_ui,change):
    tag=next(iter(check.READERS));base=make_base(tmp_path,tag,original_ui)
    if change=='ui':
        path=base/'src/plw/ui_workbench.py';path.write_bytes(path.read_bytes()+b'\n# unreviewed change\n')
    if change=='reader':
        path=base/'src/plw/reader/reader.js';path.write_bytes(path.read_bytes()+b'\n// unreviewed\n')
    if change=='vendor':(base/'assets/pdfjs/manifest.json').write_text('{}')
    if change=='tag':tag='plw:unknown'
    with pytest.raises((ValueError,AssertionError)):check.verify(base,tag)
