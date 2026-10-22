from pathlib import Path
from uuid import uuid4

import pytest

from plw import backups,reader_runtime,storage,workspace
from plw.materials import MaterialService
from plw.services import LearningService
from plw.workbench import Workbench
from streamlit.testing.v1 import AppTest

PDF=storage.PROJECT_ROOT/'.sandbox/r0/968c198e-a06e-4438-8910-6cf634af2c15/sources/原生 PDF 中文课件.pdf'


@pytest.fixture
def sample():
    root=storage.ROOTS[1]/('offline-download-'+str(uuid4()));workspace.initialize_workspace(root)
    path=workspace.active_db(root);service=LearningService(path)
    semester=service.create_semester('离线验收学期',request_id=str(uuid4()))
    course=service.create_course(semester['id'],'测试课程',request_id=str(uuid4()))
    material=MaterialService(path).import_upload(course['id'],'中文 课件.pdf',PDF.read_bytes(),request_id=str(uuid4()))
    w=Workbench(path);w.create_edition(material['id'],str(uuid4()),local_copy_confirmed=True)
    reader_runtime.reader_routes();assets=reader_runtime.ReaderAssets()
    return root,path,course,material,w.rows('reading_editions')[0],assets


def test_original_and_pdf_download_use_managed_files_and_preserve_bytes(sample):
    _,path,_,material,edition,assets=sample
    for row in (None,edition):
        url=assets.register_download(path,material,row)
        status,record=assets.download_resource('download/'+url.rsplit('/',1)[1])
        assert status==200 and record['filename']=='中文 课件.pdf'
        assert record['file'].is_relative_to(path.parent)
        assert record['file'].read_bytes()==PDF.read_bytes()
    assert assets.download_resource('download/../../plw.sqlite3')[0]==404


def test_download_rejects_tamper_removal_and_old_dataset(sample):
    root,path,_,material,edition,assets=sample
    url=assets.register_download(path,material,edition);key='download/'+url.rsplit('/',1)[1]
    service=MaterialService(path);service.set_deleted(material['id'],True)
    assert assets.download_resource(key)[0]==410
    service.set_deleted(material['id'],False)
    backup=backups.create_backup(path);backups.restore_backup(root,backup['path'],confirmation=path.parent.name)
    assert assets.download_resource(key)[0]==410


def test_download_rejects_changed_content(sample):
    _,path,_,material,edition,assets=sample
    url=assets.register_download(path,material,edition)
    (path.parent/edition['pdf_relpath']).write_bytes(b'corrupt synthetic PDF')
    assert assets.download_resource('download/'+url.rsplit('/',1)[1])[0]==409


def test_reading_and_pdf_download_survive_missing_managed_original(sample,monkeypatch):
    root,path,_,material,edition,assets=sample
    original=path.parent/material['managed_relpath']
    original.rename(original.with_name('synthetic-moved-original.pdf'))
    url=assets.register_download(path,material,edition)
    assert assets.download_resource('download/'+url.rsplit('/',1)[1])[0]==200
    monkeypatch.setenv('PLW_WORKSPACE',str(root))
    page=AppTest.from_string('''from pathlib import Path
from plw.ui_workbench import read_edition, edition_tools
from plw.workbench import Workbench
path=Path('''+repr(str(path))+''')
read_edition(path,Workbench(path).rows('reading_editions')[0])
edition_tools(path,Workbench(path).rows('reading_editions')[0])
''',default_timeout=30).run()
    assert not page.exception and not page.error
    assert any('原始课件暂不可下载' in item.value for item in page.caption)


def test_legacy_loopback_download_transport(sample,monkeypatch):
    import urllib.request
    _,path,_,material,edition,_=sample
    monkeypatch.setattr(reader_runtime,'_same_origin',False)
    assets=reader_runtime.ReaderAssets('http://127.0.0.1:8501')
    try:
        url=assets.register_download(path,material,edition)
        with urllib.request.urlopen(url,timeout=5) as response:
            assert 'attachment' in response.headers['Content-Disposition']
            assert response.read()==PDF.read_bytes()
    finally:assets.server.shutdown();assets.server.server_close()


def test_uploaded_reading_pdf_creates_independent_version_and_idempotent_request(sample,monkeypatch):
    _,path,_,material,edition,_=sample;w=Workbench(path)
    monkeypatch.setenv('PLW_PRIVATE_SITE','1')
    request=str(uuid4());body=PDF.read_bytes()+b'\n% uploaded replacement\n'
    w.create_edition(material['id'],request,local_copy_confirmed=True,uploaded_pdf=body)
    w.create_edition(material['id'],request,local_copy_confirmed=True,uploaded_pdf=body)
    with pytest.raises(ValueError,match='内容已改变'):
        w.create_edition(material['id'],request,local_copy_confirmed=True,uploaded_pdf=PDF.read_bytes())
    assert len(w.rows('reading_editions'))==2
    assert (path.parent/f'reading/{request}.pdf').read_bytes()==body
    assert (path.parent/edition['pdf_relpath']).read_bytes()==PDF.read_bytes()


def test_private_mode_does_not_call_office_for_ppt(sample,monkeypatch):
    _,path,course,_,_,_=sample
    material=MaterialService(path).import_upload(course['id'],'动画.pptx',b'PK'+b'placeholder'*10,request_id=str(uuid4()))
    monkeypatch.setenv('PLW_PRIVATE_SITE','1')
    monkeypatch.setattr(reader_runtime,'convert_ppt',lambda *_:pytest.fail('Website must not start desktop Office'))
    with pytest.raises(ValueError,match='PPT 原件'):
        Workbench(path).create_edition(material['id'],str(uuid4()),local_copy_confirmed=True)
    assert (path.parent/material['managed_relpath']).exists()
