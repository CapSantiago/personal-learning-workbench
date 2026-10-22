"""Same-origin reader boundaries; no real learning files or network exposure."""
import asyncio
import gzip
import hashlib
import time
from pathlib import Path
from uuid import uuid4
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from starlette.applications import Starlette
from streamlit.web.server.starlette.starlette_app import create_streamlit_middleware

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


@pytest.mark.parametrize('name',['legacy/build/pdf.mjs','legacy/build/pdf.worker.mjs'])
def test_legacy_reader_and_worker_remain_verified_private_assets(reader,name):
    from plw.private_auth import COOKIE, PrivateAccess, Session
    app,owner,*_=reader
    gate=PrivateAccess(app,username='synthetic',origin='https://plw.example',
                       password_digest='scrypt$'+'00'*16+'$'+'00'*64)
    gate.sessions['synthetic']=Session(time.monotonic()+60,'csrf',asyncio.Event())
    url=owner.url+'/vendor/'+name
    headers=[(b'x-forwarded-proto',b'https'),(b'accept-encoding',b'gzip')]
    assert request(gate,url,extra_headers=headers)[0]==401
    auth=headers+[(b'cookie',f'{COOKIE}=synthetic'.encode())]
    status,response,body=request(gate,url,origin='https://plw.example',extra_headers=auth)
    assert status==200 and response[b'content-encoding']==b'gzip'
    assert response[b'content-type'].startswith(b'text/javascript')
    assert response[b'cache-control']==b'private, no-store'
    assert hashlib.sha256(gzip.decompress(body)).hexdigest()==owner.vendor[name]
    assert request(gate,url,fetch_site='cross-site',extra_headers=auth)[0]==403
    owner.vendor[name]='0'*64
    assert request(gate,url,origin='https://plw.example',extra_headers=auth)[0]==409


def test_pdf_ranges_head_and_invalid_range_preserve_private_response(reader):
    app,owner,_,_,edition,payload=reader
    url=pdf_url(owner,edition)
    status,headers,body=request(app,url,method='HEAD')
    assert status==200 and body==b''
    assert int(headers[b'content-length'])==len(payload)
    assert headers[b'accept-ranges']==b'bytes'
    for interval,expected in [(b'bytes=0-7',payload[:8]),(b'bytes=-5',payload[-5:])]:
        status,headers,body=request(app,url,extra_headers=[(b'range',interval),(b'accept-encoding',b'gzip')])
        assert status==206 and body==expected
        assert b'content-range' in headers and headers.get(b'content-encoding',b'identity')==b'identity'
        assert headers[b'cache-control']==b'no-store'
    assert request(app,url,extra_headers=[(b'range',b'bytes=99999-')])[0]==416


def test_pdf_discovery_keeps_length_with_actual_streamlit_middleware(reader):
    _,owner,database,file,edition,_=reader
    payload=b'%PDF-1.7\n'+bytes(range(256))*1024+b'\n%%EOF'
    file.write_bytes(payload)
    owner.documents[edition['id']]=(database,file,hashlib.sha256(payload).hexdigest())
    app=Starlette(routes=readers.reader_routes(),middleware=create_streamlit_middleware())
    url=pdf_url(owner,edition)
    status,headers,body=request(app,url,extra_headers=[(b'accept-encoding',b'gzip')])
    assert status==200 and body==payload
    assert headers.get(b'content-encoding',b'identity')==b'identity'
    assert int(headers[b'content-length'])==len(payload)
    assert headers[b'accept-ranges']==b'bytes'


def test_range_cannot_bypass_content_or_dataset_checks(reader,monkeypatch):
    app,owner,database,file,edition,payload=reader
    url=pdf_url(owner,edition);extra=[(b'range',b'bytes=0-7')]
    file.write_bytes(b'x'*len(payload))
    assert request(app,url,extra_headers=extra)[0]==409
    file.write_bytes(payload)
    monkeypatch.setattr(workspace,'active_db',lambda root:database.with_name('different.sqlite3'))
    assert request(app,url,extra_headers=extra)[0]==410


def test_reader_code_compresses_only_verified_vendor_and_honors_refusal(reader):
    app,owner,*_=reader
    url=owner.url+'/vendor/build/pdf.worker.mjs'
    status,headers,plain=request(app,url)
    assert status==200 and headers.get(b'content-encoding',b'identity')==b'identity'
    status,headers,body=request(app,url,extra_headers=[(b'accept-encoding',b'gzip')])
    assert status==200 and headers[b'content-encoding']==b'gzip'
    assert gzip.decompress(body)==plain and len(body)<len(plain)*.5
    assert headers[b'cache-control']==b'no-store' and headers[b'vary']==b'Accept-Encoding'
    for encoding in (b'gzip;q=0, br',b'br',b'gzip;q=invalid'):
        status,headers,body=request(app,url,extra_headers=[(b'accept-encoding',encoding)])
        assert status==200 and body==plain and headers.get(b'content-encoding',b'identity')==b'identity'
    owner.vendor['build/pdf.worker.mjs']='0'*64
    status,headers,body=request(app,url,extra_headers=[(b'accept-encoding',b'gzip')])
    assert status==409 and b'content-encoding' not in headers


def test_https_proxy_pdf_ranges_still_require_live_login_and_same_origin(reader):
    from plw.private_auth import COOKIE, PrivateAccess, Session
    app,owner,_,_,edition,payload=reader
    gate=PrivateAccess(app,username='synthetic',origin='https://plw.example',
                       password_digest='scrypt$'+'00'*16+'$'+'00'*64)
    gate.sessions['synthetic']=Session(time.monotonic()+60,'csrf',asyncio.Event())
    base=[(b'x-forwarded-proto',b'https'),(b'range',b'bytes=0-7'),(b'accept-encoding',b'gzip')]
    auth=base+[(b'cookie',f'{COOKIE}=synthetic'.encode())]
    url=pdf_url(owner,edition)
    assert request(gate,url,extra_headers=base)[0]==401
    status,headers,body=request(gate,url,origin='https://plw.example',extra_headers=auth)
    assert status==206 and body==payload[:8]
    assert headers[b'cache-control']==b'private, no-store' and headers.get(b'content-encoding',b'identity')==b'identity'
    assert request(gate,url,origin='https://other.example',extra_headers=auth)[0]==403
    assert request(gate,url,fetch_site='cross-site',extra_headers=auth)[0]==403
    vendor=owner.url+'/vendor/build/pdf.worker.mjs'
    assert request(gate,vendor,extra_headers=base)[0]==401
    assert request(gate,vendor,fetch_site='cross-site',extra_headers=auth)[0]==403
    gate.sessions.clear()
    assert request(gate,url,extra_headers=auth)[0]==401


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
