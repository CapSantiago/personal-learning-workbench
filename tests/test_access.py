"""Same-origin reader boundaries; no real learning files or network exposure."""
import asyncio
import hashlib
from pathlib import Path
from uuid import uuid4
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from starlette.applications import Starlette

from plw import reader_runtime as readers, storage, workspace


def request(app, path, *, method='GET', origin=None, fetch_site=None, scheme='http', extra_headers=()):
    """Exercise the real ASGI routing stack without adding an HTTP dependency."""
    messages=[]
    headers=[(b'host', b'plw.example')]
    headers.extend(extra_headers)
    if origin is not None: headers.append((b'origin',origin.encode('ascii')))
    if fetch_site is not None: headers.append((b'sec-fetch-site',fetch_site.encode('ascii')))
    scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':method,
           'scheme':scheme,'path':path,'raw_path':path.encode('utf-8'),'query_string':b'',
           'root_path':'','headers':headers,'server':('plw.example',443 if scheme=='https' else 80),
           'client':('127.0.0.1',12345)}
    async def receive(): return {'type':'http.request','body':b'','more_body':False}
    async def send(message): messages.append(message)
    asyncio.run(app(scope,receive,send))
    start=next(m for m in messages if m['type']=='http.response.start')
    body=b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body')
    return start['status'],dict(start['headers']),body


@pytest.fixture
def reader(monkeypatch):
    monkeypatch.setattr(readers,'_same_origin',False)
    app=Starlette(routes=readers.reader_routes())
    owner=readers.ReaderAssets()
    root=storage.ROOTS[1]/('reader-route-'+str(uuid4()))
    workspace.initialize_workspace(root)
    database=workspace.active_db(root)
    file=database.parent/'reading'/(str(uuid4())+'.pdf')
    file.parent.mkdir(exist_ok=True)
    payload=b'%PDF-1.7\nSynthetic route validation only\n%%EOF'
    file.write_bytes(payload)
    edition={'id':str(uuid4()),'pdf_relpath':file.relative_to(database.parent).as_posix(),
             'size_bytes':len(payload),'pdf_sha256':hashlib.sha256(payload).hexdigest()}
    owner.register(database,edition)
    return app,owner,database,file,edition,payload


def pdf_url(owner,edition): return owner.url+'/pdf/'+edition['id']+'.pdf'


def test_same_origin_pdf_uses_no_extra_listener_and_works_under_https(reader):
    app,owner,_,_,edition,payload=reader
    assert owner.server is None
    assert owner.url.startswith('/plw-reader/') and '127.0.0.1' not in owner.url
    for scheme in ('http','https'):
        status,headers,body=request(app,pdf_url(owner,edition),scheme=scheme,origin=scheme+'://plw.example')
        assert status==200 and body==payload
        assert headers[b'content-type']==b'application/pdf'
        assert headers[b'cache-control']==b'no-store'
        assert headers[b'cross-origin-resource-policy']==b'same-origin'
        assert b'access-control-allow-origin' not in headers


def test_same_origin_vendor_is_served_with_correct_javascript_type(reader):
    app,owner,*_=reader
    status,headers,body=request(app,owner.url+'/vendor/build/pdf.mjs')
    assert status==200 and headers[b'content-type'].startswith(b'text/javascript')
    assert hashlib.sha256(body).hexdigest()==owner.vendor['build/pdf.mjs']


@pytest.mark.parametrize('suffix',[
    '/pdf/../../plw.sqlite3', '/vendor/../manifest.json', '/vendor/build/../../manifest.json',
    '/vendor/%2e%2e/manifest.json', '/vendor/build\\pdf.mjs', '/pdf/not-registered.pdf',
    '/config.json', '/vendor/manifest.json',
])
def test_unregistered_or_traversing_paths_are_rejected(reader,suffix):
    app,owner,*_=reader
    assert request(app,owner.url+suffix)[0]==404


def test_unknown_capability_and_illegal_method_are_rejected(reader):
    app,owner,_,_,edition,_=reader
    assert request(app,'/plw-reader/not-a-capability/vendor/build/pdf.mjs')[0]==404
    assert request(app,pdf_url(owner,edition),method='POST')[0]==405


@pytest.mark.parametrize('origin',[
    'http://other.example','https://plw.example','http://plw.example:9999',
    'null','http://user:pass@plw.example','http://plw.example/path','not-an-origin',
])
def test_cross_origin_and_invalid_origin_are_rejected(reader,origin):
    app,owner,_,_,edition,_=reader
    assert request(app,pdf_url(owner,edition),origin=origin)[0]==403


