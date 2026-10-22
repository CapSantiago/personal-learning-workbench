import asyncio
import gzip
import json
import time
from uuid import uuid4

import pytest
from starlette.applications import Starlette
from streamlit.web.server.starlette.starlette_app import create_streamlit_middleware

from plw import reader_runtime as readers,storage,workspace
from plw.materials import MaterialService
from plw.services import LearningService
from plw.workbench import Workbench
from plw.private_auth import COOKIE,PrivateAccess,Session
from test_access import request

PDF=storage.PROJECT_ROOT/'.sandbox/r0/968c198e-a06e-4438-8910-6cf634af2c15/sources/原生 PDF 中文课件.pdf'

@pytest.fixture
def library():
    root=storage.ROOTS[1]/('device-library-'+str(uuid4()));workspace.initialize_workspace(root)
    path=workspace.active_db(root);service=LearningService(path)
    semester=service.create_semester('长期下载测试',request_id=str(uuid4()))
    course=service.create_course(semester['id'],'第一课程',request_id=str(uuid4()))
    material=MaterialService(path).import_upload(course['id'],'中文 课件.pdf',PDF.read_bytes(),request_id=str(uuid4()))
    w=Workbench(path);w.create_edition(material['id'],str(uuid4()),local_copy_confirmed=True)
    app=Starlette(routes=readers.reader_routes(),middleware=create_streamlit_middleware());owner=readers.ReaderAssets()
    url=owner.register_library(path)
    return root,path,course,material,w.rows('reading_editions')[0],owner,app,url

def test_manifest_enumerates_original_and_latest_reading_copy_without_full_file_hashes(library,monkeypatch):
    _,path,_,material,edition,owner,app,url=library
    monkeypatch.setattr(storage,'hash_file',lambda *_:pytest.fail('Listing must not hash all files'))
    status,headers,body=request(app,url)
    assert status==200 and headers[b'cache-control']==b'no-store'
    manifest=json.loads(body);assert manifest['run']==path.parent.name
    assert {r['kind'] for r in manifest['files']}=={'pdf','original'}
    for item in manifest['files']:
        assert item['filename']=='中文 课件.pdf' and item['bytes']==len(PDF.read_bytes())
        assert item['url'].startswith(owner.url+'/download/')
    assert b'original_path' not in body and b'managed_relpath' not in body and b'database' not in body

def test_library_does_not_bypass_login_or_cross_site_restrictions(library):
    _,_,_,_,_,_,app,url=library
    gate=PrivateAccess(app,username='synthetic',origin='https://plw.example',password_digest='scrypt$'+'00'*16+'$'+'00'*64)
    gate.sessions['synthetic']=Session(time.monotonic()+60,'csrf',asyncio.Event())
    auth=[(b'x-forwarded-proto',b'https'),(b'cookie',f'{COOKIE}=synthetic'.encode())]
    assert request(gate,url,extra_headers=auth[:-1])[0]==401
    assert request(gate,url,extra_headers=auth,fetch_site='cross-site')[0]==403
    status,headers,body=request(gate,url,extra_headers=auth)
    assert status==200 and json.loads(body)['files'] and headers[b'cache-control']==b'private, no-store'

def test_original_and_pdf_bytes_from_manifest_remain_checked_and_range_compatible(library):
    _,path,_,_,edition,owner,app,url=library
    manifest=json.loads(request(app,url)[2])
    for item in manifest['files']:
        status,headers,body=request(app,item['url'],extra_headers=[(b'range',b'bytes=9-18'),(b'accept-encoding',b'gzip')])
        assert status==206 and body==PDF.read_bytes()[9:19] and headers[b'content-encoding']==b'identity'
    (path.parent/edition['pdf_relpath']).write_bytes(b'x'*edition['size_bytes'])
    item=next(r for r in manifest['files'] if r['kind']=='pdf')
    assert request(app,item['url'])[0]==409

def test_manifest_excludes_removed_material_and_reports_missing_original_independently(library):
    _,path,_,material,_,owner,app,url=library
    (path.parent/material['managed_relpath']).rename(path.parent/'synthetic-moved-original.pdf')
    manifest=json.loads(request(app,url)[2]);assert [f['kind'] for f in manifest['files']]==['pdf']
    assert manifest['unavailable'][0]['kind']=='original'
    MaterialService(path).set_deleted(material['id'],True)
    assert json.loads(request(app,url)[2])['files']==[]

def test_dataset_rotation_revokes_old_library_manifest(library):
    from plw import backups
    root,path,_,_,_,owner,app,url=library
    backup=backups.create_backup(path);backups.restore_backup(root,backup['path'],confirmation=path.parent.name)
    assert request(app,url)[0]==410

def test_bulk_library_includes_other_courses_original_ppt_and_only_latest_pdf(library):
    _,path,course,material,edition,owner,app,url=library
    service=LearningService(path)
    other=service.create_course(course['semester_id'],'另一个课程',request_id=str(uuid4()))
    ppt=MaterialService(path).import_upload(other['id'],'演示.pptx',b'PK'+b'synthetic-ppt'*20,request_id=str(uuid4()))
    Workbench(path).create_edition(material['id'],str(uuid4()),local_copy_confirmed=True,uploaded_pdf=PDF.read_bytes()+b'\n% newer\n')
    manifest=json.loads(request(app,url)[2]);assert len(manifest['files'])==3
    assert {f['course'] for f in manifest['files']}=={'第一课程','另一个课程'}
    assert next(f for f in manifest['files'] if f['kind']=='pdf')['id']!=edition['id']
    original=next(f for f in manifest['files'] if f['id']==ppt['id'])
    status,headers,body=request(app,original['url'],extra_headers=[(b'accept-encoding',b'gzip')])
    assert status==200 and body==b'PK'+b'synthetic-ppt'*20
    assert headers[b'content-encoding']==b'identity' and int(headers[b'content-length'])==len(body)

@pytest.mark.parametrize('module,file',[('device-library.mjs','device_library.js'),('reader-module.mjs','reader.js')])
def test_client_modules_are_scoped_compressed_and_private(library,module,file):
    _,_,_,_,_,owner,app,_=library
    status,headers,body=request(app,owner.url+'/'+module,extra_headers=[(b'accept-encoding',b'gzip')])
    assert status==200 and headers[b'content-type'].startswith(b'text/javascript')
    assert gzip.decompress(body)==(readers.PROJECT/'src/plw/reader'/file).read_bytes()
    assert request(app,owner.url+'/'+module,fetch_site='cross-site')[0]==403
    assert request(app,owner.url+'/../device_library.js')[0] in (400,404)