def test_cross_site_fetch_without_origin_is_rejected(reader):
    app,owner,_,_,edition,_=reader
    assert request(app,pdf_url(owner,edition),fetch_site='cross-site')[0]==403


def test_changed_or_missing_pdf_is_not_served(reader):
    app,owner,_,file,edition,_=reader
    file.write_bytes(b'corrupted')
    assert request(app,pdf_url(owner,edition))[0]==409
    owner.documents[edition['id']]=(reader[2],file.parent/'missing.pdf',edition['pdf_sha256'])
    assert request(app,pdf_url(owner,edition))[0]==409


def test_changed_vendor_hash_is_rejected(reader):
    app,owner,*_=reader
    owner.vendor['build/pdf.mjs']='0'*64
    assert request(app,owner.url+'/vendor/build/pdf.mjs')[0]==409


def test_restore_switch_invalidates_old_pdf_url(reader,monkeypatch):
    app,owner,database,_,edition,_=reader
    monkeypatch.setattr(workspace,'active_db',lambda root:database.parent.parent/'new-dataset'/'plw.sqlite3')
    assert request(app,pdf_url(owner,edition))[0]==410


def test_direct_streamlit_fallback_remains_loopback_and_origin_scoped(monkeypatch):
    monkeypatch.setattr(readers,'_same_origin',False)
    owner=readers.ReaderAssets('http://127.0.0.1:8501')
    try:
        assert owner.server.server_address[0]=='127.0.0.1'
        url=owner.url+'/vendor/build/pdf.mjs'
        with urlopen(Request(url,headers={'Origin':'http://127.0.0.1:8501'}),timeout=5) as response:
            assert response.status==200
        with pytest.raises(HTTPError) as exc:
            urlopen(Request(url,headers={'Origin':'http://other.example'}),timeout=5)
        assert exc.value.code==403
    finally:
        owner.server.shutdown();owner.server.server_close()


def test_direct_streamlit_refuses_non_loopback_origin(monkeypatch):
    monkeypatch.setattr(readers,'_same_origin',False)
    with pytest.raises(ValueError,match='loopback'):
        readers.ReaderAssets('http://192.168.1.2:8501')


@pytest.fixture
def video(reader):
    app,owner,database,_,edition,_=reader
    root=readers.locking.workspace_for(database)
    file=root/'cache'/database.parent.name/'media'/edition['id']/'synthetic.mp4'
    file.parent.mkdir(parents=True);payload=b'synthetic video route bytes, not a decoded movie'
    file.write_bytes(payload)
    item=dict(path=file,size_bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),mime='video/mp4')
    url=owner.register_media(database,edition['id'],item)
    return app,owner,database,edition,file,item,url,payload


def test_video_supports_head_and_byte_ranges(video):
    app,_,_,_,_,_,url,payload=video
    status,headers,body=request(app,url,method='HEAD')
    assert status==200 and body==b'' and int(headers[b'content-length'])==len(payload)
    status,headers,body=request(app,url,extra_headers=[(b'range',b'bytes=3-10')])
    assert status==206 and body==payload[3:11]
    assert headers[b'content-range']==f'bytes 3-10/{len(payload)}'.encode()
    assert headers[b'content-type']==b'video/mp4' and headers[b'cache-control']==b'no-store'
    assert request(app,url,extra_headers=[(b'range',b'bytes=9999-')])[0]==416
    assert request(app,url,origin='http://other.example')[0]==403
    assert request(app,url,fetch_site='cross-site')[0]==403


def test_video_changed_missing_or_inactive_is_not_served(video,monkeypatch):
    app,_,database,_,file,_,url,payload=video
    file.write_bytes(b'x'*len(payload))
    assert request(app,url)[0]==409
    file.write_bytes(payload)
    monkeypatch.setattr(workspace,'active_db',lambda root:database.with_name('different.sqlite3'))
    assert request(app,url)[0]==410


def test_video_registration_cannot_publish_arbitrary_files(video):
    _,owner,database,edition,_,item,_,_=video
    for changed in [dict(item,path=database),dict(item,mime='text/html'),dict(item,sha256='0'*64)]:
        with pytest.raises((ValueError,storage.StorageError)):
            owner.register_media(database,edition['id'],changed)
    with pytest.raises(ValueError):owner.register_media(database,str(uuid4()),item)
    assert owner.media_resource('media/../plw.sqlite3')[0]==404
